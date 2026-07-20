"""
导出API
"""
from fastapi import APIRouter, HTTPException, Depends, status, Query, Response
from fastapi.responses import JSONResponse, Response as FastResponse
from pydantic import BaseModel
from typing import Dict, Optional
from app.api.v1.auth import get_current_user
from app.services.export_service import ExportService
from app.utils.report_registry import ReportRegistry
from app.utils.simple_activation_manager import (
    get_activation_with_manager,
    get_effective_simple_root,
)
from app.utils.super_admin import is_super_admin_user
from app.utils.report_review import (
    REVIEW_STATUS_APPROVED,
    get_review_status,
    is_pending_review,
    pending_review_payload,
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


async def _run_pdf_generation(report_id: str, user_id: str, base_dir: Optional[str], force: bool):
    """后台异步生成报告 markdown（PDF 由下载时即时转换）。"""
    from app.services.report_pdf_service import ReportPdfService

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
    data = {"report_id": report.get("report_id"), "review_status": get_review_status(report)}
    if is_pending_review(report):
        data["review_deadline"] = report.get("review_deadline")
    return data


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
    if not report or not is_pending_review(report):
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

    # 审核阻塞：pending_review 时不触发生成，HTTP 200 返回审核中状态
    blocked = _review_block_payload(report_id, base_dir, current_user)
    if blocked is not None:
        return {"report_id": report_id, "status": "pending_review", **blocked}

    # 检查缓存是否已有 markdown
    service = ReportPdfService(base_dir=base_dir)
    has_cache = service.has_cached_markdown(report_id) and not force

    if has_cache:
        return {"report_id": report_id, "status": "ready", "review_status": REVIEW_STATUS_APPROVED}

    # 检查是否正在生成
    existing = _pdf_tasks.get(report_id)
    if existing and existing.get("status") == "pending":
        return {"report_id": report_id, "status": "generating", "review_status": REVIEW_STATUS_APPROVED}

    # 如果上次失败，重新触发
    # 启动后台任务
    _pdf_tasks[report_id] = {
        "status": "pending",
        "error": None,
        "created_at": asyncio.get_event_loop().time(),
    }
    asyncio.create_task(
        _run_pdf_generation(report_id, user_id, base_dir, force)
    )

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
        return {"report_id": report_id, "status": "pending_review", **blocked}

    task = _pdf_tasks.get(report_id)
    if not task:
        # 没有任务记录，检查是否有缓存
        from app.services.report_pdf_service import ReportPdfService

        service = ReportPdfService(base_dir=base_dir)
        if service.has_cached_markdown(report_id):
            return {"report_id": report_id, "status": "ready", "review_status": REVIEW_STATUS_APPROVED}
        return {"report_id": report_id, "status": "none", "review_status": REVIEW_STATUS_APPROVED}

    status = task.get("status")
    if status == "done":
        return {"report_id": report_id, "status": "ready", "review_status": REVIEW_STATUS_APPROVED}
    elif status == "error":
        return {
            "report_id": report_id,
            "status": "error",
            "error": task.get("error", "生成失败"),
            "review_status": REVIEW_STATUS_APPROVED,
        }
    else:
        return {"report_id": report_id, "status": "generating", "review_status": REVIEW_STATUS_APPROVED}


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
        pdf_bytes = service.markdown_to_pdf_bytes(markdown_text)
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
