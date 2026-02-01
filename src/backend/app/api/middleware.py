"""
API中间件
"""
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.config.settings import settings
from app.config.audio_config import AudioConfig
from app.utils.helpers import format_error_response


class AudioModeMiddleware(BaseHTTPMiddleware):
    """语音功能中间件 - 检查AUDIO_MODE"""
    
    async def dispatch(self, request: Request, call_next):
        # 检查是否是语音相关接口
        if request.url.path.startswith("/api/v1/audio"):
            if not AudioConfig.is_audio_enabled():
                return JSONResponse(
                    status_code=403,
                    content=format_error_response(
                        "Audio mode is disabled",
                        code=403
                    )
                )
        
        response = await call_next(request)
        return response


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """错误处理中间件"""
    
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except HTTPException as e:
            return JSONResponse(
                status_code=e.status_code,
                content=format_error_response(
                    e.detail,
                    code=e.status_code
                )
            )
        except Exception as e:
            if settings.DEBUG:
                # 开发环境返回详细错误
                return JSONResponse(
                    status_code=500,
                    content=format_error_response(
                        str(e),
                        code=500,
                        details={"type": type(e).__name__}
                    )
                )
            else:
                # 生产环境返回通用错误
                return JSONResponse(
                    status_code=500,
                    content=format_error_response(
                        "Internal server error",
                        code=500
                    )
                )
