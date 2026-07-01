"""
辅助工具函数
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict


def generate_uuid() -> str:
    """生成UUID字符串"""
    return str(uuid.uuid4())


def get_current_timestamp() -> datetime:
    """获取当前时间戳"""
    return datetime.now(timezone.utc)


def parse_iso_to_utc(value: str) -> datetime:
    """
    将 ISO8601 字符串解析为 offset-aware UTC datetime。

    统一替代 ``datetime.fromisoformat(s.replace("Z", ...))`` 这类脆弱写法，
    根治 ``can't compare offset-naive and offset-aware datetimes`` 错误。

    兼容历史持久化的三类格式（生产数据零改动）：
    - 带 ``Z`` 后缀：    ``2026-04-25T14:50:55.522014Z``
    - 带显式 offset：   ``2026-04-25T14:50:55.522014+00:00`` / ``+08:00``
    - 不带 tz 的 naive：``2026-04-25T14:50:55.522014`` （历史遗留，按 UTC 解释）

    解析后的 UTC 时刻在三类格式下完全一致，无时间漂移；naive 字符串
    不回写磁盘，纯内存归一化。
    """
    if not value:
        raise ValueError("empty datetime string")
    raw = str(value).strip()
    # Python 3.11+ 的 fromisoformat 已支持 'Z'，这里统一规范化为 '+00:00'
    # 以兼容 3.10 及以下，并保证解析得到 aware datetime。
    normalized = raw.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        # 历史遗留 naive 字符串：统一按 UTC 处理，避免与 aware 混比，
        # 也避免 .timestamp() 把 naive 当本地时区解释。
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def format_response(data: Any, message: str = "success", code: int = 200) -> Dict[str, Any]:
    """格式化API响应"""
    return {
        "code": code,
        "message": message,
        "data": data,
        "timestamp": get_current_timestamp().isoformat(),
    }


def format_error_response(message: str, code: int = 400, details: Any = None) -> Dict[str, Any]:
    """格式化错误响应"""
    response = {"code": code, "message": message, "timestamp": get_current_timestamp().isoformat()}
    if details:
        response["details"] = details
    return response
