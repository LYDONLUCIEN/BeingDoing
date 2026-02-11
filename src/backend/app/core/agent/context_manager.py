"""
上下文管理器：当 inner_messages 过多时折叠早期消息为一条 summary，控制 token 与等待体验。
"""
from typing import List
from app.core.agent.state import AgentState
from app.core.llmapi.base import LLMMessage


class SimpleContextManager:
    """
    按对话轮数控制上下文：超出阈值时将较早消息折叠为一条 summary，
    不额外调用 LLM，采用简单截断拼接，避免后期突然爆炸。
    """

    def __init__(self, max_messages: int = 40, min_keep_latest: int = 20):
        self.max_messages = max_messages
        self.min_keep_latest = min_keep_latest

    async def maybe_compress(self, state: AgentState) -> AgentState:
        """
        若 inner_messages 超过 max_messages，则将较早部分折叠为一条 summary 消息。
        同时同步更新 messages（用户可见）以保持双轨一致，避免偏离。
        """
        inner = state.get("inner_messages") or []
        if len(inner) <= self.max_messages:
            return state

        keep = self.min_keep_latest
        early = inner[:-keep]
        latest = inner[-keep:]

        if not early:
            return state

        contents = []
        for m in early:
            text = getattr(m, "content", None) or (m if isinstance(m, str) else "")
            if isinstance(text, str) and text.strip():
                contents.append(text)

        if not contents:
            return state

        snippet = "\n".join(contents)
        if len(snippet) > 2000:
            snippet = snippet[:2000] + "\n...[truncated]"

        summary_msg = LLMMessage(
            role="assistant",
            content=f"[Summary of earlier conversation]\n{snippet}",
        )
        new_inner: List[LLMMessage] = [summary_msg] + list(latest)
        state["inner_messages"] = new_inner
        state["messages"] = list(state.get("messages") or [])  # 可选：同步瘦身用户可见消息
        logs = state.get("logs") or []
        logs.append({
            "message": "上下文已压缩（早期对话折叠为 summary）",
            "done": True,
            "meta": {"total_before": len(inner), "total_after": len(new_inner)},
        })
        state["logs"] = logs
        return state


def get_context_manager(
    max_messages: int = 40,
    min_keep_latest: int = 20,
) -> SimpleContextManager:
    return SimpleContextManager(max_messages=max_messages, min_keep_latest=min_keep_latest)
