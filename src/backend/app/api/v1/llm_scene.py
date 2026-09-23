"""
LLM 场景分流配置（2026-09-23 拍板：admin 可配置三场景的 flash|pro 档位与 thinking 开关）。

Admin 接口（super admin 守卫）：
- GET  /api/v1/admin/llm-scene         读取配置（与默认合并后的完整三场景视图）
- PUT  /api/v1/admin/llm-scene         校验后整体写入（立即生效，factory/provider 读取时消费）
- POST /api/v1/admin/llm-scene/reset   一键恢复默认并保存生效

存储：data/admin_runtime_config.json 的 `llm_scene_config` 键（app.utils.admin_config），
消费方：core/llmapi/scene_config.py（factory._scene_model 与 openai_provider thinking 分支）。
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.v1.auth import get_current_user
from app.core.llmapi import scene_config
from app.utils.admin_config import set_admin_config
from app.utils.super_admin import is_super_admin_user

admin_router = APIRouter(prefix="/admin/llm-scene", tags=["Admin-LLM-Scene"])


def _require_super_admin(user: Optional[dict]) -> None:
    if not is_super_admin_user(user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")


@admin_router.get("")
async def admin_get_llm_scene(current_user: Optional[dict] = Depends(get_current_user)):
    """当前场景配置（未保存过时返回默认值）。"""
    _require_super_admin(current_user)
    return {"code": 200, "message": "success", "data": scene_config.get_llm_scene_config()}


class LlmScenePutRequest(BaseModel):
    config: Dict[str, Any]


@admin_router.put("")
async def admin_put_llm_scene(
    req: LlmScenePutRequest, current_user: Optional[dict] = Depends(get_current_user)
):
    """整体写入场景配置（先校验后落盘，立即生效）。"""
    _require_super_admin(current_user)
    try:
        cleaned = scene_config.validate_scene_config(req.config or {})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # 补全缺省场景/字段（validate 只保留显式提交部分，此处以默认值填齐再落盘，
    # 使存储始终是完整三场景；基础取默认而非已存配置，PUT 幂等不依赖历史）
    full = {
        scene: dict(scene_config.DEFAULT_LLM_SCENE_CONFIG[scene])
        for scene in scene_config.SCENES
    }
    for scene, item in cleaned.items():
        full[scene].update(item)
    set_admin_config(scene_config.CONFIG_KEY, full)
    return {"code": 200, "message": "success", "data": full}


@admin_router.post("/reset")
async def admin_reset_llm_scene(current_user: Optional[dict] = Depends(get_current_user)):
    """一键恢复默认配置并保存生效。"""
    _require_super_admin(current_user)
    full = {
        scene: dict(scene_config.DEFAULT_LLM_SCENE_CONFIG[scene])
        for scene in scene_config.SCENES
    }
    set_admin_config(scene_config.CONFIG_KEY, full)
    return {"code": 200, "message": "success", "data": full}


router = admin_router
