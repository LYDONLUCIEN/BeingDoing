"""
导出API
"""
from fastapi import APIRouter, HTTPException, Depends, status, Query, Response
from pydantic import BaseModel
from typing import Optional
from app.api.v1.auth import get_current_user
from app.services.export_service import ExportService
from pathlib import Path
import tempfile

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
