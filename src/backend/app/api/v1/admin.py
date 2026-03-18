"""
Admin 专用 API：数据分析仪表盘、点赞详情查看、对话明细
仅超级管理员可访问
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from app.api.v1.auth import get_current_user
from app.utils.data_paths import get_debug_logs_dir, get_logs_dir
from app.utils.simple_activation_manager import SimpleActivationManager, ActivationStatus, get_simple_base_dir
import json
from pathlib import Path

from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/admin", tags=["Admin"])


def _is_super_admin(user: Optional[dict]) -> bool:
    from app.config.settings import settings
    if not user:
        return False
    ids_str = (getattr(settings, "SUPER_ADMIN_USER_IDS", None) or "").strip()
    emails_str = (getattr(settings, "SUPER_ADMIN_EMAILS", None) or "").strip()
    if ids_str and user.get("user_id") in [x.strip() for x in ids_str.split(",") if x.strip()]:
        return True
    if emails_str and user.get("email") in [x.strip() for x in emails_str.split(",") if x.strip()]:
        return True
    return False


@router.get("/analytics")
async def get_admin_analytics(current_user: Optional[dict] = Depends(get_current_user)):
    """获取数据分析仪表盘（仅 super_admin）"""
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    data = await AnalyticsService.get_admin_dashboard()
    return {"code": 200, "message": "success", "data": data}


@router.post("/analytics/sync-from-history")
async def sync_analytics_from_history(current_user: Optional[dict] = Depends(get_current_user)):
    """从 runs.jsonl 历史同步 LLM tokens、用户字数、维度等到 analytics 表（仅 super_admin）"""
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    result = await AnalyticsService.sync_from_history()
    return {"code": 200, "message": "success", "data": result}


@router.get("/analytics/like-detail")
async def get_like_detail(
    session_id: str,
    log_index: int,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """根据 session_id 和 log_index 获取被点赞的原始记录详情（runs.jsonl 中对应行）"""
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    debug_path = get_debug_logs_dir() / f"{session_id}.jsonl"
    candidates = [debug_path]
    logs_root = get_logs_dir()
    if logs_root.is_dir():
        for user_dir in logs_root.iterdir():
            if user_dir.is_dir():
                p = user_dir / session_id / "runs.jsonl"
                if p.is_file():
                    candidates.append(p)
    for p in candidates:
        if not p.is_file():
            continue
        with open(p, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i == log_index:
                    try:
                        return {"code": 200, "message": "success", "data": json.loads(line)}
                    except json.JSONDecodeError:
                        return {"code": 200, "message": "success", "data": {"raw": line[:2000]}}
    return {"code": 404, "message": "未找到对应记录", "data": None}


@router.get("/analytics/chat-records")
async def get_chat_records(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    dimension: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    current_user: Optional[dict] = Depends(get_current_user),
):
    """分页获取所有对话轮次明细（仅 super_admin）"""
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    result = await AnalyticsService.get_chat_records_paginated(
        page=page, page_size=page_size, dimension=dimension, session_id=session_id
    )
    return {"code": 200, "message": "success", "data": result}


@router.get("/analytics/session-detail")
async def get_session_detail(
    session_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """获取某 session 的完整对话内容（runs.jsonl 或 data/simple 下的多轮会话）（仅 super_admin）"""
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    detail = await AnalyticsService.get_session_conversation_detail(session_id)
    if detail is None:
        return {"code": 404, "message": "未找到会话", "data": None}
    return {"code": 200, "message": "success", "data": detail}


@router.get("/activations")
async def list_activations(
    status: Optional[str] = None,
    mode: Optional[str] = None,
    q: Optional[str] = None,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    列出 simple 模式下的所有激活码记录（仅 super_admin）。
    - status: active / expired / revoked，可选过滤
    - mode: values / strengths / interests / combined，可选过滤
    - q: 按 activation_code 或 session_id 进行模糊匹配
    """
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")

    manager = SimpleActivationManager()
    records = manager.list_activations()

    items = []
    for code, rec in records.items():
        if status and rec.status != status:
            continue
        if mode and rec.mode != mode:
            continue
        if q and (q not in rec.code and q not in rec.session_id):
            continue
        items.append(
            {
                "activation_code": rec.code,
                "session_id": rec.session_id,
                "mode": rec.mode,
                "created_at": rec.created_at,
                "expires_at": rec.expires_at,
                "last_activity_at": rec.last_activity_at,
                "status": rec.status,
            }
        )

    # 按创建时间倒序
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": items,
            "total": len(items),
        },
    }
