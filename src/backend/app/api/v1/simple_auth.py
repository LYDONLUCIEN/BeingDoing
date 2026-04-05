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

