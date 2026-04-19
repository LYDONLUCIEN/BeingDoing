"""
简单模式激活码相关 API

- 创建激活码（开发/内部使用）
- 使用激活码激活一个简单会话
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.utils.simple_activation_manager import (
    SimpleActivationManager,
    ActivationStatus,
    bind_session_id_for_ensure_report,
    get_effective_simple_root,
    get_activation_with_manager,
)
from app.utils.sandbox_fork import assert_sandbox_not_expired
from app.api.v1.auth import get_current_user
from fastapi import Depends
from app.utils.report_registry import ReportRegistry, compute_explore_resume


router = APIRouter(prefix="/simple-auth", tags=["简单模式认证"])


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
            "session_id": rec.session_id,
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
    if not manager.is_owner(rec, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="该激活码已被其他用户使用",
        )
    if rec.status in {ActivationStatus.REVOKED, ActivationStatus.DELETED}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="激活码不可用",
        )
    if not rec.owner_user_id and not rec.owner_email:
        rec = manager.claim_owner(rec.code, current_user)
    else:
        manager.touch_activity(rec.code)

    # 绑定/创建 report（activation_code + user_id -> report_id）
    user_id = (current_user or {}).get("user_id")
    data = {
        "activation_code": rec.code,
        "session_id": rec.session_id,
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
        return ActivationResponse(code=200, message="success", data={"journeys": []})

    journeys = []

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
        data={"journeys": journeys},
    )

