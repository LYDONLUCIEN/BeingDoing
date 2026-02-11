"""
推理节点：分析用户输入，决定下一步行动（使用 YAML 提示词 + 结构化输出）。
思考链写入 inner_messages 与 logs，不直接写用户可见的 messages。
规则命中时预填 knowledge_snippets（domain 知识规则），保持解耦与知识集中。
"""
import json
from typing import Dict
from app.core.agent.state import AgentState
from app.core.agent.models import ReasoningDecision
from app.core.agent.context_manager import get_context_manager
from app.domain.prompts import get_reasoning_prompt
from app.domain.knowledge_rules import should_force_knowledge_query, get_search_category_for_step
from app.domain.knowledge_config import get_knowledge_config
from app.core.llmapi import get_default_llm_provider, LLMMessage


def _append_log(state: AgentState, message: str, done: bool = True, meta: Dict = None):
    logs = state.get("logs") or []
    logs.append({"message": message, "done": done, **(meta or {})})
    state["logs"] = logs


def _format_search_snippet(category: str, results: list, limit: int = 8) -> str:
    """将检索结果格式化为简短文本，供 reasoning 提示词使用。"""
    lines = []
    for r in results[:limit]:
        item = r.get("item")
        if not item:
            continue
        if category == "values":
            lines.append(f"- {getattr(item, 'name', '')}：{getattr(item, 'definition', '')}")
        elif category == "interests":
            lines.append(f"- {getattr(item, 'name', '')}")
        elif category == "strengths":
            lines.append(f"- {getattr(item, 'name', '')}（优势：{getattr(item, 'strengths', '')}；劣势：{getattr(item, 'weaknesses', '')}）")
    return "\n".join(lines) if lines else "（无匹配）"


async def reasoning_node(state: AgentState) -> AgentState:
    """
    推理节点：根据 current_step、step_summary、user_input 决定 action；
    规则命中时预填 context.knowledge_snippets，再调用 LLM。
    """
    try:
        ctx_manager = get_context_manager()
        state = await ctx_manager.maybe_compress(state)

        context = state.get("context", {}) or {}
        current_step = state.get("current_step", "unknown")
        user_input = state.get("user_input", "")

        # 规则命中时预填知识库片段（domain 知识规则，解耦且集中）
        knowledge_snippets = context.get("knowledge_snippets", "")
        if should_force_knowledge_query(state):
            from app.core.knowledge import KnowledgeLoader, KnowledgeSearcher
            cfg = get_knowledge_config()
            loader = KnowledgeLoader(config=cfg)
            searcher = KnowledgeSearcher(loader=loader)
            category = get_search_category_for_step(current_step)
            if category == "values":
                results = searcher.search_values(user_input, limit=8)
            elif category == "interests":
                results = searcher.search_interests(user_input, limit=8)
            else:
                results = searcher.search_strengths(user_input, limit=8)
            knowledge_snippets = _format_search_snippet(category, results)
            context["knowledge_snippets"] = knowledge_snippets
            state["context"] = context
            _append_log(state, "已按规则预填知识库片段", meta={"category": category})

        llm = get_default_llm_provider()
        summaries = context.get("summaries", {})
        step_summary = summaries.get(current_step, "")
        tools_used = ", ".join(state.get("tools_used") or [])

        system_content = get_reasoning_prompt({
            "current_step": current_step,
            "step_summary": step_summary,
            "user_input": user_input,
            "tools_used": tools_used,
            "knowledge_snippets": knowledge_snippets or "",
        })
        if not (system_content or "").strip():
            system_content = (
                f"当前步骤：{current_step}\n该步骤的阶段性总结：{step_summary}\n"
                f"用户输入：{user_input}\n已使用的工具：{tools_used}\n"
                "请以 JSON 返回：{\"action\": \"use_tool\"|\"respond\"|\"guide\", "
                "\"tool_name\": \"...\", \"tool_input\": {}, \"response\": \"...\", \"reasoning\": \"...\"}"
            )

        messages = [
            LLMMessage(role="system", content=system_content),
            LLMMessage(role="user", content=user_input or "请分析并决定下一步。"),
        ]
        stream_queue = state.get("stream_queue")
        response_content = ""
        full_content = ""

        if stream_queue is not None:
            # 真流式：边生成边推块，按 RESPONSE_END 切分回复与 JSON
            buffer = ""
            pushed_len = 0
            marker = "RESPONSE_END"
            async for chunk in llm.chat_stream(messages, temperature=0.7):
                buffer += chunk
                if marker not in buffer:
                    await stream_queue.put(chunk)
                    pushed_len = len(buffer)
                else:
                    idx = buffer.index(marker)
                    to_push = buffer[pushed_len:idx]
                    if to_push:
                        await stream_queue.put(to_push)
                    json_str = buffer[idx + len(marker) :].strip()
                    full_content = buffer
                    response_content = buffer[:idx].strip()
                    break
            else:
                full_content = buffer
                response_content = buffer.strip()
                json_str = ""
        else:
            response = await llm.chat(messages, temperature=0.7)
            full_content = response.content or ""
            raw = full_content.strip()

        # 结构化解析：优先 RESPONSE_END 格式，否则回退为纯 JSON
        try:
            if stream_queue is not None:
                raw = json_str
            else:
                raw = full_content.strip()
                if "RESPONSE_END" in raw:
                    idx = raw.index("RESPONSE_END")
                    response_content = raw[:idx].strip()
                    raw = raw[idx + len("RESPONSE_END") :].strip()
                else:
                    response_content = ""
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
            if not raw:
                raise ValueError("empty json")
            data = json.loads(raw)
            decision = ReasoningDecision.model_validate(data)
            if getattr(decision, "response", None) is None or (isinstance(data, dict) and not data.get("response")):
                decision.response = response_content or decision.response
        except Exception:
            resp_text = (response_content if stream_queue is not None else full_content) or "请继续描述你的想法。"
            decision = ReasoningDecision(
                action="respond",
                response=resp_text,
                reasoning="LLM 直接生成回答",
            )

        state["context"] = {**(state.get("context") or {}), "reasoning": decision.model_dump()}

        inner = state.get("inner_messages") or []
        inner.append(LLMMessage(role="assistant", content=full_content))
        state["inner_messages"] = inner

        _append_log(state, "推理完成", meta={"action": decision.action, "reasoning": (decision.reasoning or "")[:200]})

        return state
    except Exception as e:
        state["error"] = f"推理节点错误: {str(e)}"
        state["should_continue"] = False
        _append_log(state, f"推理节点错误: {str(e)}", done=False)
        return state
