"""
埋点 API：点赞（增删查）、报告生成等（前端调用记录）
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.v1.auth import get_current_user_optional
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["埋点"])


# ──────────────── 请求/响应模型 ────────────────

class LikeRequest(BaseModel):
    """创建点赞（新接口）"""
    session_id: str
    thread_id: Optional[str] = None
    message_id: str
    role: Optional[str] = None
    content_preview: Optional[str] = None
    content_snapshot: Optional[str] = None
    dimension: Optional[str] = None
    phase: Optional[str] = None
    activation_code: Optional[str] = None
    log_index: Optional[int] = None


class LegacyLikeRequest(BaseModel):
    """旧版点赞（兼容保留）"""
    session_id: str
    log_index: int
    content_preview: Optional[str] = None
    dimension: Optional[str] = None


class UnlikeRequest(BaseModel):
    """取消点赞"""
    message_id: str


class ReportGeneratedRequest(BaseModel):
    session_id: str
    activation_code: Optional[str] = None


# ──────────────── 点赞接口 ────────────────

@router.post("/like")
async def toggle_like(req: LikeRequest, current_user: Optional[dict] = Depends(get_current_user_optional)):
    """
    点赞 / 取消点赞（toggle）。
    同一 message_id + user_id 重复点赞视为取消。
    返回 liked: True（已点赞）或 False（已取消）。
    """
    user_id = None
    if current_user:
        user_id = current_user.get("user_id") or current_user.get("email")

    liked = await AnalyticsService.toggle_like(
        user_id=user_id,
        session_id=req.session_id,
        thread_id=req.thread_id,
        message_id=req.message_id,
        role=req.role,
        content_preview=req.content_preview,
        content_snapshot=req.content_snapshot,
        dimension=req.dimension,
        phase=req.phase,
        activation_code=req.activation_code,
        log_index=req.log_index,
    )
    return {"code": 200, "message": "success", "data": {"liked": liked}}


@router.post("/unlike")
async def unlike(req: UnlikeRequest):
    """取消指定消息的点赞"""
    removed = await AnalyticsService.remove_like(message_id=req.message_id)
    return {"code": 200, "message": "success", "data": {"removed": removed}}


@router.get("/likes")
async def get_likes(
    activation_code: Optional[str] = Query(None, description="激活码"),
    phase: Optional[str] = Query(None, description="阶段筛选"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """
    获取点赞列表（按激活码/阶段筛选）。
    用于报告页展示点赞内容，数据来源为 content_snapshot（原文快照）。
    """
    result = await AnalyticsService.get_likes(
        activation_code=activation_code,
        phase=phase,
        limit=limit,
        offset=offset,
    )
    return {"code": 200, "message": "success", "data": result}


@router.get("/likes/check")
async def check_like_status(
    message_ids: str = Query(..., description="逗号分隔的 message_id 列表"),
):
    """
    批量查询消息点赞状态。
    返回 {message_id: True/False}，供前端初始化渲染。
    """
    ids = [m.strip() for m in message_ids.split(",") if m.strip()]
    if not ids:
        return {"code": 200, "message": "success", "data": {}}
    result = await AnalyticsService.check_like_status(message_ids=ids)
    return {"code": 200, "message": "success", "data": result}


@router.get("/likes/message/{message_id}")
async def get_liked_message(message_id: str):
    """
    按 message_id 回查原文。
    优先返回 content_snapshot（快照），若快照为空则尝试从对话历史中加载。
    这是报告页"可溯源"的核心接口。
    """
    result = await AnalyticsService.get_liked_message_trace(message_id=message_id)
    if result is None:
        raise HTTPException(status_code=404, detail="该点赞消息不存在或已被清除")
    return {"code": 200, "message": "success", "data": result}


# ──────────────── 旧接口兼容 ────────────────

@router.post("/like/legacy")
async def record_like_legacy(req: LegacyLikeRequest):
    """旧版点赞记录（兼容保留）"""
    await AnalyticsService.record_like(
        session_id=req.session_id,
        log_index=req.log_index,
        content_preview=req.content_preview,
        dimension=req.dimension,
    )
    return {"code": 200, "message": "success", "data": {"recorded": True}}


# ──────────────── 报告生成 ────────────────

@router.post("/report-generated")
async def record_report_generated(req: ReportGeneratedRequest):
    """记录报告生成（前端在报告就绪时调用）"""
    await AnalyticsService.record_report(
        session_id=req.session_id,
        activation_code=req.activation_code,
    )
    return {"code": 200, "message": "success", "data": {"recorded": True}}
