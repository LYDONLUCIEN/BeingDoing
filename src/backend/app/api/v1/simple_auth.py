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


router = APIRouter(prefix="/simple-auth", tags=["简单模式认证"])


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

    def _has_report(rec) -> bool:
        if getattr(rec, "report_id", None):
            return True
        try:
            root = get_effective_simple_root(rec)
            registry = ReportRegistry(base_dir=str(root))
            if user_id and registry.get_by_activation_user(rec.code, user_id):
                return True
            if email and registry.get_by_activation_user(rec.code, email):
                return True
        except Exception:
            pass
        return False

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
        items.append({
            "code": rec.code,
            "code_type": getattr(rec, "code_type", None) or "full",
            "status": rec.status,
            "expires_at": rec.expires_at,
            "created_at": rec.created_at,
            "source": source,
            "session_id": rec.session_id,
            "has_report": _has_report(rec),
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

    # report 就绪索引（审核通过/存量豁免）
    approved_codes: set[str] = set()
    try:
        registry = ReportRegistry()
        for record in registry.list_reports():
            review_status = record.get("review_status") or "approved"
            if review_status == "approved":
                approved_codes.add((record.get("activation_code") or "").strip().upper())
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
                "status": rec.status,
                "expires_at": rec.expires_at,
                "created_at": rec.created_at,
                "activated": bool(rec.owner_user_id),
                "activated_by": _mask_email(rec.owner_email or "") or None,
                "activated_by_self": rec.owner_user_id == user_id,
                "has_report": norm in approved_codes,
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
    if purchaser_user_id:
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

    updated = mgr.set_report_authorized(code, payload.authorized, actor=current_user)
    return ActivationResponse(
        code=200,
        message="success",
        data={"code": updated.code, "authorized": bool(updated.report_authorized)},
    )

