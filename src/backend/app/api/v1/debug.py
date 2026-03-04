"""
Debug 模式 API

仅在 DEBUG_MODE=true 且当前用户在 SUPER_ADMIN 名单内时有效。
用于前端判断是否展示调试入口、是否允许载入过期激活码等。
"""

from fastapi import APIRouter, Depends
from app.api.v1.auth import get_current_user, _is_debug_admin
from app.config.settings import settings

router = APIRouter(prefix="/debug", tags=["Debug 模式"])


@router.get("/status")
async def get_debug_status(current_user: dict = Depends(get_current_user)):
    """
    获取 Debug 模式状态。需登录，仅返回当前用户是否具备调试权限。
    """
    debug_mode = getattr(settings, "DEBUG_MODE", False)
    is_debug_admin = _is_debug_admin(current_user)
    return {
        "debug_mode": debug_mode,
        "is_debug_admin": debug_mode and is_debug_admin,
    }
