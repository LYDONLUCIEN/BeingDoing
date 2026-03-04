"""
简单模式激活码相关 API

- 创建激活码（开发/内部使用）
- 使用激活码激活一个简单会话
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.utils.simple_activation_manager import SimpleActivationManager, ActivationStatus


router = APIRouter(prefix="/simple-auth", tags=["简单模式认证"])


class CreateActivationRequest(BaseModel):
    """创建激活码请求（仅开发/内部使用）"""
    mode: str = "values"  # values | strengths | interests_goals | combined
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
async def activate(request: ActivateRequest):
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
    manager = SimpleActivationManager()
    rec = manager.get_activation(code)
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="激活码不存在",
        )

    # 更新活跃时间（仅在 ACTIVE 状态下）
    manager.touch_activity(rec.code)

    return ActivationResponse(
        code=200,
        message="success",
        data={
            "activation_code": rec.code,
            "session_id": rec.session_id,
            "mode": rec.mode,
            "created_at": rec.created_at,
            "expires_at": rec.expires_at,
            "status": rec.status,
        },
    )

