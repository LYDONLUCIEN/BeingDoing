"""
导出API
"""
from fastapi import APIRouter, HTTPException, Depends, status, Query, Response
from fastapi.responses import JSONResponse, Response as FastResponse
from pydantic import BaseModel
from typing import Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.v1.auth import get_current_user
from app.models.database import get_db
from app.services.export_service import ExportService
from app.utils.report_registry import ReportRegistry, _report_portal_unlocked
from app.utils.simple_activation_manager import (
    SimpleActivationManager,
    get_activation_with_manager,
    get_effective_simple_root,
    get_simple_base_dir,
    get_simple_test_base_dir,
)
from app.utils.super_admin import is_super_admin_user
from app.utils.report_review import (
    REVIEW_STATUS_APPROVED,
    REVIEW_STATUS_NOT_STARTED,
    get_review_status,
    is_not_started,
    is_pending_review,
    pending_review_payload,
    start_review,
)
from pathlib import Path
from urllib.parse import quote
import logging
import tempfile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/export", tags=["导出"])


class ExportRequest(BaseModel):
    """导出请求"""
    user_id: str
    session_id: str
    format: str  # pdf, json, markdown


class StandardResponse(BaseModel):
    """标准响应"""
    code: int = 200
    message: str = "success"
    data: dict


@router.post("/generate", response_model=StandardResponse)
async def generate_export(
    request: ExportRequest,
    current_user: dict = Depends(get_current_user)
):
    """生成导出文件"""
    try:
        # 验证用户权限
        if current_user["user_id"] != request.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权访问此用户的数据"
            )
        
        export_service = ExportService()
        
        # 收集导出数据
        data = await export_service.collect_export_data(
            user_id=request.user_id,
            session_id=request.session_id
        )
        
        # 根据格式导出
        temp_dir = Path(tempfile.gettempdir())
        export_id = f"export_{request.session_id}_{request.format}"
        
        if request.format == "json":
            output_path = export_service.export_to_json(
                data,
                str(temp_dir / f"{export_id}.json")
            )
        elif request.format == "markdown":
            output_path = export_service.export_to_markdown(
                data,
                str(temp_dir / f"{export_id}.md")
            )
        elif request.format == "pdf":
            try:
                output_path = export_service.export_to_pdf(
                    data,
                    str(temp_dir / f"{export_id}.pdf")
                )
            except ImportError:
                # 如果PDF导出失败，降级为Markdown
                output_path = export_service.export_to_markdown(
                    data,
                    str(temp_dir / f"{export_id}.md")
                )
                return StandardResponse(
                    code=200,
                    message="PDF导出需要安装reportlab，已降级为Markdown格式",
                    data={
                        "export_id": export_id,
                        "format": "markdown",
                        "file_path": output_path
                    }
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支持的导出格式: {request.format}"
            )
        
        return StandardResponse(
            code=200,
            message="导出成功",
            data={
                "export_id": export_id,
                "format": request.format,
                "file_path": output_path
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/download")
async def download_export(
    export_id: str = Query(..., description="导出ID"),
    current_user: dict = Depends(get_current_user)
):
    """下载导出文件"""
    try:
        temp_dir = Path(tempfile.gettempdir())
        
        # 尝试查找文件
        for ext in [".json", ".md", ".pdf"]:
            file_path = temp_dir / f"{export_id}{ext}"
            if file_path.exists():
                # 读取文件
                with open(file_path, "rb") as f:
                    content = f.read()
                
                # 确定Content-Type
                content_type_map = {
                    ".json": "application/json",
                    ".md": "text/markdown",
                    ".pdf": "application/pdf"
                }
                content_type = content_type_map.get(ext, "application/octet-stream")
                
                return Response(
                    content=content,
                    media_type=content_type,
                    headers={
                        "Content-Disposition": f'attachment; filename="{export_id}{ext}"'
                    }
                )
        
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="导出文件不存在"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ── PDF 报告导出（异步生成 + 轮询 + 下载）────────────────────

import asyncio
import uuid

# 内存任务表：report_id → 任务状态
# 状态: {"status": "pending"|"done"|"error", "error": str|None, "created_at": float}
_pdf_tasks: Dict[str, dict] = {}


async def _run_pdf_generation(
    report_id: str,
    user_id: str,
    base_dir: Optional[str],
    force: bool,
):
    """后台异步生成报告 markdown（PDF 由下载时即时转换）。"""
    from app.services.report_pdf_service import ReportPdfService, release_generation

    try:
        service = ReportPdfService(base_dir=base_dir)
        # 只生成并缓存 markdown，不在此处生成 PDF bytes
        # 如果缓存命中或生成完毕，markdown 会写入文件
        await service.generate_markdown_only(
            report_id=report_id,
            user_id=user_id,
            force=force,
        )
        _pdf_tasks[report_id] = {
            "status": "done",
            "error": None,
            "created_at": _pdf_tasks.get(report_id, {}).get("created_at", asyncio.get_event_loop().time()),
        }
        logger.info("PDF 报告 markdown 生成完成: report_id=%s", report_id)
    except Exception as e:
        logger.exception("PDF 报告生成失败: report_id=%s", report_id)
        _pdf_tasks[report_id] = {
            "status": "error",
            "error": str(e),
            "created_at": _pdf_tasks.get(report_id, {}).get("created_at", asyncio.get_event_loop().time()),
        }
    finally:
        release_generation(report_id)


def _kick_pdf_generation(
    report_id: str,
    user_id: str,
    base_dir: Optional[str],
    force: bool = False,
) -> None:
    """若未在生成中，启动后台任务预生成报告 markdown（审核期间完成，批复后下载秒出）。

    单轨锁（report_pdf_service._generation_inflight）：三条触发路径统一登记，
    生成中任何路径再触发都直接返回（force 也不并发起第二个任务）。
    """
    from app.services.report_pdf_service import is_generation_inflight, try_acquire_generation

    rid = (report_id or "").strip()
    if not rid:
        return
    existing = _pdf_tasks.get(rid)
    if existing and existing.get("status") == "pending":
        return
    if is_generation_inflight(rid):
        # 另一路径（如批复自动生成）正在生成：状态表标记 pending，本轮复用其结果
        _pdf_tasks[rid] = {
            "status": "pending",
            "error": None,
            "created_at": asyncio.get_event_loop().time(),
        }
        return
    if not try_acquire_generation(rid):
        return
    _pdf_tasks[rid] = {
        "status": "pending",
        "error": None,
        "created_at": asyncio.get_event_loop().time(),
    }
    asyncio.create_task(_run_pdf_generation(rid, user_id, base_dir, force))


def _ensure_review_started(
    report: dict,
    registry: ReportRegistry,
    base_dir: Optional[str],
    user_id: str,
) -> dict:
    """
    审核计时起点（ADR-0009，2026-08-23 修订）：
    not_started 且五阶段均已完成（报告入口解锁）→ 转 pending_review + 固定 24h 时限（2026-09-06 起，原随机 3~24h），
    并立即后台预生成报告 markdown（审核期间报告已在自动生成）。
    主触发点已前移至 rumination v4 终选提交（rumination_v4_routes.submit_final_selection_endpoint），
    此处为存量 not_started 报告与直连 PDF 端点的懒触发兜底。
    幂等：已 pending/approved 或五阶段未完成时不动。
    """
    if not is_not_started(report):
        return report
    if not _report_portal_unlocked(report.get("steps") or {}):
        return report
    start_review(report)
    registry.save_record(report)
    logger.info(
        "报告审核计时开始: report_id=%s review_deadline=%s",
        report.get("report_id"),
        report.get("review_deadline"),
    )
    _kick_pdf_generation(report.get("report_id") or "", user_id, base_dir)
    return report


@router.get("/my-report-id")
async def get_my_report_id(
    activation_code: str = Query(..., description="激活码"),
    current_user: dict = Depends(get_current_user),
):
    """用户端：通过 activation_code 获取自己的 report_id（含审核状态）。"""
    user_id = current_user.get("user_id") or ""
    code = activation_code.strip().upper()
    _mgr, rec = get_activation_with_manager(code)
    if not rec:
        raise HTTPException(status_code=404, detail="激活码不存在")
    root = get_effective_simple_root(rec)
    registry = ReportRegistry(base_dir=str(root))
    report = registry.get_by_activation_user(code, user_id)
    if not report:
        raise HTTPException(status_code=404, detail="未找到您的报告")
    # 进入报告页即触发审核计时起点（五阶段已完成时），并后台预生成报告
    report = _ensure_review_started(report, registry, str(root), user_id)
    from app.services.report_recheck_service import get_recheck_status

    data = {
        "report_id": report.get("report_id"),
        "review_status": get_review_status(report),
        # 复核进行中（pending/regenerating/pending_confirm）时前端展示提示条并禁用申请入口
        "recheck_status": get_recheck_status(report),
    }
    if is_pending_review(report):
        data["review_deadline"] = report.get("review_deadline")
    return data


@router.get("/my-reports")
async def list_my_reports(
    current_user: dict = Depends(get_current_user),
):
    """用户端：列出当前用户（作为激活人）名下的全部报告。

    纯只读：不触发审核计时（不调 _ensure_review_started），也不创建报告（不调 ensure_report）。
    review_status 应用祖父豁免口径（存量缺字段视为 approved）。
    """
    user_id = (current_user.get("user_id") or "").strip()
    email = (current_user.get("email") or "").strip()
    if not user_id and not email:
        return {"items": []}

    # 合并生产 + 测试/沙箱索引（取码逻辑与 simple-auth/my-codes 一致）
    merged: Dict[str, object] = {}  # code -> ActivationRecord
    for base_dir in (get_simple_base_dir(), get_simple_test_base_dir()):
        mgr = SimpleActivationManager(base_dir=str(base_dir))
        for code, rec in mgr.list_activations().items():
            norm = (code or "").strip().upper()
            if norm:
                merged[norm] = rec

    items = []
    seen: set = set()
    for _norm, rec in merged.items():
        owner_uid = (getattr(rec, "owner_user_id", None) or "").strip()
        owner_email = (getattr(rec, "owner_email", None) or "").strip()
        is_mine = (user_id and owner_uid == user_id) or (email and owner_email == email)
        if not is_mine:
            continue
        try:
            root = get_effective_simple_root(rec)
            registry = ReportRegistry(base_dir=str(root))
            report = registry.get_by_activation_user(rec.code, user_id) if user_id else None
            if not report and email:
                report = registry.get_by_activation_user(rec.code, email)
        except Exception:
            logger.exception("查询报告失败: code=%s", rec.code)
            continue
        if not report:
            continue
        report_id = (report.get("report_id") or "").strip()
        if not report_id or report_id in seen:
            continue
        seen.add(report_id)
        items.append({
            "report_id": report_id,
            "activation_code": report.get("activation_code") or rec.code,
            "review_status": get_review_status(report),
            "review_deadline": report.get("review_deadline"),
            "created_at": report.get("created_at"),
            "code_type": getattr(rec, "code_type", None),
        })

    items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return {"items": items}


def _verify_report_access(
    report_id: str, current_user: dict, activation_code: Optional[str]
) -> tuple:
    """
    校验权限，返回 (base_dir, user_id)。
    admin 可访问任意 report；用户必须通过 activation_code 访问自己的。
    """
    user_id = current_user.get("user_id") or ""
    is_admin = is_super_admin_user(current_user)

    if not is_admin:
        code = (activation_code or "").strip().upper()
        if not code:
            raise HTTPException(status_code=403, detail="缺少 activation_code 参数")
        _mgr, rec = get_activation_with_manager(code)
        if not rec:
            raise HTTPException(status_code=404, detail="激活码不存在")
        root = get_effective_simple_root(rec)
        registry = ReportRegistry(base_dir=str(root))
        report = registry.get_by_activation_user(code, user_id)
        if not report or report.get("report_id") != report_id:
            raise HTTPException(status_code=403, detail="无权访问此报告")
        return str(root), user_id
    else:
        registry = ReportRegistry()
        report = registry.get_report_by_id(report_id)
        if not report:
            raise HTTPException(status_code=404, detail="报告不存在")
        return None, user_id


def _review_block_payload(
    report_id: str, base_dir: Optional[str], current_user: dict
) -> Optional[dict]:
    """
    报告阻塞式审核（ADR-0009）：非 admin 用户访问 pending_review 报告时，
    返回阻塞 payload（HTTP 200，由前端展示「审核中」）；否则返回 None 放行。
    admin 不受阻塞（审核需要查看报告内容）。存量无审核字段视为 approved。
    """
    if is_super_admin_user(current_user):
        return None
    registry = ReportRegistry(base_dir=base_dir) if base_dir else ReportRegistry()
    report = registry.get_report_by_id(report_id)
    if not report:
        return None
    if is_not_started(report):
        # 五阶段完成则即刻开始审核计时（直连 PDF 端点、未经过 my-report-id 的兜底路径）
        report = _ensure_review_started(
            report, registry, base_dir, current_user.get("user_id") or ""
        )
        if is_not_started(report):
            # 五阶段未完成：阻塞，提示先完成探索流程
            return {"review_status": REVIEW_STATUS_NOT_STARTED}
    if not is_pending_review(report):
        return None
    return pending_review_payload(report)


@router.post("/report-pdf/{report_id}")
async def trigger_report_pdf(
    report_id: str,
    force: bool = Query(False, description="强制重新生成，跳过缓存"),
    activation_code: Optional[str] = Query(None, description="用户端需传入激活码"),
    current_user: dict = Depends(get_current_user),
):
    """
    触发 PDF 报告生成（异步）。

    - 如果缓存命中（已有 markdown），直接返回 status=ready
    - 如果正在生成中，返回 status=generating
    - 否则启动后台任务，返回 status=generating
    """
    from app.services.report_pdf_service import ReportPdfService

    base_dir, user_id = _verify_report_access(report_id, current_user, activation_code)

    # 完成度门控（2026-08-07）：五阶段未完成一律 409，admin 也不例外。
    # admin 的豁免仅限审核状态阻塞（_review_block_payload，审核需要查看报告内容），
    # 不豁免「流程未完成」——未完成的报告生成出来只有占位文案，无意义且易误导。
    registry = ReportRegistry(base_dir=base_dir) if base_dir else ReportRegistry()
    report = registry.get_report_by_id(report_id)
    if not _report_portal_unlocked((report or {}).get("steps") or {}):
        raise HTTPException(
            status_code=409,
            detail="用户尚未完成全部探索阶段，暂不可生成报告 PDF",
        )

    # 审核阻塞：pending_review 时不触发生成，HTTP 200 返回审核中状态
    blocked = _review_block_payload(report_id, base_dir, current_user)
    if blocked is not None:
        return {"report_id": report_id, "status": blocked["review_status"], **blocked}

    # force 重新生成：用户侧已于 2026-08-18 下线（改走复核体系），
    # 后端 force 能力保留，供 admin/运维脚本调用（不计数、不限次）。

    # 检查缓存是否已有 markdown
    service = ReportPdfService(base_dir=base_dir)
    has_cache = service.has_cached_markdown(report_id) and not force

    if has_cache:
        return {"report_id": report_id, "status": "ready", "review_status": REVIEW_STATUS_APPROVED}

    # 检查是否正在生成（单轨锁：含审核预生成/批复自动生成路径）；若上次失败则重新触发
    from app.services.report_pdf_service import is_generation_inflight

    existing = _pdf_tasks.get(report_id)
    if (existing and existing.get("status") == "pending") or is_generation_inflight(report_id):
        return {"report_id": report_id, "status": "generating", "review_status": REVIEW_STATUS_APPROVED}

    _kick_pdf_generation(report_id, user_id, base_dir, force)

    return {"report_id": report_id, "status": "generating", "review_status": REVIEW_STATUS_APPROVED}


@router.get("/report-pdf-status/{report_id}")
async def get_report_pdf_status(
    report_id: str,
    activation_code: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """轮询报告生成状态。"""
    # 权限校验
    base_dir, _ = _verify_report_access(report_id, current_user, activation_code)

    # 审核阻塞：pending_review 时 HTTP 200 返回审核中状态
    blocked = _review_block_payload(report_id, base_dir, current_user)
    if blocked is not None:
        return {"report_id": report_id, "status": blocked["review_status"], **blocked}

    from app.services.report_pdf_service import (
        ReportPdfService,
        is_generation_inflight,
    )

    task = _pdf_tasks.get(report_id)
    # pending 以单轨锁为准：任务表 pending 但锁已释放 = 另一路径的任务已结束
    # （批复路径不写本表），此时落到缓存检查，避免状态永远卡在 generating
    if task and task.get("status") == "pending" and is_generation_inflight(report_id):
        return {
            "report_id": report_id,
            "status": "generating",
            "review_status": REVIEW_STATUS_APPROVED,
        }
    if task and task.get("status") == "error":
        return {
            "report_id": report_id,
            "status": "error",
            "error": task.get("error", "生成失败"),
            "review_status": REVIEW_STATUS_APPROVED,
        }

    # done / 无任务记录 / 残留 pending：以缓存为准
    service = ReportPdfService(base_dir=base_dir)
    if service.has_cached_markdown(report_id):
        return {
            "report_id": report_id,
            "status": "ready",
            "review_status": REVIEW_STATUS_APPROVED,
        }
    return {
        "report_id": report_id,
        "status": "none",
        "review_status": REVIEW_STATUS_APPROVED,
    }


@router.get("/report-pdf-download/{report_id}")
async def download_report_pdf(
    report_id: str,
    activation_code: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """
    下载已生成的 PDF 报告。
    如果 markdown 缓存不存在，返回 409。
    """
    from app.services.report_pdf_service import ReportPdfService

    base_dir, user_id = _verify_report_access(report_id, current_user, activation_code)

    # 审核阻塞：pending_review 时不返回 PDF，HTTP 200 返回审核中状态
    blocked = _review_block_payload(report_id, base_dir, current_user)
    if blocked is not None:
        return JSONResponse(
            status_code=200,
            content={"code": 200, "message": "报告审核中", "data": {"report_id": report_id, **blocked}},
        )

    service = ReportPdfService(base_dir=base_dir)

    if not service.has_cached_markdown(report_id):
        raise HTTPException(status_code=409, detail="报告尚未生成，请先触发生成")

    # 从缓存读 markdown，转 PDF
    markdown_text = service.load_cached_markdown(report_id)
    if not markdown_text:
        raise HTTPException(status_code=409, detail="报告缓存已失效，请重新生成")

    try:
        pdf_bytes = service.markdown_to_pdf_bytes(markdown_text, report_id=report_id)
    except Exception as e:
        logger.exception("PDF 转换失败: report_id=%s", report_id)
        raise HTTPException(status_code=500, detail=f"PDF 转换失败: {e}")

    # 文件名
    registry = ReportRegistry(base_dir=base_dir) if base_dir else ReportRegistry()
    report = registry.get_report_by_id(report_id) or {}
    filename = service.get_report_filename(report)
    filename_encoded = quote(filename)

    return FastResponse(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename_encoded}",
        },
    )


# ── 报告复核申请（2026-08-18，tasks/report-review-plan.md）──────


class RecheckRequest(BaseModel):
    """复核申请：分类必选 + 描述选填"""
    category: str  # content_issue 内容有问题 / download_issue 下载或打开失败
    description: Optional[str] = None


@router.post("/report-recheck/{report_id}")
async def submit_report_recheck(
    report_id: str,
    payload: RecheckRequest,
    activation_code: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """用户申请报告复核。

    - content_issue → 建复核单（record.json 权威数据源）+ 双写 Feedback 工单；
      每报告每天限 1 次，有未关闭复核单时 409
    - download_issue → 只进 Feedback 通道（与右侧「反馈 bug」完全同流程同结果），
      不建复核单、不出现重新生成按钮
    """
    from app.services import feedback_service, report_recheck_service

    category = (payload.category or "").strip()
    if category not in ("content_issue", "download_issue"):
        raise HTTPException(status_code=400, detail="无效的复核分类")

    base_dir, user_id = _verify_report_access(report_id, current_user, activation_code)
    user_email = (current_user.get("email") or "").strip()
    registry = ReportRegistry(base_dir=base_dir) if base_dir else ReportRegistry()
    report = registry.get_report_by_id(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    code = (activation_code or report.get("activation_code") or "").strip().upper()
    description = (payload.description or "").strip()
    if len(description) > 2000:
        raise HTTPException(status_code=400, detail="描述最长 2000 字")

    if category == "download_issue":
        # 与「反馈 bug」完全同流程：auto_ack + admin 通知 + SLA，不建复核单
        await feedback_service.create_feedback(
            db=db,
            user_id=user_id,
            user_email=user_email,
            type_="bug",
            content=report_recheck_service.compose_download_issue_feedback_content(
                report_id, code, description
            ),
            attachment_ids=[],
        )
        await db.commit()
        return {"report_id": report_id, "path": "feedback"}

    try:
        entry = await report_recheck_service.submit_recheck(
            db,
            registry,
            report,
            user_id=user_id,
            user_email=user_email,
            description=description,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    await db.commit()
    return {"report_id": report_id, "path": "recheck", "recheck": entry}
