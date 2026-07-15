"""
导出API
"""
from fastapi import APIRouter, HTTPException, Depends, status, Query, Response
from fastapi.responses import Response as FastResponse
from pydantic import BaseModel
from typing import Optional
from app.api.v1.auth import get_current_user
from app.services.export_service import ExportService
from app.utils.report_registry import ReportRegistry
from app.utils.simple_activation_manager import (
    get_activation_with_manager,
    get_effective_simple_root,
)
from app.utils.super_admin import is_super_admin_user
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


# ── PDF 报告导出 ────────────────────────────────────────────


@router.get("/my-report-id")
async def get_my_report_id(
    activation_code: str = Query(..., description="激活码"),
    current_user: dict = Depends(get_current_user),
):
    """用户端：通过 activation_code 获取自己的 report_id。"""
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
    return {"report_id": report.get("report_id")}


@router.post("/report-pdf/{report_id}")
async def generate_report_pdf(
    report_id: str,
    force: bool = Query(False, description="强制重新生成，跳过缓存"),
    activation_code: Optional[str] = Query(None, description="用户端需传入自己的激活码用于权限校验"),
    current_user: dict = Depends(get_current_user),
):
    """
    生成并下载 PDF 报告。

    权限：
    - admin（super_admin）可下载任意 report_id
    - 普通用户必须传入 activation_code，且 report 必须属于该用户
    """
    from app.services.report_pdf_service import ReportPdfService

    user_id = current_user.get("user_id") or ""
    is_admin = is_super_admin_user(current_user)

    # 权限校验
    if not is_admin:
        # 普通用户：通过 activation_code 找到自己的 report 并验证
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
            raise HTTPException(status_code=403, detail="无权下载此报告")
        base_dir = str(root)
    else:
        # admin
        registry = ReportRegistry()
        report = registry.get_report_by_id(report_id)
        if not report:
            raise HTTPException(status_code=404, detail="报告不存在")
        base_dir = None  # 用默认 base_dir

    # 生成 PDF
    try:
        service = ReportPdfService(base_dir=base_dir)
        pdf_bytes = await service.generate_pdf(
            report_id=report_id,
            user_id=user_id,
            force=force,
        )
    except Exception as e:
        logger.exception("PDF 生成失败: report_id=%s", report_id)
        raise HTTPException(status_code=500, detail=f"PDF 生成失败: {e}")

    # 文件名
    filename = service.get_report_filename(report)
    # RFC 5987 编码中文文件名
    filename_encoded = quote(filename)

    return FastResponse(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename_encoded}",
        },
    )
