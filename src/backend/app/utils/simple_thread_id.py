"""
Simple 模式对话 thread / 会话 ID 由服务端签发时的工具函数。

前端若改为「无 id 时请求后端分配」，可避免弱随机 t_ 前缀冲突。
保留 `t_` 前缀以便与现有按 thread 分文件的命名习惯兼容。
"""
from __future__ import annotations

import uuid


def allocate_simple_chat_thread_id() -> str:
    """生成全局唯一的 thread 会话 ID（UUID，带 t_ 前缀）。"""
    return f"t_{uuid.uuid4().hex}"
