"""
用户侧输出节点：将思考链结果（final_response）转为对用户可见的 messages。
前端用户 Agent 只消费思考 Agent 的输出，不参与推理；此处统一写入 messages 与可选 logs。
"""
from app.core.agent.state import AgentState
from app.core.llmapi.base import LLMMessage
from app.domain.steps import EXPLORATION_STEP_IDS


def _append_log(state: AgentState, message: str, done: bool = True, meta: dict = None):
    logs = state.get("logs") or []
    logs.append({"message": message, "done": done, **(meta or {})})
    state["logs"] = logs


async def user_agent_node(state: AgentState) -> AgentState:
    """
    用户 Agent 节点：读取思考链的 final_response（或 error），写入对用户可见的 messages。
    保证「用户每次拿到的都是思考 Agent 后端的结果」。
    """
    messages = state.get("messages") or []
    final_response = state.get("final_response")
    error = state.get("error")

    if error:
        content = f"抱歉，处理时遇到问题：{error}"
    elif final_response:
        content = final_response
    else:
        content = "抱歉，我暂时无法给出回复，请再试一次。"

    messages.append(LLMMessage(role="assistant", content=content))
    state["messages"] = messages

    # 为前端准备答题卡元信息：区分 AI 分析与用户回答
    try:
        if final_response:
            current_step = state.get("current_step", "")
            user_input = state.get("user_input") or ""
            # 仅在探索类步骤、循环已结束且用户回答有一定长度时，认为有生成答题卡的意义
            if current_step not in EXPLORATION_STEP_IDS:
                raise ValueError("non-exploration step, skip answer_card")
            if state.get("should_continue", True):
                raise ValueError("loop not finished, skip answer_card")
            if len((user_input or "").strip()) < 20:
                raise ValueError("user answer too short for answer_card")
            state["answer_card"] = {
                "question_step": current_step,
                "ai_analysis": final_response,
                "user_answer": user_input,
            }
    except Exception:
        # 不影响主流程
        pass

    _append_log(state, "已向用户输出回复", meta={"has_error": bool(error)})
    return state
