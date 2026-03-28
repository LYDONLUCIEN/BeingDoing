"""
Admin 专用 API：数据分析仪表盘、点赞详情查看、对话明细
仅超级管理员可访问
"""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from app.api.v1.auth import get_current_user
from app.utils.data_paths import get_debug_logs_dir, get_logs_dir
from app.utils.simple_activation_manager import SimpleActivationManager, ActivationStatus, get_simple_base_dir
import json
from pathlib import Path
from datetime import datetime
from sqlalchemy import select
from app.models.database import AsyncSessionLocal
from app.models.analytics import AnalyticsReport
from app.utils.report_registry import ReportRegistry
from app.config.settings import settings
from app.utils.super_admin import is_super_admin_user

from app.services.analytics_service import AnalyticsService
from app.utils.sandbox_fork import (
    SANDBOX_RETENTION_DAYS,
    delete_sandbox_by_code,
    fork_activation_from_source,
    list_sandboxes,
    purge_expired_sandboxes,
)
from app.utils.admin_workspace import ensure_admin_resident_workspace
from app.utils.admin_policy import (
    is_admin_debug_workspace_enabled,
    is_admin_sandbox_enabled,
)
from app.utils.admin_prompt_lab import (
    add_profile_version,
    bind_profile_to_activation,
    create_profile,
    export_current_profile_payload,
    get_profile,
    list_bindings as list_prompt_bindings,
    list_profiles as list_prompt_profiles,
    set_current_version,
)

router = APIRouter(prefix="/admin", tags=["Admin"])


class ActivationBatchCreateRequest(BaseModel):
    ttl_days: int = Field(default=30, ge=1, le=3650)
    count: int = Field(default=1, ge=1, le=500)


class ActivationBatchActionRequest(BaseModel):
    codes: List[str] = Field(default_factory=list)


class ActivationBatchStatusRequest(ActivationBatchActionRequest):
    status: str


class ActivationSyncRequest(BaseModel):
    sources: List[str] = Field(default_factory=list)
    dry_run: bool = False
    mode: str = "insert_only"
    default_status: str = ActivationStatus.REVOKED.value


class SandboxForkRequest(BaseModel):
    """从正式激活码 Fork 调试沙箱（独立目录，默认保留 15 天）"""

    source_activation_code: str = Field(..., min_length=1)


_SYNC_SOURCES = ("analytics_reports", "reports_registry", "simple_activations_file")


def _is_super_admin(user: Optional[dict]) -> bool:
    return is_super_admin_user(user)


def _assert_admin_debug_workspace_enabled() -> None:
    if not is_admin_debug_workspace_enabled():
        raise HTTPException(status_code=403, detail="当前环境未开启管理员常驻工作区功能")


def _assert_admin_sandbox_enabled() -> None:
    if not is_admin_sandbox_enabled():
        raise HTTPException(status_code=403, detail="当前环境未开启管理员调试沙箱功能")


async def _rows_from_analytics_reports(default_status: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(
                AnalyticsReport.activation_code,
                AnalyticsReport.session_id,
                AnalyticsReport.created_at,
            ).where(AnalyticsReport.activation_code.isnot(None))
        )
        for activation_code, session_id, created_at in result.all():
            if not activation_code or not session_id:
                continue
            rows.append(
                {
                    "activation_code": activation_code,
                    "session_id": session_id,
                    "created_at": created_at.isoformat() + "Z" if created_at else None,
                    "mode": "combined",
                    "status": default_status,
                    "source": "analytics_reports",
                }
            )
    return rows


