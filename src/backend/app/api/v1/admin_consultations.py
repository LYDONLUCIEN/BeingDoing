"""
Admin 报告解读咨询管理 API（P-D）

接口（超管门控，统一响应 {code, message, data}）：
- GET  /admin/consultations                 预约单列表（状态筛选 + 分页，含 user_email）
- GET  /admin/consultations/{id}            预约单详情（问卷内容）
- POST /admin/consultations/{id}/schedule   标记已预约（submitted → scheduled，填实际时间）
- POST /admin/consultations/{id}/complete   标记已完成（scheduled → completed）

退款：走 /admin/payment/orders/{id}/refund（payment_service.admin_refund 已按状态机守卫）。
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.v1.auth import get_current_user
from app.services.consultation_service import BookingNotFoundError, ConsultationService
from app.utils.super_admin import is_super_admin_user

router = APIRouter(prefix="/admin/consultations", tags=["AdminConsultations"])


def _ok(data: Any) -> Dict[str, Any]:
    return {"code": 200, "message": "success", "data": data}


def _require_super_admin(current_user: Optional[dict]) -> None:
    if not is_super_admin_user(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")


class ScheduleRequest(BaseModel):
    """标记已预约"""

    scheduled_at: str = Field(..., description="实际预约时间（ISO 格式，如 2026-07-25 20:00）")
    admin_note: Optional[str] = Field(None, description="管理员备注")


@router.get("")
async def list_bookings(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """咨询预约单列表"""
    _require_super_admin(current_user)
    items, total = await ConsultationService.admin_list_bookings(
        status=status, page=page, page_size=page_size
    )
    return _ok({"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/{booking_id}")
async def get_booking(
    booking_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """预约单详情"""
    _require_super_admin(current_user)
    try:
        booking = await ConsultationService.admin_get_booking(booking_id)
    except BookingNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _ok({"booking": booking})


@router.post("/{booking_id}/schedule")
async def schedule_booking(
    booking_id: str,
    payload: ScheduleRequest,
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """标记已预约（填实际时间 + 备注）"""
    _require_super_admin(current_user)
    try:
        booking = await ConsultationService.admin_schedule(
            booking_id,
            scheduled_at=payload.scheduled_at,
            admin_note=payload.admin_note,
            actor=current_user,
        )
    except BookingNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _ok({"booking": booking})


@router.post("/{booking_id}/complete")
async def complete_booking(
    booking_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
) -> Dict[str, Any]:
    """标记已完成"""
    _require_super_admin(current_user)
    try:
        booking = await ConsultationService.admin_complete(booking_id, actor=current_user)
    except BookingNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _ok({"booking": booking})
