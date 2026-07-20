"""
报告解读咨询 API（用户侧，P-D）

接口（全部 get_current_user 登录鉴权，统一响应 {code, message, data}）：
- GET  /consultation/my-reports              我的已完成报告（问卷选报告用）
- GET  /consultation/bookings                我的咨询预约单列表
- GET  /consultation/bookings/{id}           我的预约单详情
- POST /consultation/bookings/{id}/survey    提交预约问卷（pending_survey → submitted）

异常映射：ValueError → 400；BookingNotFoundError → 404。
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.v1.auth import get_current_user
from app.services.consultation_service import BookingNotFoundError, ConsultationService

router = APIRouter(prefix="/consultation", tags=["Consultation"])


def _ok(data: Any) -> Dict[str, Any]:
    return {"code": 200, "message": "success", "data": data}


def _raise_for_service_error(e: Exception) -> None:
    if isinstance(e, BookingNotFoundError):
        raise HTTPException(status_code=404, detail=str(e))
    if isinstance(e, ValueError):
        raise HTTPException(status_code=400, detail=str(e))
    raise e


class SurveySubmitRequest(BaseModel):
    """预约问卷提交"""

    report_id: str = Field(..., description="要解读的报告 ID")
    topics: str = Field(..., min_length=1, description="想探讨的主题/期望")
    time_slots: List[str] = Field(..., min_length=1, max_length=5, description="候选时间段")
    contact: str = Field(..., min_length=1, description="联系方式（微信或电话）")
    note: Optional[str] = Field(None, description="备注（可选）")


@router.get("/my-reports")
async def my_reports(
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """我的已完成且审核通过的报告列表（咨询前置/问卷选报告）"""
    return _ok({"items": ConsultationService.list_user_completed_reports(str(current_user["user_id"]))})


@router.get("/bookings")
async def list_bookings(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """我的咨询预约单列表"""
    items, total = await ConsultationService.list_my_bookings(
        user_id=str(current_user["user_id"]), page=page, page_size=page_size
    )
    return _ok({"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/bookings/{booking_id}")
async def get_booking(
    booking_id: str,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """我的预约单详情（仅本人）"""
    try:
        booking = await ConsultationService.get_my_booking(
            user_id=str(current_user["user_id"]), booking_id=booking_id
        )
    except BookingNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _ok({"booking": booking})


@router.post("/bookings/{booking_id}/survey")
async def submit_survey(
    booking_id: str,
    payload: SurveySubmitRequest,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """提交预约问卷（pending_survey → submitted）"""
    try:
        booking = await ConsultationService.submit_survey(
            user_id=str(current_user["user_id"]),
            booking_id=booking_id,
            report_id=payload.report_id,
            topics=payload.topics,
            time_slots=payload.time_slots,
            contact=payload.contact,
            note=payload.note,
        )
    except (ValueError, BookingNotFoundError) as e:
        _raise_for_service_error(e)
    return _ok({"booking": booking})
