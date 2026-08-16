"""
LLM 用量归属上下文（contextvar）

在请求/任务入口设置一次，provider 层记录用量时自动带出归属信息。
contextvars 会随 asyncio task 创建时拷贝传播，因此：
- FastAPI 请求内（含 SSE 流式生成器）设置的上下文对流式 LLM 调用有效
- 请求内 asyncio.create_task 派生的后台任务继承创建时刻的上下文
- 独立后台 job（如报告生成）需在 job 内显式 set_llm_usage_context

每个请求运行在独立 task，不会串上下文；后台 job 结束建议 reset_llm_usage_context。
"""

from contextvars import ContextVar, Token
from typing import Optional

_usage_context: ContextVar[dict] = ContextVar("llm_usage_context", default={})


def set_llm_usage_context(
    *,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    activation_code: Optional[str] = None,
    scene: Optional[str] = None,
) -> Token:
    """设置当前上下文的 LLM 用量归属，返回 Token 供 reset 使用"""
    return _usage_context.set(
        {
            "user_id": user_id,
            "session_id": session_id,
            "activation_code": activation_code,
            "scene": scene or "unknown",
        }
    )


def get_llm_usage_context() -> dict:
    return _usage_context.get()


def reset_llm_usage_context(token: Token) -> None:
    _usage_context.reset(token)
