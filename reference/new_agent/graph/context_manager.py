from typing import List

from langchain_core.messages import BaseMessage, AIMessage

from new_agent.graph.state import AgentState


class SimpleContextManager:
    """
    极简上下文管理器：

    - 按对话轮数（消息长度）控制上下文；
    - 超出阈值时，将较早的消息折叠成一条 summary 消息；
    - 不额外调用 LLM，总结策略采用简单的截断拼接。

    设计目标：在不牺牲用户体验的前提下，持续“瘦身”上下文，避免后期突然爆炸。
    """

    def __init__(self, max_messages: int = 40, min_keep_latest: int = 20):
        self.max_messages = max_messages
        self.min_keep_latest = min_keep_latest

    async def maybe_compress(self, state: AgentState) -> AgentState:
        """
        如果消息太多，则对更早的部分做一次粗略压缩。

        策略：
        - 保留最近 min_keep_latest 条消息原样；
        - 将更早的消息内容简单串联，并放入一条 AIMessage 作为 summary；
        - 确保 messages / inner_messages 同步更新。
        """
        msgs: List[BaseMessage] = state.get("inner_messages", []) or []
        if len(msgs) <= self.max_messages:
            return state

        # 分割为“较早的部分”和“近期部分”
        keep_latest = self.min_keep_latest
        early = msgs[:-keep_latest]
        latest = msgs[-keep_latest:]

        if not early:
            return state

        # 简单拼接早期消息内容
        contents = []
        for m in early:
            try:
                text = m.content if isinstance(m.content, str) else str(m.content)
            except Exception:
                text = ""
            if text:
                contents.append(text)

        if not contents:
            return state

        snippet = "\n".join(contents)
        # 为避免过长，做一次简单截断
        if len(snippet) > 2000:
            snippet = snippet[:2000] + "\n...[truncated]"

        summary = AIMessage(
            content=f"Summary of earlier conversation (for internal use):\n{snippet}",
            name="context_summary",
        )

        new_messages: List[BaseMessage] = [summary] + latest
        state["inner_messages"] = list(new_messages)

        # 对外可见的 messages 也做相同处理，避免两者越来越偏离
        state["messages"] = list(new_messages)

        # 可以在 logs 中记录一次压缩事件
        logs = state.get("logs", []) or []
        logs.append(
            {
                "message": "上下文已压缩（早期对话折叠为 summary）",
                "done": True,
                "meta": {"total_before": len(msgs), "total_after": len(new_messages)},
            }
        )
        state["logs"] = logs

        return state

