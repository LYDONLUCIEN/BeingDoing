"""
行动节点：根据推理结果调用工具或设置 final_response。
思考链结果来自 context.reasoning（ReasoningDecision），不直接写用户可见 messages。
"""
from app.core.agent.state import AgentState
from app.core.agent.tools import ToolRegistry


def _append_log(state: AgentState, message: str, done: bool = True, meta: dict = None):
    logs = state.get("logs") or []
    logs.append({"message": message, "done": done, **(meta or {})})
    state["logs"] = logs


async def action_node(state: AgentState) -> AgentState:
    """
    行动节点：根据 context.reasoning（结构化）调用工具或写 final_response。
    """
    try:
        reasoning = state.get("context", {}).get("reasoning", {}) or {}
        action = reasoning.get("action", "respond")

        if action == "use_tool":
            tool_name = reasoning.get("tool_name")
            tool_input = reasoning.get("tool_input") or {}

            if not tool_name:
                state["error"] = "工具名称未指定"
                state["should_continue"] = False
                _append_log(state, "行动失败：未指定工具名", done=False)
                return state

            tool = ToolRegistry.get_tool(tool_name)
            if not tool:
                state["error"] = f"工具不存在: {tool_name}"
                state["should_continue"] = False
                _append_log(state, f"行动失败：工具不存在 {tool_name}", done=False)
                return state

            tool_result = await tool.execute(tool_input, state)

            state["tools_used"] = state.get("tools_used") or []
            state["tools_used"].append(tool_name)
            state["tool_results"] = state.get("tool_results") or []
            state["tool_results"].append({
                "tool": tool_name,
                "input": tool_input,
                "output": tool_result,
            })
            state["context"] = state.get("context") or {}
            state["context"]["last_tool_result"] = tool_result

            _append_log(state, f"已调用工具: {tool_name}", meta={"tool": tool_name})

        elif action in ("respond", "guide"):
            response = reasoning.get("response", "")
            state["final_response"] = response
            state["should_continue"] = False
            _append_log(state, "已生成回答", meta={"action": action})

        return state
    except Exception as e:
        state["error"] = f"行动节点错误: {str(e)}"
        state["should_continue"] = False
        _append_log(state, f"行动节点错误: {str(e)}", done=False)
        return state
