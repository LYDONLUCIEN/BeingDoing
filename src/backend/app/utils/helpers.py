"""
辅助工具函数
"""
from typing import Any, Dict
from datetime import datetime
import uuid


def generate_uuid() -> str:
    """生成UUID字符串"""
    return str(uuid.uuid4())


def get_current_timestamp() -> datetime:
    """获取当前时间戳"""
    return datetime.utcnow()


def format_response(data: Any, message: str = "success", code: int = 200) -> Dict[str, Any]:
    """格式化API响应"""
    return {
        "code": code,
        "message": message,
        "data": data,
        "timestamp": get_current_timestamp().isoformat()
    }


def format_error_response(message: str, code: int = 400, details: Any = None) -> Dict[str, Any]:
    """格式化错误响应"""
    response = {
        "code": code,
        "message": message,
        "timestamp": get_current_timestamp().isoformat()
    }
    if details:
        response["details"] = details
    return response
