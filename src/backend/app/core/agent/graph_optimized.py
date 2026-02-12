"""
LangGraph 状态图：思考链（reasoning → action → observation）循环，
结束后可选进入 user_agent 节点，将思考结果转为用户可见 messages。

优化特性：
- 集成 Graph 缓存（避免每次编译）
- 集成完整上下文加载（inner_messages + context 持久化）
- 支持新的增强对话管理（all_flow + note）
"""
from typing import Optional, Any, Dict, List
from datetime import datetime
from langgraph.graph import StateGraph, END
from app.core.llmapi.base import LLMMessage
from app.core.agent.state import AgentState
from app.core.agent.config import AgentRunConfig, DEFAULT_RUN_CONFIG
from app.core.agent.nodes import (
    action_node,
    observation_node,
    guide_node,
)
# v2.4: 切换到新的reasoning节点（支持逐题引导）
from app.core.agent.nodes.reasoning_v2 import reasoning_node
from app.core.agent.nodes.user_agent import user_agent_node
from app.core.agent.tools import ToolRegistry, SearchTool, GuideTool, ExampleTool
from app.core.agent.graph_cache import get_or_create_graph
from app.utils.enhanced_conversation_manager import EnhancedConversationFileManager


def make_should_continue(max_iterations: int = 10):
    """供测试或外部构造条件边使用。"""
    def should_continue(state: AgentState) -> str:
        if state.get("error"):
            return "end"
        if not state.get("should_continue", False):
            return "end"
        if state.get("iteration_count", 0) >= max_iterations:
            return "end"
        context = state.get("context", {}) or {}
        current_step = state.get("current_step", "unknown")
        step_rounds = context.get("step_rounds", {})
        step_round_count = step_rounds.get(current_step, 0)
        max_rounds_per_step = context.get("limits", {}).get("max_rounds_per_step", 5)
        if step_round_count >= max_rounds_per_step:
            return "end"
        return "continue"
    return should_continue


def create_agent_graph(config: Optional[AgentRunConfig] = None):
    """
    创建智能体状态图（可配置）。

    优化特性：
    - 使用 Graph 缓存（避免每次编译）
    - 支持增强对话管理（all_flow + note）

    - config.use_user_agent_node=True（默认）：observation 结束 → user_agent → END，用户可见 messages 由 user_agent 写入
    - config.use_user_agent_node=False：observation 结束 → END（仅思考链，适合调试或流式后续处理）
    """
    config = config or DEFAULT_RUN_CONFIG
    should_continue = make_should_continue(config.max_iterations)

    ToolRegistry.register(SearchTool())
    ToolRegistry.register(GuideTool())
    ToolRegistry.register(ExampleTool())

    if StateGraph is None:
        raise ImportError("LangGraph未安装，请运行: pip install langgraph")

    graph = StateGraph(AgentState)
    graph.add_node("reasoning", reasoning_node)
    graph.add_node("action", action_node)
    graph.add_node("observation", observation_node)
    graph.add_node("guide", guide_node)
    graph.add_node("user_agent", user_agent_node)

    graph.set_entry_point("reasoning")
    graph.add_edge("reasoning", "action")
    graph.add_edge("action", "observation")

    if config.use_user_agent_node:
        graph.add_conditional_edges(
            "observation",
            should_continue,
            {
                "continue": "reasoning",
                "end": "user_agent",
            }
        )
        graph.add_edge("user_agent", END)
    else:
        graph.add_conditional_edges(
            "observation",
            should_continue,
            {
                "continue": "reasoning",
                "end": END,
            }
        )

    return graph.compile()


