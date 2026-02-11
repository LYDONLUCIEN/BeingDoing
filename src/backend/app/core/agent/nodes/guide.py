"""
引导节点：主动引导用户（使用 YAML 提示词，写入 inner_messages 与 logs）。
"""
from app.core.agent.state import AgentState
from app.domain.prompts import get_guide_prompt
from app.core.llmapi import get_default_llm_provider, LLMMessage


def _append_log(state: AgentState, message: str, done: bool = True, meta: dict = None):
    logs = state.get("logs") or []
    logs.append({"message": message, "done": done, **(meta or {})})
    state["logs"] = logs


async def guide_node(state: AgentState) -> AgentState:
    """
    引导节点：根据 current_step、user_input 生成引导语，写 final_response 与 messages。
    """
    try:
        llm = get_default_llm_provider()
        current_step = state.get("current_step", "unknown")
        user_input = state.get("user_input", "")
        system_content = get_guide_prompt({"current_step": current_step, "user_input": user_input})
        if not (system_content or "").strip():
            system_content = (
                f"当前步骤：{current_step}\n用户输入：{user_input}\n"
                "请提供鼓励性引导、具体建议和相关示例，用友好语气回答。"
            )

        messages = [
            LLMMessage(role="system", content=system_content),
            LLMMessage(role="user", content="我需要一些引导和帮助"),
        ]
        response = await llm.chat(messages, temperature=0.8)

        state["final_response"] = response.content
        state["messages"] = state.get("messages") or []
        state["messages"].append(LLMMessage(role="assistant", content=response.content))
        state["should_continue"] = False
        _append_log(state, "引导完成", meta={"current_step": current_step})
        return state
    except Exception as e:
        state["error"] = f"引导节点错误: {str(e)}"
        state["should_continue"] = False
        _append_log(state, f"引导节点错误: {str(e)}", done=False)
        return state
