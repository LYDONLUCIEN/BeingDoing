"""
埋点 API：点赞、报告生成等（前端调用记录）
"""
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel

from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["埋点"])


class LikeRequest(BaseModel):
    session_id: str
    log_index: int
    content_preview: Optional[str] = None
    dimension: Optional[str] = None


class ReportGeneratedRequest(BaseModel):
    session_id: str
    activation_code: Optional[str] = None


@router.post("/like")
async def record_like(req: LikeRequest):
    """记录用户点赞"""
    await AnalyticsService.record_like(
        session_id=req.session_id,
        log_index=req.log_index,
        content_preview=req.content_preview,
        dimension=req.dimension,
    )
    return {"code": 200, "message": "success", "data": {"recorded": True}}


@router.post("/report-generated")
async def record_report_generated(req: ReportGeneratedRequest):
    """记录报告生成（前端在报告就绪时调用）"""
    await AnalyticsService.record_report(
        session_id=req.session_id,
        activation_code=req.activation_code,
    )
    return {"code": 200, "message": "success", "data": {"recorded": True}}