def _rows_from_reports_registry(default_status: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    registry = ReportRegistry()
    reports = registry.list_reports()
    for report in reports:
        activation_code = (report or {}).get("activation_code")
        steps = (report or {}).get("steps") or {}
        created_at = (report or {}).get("created_at")
        if not activation_code or not steps:
            continue

        # 优先 values，缺失时按固定顺序回退
        session_id = None
        for sid in ("values", "strengths", "interests", "purpose", "rumination"):
            sessions = ((steps.get(sid) or {}).get("session_ids")) or []
            if sessions:
                session_id = sessions[0]
                break
        if not session_id:
            continue

        rows.append(
            {
                "activation_code": activation_code,
                "session_id": session_id,
                "created_at": created_at,
                "mode": "combined",
                "status": default_status,
                "source": "reports_registry",
            }
        )
    return rows


def _rows_from_simple_activations_file(default_status: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    activations_file = get_simple_base_dir() / "activations.json"
    if not activations_file.is_file():
        return rows
    try:
        raw = json.loads(activations_file.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        return rows

    for code, rec in (raw or {}).items():
        if not isinstance(rec, dict):
            continue
        session_id = (rec.get("session_id") or "").strip()
        if not code or not session_id:
            continue
        rows.append(
            {
                "activation_code": code,
                "session_id": session_id,
                "created_at": rec.get("created_at"),
                "expires_at": rec.get("expires_at"),
                "last_activity_at": rec.get("last_activity_at"),
                "mode": "combined",
                "status": rec.get("status") or default_status,
                "source": "simple_activations_file",
            }
        )
    return rows


@router.get("/analytics")
async def get_admin_analytics(current_user: Optional[dict] = Depends(get_current_user)):
    """获取数据分析仪表盘（仅 super_admin）"""
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    data = await AnalyticsService.get_admin_dashboard()
    return {"code": 200, "message": "success", "data": data}


@router.get("/dashboard/overview")
async def get_dashboard_overview(current_user: Optional[dict] = Depends(get_current_user)):
    """Admin Dashboard 概览统计（仅 super_admin）"""
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    data = await AnalyticsService.get_dashboard_overview_from_static()
    return {"code": 200, "message": "success", "data": data}


@router.post("/dashboard/overview/sync")
async def sync_dashboard_overview(current_user: Optional[dict] = Depends(get_current_user)):
    """手动从 /data 重算 dashboard，并写入 data/static 缓存"""
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    data = await AnalyticsService.sync_dashboard_overview_to_static()
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
    activation_type: Optional[str] = Query(
        None,
        description="normal=正式激活码，fork=调试沙箱 Fork（SBX），不传则全部",
    ),
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    列出 simple 模式下的所有激活码记录（仅 super_admin）。
    - status: active / expired / revoked，可选过滤
    - mode: 兼容保留参数（激活码统一按 combined 处理）
    - q: 按 activation_code 或 session_id 进行模糊匹配
    - activation_type: normal | fork（沙箱）
    """
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")

    manager = SimpleActivationManager()
    records = manager.list_activations()

    at = (activation_type or "").strip().lower()
    items = []
    for code, rec in records.items():
        # 删除到垃圾桶的激活码只在 recycle-bin 展示，不再出现在主列表
        if rec.status == ActivationStatus.DELETED.value and (status is None or status != ActivationStatus.DELETED.value):
            continue
        if status and rec.status != status:
            continue
        if q and (q not in rec.code and q not in rec.session_id):
            continue
        is_fork = bool(getattr(rec, "is_sandbox", False))
        if at == "fork" and not is_fork:
            continue
        if at == "normal" and is_fork:
            continue
        items.append(
            {
                "activation_code": rec.code,
                "session_id": rec.session_id,
                "mode": "combined",
                "created_at": rec.created_at,
                "expires_at": rec.expires_at,
                "last_activity_at": rec.last_activity_at,
                "status": rec.status,
                "owner_user_id": rec.owner_user_id,
                "owner_email": rec.owner_email,
                "claimed_at": rec.claimed_at,
                "deleted_at": rec.deleted_at,
                "purge_after": rec.purge_after,
                "source": rec.source,
                "activation_type": "fork" if is_fork else "normal",
                "is_sandbox": is_fork,
                "sandbox_root": getattr(rec, "sandbox_root", None),
                "fork_id": getattr(rec, "fork_id", None),
                "forked_from_code": getattr(rec, "forked_from_code", None),
                "forked_at": getattr(rec, "forked_at", None),
                "sandbox_expires_at": getattr(rec, "sandbox_expires_at", None),
                "workspace_kind": getattr(rec, "workspace_kind", None),
                "workspace_root": getattr(rec, "workspace_root", None),
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


@router.post("/activations/batch-create")
async def batch_create_activations(
    request: ActivationBatchCreateRequest,
    current_user: Optional[dict] = Depends(get_current_user),
):
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    manager = SimpleActivationManager()
    created = manager.create_activation_batch(
        mode="combined",
        ttl_minutes=request.ttl_days * 24 * 60,
        count=request.count,
    )
    return {
        "code": 200,
        "message": "success",
        "data": {
            "count": len(created),
            "ttl_days": request.ttl_days,
            "items": [
                {
                    "activation_code": rec.code,
                    "session_id": rec.session_id,
                    "mode": rec.mode,
                    "created_at": rec.created_at,
                    "expires_at": rec.expires_at,
                    "status": rec.status,
                }
                for rec in created
            ],
        },
    }


@router.post("/activations/batch-status")
async def batch_update_activation_status(
    request: ActivationBatchStatusRequest,
    current_user: Optional[dict] = Depends(get_current_user),
):
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    manager = SimpleActivationManager()
    changed = manager.update_status(request.codes, request.status)
    return {"code": 200, "message": "success", "data": {"changed": changed}}


@router.post("/activations/batch-delete")
async def batch_delete_activations(
    request: ActivationBatchActionRequest,
    current_user: Optional[dict] = Depends(get_current_user),
):
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    manager = SimpleActivationManager()
    changed = manager.soft_delete_to_recycle_bin(
        request.codes,
        deleted_by=current_user,
        retention_days=30,
    )
    return {"code": 200, "message": "success", "data": {"changed": changed, "retention_days": 30}}


@router.get("/activations/recycle-bin")
async def list_activation_recycle_bin(current_user: Optional[dict] = Depends(get_current_user)):
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    manager = SimpleActivationManager()
    recycle = manager.list_recycle_bin()
    now = datetime.utcnow()
    items = []
    for rec in recycle.values():
        try:
            purge_after_dt = datetime.fromisoformat((rec.purge_after or "").replace("Z", ""))
            days_remaining = max(0, (purge_after_dt - now).days)
        except ValueError:
            days_remaining = None
        items.append(
            {
                "activation_code": rec.activation_code,
                "session_id": rec.session_id,
                "mode": rec.mode,
                "deleted_at": rec.deleted_at,
                "purge_after": rec.purge_after,
                "days_remaining": days_remaining,
                "deleted_by_user_id": rec.deleted_by_user_id,
                "deleted_by_email": rec.deleted_by_email,
            }
        )
    items.sort(key=lambda x: x.get("deleted_at", ""), reverse=True)
    return {"code": 200, "message": "success", "data": {"items": items, "total": len(items)}}


@router.post("/activations/recycle-bin/restore")
async def restore_activations_from_recycle(
    request: ActivationBatchActionRequest,
    current_user: Optional[dict] = Depends(get_current_user),
):
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    manager = SimpleActivationManager()
    changed = manager.restore_from_recycle_bin(request.codes)
    return {"code": 200, "message": "success", "data": {"changed": changed}}


@router.post("/activations/recycle-bin/purge")
async def purge_activation_recycle_bin(current_user: Optional[dict] = Depends(get_current_user)):
    """清理过期垃圾桶条目（按 purge_after 自动）"""
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    manager = SimpleActivationManager()
    purged = manager.purge_recycle_bin()
    return {"code": 200, "message": "success", "data": {"purged": purged}}


@router.post("/activations/recycle-bin/permanent-delete")
async def permanent_delete_from_recycle_bin(
    request: ActivationBatchActionRequest,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """确认立即永久删除：移除激活码、report 目录、flat session 目录等所有相关数据"""
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    manager = SimpleActivationManager()
    base = get_simple_base_dir()
    deleted = manager.permanent_delete_from_recycle_bin(
        request.codes, reports_root=base / "reports"
    )
    return {"code": 200, "message": "success", "data": {"deleted": deleted}}


@router.post("/activations/sync-from-db")
async def sync_activations_from_db(
    request: Optional[ActivationSyncRequest] = None,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    多源补齐激活码列表（insert-only）。
    支持来源：
    - analytics_reports
    - reports_registry
    - simple_activations_file
    """
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")

    req = request or ActivationSyncRequest()
    selected_sources = req.sources or list(_SYNC_SOURCES)
    invalid_sources = [s for s in selected_sources if s not in _SYNC_SOURCES]
    if invalid_sources:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的数据源: {', '.join(invalid_sources)}",
        )
    if req.mode != "insert_only":
        raise HTTPException(status_code=400, detail="当前仅支持 mode=insert_only")

    allowed_status = {
        ActivationStatus.ACTIVE.value,
        ActivationStatus.EXPIRED.value,
        ActivationStatus.REVOKED.value,
        ActivationStatus.DELETED.value,
    }
    default_status = (req.default_status or ActivationStatus.REVOKED.value).strip().lower()
    if default_status not in allowed_status:
        raise HTTPException(status_code=400, detail="default_status 不支持")

    source_rows: Dict[str, List[Dict[str, Any]]] = {}
    for source in selected_sources:
        if source == "analytics_reports":
            source_rows[source] = await _rows_from_analytics_reports(default_status)
        elif source == "reports_registry":
            source_rows[source] = _rows_from_reports_registry(default_status)
        elif source == "simple_activations_file":
            source_rows[source] = _rows_from_simple_activations_file(default_status)

    by_source: Dict[str, Dict[str, int]] = {
        source: {"scanned": len(source_rows.get(source, [])), "normalized": 0, "would_insert": 0, "inserted": 0}
        for source in selected_sources
    }

    merged: Dict[str, Dict[str, Any]] = {}
    conflicts = 0
    skipped_invalid = 0
    duplicates = 0
    for source in selected_sources:
        for row in source_rows.get(source, []):
            code = ((row.get("activation_code") or "").strip().upper())
            session_id = (row.get("session_id") or "").strip()
            if not code or not session_id:
                skipped_invalid += 1
                continue
            by_source[source]["normalized"] += 1

            if code in merged:
                existing_session = (merged[code].get("session_id") or "").strip()
                if existing_session != session_id:
                    conflicts += 1
                    continue
                duplicates += 1
                continue

            merged[code] = {
                "activation_code": code,
                "session_id": session_id,
                "created_at": row.get("created_at"),
                "expires_at": row.get("expires_at"),
                "last_activity_at": row.get("last_activity_at"),
                "mode": "combined",
                "status": row.get("status") or default_status,
                "source": row.get("source") or source,
            }

    manager = SimpleActivationManager()
    existing_codes = set(manager.list_activations().keys())
    for code, row in merged.items():
        source = (row.get("source") or "unknown")
        if code not in existing_codes and source in by_source:
            by_source[source]["would_insert"] += 1

    merged_rows = list(merged.values())
    inserted = 0
    if not req.dry_run:
        inserted = manager.upsert_from_db_rows(merged_rows)
        # 按 source 统计实际 inserted（insert_only 下与 would_insert 等价）
        for source in selected_sources:
            by_source[source]["inserted"] = by_source[source]["would_insert"]

    return {
        "code": 200,
        "message": "success",
        "data": {
            "mode": req.mode,
            "dry_run": req.dry_run,
            "sources": selected_sources,
            "rows_scanned": sum(v["scanned"] for v in by_source.values()),
            "rows_normalized": sum(v["normalized"] for v in by_source.values()),
            "rows_merged": len(merged_rows),
            "skipped_invalid": skipped_invalid,
            "duplicates": duplicates,
            "conflicts": conflicts,
            "would_insert": sum(v["would_insert"] for v in by_source.values()),
            "synced": inserted,
            "by_source": by_source,
        },
    }


@router.get("/reports")
async def list_reports(
    q: Optional[str] = None,
    activation_code: Optional[str] = None,
    user_id: Optional[str] = None,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """报告列表（文件注册表）"""
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    registry = ReportRegistry()
    reports = registry.list_reports()
    items = []
    for report in reports:
        rid = report.get("report_id")
        ac = report.get("activation_code")
        uid = report.get("user_id")
        if activation_code and (ac or "").upper() != activation_code.upper():
            continue
        if user_id and uid != user_id:
            continue
        if q:
            target = f"{rid} {ac} {uid}".lower()
            if q.lower() not in target:
                continue
        steps = report.get("steps") or {}
        step_stats = {}
        completed = 0
        for step_id in ["values", "strengths", "interests", "purpose", "rumination"]:
            sessions = ((steps.get(step_id) or {}).get("session_ids")) or []
            cnt = len(sessions)
            step_stats[step_id] = cnt
            if cnt > 0:
                completed += 1
        items.append(
            {
                "report_id": rid,
                "activation_code": ac,
                "user_id": uid,
                "status": report.get("status", "in_progress"),
                "created_at": report.get("created_at"),
                "updated_at": report.get("updated_at"),
                "step_stats": step_stats,
                "completed_steps": completed,
            }
        )
    items.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    return {"code": 200, "message": "success", "data": {"items": items, "total": len(items)}}


@router.get("/reports/{report_id}")
async def get_report_detail(
    report_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    registry = ReportRegistry()
    report = next((r for r in registry.list_reports() if r.get("report_id") == report_id), None)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    return {"code": 200, "message": "success", "data": report}


@router.get("/reports/{report_id}/download")
async def download_report_json(
    report_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    registry = ReportRegistry()
    report = next((r for r in registry.list_reports() if r.get("report_id") == report_id), None)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    return JSONResponse(
        content=report,
        headers={"Content-Disposition": f'attachment; filename="report-{report_id}.json"'},
    )


@router.post("/reports/sync-from-activations")
async def sync_reports_from_activations(current_user: Optional[dict] = Depends(get_current_user)):
    """
    从 activations 反向补齐 report 注册表：
    - 仅对「已激活」（有 owner）且缺失 report 的 activation 生成 report
    - 从未被使用过的激活码（无 owner）不创建 report
    """
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    manager = SimpleActivationManager()
    registry = ReportRegistry()
    activations = manager.list_activations()
    created = 0
    for rec in activations.values():
        user_id = (rec.owner_user_id or rec.owner_email or "").strip()
        if not user_id:
            continue
        existed = registry.get_by_activation_user(rec.code, user_id)
        if existed:
            continue
        registry.ensure_report(
            activation_code=rec.code,
            user_id=user_id,
            session_id=rec.session_id,
        )
        created += 1
    return {"code": 200, "message": "success", "data": {"created": created, "scanned": len(activations)}}


def _load_report_step_session(report_id: str, step_id: str, session_id: str) -> Optional[dict]:
    registry = ReportRegistry()
    file = registry.get_step_session_file(report_id, step_id, session_id)
    if not file.is_file():
        return None
    try:
        return json.loads(file.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        return None


def _save_report_step_session(report_id: str, step_id: str, session_id: str, data: dict) -> None:
    """写入 report step session 对话文件"""
    registry = ReportRegistry()
    file = registry.get_step_session_file(report_id, step_id, session_id)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class ConversationCloneRequest(BaseModel):
    source_report_id: str
    source_phase: str
    source_thread_id: str
    target_activation_code: str
    target_phase: str
    target_thread_id: Optional[str] = None


class JumpToRuminationRequest(BaseModel):
    activation_code: str
    target_section: str = "opening"
    target_filter_step: Optional[int] = None
    seed_table: Optional[dict] = None


class ApplyMockRequest(BaseModel):
    activation_code: str


class SaveAsMockRequest(BaseModel):
    activation_code: Optional[str] = None
    report_id: Optional[str] = None


class PromptProfileCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None


class PromptProfileVersionCreateRequest(BaseModel):
    simple_chat_system_prompt_template: str
    extra_goal_hint: Optional[str] = None


class PromptProfileActivateVersionRequest(BaseModel):
    version_id: str


class PromptActivationBindRequest(BaseModel):
    activation_code: str
    profile_id: str


@router.get("/conversations/mock-info")
async def get_mock_info(current_user: Optional[dict] = Depends(get_current_user)):
    """获取 Admin Mock 数据信息"""
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    _assert_admin_sandbox_enabled()
    from app.utils.admin_mock import get_mock_info as _get
    return {"code": 200, "message": "success", "data": _get()}


@router.post("/conversations/init-mock")
async def init_mock(current_user: Optional[dict] = Depends(get_current_user)):
    """强制初始化 mock 数据（覆盖为默认模板），供 rumination 测试"""
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    _assert_admin_sandbox_enabled()
    from app.utils.admin_mock import init_mock_force
    return {"code": 200, "message": "success", "data": init_mock_force()}


@router.post("/conversations/apply-mock-to-activation")
async def apply_mock_to_activation(
    request: ApplyMockRequest,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """将 mock 数据应用到指定激活码，满足进入 rumination 等阶段的前置要求"""
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    _assert_admin_sandbox_enabled()
    from app.utils.admin_mock import apply_mock_to_activation as _apply
    try:
        registry = ReportRegistry()
        result = _apply(request.activation_code.strip().upper(), registry)
        return {"code": 200, "message": "success", "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/conversations/save-as-mock")
async def save_as_mock(
    request: SaveAsMockRequest,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """将指定 report 的 prior 数据保存为 mock，可用 data 中历史数据替换"""
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    _assert_admin_sandbox_enabled()
    from app.utils.admin_mock import save_report_as_mock
    try:
        result = save_report_as_mock(
            activation_code=request.activation_code.strip().upper() if request.activation_code else None,
            report_id=request.report_id,
        )
        return {"code": 200, "message": "success", "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/conversations/clone")
async def clone_conversation(
    request: ConversationCloneRequest,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    克隆会话：将源对话内容复制到目标 activation 的对应 phase。
    仅 super_admin 可访问。
    """
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    _assert_admin_sandbox_enabled()

    registry = ReportRegistry()
    manager = SimpleActivationManager()
    reports_root = get_simple_base_dir() / "reports"

    src_file = reports_root / request.source_report_id / f"{request.source_phase}__{request.source_thread_id}.json"
    if not src_file.is_file():
        raise HTTPException(status_code=404, detail="源会话不存在")

    rec = manager.get_activation(request.target_activation_code.strip().upper())
    if not rec:
        raise HTTPException(status_code=404, detail="目标激活码不存在")

    user_id = (current_user or {}).get("user_id") or f"unknown:{rec.code}"
    target_report = registry.ensure_report(
        activation_code=rec.code,
        user_id=user_id,
        session_id=rec.session_id,
    )
    target_report_id = target_report.get("report_id")
    if not target_report_id:
        raise HTTPException(status_code=500, detail="目标报告初始化失败")

    target_thread_id = (request.target_thread_id or "").strip()
    if not target_thread_id:
        import uuid
        target_thread_id = str(uuid.uuid4())

    try:
        data = json.loads(src_file.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        raise HTTPException(status_code=500, detail="源会话文件读取失败")

    _save_report_step_session(
        target_report_id,
        ReportRegistry.normalize_step_id(request.target_phase),
        target_thread_id,
        data,
    )
    registry.bind_session(target_report_id, request.target_phase, target_thread_id)

    return {
        "code": 200,
        "message": "success",
        "data": {
            "target_report_id": target_report_id,
            "target_phase": request.target_phase,
            "target_thread_id": target_thread_id,
        },
    }


@router.post("/conversations/jump-to-rumination")
async def jump_to_rumination(
    request: JumpToRuminationRequest,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    跳步到 Rumination：设置进度并可选注入种子消息，供调试使用。
    仅 super_admin 可访问。
    """
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    _assert_admin_sandbox_enabled()

    manager = SimpleActivationManager()
    registry = ReportRegistry()
    rec = manager.get_activation(request.activation_code.strip().upper())
    if not rec:
        raise HTTPException(status_code=404, detail="激活码不存在")

    user_id = (current_user or {}).get("user_id") or f"unknown:{rec.code}"
    report = registry.ensure_report(
        activation_code=rec.code,
        user_id=user_id,
        session_id=rec.session_id,
    )
    report_id = report.get("report_id")
    if not report_id:
        raise HTTPException(status_code=500, detail="报告初始化失败")

    # 使用 mock 数据预填未完成阶段（含 prior context），避免 init 报 400
    try:
        from app.utils.admin_mock import apply_mock_to_activation as _apply_mock
        _apply_mock(request.activation_code.strip().upper(), registry)
    except ValueError:
        pass  # 激活码无 report 等，回退到原有逻辑
    except Exception:
        # 回退：仅预填 steps
        placeholder = rec.session_id or str(report_id)
        record = registry.get_report_by_id(report_id)
        if record:
            for step in ("values", "strengths", "interests", "purpose"):
                st = (record.get("steps") or {}).get(step, {})
                if st.get("selected_session_id"):
                    continue
                try:
                    registry.bind_session(report_id, step, placeholder)
                    registry.select_session(report_id, step, placeholder)
                    registry.lock_step(report_id, step)
                except ValueError:
                    pass

    from app.utils.rumination_progress import save_rumination_progress

    reports_root = get_simple_base_dir() / "reports"
    progress = save_rumination_progress(
        reports_root,
        report_id,
        main_section=request.target_section,
        filter_step=request.target_filter_step or 0,
        filter_table=request.seed_table,
    )

    return {
        "code": 200,
        "message": "success",
        "data": {"progress": progress, "activation_code": rec.code},
    }


@router.get("/conversations")
async def list_conversations(
    q: Optional[str] = None,
    report_id: Optional[str] = None,
    activation_code: Optional[str] = None,
    user_id: Optional[str] = None,
    step_id: Optional[str] = None,
    session_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: Optional[dict] = Depends(get_current_user),
):
    """按 report-step-session 展开会话列表"""
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    registry = ReportRegistry()
    reports = registry.list_reports()
    rows = []
    for report in reports:
        rid = report.get("report_id")
        ac = report.get("activation_code")
        uid = report.get("user_id")
        if report_id and rid != report_id:
            continue
        if activation_code and (ac or "").upper() != activation_code.upper():
            continue
        if user_id and uid != user_id:
            continue
        steps = report.get("steps") or {}
        for sid, step_payload in steps.items():
            normalized_step = ReportRegistry.normalize_step_id(sid)
            if step_id and normalized_step != ReportRegistry.normalize_step_id(step_id):
                continue
            for sess_id in (step_payload.get("session_ids") or []):
                if session_id and session_id != sess_id:
                    continue
                if q:
                    target = f"{rid} {ac} {uid} {normalized_step} {sess_id}".lower()
                    if q.lower() not in target:
                        continue
                conv = _load_report_step_session(rid, normalized_step, sess_id)
                msg_count = 0
                last_ts = None
                if conv:
                    messages = conv.get("messages") or []
                    msg_count = len(messages)
                    if messages:
                        ts = (messages[-1] or {}).get("created_at") or (messages[-1] or {}).get("timestamp")
                        if ts:
                            last_ts = ts
                rows.append(
                    {
                        "report_id": rid,
                        "activation_code": ac,
                        "user_id": uid,
                        "step_id": normalized_step,
                        "session_id": sess_id,
                        "message_count": msg_count,
                        "last_message_at": last_ts,
                        "updated_at": (step_payload or {}).get("updated_at") or report.get("updated_at"),
                    }
                )
    rows.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    total = len(rows)
    start = (page - 1) * page_size
    end = start + page_size
    page_rows = rows[start:end]
    return {"code": 200, "message": "success", "data": {"items": page_rows, "total": total, "page": page, "page_size": page_size}}


@router.get("/conversations/{session_id}")
async def get_conversation_detail(
    session_id: str,
    report_id: Optional[str] = Query(None),
    step_id: Optional[str] = Query(None),
    current_user: Optional[dict] = Depends(get_current_user),
):
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    registry = ReportRegistry()

    # 优先使用前端传入的 report_id + step_id 精确定位
    if report_id and step_id:
        normalized_step = ReportRegistry.normalize_step_id(step_id)
        conv = _load_report_step_session(report_id, normalized_step, session_id)
        if conv:
            return {
                "code": 200,
                "message": "success",
                "data": {
                    "source": "report_dir",
                    "report_id": report_id,
                    "step_id": normalized_step,
                    "session_id": session_id,
                    "conversation": conv,
                },
            }

    # 兜底：仅按 session_id 在注册表中反查
    found = registry.find_report_step_by_session(session_id)
    if found:
        report, resolved_step_id = found
        conv = _load_report_step_session(report["report_id"], resolved_step_id, session_id)
        if conv:
            return {
                "code": 200,
                "message": "success",
                "data": {
                    "source": "report_dir",
                    "report_id": report["report_id"],
                    "step_id": resolved_step_id,
                    "session_id": session_id,
                    "conversation": conv,
                },
            }

    detail = await AnalyticsService.get_session_conversation_detail(session_id)
    if not detail:
        # Admin 前端需要“可读返回”而不是抛 404，避免按钮点击后直接报错。
        return {
            "code": 200,
            "message": "success",
            "data": {
                "source": "not_found",
                "session_id": session_id,
                "report_id": report_id,
                "step_id": step_id,
                "conversation": {"messages": [], "metadata": {}},
            },
        }
    return {"code": 200, "message": "success", "data": detail}


@router.get("/system/settings")
async def get_system_settings(current_user: Optional[dict] = Depends(get_current_user)):
    """系统只读配置（脱敏）"""
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    from app.utils.admin_config import get_basic_info_merge_strategy
    return {
        "code": 200,
        "message": "success",
        "data": {
            "APP_ENV": getattr(settings, "APP_ENV", None),
            "ARCHITECTURE_MODE": getattr(settings, "ARCHITECTURE_MODE", None),
            "LLM_PROVIDER": getattr(settings, "LLM_PROVIDER", None),
            "LLM_MODEL": getattr(settings, "LLM_MODEL", None),
            "AUDIO_MODE": getattr(settings, "AUDIO_MODE", None),
            "DEBUG_MODE": getattr(settings, "DEBUG_MODE", None),
            "ADMIN_DEBUG_POLICY_ENABLED": getattr(settings, "ADMIN_DEBUG_POLICY_ENABLED", False),
            "ADMIN_DEBUG_WORKSPACE_ENABLED": getattr(settings, "ADMIN_DEBUG_WORKSPACE_ENABLED", True),
            "ADMIN_SANDBOX_ENABLED": getattr(settings, "ADMIN_SANDBOX_ENABLED", True),
            "SUPER_ADMIN_EMAILS_CONFIGURED": bool((getattr(settings, "SUPER_ADMIN_EMAILS", "") or "").strip()),
            "BASIC_INFO_MERGE_STRATEGY": get_basic_info_merge_strategy(),
        },
    }


class SystemSettingsPatchRequest(BaseModel):
    basic_info_merge_strategy: Optional[str] = None


@router.patch("/system/settings")
async def patch_system_settings(
    req: SystemSettingsPatchRequest,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """更新可配置的系统设置（如 basic_info 合并策略）"""
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    from app.utils.admin_config import set_admin_config
    if req.basic_info_merge_strategy is not None:
        val = (req.basic_info_merge_strategy or "").strip().upper()
        if val not in ("A", "B", "C"):
            raise HTTPException(status_code=400, detail="basic_info_merge_strategy 须为 A/B/C")
        set_admin_config("basic_info_merge_strategy", val)
    return {"code": 200, "message": "success", "data": {}}


@router.get("/prompt-lab/profiles")
async def admin_list_prompt_profiles(current_user: Optional[dict] = Depends(get_current_user)):
    """
    Prompt Lab profile 列表（sandbox_only）。
    """
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    _assert_admin_sandbox_enabled()
    return {"code": 200, "message": "success", "data": {"items": list_prompt_profiles()}}


@router.post("/prompt-lab/profiles")
async def admin_create_prompt_profile(
    req: PromptProfileCreateRequest,
    current_user: Optional[dict] = Depends(get_current_user),
):
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    _assert_admin_sandbox_enabled()
    try:
        item = create_profile(req.name, req.description or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"code": 200, "message": "success", "data": item}


@router.get("/prompt-lab/profiles/{profile_id}")
async def admin_get_prompt_profile(
    profile_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    _assert_admin_sandbox_enabled()
    item = get_profile(profile_id)
    if not item:
        raise HTTPException(status_code=404, detail="profile 不存在")
    return {"code": 200, "message": "success", "data": item}


@router.get("/prompt-lab/profiles/{profile_id}/export-current")
async def admin_export_prompt_profile_current(
    profile_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    _assert_admin_sandbox_enabled()
    try:
        payload = export_current_profile_payload(profile_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"code": 200, "message": "success", "data": payload}


@router.post("/prompt-lab/profiles/{profile_id}/versions")
async def admin_add_prompt_profile_version(
    profile_id: str,
    req: PromptProfileVersionCreateRequest,
    current_user: Optional[dict] = Depends(get_current_user),
):
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    _assert_admin_sandbox_enabled()
    try:
        ver = add_profile_version(
            profile_id,
            simple_chat_system_prompt_template=req.simple_chat_system_prompt_template,
            extra_goal_hint=req.extra_goal_hint or "",
            created_by=current_user or {},
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"code": 200, "message": "success", "data": ver}


@router.post("/prompt-lab/profiles/{profile_id}/activate-version")
async def admin_activate_prompt_profile_version(
    profile_id: str,
    req: PromptProfileActivateVersionRequest,
    current_user: Optional[dict] = Depends(get_current_user),
):
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    _assert_admin_sandbox_enabled()
    try:
        item = set_current_version(profile_id, req.version_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"code": 200, "message": "success", "data": item}


@router.get("/prompt-lab/bindings")
async def admin_list_prompt_bindings(current_user: Optional[dict] = Depends(get_current_user)):
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    _assert_admin_sandbox_enabled()
    return {"code": 200, "message": "success", "data": {"items": list_prompt_bindings()}}


@router.post("/prompt-lab/bindings")
async def admin_bind_prompt_profile_to_activation(
    req: PromptActivationBindRequest,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    sandbox_only：仅允许绑定到管理员调试工作区激活码（SBX / ADM）。
    """
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    _assert_admin_sandbox_enabled()
    manager = SimpleActivationManager()
    rec = manager.get_activation((req.activation_code or "").strip().upper())
    if not rec:
        raise HTTPException(status_code=404, detail="激活码不存在")
    kind = (getattr(rec, "workspace_kind", None) or "").strip().lower()
    if kind not in {"fork", "resident"} and not bool(getattr(rec, "is_sandbox", False)):
        raise HTTPException(status_code=400, detail="仅支持绑定到管理员调试工作区激活码（SBX/ADM）")
    try:
        result = bind_profile_to_activation(
            req.activation_code,
            req.profile_id,
            actor=current_user or {},
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"code": 200, "message": "success", "data": result}


@router.get("/sandboxes")
async def admin_list_sandboxes(current_user: Optional[dict] = Depends(get_current_user)):
    """列出所有调试沙箱 Fork"""
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    _assert_admin_sandbox_enabled()
    items = list_sandboxes()
    return {
        "code": 200,
        "message": "success",
        "data": {
            "items": items,
            "total": len(items),
            "retention_days": SANDBOX_RETENTION_DAYS,
        },
    }


@router.post("/workspace/ensure")
async def admin_ensure_workspace(current_user: Optional[dict] = Depends(get_current_user)):
    """
    确保当前超级管理员存在常驻调试工作区（长期激活码，独立目录）。
    """
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    _assert_admin_debug_workspace_enabled()
    try:
        rec, created = ensure_admin_resident_workspace(current_user or {})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "code": 200,
        "message": "success",
        "data": {
            "created": created,
            "activation_code": rec.code,
            "session_id": rec.session_id,
            "workspace_kind": getattr(rec, "workspace_kind", None),
            "workspace_root": getattr(rec, "workspace_root", None),
            "status": rec.status,
            "expires_at": rec.expires_at,
        },
    }


@router.post("/sandboxes/fork")
async def admin_fork_sandbox(
    req: SandboxForkRequest,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    从正式激活码复制报告与问卷到 data/simple/sandboxes/{fork_id}/，并生成新激活码（SBX 前缀）。
    禁止从沙箱再次 Fork。
    """
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    _assert_admin_sandbox_enabled()
    try:
        _, summary = fork_activation_from_source(
            req.source_activation_code.strip(),
            current_user or {},
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"code": 200, "message": "success", "data": summary}


@router.delete("/sandboxes")
async def admin_delete_sandbox(
    activation_code: str = Query(..., description="沙箱激活码，如 SBXxxxxxxxx"),
    current_user: Optional[dict] = Depends(get_current_user),
):
    """删除沙箱目录及 activations.json 中的记录"""
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    _assert_admin_sandbox_enabled()
    try:
        ok = delete_sandbox_by_code(activation_code, current_user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="沙箱激活码不存在")
    return {"code": 200, "message": "success", "data": {"deleted": True}}


@router.post("/sandboxes/purge-expired")
async def admin_purge_expired_sandboxes(current_user: Optional[dict] = Depends(get_current_user)):
    """清理已超过 sandbox_expires_at 的沙箱（可挂定时任务调用）"""
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    _assert_admin_sandbox_enabled()
    n = purge_expired_sandboxes()
    return {"code": 200, "message": "success", "data": {"removed": n}}