async def create_initial_state(
    user_input: str,
    current_step: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    stream_queue: Optional[Any] = None,
    question_progress: Optional[Dict] = None,
    force_regenerate_card: bool = False,
    # ===== 新增参数：支持完整上下文加载 =====
    load_full_context: bool = True,
    enhanced_manager: Optional[EnhancedConversationFileManager] = None,
) -> AgentState:
    """
    创建初始状态（含双轨 messages / inner_messages 与 logs）。

    优化特性：
    - 加载完整上下文到 inner_messages（AI 思考历史）
    - 从持久化存储恢复 context（summaries, profile 等）
    - 支持 note.json 的结论性内容

    Args:
        user_input: 用户输入
        current_step: 当前步骤
        user_id: 用户 ID
        session_id: 会话 ID
        stream_queue: SSE 流式队列
        question_progress: 从持久化存储加载的题目进度
        force_regenerate_card: 强制重新生成答题卡
        load_full_context: 是否加载完整上下文（默认 True）
        enhanced_manager: 增强的对话管理器（可选）

    Returns:
        初始化的 AgentState
    """
    from app.core.llmapi.base import LLMMessage
    from app.domain import DEFAULT_CURRENT_STEP
    from app.config.settings import settings

    if current_step is None:
        current_step = DEFAULT_CURRENT_STEP

    # 初始化基础状态
    state: AgentState = AgentState(
        messages=[],               # 用户可见消息（前端管理）
        inner_messages=[],      # 内部思考消息（将被填充）
        logs=[],
        context={},
        current_step=current_step,
        tools_used=[],
        tool_results=[],
        user_input=user_input,
        user_id=user_id,
        session_id=session_id,
        iteration_count=0,
        should_continue=True,
        final_response=None,
        error=None,
    )

    # ===== 优化：加载完整上下文到 inner_messages =====
    if load_full_context and session_id and settings.FULL_CONTEXT_ENABLED:
        conv_manager = enhanced_manager or EnhancedConversationFileManager()
        context_data = await conv_manager.get_compressed_context(
            session_id=session_id,
            max_rounds=settings.CONTEXT_COMPRESS_AFTER_ROUNDS,
            keep_latest=settings.CONTEXT_KEEP_LATEST_MESSAGES,
            include_all_flow=True,
        )

        # 将压缩后的上下文转换为 inner_messages
        loaded_messages: List[LLMMessage] = []
        for msg in context_data.get("messages", []):
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ["user", "assistant", "system"]:
                loaded_messages.append(LLMMessage(role=role, content=content))

        # 添加 AI 思考过程（来自 all_flow）
        for flow_msg in context_data.get("all_flow_messages", []):
            loaded_messages.append(LLMMessage(
                role="system",
                content=f"[AI 思考] {flow_msg.get('content', '')}"
            ))

        if loaded_messages:
            state["inner_messages"] = loaded_messages

        # 恢复 context 中的持久化数据
        # 这些数据在 agent 执行过程中会被更新和保存
        state["context"]["_loaded_session_id"] = session_id
        state["context"]["_context_round_count"] = context_data.get("round_count", 0)

    # ===== 原有逻辑 =====
    if stream_queue is not None:
        state["stream_queue"] = stream_queue
    if question_progress is not None:
        state["question_progress"] = question_progress
    if force_regenerate_card:
        state["force_regenerate_card"] = force_regenerate_card

    return state


async def save_context_after_agent(
    session_id: str,
    state: AgentState,
    enhanced_manager: Optional[EnhancedConversationFileManager] = None,
):
    """
    在 Agent 执行完成后保存上下文到持久化存储

    Args:
        session_id: 会话 ID
        state: 最终的 Agent 状态
        enhanced_manager: 增强的对话管理器
    """
    from app.config.settings import settings

    if not settings.FULL_CONTEXT_ENABLED:
        return  # 未启用完整上下文，跳过

    conv_manager = enhanced_manager or EnhancedConversationFileManager()

    # 1. 保存用户的原始输入到 all_flow
    if state.get("user_input"):
        await conv_manager.append_all_flow_message(
            session_id=session_id,
            role="user",
            content=state.get("user_input", ""),
            message_type="user_input",
            metadata={"current_step": state.get("current_step")}
        )

    # 2. 保存 AI 的思考过程到 all_flow（来自 logs）
    logs = state.get("logs", [])
    for log_entry in logs:
        await conv_manager.append_all_flow_message(
            session_id=session_id,
            role="system",
            content=log_entry.get("message", ""),
            message_type="ai_thinking",
            metadata={
                "done": log_entry.get("done", True),
                "step": state.get("current_step")
            }
        )

    # 3. 保存 AI 的最终响应到 all_flow
    messages = state.get("messages", [])
    final_response = state.get("final_response") or (getattr(messages[-1], "content", "") if messages else "")
    if final_response:
        await conv_manager.append_all_flow_message(
            session_id=session_id,
            role="assistant",
            content=final_response,
            message_type="ai_response",
            metadata={"current_step": state.get("current_step")}
        )

    # 4. 保存 AI 总结的 note（结论性内容）
    # 从 context.summaries 提取总结，保存到 note.json
    context = state.get("context", {})
    summaries = context.get("summaries", {})

    if summaries:
        # 构建笔记内容
        note_content_parts = []
        for step, summary in summaries.items():
            note_content_parts.append(f"## {step}\n{summary}")

        if note_content_parts:
            await conv_manager.save_note(
                session_id=session_id,
                note_content="\n\n".join(note_content_parts),
                note_type="summary",
                metadata={
                    "current_step": state.get("current_step"),
                    "total_summaries": len(summaries),
                    "generated_at": datetime.utcnow().isoformat() + "Z"
                }
            )

    # 5. 保存 Answer Card 到 note.json
    # 当 agent 生成 answer_card 时，保存到持久化存储
    answer_card = state.get("answer_card")
    if answer_card and answer_card.get("user_answer"):
        await conv_manager.save_answer_card(
            session_id=session_id,
            answer_card={
                "question_id": answer_card.get("question_id"),
                "question_content": answer_card.get("question_content"),
                "user_answer": answer_card.get("user_answer"),
                "ai_summary": answer_card.get("ai_summary"),
                "ai_analysis": answer_card.get("ai_analysis"),
                "key_insights": answer_card.get("key_insights"),
                "current_step": state.get("current_step"),
                "created_at": datetime.utcnow().isoformat() + "Z"
            }
        )
