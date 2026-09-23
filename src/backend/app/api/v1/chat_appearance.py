"""
Chat 外观全局默认配置（2026-09-23 拍板：配置入口迁 admin，全局生效，用户不可自行修改）。

公开接口（登录不强制，无敏感信息）：
- GET /api/v1/chat-appearance          当前全局外观配置（未配置时返回空对象，前端回落内置默认）

Admin 接口（super admin 守卫）：
- GET /api/v1/admin/chat-appearance    读取全局配置
- PUT /api/v1/admin/chat-appearance    校验白名单后整体写入
- POST /api/v1/admin/chat-appearance/reset  一键恢复默认并保存生效（2026-09-23）

存储：data/admin_runtime_config.json 的 `chat_appearance` 键（app.utils.admin_config），
字段与前端 stores/chatAppearanceStore.ts 一一对应。
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.v1.auth import get_current_user
from app.utils.admin_config import get_admin_config, set_admin_config
from app.utils.super_admin import is_super_admin_user

public_router = APIRouter(prefix="/chat-appearance", tags=["Chat-Appearance"])
admin_router = APIRouter(prefix="/admin/chat-appearance", tags=["Admin-Chat-Appearance"])

CONFIG_KEY = "chat_appearance"

# 出厂默认（= 前端 RECOMMENDED_CHAT_APPEARANCE，stores/chatAppearanceStore.ts；
# 两处须保持同步，恢复默认以本表为准写入）
DEFAULT_CHAT_APPEARANCE: Dict[str, Any] = {
    "background": "flow",
    "placement": "both",
    "strength": 22,
    "motionPaused": False,
    "aiBubble": "ink",
    "userBubble": "white",
    "actionStyle": "ink",
    "ruminationLayout": "guided",
    "ruminationSkin": "mist",
    "palette": "lavender",
    "matrixStyle": "soft",
    "matrixPalette": "duo",
    "conclusionTone": "theme-mist",
    "conclusionTags": "soft",
}

# 字段白名单 + 枚举（与前端 chatAppearanceStore 类型对齐；density/newChatStyle 为 A/B 保留项）
FIELD_ENUMS: Dict[str, tuple] = {
    "density": ("compact", "roomy"),
    "newChatStyle": ("dashed", "solid"),
    "background": ("white", "tint", "flow", "illustration"),
    "placement": ("both", "sidebar", "edge", "off"),
    "motionPaused": None,  # bool
    "aiBubble": ("ink", "soft", "theme", "white"),
    "userBubble": ("ink", "soft", "theme", "white"),
    "actionStyle": ("ink", "theme"),
    "ruminationLayout": ("classic", "studio", "guided"),
    "ruminationSkin": ("folio", "modules", "editorial", "mist"),
    "palette": ("lavender", "sage", "slate"),
    "matrixStyle": ("soft", "outline", "solid"),
    "matrixPalette": ("duo", "violet", "multi"),
    "conclusionTone": ("theme-mist", "theme-paper", "theme-gradient", "theme-outline", "theme-solid"),
    "conclusionTags": ("soft", "outline", "editorial"),
}


def _validate(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """只保留白名单字段并逐项校验枚举/类型，非法值直接 400（不静默吞错）。"""
    cleaned: Dict[str, Any] = {}
    for key, allowed in FIELD_ENUMS.items():
        if key not in cfg:
            continue
        val = cfg[key]
        if allowed is None:
            if not isinstance(val, bool):
                raise HTTPException(status_code=400, detail=f"{key} 须为布尔值")
        else:
            if val not in allowed:
                raise HTTPException(
                    status_code=400, detail=f"{key} 非法：{val}，可选 {list(allowed)}"
                )
        cleaned[key] = val
    # strength 单独校验（0-50 整数）
    if "strength" in cfg:
        try:
            strength = int(cfg["strength"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="strength 须为 0-50 整数")
        if not 0 <= strength <= 50:
            raise HTTPException(status_code=400, detail="strength 须为 0-50 整数")
        cleaned["strength"] = strength
    unknown = set(cfg.keys()) - set(FIELD_ENUMS.keys()) - {"strength"}
    if unknown:
        raise HTTPException(status_code=400, detail=f"未知字段：{sorted(unknown)}")
    return cleaned


def _load_config() -> Dict[str, Any]:
    cfg = get_admin_config(CONFIG_KEY) or {}
    return cfg if isinstance(cfg, dict) else {}


def _require_super_admin(user: Optional[dict]) -> None:
    if not is_super_admin_user(user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")


# ── 公开接口 ─────────────────────────────────────────────
@public_router.get("")
async def get_public_chat_appearance():
    """全局外观默认值（所有用户可读；未配置返回空对象，前端回落内置默认）。"""
    return {"code": 200, "message": "success", "data": _load_config()}


# ── Admin 接口 ───────────────────────────────────────────
@admin_router.get("")
async def admin_get_chat_appearance(current_user: Optional[dict] = Depends(get_current_user)):
    _require_super_admin(current_user)
    return {"code": 200, "message": "success", "data": _load_config()}


class ChatAppearancePutRequest(BaseModel):
    config: Dict[str, Any]


@admin_router.put("")
async def admin_put_chat_appearance(
    req: ChatAppearancePutRequest, current_user: Optional[dict] = Depends(get_current_user)
):
    """整体写入全局外观配置（先白名单校验，后落盘）。"""
    _require_super_admin(current_user)
    cleaned = _validate(req.config or {})
    set_admin_config(CONFIG_KEY, cleaned)
    return {"code": 200, "message": "success", "data": cleaned}


@admin_router.post("/reset")
async def admin_reset_chat_appearance(current_user: Optional[dict] = Depends(get_current_user)):
    """一键恢复出厂默认并保存生效（前端「恢复默认」按钮直接调用）。"""
    _require_super_admin(current_user)
    set_admin_config(CONFIG_KEY, DEFAULT_CHAT_APPEARANCE)
    return {"code": 200, "message": "success", "data": DEFAULT_CHAT_APPEARANCE}


router = APIRouter()
router.include_router(public_router)
router.include_router(admin_router)
