"""
简单模式激活码相关 API

- 创建激活码（开发/内部使用）
- 使用激活码激活一个简单会话
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from app.utils.simple_activation_manager import (
    SimpleActivationManager,
    ActivationStatus,
    bind_session_id_for_ensure_report,
    get_effective_simple_root,
    get_activation_with_manager,
    get_simple_base_dir,
    get_simple_test_base_dir,
)
from app.utils.sandbox_fork import assert_sandbox_not_expired
from app.api.v1.auth import get_current_user
from fastapi import Depends, Request
from app.utils.report_registry import ReportRegistry, compute_explore_resume
from app.utils.id_codec import IDCodec
from app.utils.activation_audit import (
    append_activation_audit,
    EVENT_OWNER_DENIED,
    EVENT_OWNER_VERIFIED,
    EVENT_ACCESS,
)
from app.utils.survey_storage import load_basic_info_by_user
from app.utils.trial_codes import (
    TRIAL_CODE_TYPE,
    ensure_trial_code_for_user,
    is_trial_code,
)
from app.utils.report_review import REVIEW_STATUS_APPROVED, get_review_status


router = APIRouter(prefix="/simple-auth", tags=["简单模式认证"])


def _derive_code_status(rec) -> str:
    """派生展示状态：套餐完整码尚未首次使用（expires_at 为空）时显示 inactive（未激活）

    仅展示层派生，不落盘；试用码（不过期）与已有有效期的码不受影响。
    """
    status_out = rec.status
    if (
        status_out == "active"
        and (getattr(rec, "code_type", None) or "full") == "full"
        and (getattr(rec, "package_type", None) or "").strip()
        and not getattr(rec, "expires_at", None)
    ):
        return "inactive"
    return status_out


def _report_status(rec, user_id: str, email: str) -> Optional[str]:
    """报告三态口径（ADR-0009）：无 record → None；有 record →
    not_started / pending_review / approved。

    存量 record 缺 review_status 字段时祖父豁免视为 approved（与 export.py 同口径，
    复用 report_review.get_review_status）。纯只读，不触发审核计时。
    """
    try:
        root = get_effective_simple_root(rec)
        registry = ReportRegistry(base_dir=str(root))
        record = None
        if user_id:
            record = registry.get_by_activation_user(rec.code, user_id)
        if not record and email:
            record = registry.get_by_activation_user(rec.code, email)
        if record:
            return get_review_status(record)
    except Exception:
        pass
    # 兜底：registry 查不到但激活记录上挂了 report_id，按存量 approved 处理（保持旧口径）
    if getattr(rec, "report_id", None):
        return REVIEW_STATUS_APPROVED
    return None


def _client_ip(request) -> str:
    """从 FastAPI Request 中提取客户端 IP。"""
    if request is None:
        return ""
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")
    if forwarded and forwarded[0].strip():
        return forwarded[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return ""


class CreateActivationRequest(BaseModel):
    """创建激活码请求（仅开发/内部使用）"""
    mode: str = "values"  # values | strengths | interests | combined
    ttl_minutes: int = 60


class ActivationResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: dict


class ActivateRequest(BaseModel):
    """使用激活码激活简单会话"""
    code: str


@router.post("/activation", response_model=ActivationResponse)
async def create_activation(request: CreateActivationRequest):
    """
    创建一个新的简单模式激活码。

    注意：当前为开发/内部接口，用于生成测试用激活码。
    """
    manager = SimpleActivationManager()
    rec = manager.create_activation(
        mode=request.mode,
        ttl_minutes=request.ttl_minutes,
    )
    return ActivationResponse(
        code=200,
        message="created",
        data={
            "activation_code": rec.code,
            **IDCodec.build_activation_response_ids(rec.session_id),
            "mode": rec.mode,
            "created_at": rec.created_at,
            "expires_at": rec.expires_at,
            "status": rec.status,
        },
    )


@router.post("/activate", response_model=ActivationResponse)
async def activate(
    request: ActivateRequest,
    current_user: dict = Depends(get_current_user),
    req: Request = None,
):
    """
    使用激活码获取简单会话信息。

    - 激活码过期后，仍然可以查询到记录，但 status 会为 expired
    - 客户端可以根据 status 决定是否允许继续对话（或仅展示历史结果）
    """
    code = (request.code or "").strip()
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请输入激活码",
        )
    manager, rec = get_activation_with_manager(code)
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="激活码不存在",
        )
    try:
        assert_sandbox_not_expired(rec)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # 首次激活绑定归属用户；已绑定则仅允许归属者使用
    client_ip = _client_ip(req)
    uid = (current_user or {}).get("user_id")
    email = (current_user or {}).get("email")
    if not manager.is_owner(rec, current_user):
        # 审计日志：归属拒绝
        append_activation_audit(
            EVENT_OWNER_DENIED,
            code,
            actor_user_id=uid,
            actor_email=email,
            client_ip=client_ip,
            detail={
                "owner_user_id": rec.owner_user_id,
                "owner_email": rec.owner_email,
                "endpoint": "POST /simple-auth/activate",
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="该激活码已被其他用户使用",
        )
    if rec.status in {ActivationStatus.REVOKED, ActivationStatus.DELETED}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="激活码不可用",
        )
    if rec.status == ActivationStatus.CONSUMED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该激活码已用于升级试用码，不可再次使用",
        )

    # 邮箱验证门控：未验证邮箱的用户不能使用激活码
    email_verified = (current_user or {}).get("email_verified", True)
    if not email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="请先验证邮箱再使用激活码",
        )
    if not rec.owner_user_id and not rec.owner_email:
        rec = manager.claim_owner(rec.code, current_user)
    else:
        # 审计日志：归属校验通过（已绑定用户的回访）
        append_activation_audit(
            EVENT_OWNER_VERIFIED,
            code,
            actor_user_id=uid,
            actor_email=email,
            client_ip=client_ip,
            detail={"endpoint": "POST /simple-auth/activate"},
        )
        manager.touch_activity(rec.code)

    # 绑定/创建 report（activation_code + user_id -> report_id）
    user_id = (current_user or {}).get("user_id")
    data = {
        "activation_code": rec.code,
        **IDCodec.build_activation_response_ids(rec.session_id),
        "mode": rec.mode,
        "created_at": rec.created_at,
        "expires_at": rec.expires_at,
        "status": rec.status,
        "is_sandbox": getattr(rec, "is_sandbox", False),
        "workspace_kind": getattr(rec, "workspace_kind", None),
        "workspace_root": getattr(rec, "workspace_root", None),
    }
    if user_id:
        root = get_effective_simple_root(rec)
        registry = ReportRegistry(base_dir=str(root))
        record = registry.ensure_report(
            activation_code=rec.code,
            user_id=user_id,
            session_id=bind_session_id_for_ensure_report(rec),
        )
        data["explore_resume"] = compute_explore_resume(record)

    return ActivationResponse(
        code=200,
        message="success",
        data=data,
    )


@router.get("/journeys", response_model=ActivationResponse)
async def list_user_journeys(
    current_user: dict = Depends(get_current_user),
):
    """
    返回当前用户的所有激活码（职业旅程）及进度摘要。
    按最后活跃时间倒序排列，最近使用的排第一。
    清除浏览器缓存后仍可从此接口恢复。
    """
    user_id = (current_user or {}).get("user_id", "")
    email = (current_user or {}).get("email", "")
    if not user_id and not email:
        return ActivationResponse(code=200, message="success", data={"journeys": [], "user_survey": {}})

    journeys = []

    # ── 用户级问卷直读：不依赖激活码，登录后即可获取 ──
    user_survey_data = {}
    user_survey_completed = False
    if user_id:
        user_survey_data = load_basic_info_by_user(user_id) or {}
        user_survey_completed = bool(user_survey_data) and any(
            v is not None and v != "" and (not isinstance(v, list) or len(v) > 0)
            for v in user_survey_data.values()
        )

    from app.utils.simple_activation_manager import (
        SimpleActivationManager,
        get_simple_base_dir,
        get_simple_test_base_dir,
    )

    def _report_for_journey(rec, uid: str, em: str):
        """与 ensure_report 一致：record.json 的 user_id 可能为历史邮箱或当前 user_id，双键尝试。"""
        root = get_effective_simple_root(rec)
        registry = ReportRegistry(base_dir=str(root))
        if uid:
            rpt = registry.get_by_activation_user(rec.code, uid)
            if rpt:
                return rpt
        if em:
            return registry.get_by_activation_user(rec.code, em)
        return None

    # P-A 老用户懒补发：名下 0 个可用码时自动发一个试用码并绑定（防并发重复发：绑定后复查）
    try:
        ensure_trial_code_for_user({"user_id": user_id, "email": email})
    except Exception as e:
        logger.warning("journeys 懒补发试用码失败（不影响列表返回）: %s", e)

    # 合并生产 + 测试/沙箱索引（管理员 ADM/SBX、fork、resident 仅在 test 根）
    merged: dict[str, tuple] = {}  # code -> (last_activity_at str, ActivationRecord)
    for base_dir in (get_simple_base_dir(), get_simple_test_base_dir()):
        mgr = SimpleActivationManager(base_dir=str(base_dir))
        for code, rec in mgr.list_activations().items():
            norm = (code or "").strip().upper()
            if not norm:
                continue
            ts = getattr(rec, "last_activity_at", None) or rec.created_at or ""
            prev = merged.get(norm)
            if prev is None or (ts or "") >= (prev[0] or ""):
                merged[norm] = (ts, rec)

    for _norm, (_ts, rec) in sorted(merged.items(), key=lambda x: x[1][0] or "", reverse=True):
        owner_uid = (getattr(rec, "owner_user_id", None) or "").strip()
        owner_email = (getattr(rec, "owner_email", None) or "").strip()
        is_mine = (user_id and owner_uid == user_id) or (email and owner_email == email)
        if not is_mine:
            continue
        if rec.status in {ActivationStatus.DELETED, ActivationStatus.REVOKED}:
            continue

        report = _report_for_journey(rec, user_id, email)
        resume = compute_explore_resume(report) if report else {}

        journeys.append({
            "activation_code": rec.code,
            "code_type": getattr(rec, "code_type", None) or "full",
            "mode": rec.mode,
            "status": rec.status,
            "created_at": rec.created_at,
            "expires_at": rec.expires_at,
            "last_activity_at": getattr(rec, "last_activity_at", None) or rec.created_at,
            "explore_resume": resume,
        })

    # 按最后活跃时间倒序
    journeys.sort(key=lambda j: j.get("last_activity_at") or "", reverse=True)
    # 标记最近使用的
    if journeys:
        journeys[0]["is_latest"] = True

    return ActivationResponse(
        code=200,
        message="success",
        data={
            "journeys": journeys,
            "user_survey": {
                "completed": user_survey_completed,
                "survey_data": user_survey_data,
            },
        },
    )


@router.get("/my-codes", response_model=ActivationResponse)
async def list_my_codes(
    current_user: dict = Depends(get_current_user),
):
    """
    返回当前用户名下（owner_user_id=我）全部激活码（P-A，ADR-0008）。

    按创建时间倒序。deleted 状态的码不返回。
    source 推断：trial=试用赠送；其余按记录 source 字段，缺省 admin。
    """
    user_id = (current_user or {}).get("user_id", "")
    email = (current_user or {}).get("email", "")
    if not user_id and not email:
        return ActivationResponse(code=200, message="success", data={"items": []})

    from app.utils.simple_activation_manager import (
        SimpleActivationManager,
        get_simple_base_dir,
        get_simple_test_base_dir,
    )

    # 合并生产 + 测试/沙箱索引（与 journeys 口径一致）
    merged: dict[str, object] = {}  # code -> ActivationRecord
    for base_dir in (get_simple_base_dir(), get_simple_test_base_dir()):
        mgr = SimpleActivationManager(base_dir=str(base_dir))
        for code, rec in mgr.list_activations().items():
            norm = (code or "").strip().upper()
            if norm:
                merged[norm] = rec

    items = []
    for _norm, rec in merged.items():
        owner_uid = (getattr(rec, "owner_user_id", None) or "").strip()
        owner_email = (getattr(rec, "owner_email", None) or "").strip()
        is_mine = (user_id and owner_uid == user_id) or (email and owner_email == email)
        if not is_mine:
            continue
        if rec.status == ActivationStatus.DELETED:
            continue
        if is_trial_code(rec):
            source = "试用赠送"
        else:
            source = (getattr(rec, "source", None) or "").strip() or "admin"
        report_status = _report_status(rec, user_id, email)
        items.append({
            "code": rec.code,
            "code_type": getattr(rec, "code_type", None) or "full",
            "status": _derive_code_status(rec),
            "expires_at": rec.expires_at,
            "created_at": rec.created_at,
            "source": source,
            "session_id": rec.session_id,
            # has_report 语义：报告已生成 = 审核通过（与 my-purchased-codes 口径拉齐）
            "has_report": report_status == REVIEW_STATUS_APPROVED,
            "report_status": report_status,
        })

    # 按创建时间倒序
    items.sort(key=lambda x: x.get("created_at") or "", reverse=True)

    return ActivationResponse(
        code=200,
        message="success",
        data={"items": items},
    )


@router.get("/my-purchased-codes", response_model=ActivationResponse)
async def list_my_purchased_codes(
    current_user: dict = Depends(get_current_user),
):
    """所属人视角（P-E，ADR-0010）：我购买的全部码（含送出的赠品码）。

    返回每码的激活人（脱敏邮箱）、报告就绪与授权状态。
    所属人可见「被谁激活」与「报告是否就绪/已授权」，但对话内容永不可见。
    """
    user_id = (current_user or {}).get("user_id", "")
    if not user_id:
        return ActivationResponse(code=200, message="success", data={"items": []})

    from app.utils.simple_activation_manager import (
        SimpleActivationManager,
        get_simple_base_dir,
        get_simple_test_base_dir,
    )

    def _mask_email(email: str) -> str:
        if not email or "@" not in email:
            return email
        local, domain = email.split("@", 1)
        return f"{local[:1]}***@{domain}"

    # report 状态索引（审核通过/存量豁免 → approved；祖父豁免由 get_review_status 封装）
    approved_codes: set[str] = set()
    report_status_by_code: dict[str, str] = {}
    try:
        registry = ReportRegistry()
        for record in registry.list_reports():
            code = (record.get("activation_code") or "").strip().upper()
            if not code:
                continue
            review_status = get_review_status(record)
            report_status_by_code.setdefault(code, review_status)
            if review_status == REVIEW_STATUS_APPROVED:
                approved_codes.add(code)
    except Exception:
        pass

    items = []
    for base_dir in (get_simple_base_dir(), get_simple_test_base_dir()):
        mgr = SimpleActivationManager(base_dir=str(base_dir))
        for code, rec in mgr.list_activations().items():
            if (getattr(rec, "purchaser_user_id", None) or "") != user_id:
                continue
            if rec.status == ActivationStatus.DELETED:
                continue
            norm = (rec.code or "").strip().upper()
            items.append({
                "code": rec.code,
                "code_type": getattr(rec, "code_type", None) or "full",
                "package_type": getattr(rec, "package_type", None),
                "status": _derive_code_status(rec),
                "expires_at": rec.expires_at,
                "created_at": rec.created_at,
                "activated": bool(rec.owner_user_id),
                "activated_by": _mask_email(rec.owner_email or "") or None,
                "activated_by_self": rec.owner_user_id == user_id,
                "has_report": norm in approved_codes,
                "report_status": report_status_by_code.get(norm),
                "report_authorized": bool(getattr(rec, "report_authorized", False)),
            })

    items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return ActivationResponse(code=200, message="success", data={"items": items})


class ReportAuthorizeRequest(BaseModel):
    """报告授权开关请求"""

    authorized: bool


@router.get("/codes/{code}/report-authorize", response_model=ActivationResponse)
async def get_report_authorize(
    code: str,
    current_user: dict = Depends(get_current_user),
):
    """查询报告授权状态（P-E，ADR-0010）：返回授权标记与所属人（脱敏）。"""
    mgr, rec = get_activation_with_manager(code)
    if rec is None:
        raise HTTPException(status_code=404, detail="激活码不存在")

    purchaser_email = None
    purchaser_user_id = getattr(rec, "purchaser_user_id", None)
    # 自购自用（所属人=激活人）没有"赠送者"，不暴露 purchaser_email，
    # 前端据此不渲染授权开关（授权语义仅存在于转赠/团队场景）
    if purchaser_user_id and purchaser_user_id != rec.owner_user_id:
        try:
            from app.models.database import AsyncSessionLocal
            from app.models.user import User
            from sqlalchemy import select as _select

            async with AsyncSessionLocal() as db:
                purchaser_email = (
                    await db.execute(_select(User.email).where(User.id == purchaser_user_id))
                ).scalar_one_or_none()
        except Exception:
            purchaser_email = None
    masked = None
    if purchaser_email and "@" in purchaser_email:
        local, domain = purchaser_email.split("@", 1)
        masked = f"{local[:1]}***@{domain}"

    return ActivationResponse(
        code=200,
        message="success",
        data={
            "code": rec.code,
            "authorized": bool(getattr(rec, "report_authorized", False)),
            "is_activator": rec.owner_user_id == (current_user or {}).get("user_id"),
            "purchaser_email": masked,
        },
    )


@router.post("/codes/{code}/report-authorize", response_model=ActivationResponse)
async def set_report_authorize(
    code: str,
    payload: ReportAuthorizeRequest,
    current_user: dict = Depends(get_current_user),
):
    """激活人一键授权/撤销报告给所属人（P-E，ADR-0010）。

    仅该码的激活人（owner_user_id）可操作；授权内容仅为报告，对话不可分享。
    """
    user_id = (current_user or {}).get("user_id", "")
    mgr, rec = get_activation_with_manager(code)
    if rec is None:
        raise HTTPException(status_code=404, detail="激活码不存在")
    if rec.owner_user_id != user_id:
        raise HTTPException(status_code=403, detail="仅该激活码的使用人可授权")
    # 自购自用码不存在赠送者，授权无意义（自己的报告在团队分析中本就可选）
    if getattr(rec, "purchaser_user_id", None) in (None, user_id):
        raise HTTPException(status_code=400, detail="自购激活码无需授权，仅转赠码可授权给购买者")

    updated = mgr.set_report_authorized(code, payload.authorized, actor=current_user)
    return ActivationResponse(
        code=200,
        message="success",
        data={"code": updated.code, "authorized": bool(updated.report_authorized)},
    )



# ─── 消耗升级（ADR-0014）───────────────────────────────────────


class ApplyToTrialRequest(BaseModel):
    """消耗升级请求：将一个未绑定完整码作废，升级当前用户的试用码"""

    code: str


@router.post("/codes/apply-to-trial", response_model=ActivationResponse)
async def apply_code_to_trial(
    payload: ApplyToTrialRequest,
    current_user: dict = Depends(get_current_user),
):
    """消耗升级（ADR-0014）：作废一个未绑定完整码，把当前用户的试用码原地升级为完整码。

    - 码须 status=active、code_type=full、未绑定（owner 为空）；自购或被赠的码均可
    - 升级后试用码的码字符串/对话记录/session 全部保留
    - 用被赠的码升级时，试用码所属人记为原购买者（upgrade_to_full 已有值不覆盖）
    """
    from app.config.settings import settings
    from app.utils.trial_codes import get_active_trial_code_for_user

    user_id = (current_user or {}).get("user_id", "")
    email = (current_user or {}).get("email", "")
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")

    trial = get_active_trial_code_for_user(user_id)
    if trial is None:
        raise HTTPException(status_code=400, detail="当前账号没有可升级的试用码")

    mgr, rec = get_activation_with_manager(payload.code)
    if rec is None:
        raise HTTPException(status_code=400, detail="激活码不存在")

    # 消耗（内部校验 status/code_type/未绑定/未消耗）
    try:
        mgr.consume_for_trial_upgrade(rec.code, trial.code, actor=current_user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 原地升级试用码（时长按被消耗码的套餐类型；缺省按季度）
    package_type = (getattr(rec, "package_type", None) or "").strip().lower()
    if package_type not in ("quarterly", "annual"):
        package_type = "quarterly"
    days = settings.ANNUAL_DAYS if package_type == "annual" else settings.QUARTERLY_DAYS
    trial_mgr, _ = get_activation_with_manager(trial.code)
    upgraded = (trial_mgr or mgr).upgrade_to_full(
        trial.code,
        package_type,
        days,
        source_order_id=getattr(rec, "source_order_id", None),
        purchaser_user_id=getattr(rec, "purchaser_user_id", None) or user_id,
        actor=current_user,
    )
    logger.info(
        "消耗升级完成: user=%s consumed=%s trial=%s package=%s",
        user_id,
        rec.code,
        trial.code,
        package_type,
    )
    return ActivationResponse(
        code=200,
        message="success",
        data={
            "trial_code": upgraded.code,
            "consumed_code": rec.code,
            "package_type": package_type,
            "code_type": upgraded.code_type,
        },
    )


@router.get("/upgrade-context", response_model=ActivationResponse)
async def get_upgrade_context(
    current_user: dict = Depends(get_current_user),
):
    """升级试用码弹窗上下文（ADR-0014）：

    - has_started_trial / trial_code：是否有已开聊（≥1 条用户消息）的试用码
    - unbound_codes：我购买的未绑定未消耗完整码（可用于消耗升级/转赠/自激活）
    - dont_remind：支付结果页升级弹窗「不再提醒」偏好
    """
    from app.utils.trial_codes import get_started_trial_code

    user_id = (current_user or {}).get("user_id", "")
    if not user_id:
        return ActivationResponse(
            code=200,
            message="success",
            data={
                "has_started_trial": False,
                "trial_code": None,
                "unbound_codes": [],
                "dont_remind": False,
            },
        )

    trial = get_started_trial_code(user_id)

    unbound_codes = []
    for base_dir in (get_simple_base_dir(), get_simple_test_base_dir()):
        mgr = SimpleActivationManager(base_dir=str(base_dir))
        for code, rec in mgr.list_activations().items():
            if (getattr(rec, "purchaser_user_id", None) or "") != user_id:
                continue
            if rec.owner_user_id:
                continue
            if rec.status != ActivationStatus.ACTIVE.value:
                continue
            if (getattr(rec, "code_type", "full") or "full") != "full":
                continue
            unbound_codes.append(
                {
                    "code": rec.code,
                    "package_type": getattr(rec, "package_type", None),
                    "created_at": rec.created_at,
                    "source_order_id": getattr(rec, "source_order_id", None),
                }
            )
    unbound_codes.sort(key=lambda x: x.get("created_at") or "", reverse=True)

    prefs = await _read_user_preferences(user_id)
    return ActivationResponse(
        code=200,
        message="success",
        data={
            "has_started_trial": trial is not None,
            "trial_code": trial.code if trial else None,
            "unbound_codes": unbound_codes,
            "dont_remind": bool(prefs.get("upgrade_modal_dont_remind")),
        },
    )


# ─── 用户偏好（ADR-0014：升级弹窗「不再提醒」跨设备生效）─────────


async def _read_user_preferences(user_id: str) -> dict:
    """读 users.preferences（JSON 字符串）；异常/为空返回 {}"""
    import json as _json

    from sqlalchemy import select as _select

    from app.models.database import AsyncSessionLocal
    from app.models.user import User

    try:
        async with AsyncSessionLocal() as db:
            raw = (
                await db.execute(_select(User.preferences).where(User.id == user_id))
            ).scalar_one_or_none()
    except Exception:
        return {}
    if not raw:
        return {}
    try:
        data = _json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


class PreferencesUpdateRequest(BaseModel):
    """用户偏好更新（仅支持白名单 key）"""

    upgrade_modal_dont_remind: Optional[bool] = None


@router.get("/preferences", response_model=ActivationResponse)
async def get_preferences(
    current_user: dict = Depends(get_current_user),
):
    """读当前用户偏好"""
    user_id = (current_user or {}).get("user_id", "")
    prefs = await _read_user_preferences(user_id) if user_id else {}
    return ActivationResponse(code=200, message="success", data={"preferences": prefs})


@router.patch("/preferences", response_model=ActivationResponse)
async def update_preferences(
    payload: PreferencesUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    """更新当前用户偏好（白名单 key 合入，不传的不动）"""
    import json as _json

    from sqlalchemy import select as _select

    from app.models.database import AsyncSessionLocal
    from app.models.user import User

    user_id = (current_user or {}).get("user_id", "")
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")

    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(_select(User).where(User.id == user_id))
        ).scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        prefs = await _read_user_preferences(user_id)
        if payload.upgrade_modal_dont_remind is not None:
            prefs["upgrade_modal_dont_remind"] = bool(payload.upgrade_modal_dont_remind)
        user.preferences = _json.dumps(prefs, ensure_ascii=False)
        await db.commit()
    return ActivationResponse(code=200, message="success", data={"preferences": prefs})
