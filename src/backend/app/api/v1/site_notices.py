"""
站内公告 API

公开接口（无鉴权）：
- GET /api/v1/site-notices/active  当前生效的 banner

Admin 接口（super admin 守卫）：
- GET    /api/v1/admin/site-notices            分页列表
- POST   /api/v1/admin/site-notices            创建
- GET    /api/v1/admin/site-notices/{id}       详情
- PUT    /api/v1/admin/site-notices/{id}       更新
- DELETE /api/v1/admin/site-notices/{id}       删除
- POST   /api/v1/admin/site-notices/{id}/toggle 启用/停用切换
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.v1.auth import get_current_user
from app.services.site_notice_service import SiteNoticeService
from app.utils.super_admin import is_super_admin_user

# 公开 router：/api/v1/site-notices
public_router = APIRouter(prefix="/site-notices", tags=["Site-Notices"])

# Admin router：/api/v1/admin/site-notices
admin_router = APIRouter(prefix="/admin/site-notices", tags=["Admin-Site-Notices"])


def _is_super_admin(user: Optional[dict]) -> bool:
    return is_super_admin_user(user)


# ── 公开接口 ─────────────────────────────────────────────
@public_router.get("/active")
async def get_active_notices(
    type: str = Query("banner", description="公告类型，默认 banner"),
    limit: int = Query(1, ge=1, le=10),
) -> List[Dict[str, Any]]:
    """返回当前生效的公告（时间窗口内 + is_active）"""
    return await SiteNoticeService.list_active(notice_type=type, limit=limit)


# ── Pydantic 模型 ───────────────────────────────────────
class ChannelItem(BaseModel):
    type: str = Field(..., description="wechat | blog | xiaohongshu | other")
    url: Optional[str] = Field(None, description="链接型渠道 URL")
    qr_url: Optional[str] = Field(None, description="图片型渠道（微信群二维码）URL")
    label: Optional[str] = Field(None, description="展示名称，如「微信群」「博客」")


class NoticeCreate(BaseModel):
    type: str = Field("banner")
    title: str = Field(..., min_length=1, max_length=120)
    content_md: Optional[str] = None
    severity: str = Field("info")
    start_at: Optional[str] = None
    end_at: Optional[str] = None
    dismissible: bool = True
    is_active: bool = True
    channels: Optional[List[ChannelItem]] = None


class NoticeUpdate(BaseModel):
    type: Optional[str] = None
    title: Optional[str] = None
    content_md: Optional[str] = None
    severity: Optional[str] = None
    start_at: Optional[str] = None
    end_at: Optional[str] = None
    dismissible: Optional[bool] = None
    is_active: Optional[bool] = None
    channels: Optional[List[ChannelItem]] = None


def _ok(data: Any) -> Dict[str, Any]:
    """统一返回 {code, message, data} 信封，与 app/api/v1/admin.py 一致。

    前端 ApiClient（lib/api/client.ts）的 get/post/patch/delete 会原样返回
    axios 的 response.data，再由各 api 模块取 `.data` 字段拿到业务 payload。
    """
    return {"code": 200, "message": "success", "data": data}


# ── Admin 接口 ──────────────────────────────────────────
@admin_router.get("")
async def admin_list_notices(
    type: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: Optional[dict] = Depends(get_current_user),
):
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    data = await SiteNoticeService.admin_list(
        notice_type=type, is_active=is_active, page=page, page_size=page_size
    )
    return _ok(data)


@admin_router.post("")
async def admin_create_notice(
    payload: NoticeCreate,
    current_user: Optional[dict] = Depends(get_current_user),
):
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    data = payload.model_dump(exclude_none=True)
    # channels 转换为可序列化 dict 列表
    if "channels" in data and data["channels"] is not None:
        data["channels"] = [c if isinstance(c, dict) else c.model_dump() for c in payload.channels]
    return _ok(await SiteNoticeService.admin_create(data))


@admin_router.get("/{notice_id}")
async def admin_get_notice(
    notice_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    r = await SiteNoticeService.admin_get(notice_id)
    if not r:
        raise HTTPException(status_code=404, detail="公告不存在")
    return _ok(r)


@admin_router.put("/{notice_id}")
@admin_router.patch("/{notice_id}")
async def admin_update_notice(
    notice_id: str,
    payload: NoticeUpdate,
    current_user: Optional[dict] = Depends(get_current_user),
):
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    data = payload.model_dump(exclude_none=True)
    if "channels" in data and data["channels"] is not None:
        data["channels"] = [c if isinstance(c, dict) else c.model_dump() for c in payload.channels]
    r = await SiteNoticeService.admin_update(notice_id, data)
    if not r:
        raise HTTPException(status_code=404, detail="公告不存在")
    return _ok(r)


@admin_router.delete("/{notice_id}")
async def admin_delete_notice(
    notice_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    ok = await SiteNoticeService.admin_delete(notice_id)
    if not ok:
        raise HTTPException(status_code=404, detail="公告不存在")
    return _ok({"ok": True})


@admin_router.post("/{notice_id}/toggle")
async def admin_toggle_notice(
    notice_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    r = await SiteNoticeService.admin_toggle(notice_id)
    if not r:
        raise HTTPException(status_code=404, detail="公告不存在")
    return _ok(r)


# 统一导出 router（main.py 注册时用）
router = APIRouter()
router.include_router(public_router)
router.include_router(admin_router)
