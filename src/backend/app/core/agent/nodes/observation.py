"""
观察节点：处理工具结果，决定是否继续；使用 YAML 提示词 + 结构化输出。
思考链写入 inner_messages、context、logs；final_response 由后续 user_agent 转为用户可见 messages。
"""
import json
from app.core.agent.state import AgentState
from app.core.agent.models import ObservationDecision
from app.domain.prompts import get_observation_prompt
from app.core.llmapi import get_default_llm_provider, LLMMessage


def _append_log(state: AgentState, message: str, done: bool = True, meta: dict = None):
    logs = state.get("logs") or []
    logs.append({"message": message, "done": done, **(meta or {})})
    state["logs"] = logs


async def observation_node(state: AgentState) -> AgentState:
    """
    观察节点：分析最后一轮工具结果，更新 should_continue、final_response、summaries、logs。
    若无 tool_results 则直接结束并设 final_response 为空，由 user_agent 统一输出。
    """
    try:
        tool_results = state.get("tool_results") or []
        if not tool_results:
            # 未调用工具（如 action 为 respond/guide 时），不覆盖 final_response，仅结束循环
            state["should_continue"] = False
            _append_log(state, "无工具结果，结束本轮")
            return state

        last_result = tool_results[-1]
        tool_output = last_result.get("output", {})

        llm = get_default_llm_provider()
        system_content = get_observation_prompt({"tool_output": str(tool_output)})
        if not (system_content or "").strip():
            system_content = (
                f"工具结果：{tool_output}\n"
                "请以 JSON 返回：{\"should_continue\": true|false, \"next_action\": \"use_tool\"|\"respond\", "
                "\"analysis\": \"...\", \"response\": \"...\"}"
            )

        messages = [
            LLMMessage(role="system", content=system_content),
            LLMMessage(role="user", content="请分析工具结果并决定下一步行动。"),
        ]
        response = await llm.chat(messages, temperature=0.7)

        try:
            raw = response.content.strip()
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.strip().lower().startswith("json"):
                    raw = raw.strip()[4:]
                raw = raw.strip()
            data = json.loads(raw)
            observation_result = ObservationDecision.model_validate(data)
        except Exception:
            observation_result = ObservationDecision(
                should_continue=False,
                response=response.content or "",
                analysis=response.content,
            )

        obs_dict = observation_result.model_dump()
        context = state.get("context") or {}
        context["observation"] = obs_dict
        state["context"] = context
        state["should_continue"] = observation_result.should_continue
        if not state["should_continue"]:
            state["final_response"] = observation_result.response or response.content

        inner = state.get("inner_messages") or []
        inner.append(LLMMessage(role="assistant", content=response.content))
        state["inner_messages"] = inner

        _append_log(
            state,
            "观察完成",
            meta={"should_continue": observation_result.should_continue, "analysis": (observation_result.analysis or "")[:200]},
        )

        # 按步骤摘要、profile、step_rounds（与原有逻辑一致）
        try:
            current_step = state.get("current_step", "unknown")
            summaries = context.get("summaries", {}) or {}
            prev_summary = summaries.get(current_step, "")
            new_piece = (observation_result.analysis or str(tool_output)).strip()

            if new_piece:
                MAX_SUMMARY_CHARS = 1000
                combined = (prev_summary + "\n" + new_piece).strip() if prev_summary else new_piece
                if len(combined) > MAX_SUMMARY_CHARS:
                    combined = combined[-MAX_SUMMARY_CHARS:]
                summaries[current_step] = combined
                context["summaries"] = summaries

                profile = context.get("profile", {}) or {}
                notes = profile.get("notes", [])
                notes.append({"step": current_step, "analysis": new_piece})
                profile["notes"] = notes

                contradictions = profile.get("contradictions", [])
                if len(notes) >= 2:
                    last = notes[-1]["analysis"]
                    prev = notes[-2]["analysis"]
                    keywords = ["稳定", "自由", "安全", "风险", "变化"]
                    opposite_pairs = [("喜欢", "不喜欢"), ("重要", "不重要")]
                    for kw in keywords:
                        for a, b in opposite_pairs:
                            if kw in last and kw in prev and ((a in last and b in prev) or (a in prev and b in last)):
                                contradictions.append({"step": current_step, "keyword": kw, "a": prev, "b": last})
                                break
                profile["contradictions"] = contradictions
                context["profile"] = profile

                step_rounds = context.get("step_rounds", {}) or {}
                step_rounds[current_step] = step_rounds.get(current_step, 0) + 1
                context["step_rounds"] = step_rounds
                state["iteration_count"] = state.get("iteration_count", 0) + 1
                state["context"] = context
        except Exception:
            pass

        return state
    except Exception as e:
        state["error"] = f"观察节点错误: {str(e)}"
        state["should_continue"] = False
        _append_log(state, f"观察节点错误: {str(e)}", done=False)
        return state
