import copy
import uuid
from typing import Dict, Any, Literal, Optional, Tuple

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START
from langgraph.types import Command
from pydantic import BaseModel

from langgraph_agent.config import global_config  # 复用现有配置，避免重复造轮子
from new_agent.graph.state import AgentState, create_initial_state
from new_agent.graph.context_manager import SimpleContextManager
from new_agent.tools.db_tool import record_event
from new_agent.tools.note_tool import write_note
from new_agent.tools.knowledge_tool import query_knowledge
from new_agent.prompts.loader import get_loader


_prompt_loader = get_loader()


class PlannerDecision(BaseModel):
    next: Literal["front", "db_writer", "note_writer", "knowledge", "FINISH"]
    ask_user: str = ""
    sub_task: str = ""          # 内部使用的下一步任务描述
    final_answer: str = ""      # 当 next == FINISH 时，给用户的最终总结
    db_record: Optional[Dict[str, Any]] = None
    note: Optional[Dict[str, Any]] = None


def _get_llm(model: Optional[str] = None) -> ChatOpenAI:
    """
    获取一个 ChatOpenAI 客户端。
    默认复用 JoinAI 的 BASE_LLM 与 OPENAI_BASE_URL，保持一致性。
    """
    model_name = model or global_config.BASE_LLM
    return ChatOpenAI(
        model=model_name,
        base_url=global_config.OPENAI_BASE_URL,
        temperature=0.2,
    )


class ConsultationGraph:
    """
    简化版咨询智能体图：
    - initial_setup
    - front_agent
    - planner_agent
    - db_writer
    - note_writer
    """

    def __init__(self):
        self.graph = self._build_graph()
        # 简单上下文管理器
        self._ctx_manager = SimpleContextManager()

    # === 节点实现 ==============================================================

    async def initial_setup_node(self, state: AgentState, config: Dict[str, Any]) -> Command[Literal["front_agent"]]:
        """初始化会话状态，设置 session_id 等。"""
        state = create_initial_state(state)

        if not state.get("session_id"):
            state["session_id"] = f"session_{uuid.uuid4().hex[:8]}"

        # 确保 logs 存在
        state["logs"] = state.get("logs", [])
        state["logs"].append(
            {"message": "会话初始化完成", "done": True, "session_id": state["session_id"]}
        )

        return Command(update=state, goto="front_agent")

    async def front_agent_node(
        self, state: AgentState, config: RunnableConfig
    ) -> Command[Literal["planner_agent", "__end__"]]:
        """
        面向用户的前台智能体。
        - 读取最新的用户消息
        - 给出自然语言应答
        - 将回复写入 messages/inner_messages
        - 简化逻辑：默认交给 planner 继续思考，除非用户明显要求结束
        """
        # 上下文压缩（尽早执行，避免对用户体验造成突兀影响）
        state = await self._ctx_manager.maybe_compress(state)

        llm = _get_llm()

        # 构造系统 + 历史 + 最新用户消息
        # 可选注入专业知识与用户历史
        theory_snippets = state.get("context", {}).get("theory_snippets", "")
        user_history_summary = state.get("context", {}).get("user_history_summary", "")
        sys_content = _prompt_loader.render_prompt(
            "front_agent",
            {
                "theory_snippets": theory_snippets,
                "user_history_summary": user_history_summary,
            },
        )
        sys_msg = SystemMessage(content=sys_content)
        history = copy.deepcopy(state.get("messages", []))

        # 找到最近一条 HumanMessage
        last_user_msg: Optional[BaseMessage] = None
        for msg in reversed(history):
            if isinstance(msg, HumanMessage):
                last_user_msg = msg
                break

        if not last_user_msg:
            # 没有用户消息时，简单询问
            user_prompt = HumanMessage(content="请告诉我你想咨询的问题。")
            messages = [sys_msg, user_prompt]
        else:
            messages = [sys_msg] + history

        ai_resp = await llm.ainvoke(messages)
        reply = AIMessage(content=ai_resp.content)

        state["messages"].append(reply)
        state["inner_messages"].append(reply)

        text = (last_user_msg.content or "").lower() if last_user_msg else ""
        if any(kw in text for kw in ["结束", "没问题了", "thanks", "thank you", "bye"]):
            state["completed"] = True
            return Command(update=state, goto="__end__")

        return Command(update=state, goto="planner_agent")

    async def planner_agent_node(
        self, state: AgentState, config: RunnableConfig
    ) -> Command[Literal["front_agent", "db_writer", "note_writer", "__end__"]]:
        """
        背后思考的 Planner：
        - 不直接对用户说话
        - 根据当前对话决定下一步
        - 输出结构化决策 PlannerDecision
        """
        # 上下文压缩
        state = await self._ctx_manager.maybe_compress(state)

        llm = _get_llm()

        theory_snippets = state.get("context", {}).get("theory_snippets", "")
        user_history_summary = state.get("context", {}).get("user_history_summary", "")
        sys_content = _prompt_loader.render_prompt(
            "planner",
            {
                "theory_snippets": theory_snippets,
                "user_history_summary": user_history_summary,
            },
        )
        sys_msg = SystemMessage(content=sys_content)
        history = copy.deepcopy(state.get("inner_messages", []))
        messages = [sys_msg] + history

        raw_resp = await llm.ainvoke(
            messages,
            response_format={"type": "json_object"},
        )

        import json

        try:
            data = json.loads(raw_resp.content)
            decision = PlannerDecision.model_validate(data)
        except Exception:
            decision = PlannerDecision(next="front", ask_user="")

        # 记录 planner 决策到 logs，便于调试/回溯
        logs = state.get("logs", [])
        logs.append(
            {
                "message": "Planner 决策完成",
                "done": True,
                "meta": {
                    "next": decision.next,
                    "ask_user": decision.ask_user,
                    "sub_task": decision.sub_task,
                    "has_db_record": decision.db_record is not None,
                    "has_note": decision.note is not None,
                },
            }
        )
        state["logs"] = logs

        if decision.db_record:
            queue = state.get("db_records", [])
            queue.append(decision.db_record)
            state["db_records"] = queue

        if decision.note:
            notes = state.get("notes", [])
            notes.append(decision.note)
            state["notes"] = notes

        # 可选：把 sub_task 记录到状态中，用于后续分析/展示
        if decision.sub_task:
            state["current_step"] = decision.sub_task

        if decision.next == "front":
            if decision.ask_user:
                prompt_msg = AIMessage(content=decision.ask_user)
                state["messages"].append(prompt_msg)
                state["inner_messages"].append(prompt_msg)
            return Command(update=state, goto="front_agent")

        if decision.next == "db_writer":
            return Command(update=state, goto="db_writer")

        if decision.next == "note_writer":
            return Command(update=state, goto="note_writer")

        if decision.next == "knowledge":
            return Command(update=state, goto="knowledge_node")

        state["completed"] = True
        # 若有 final_answer，则作为最后一条消息返回给用户
        if decision.final_answer:
            final_msg = AIMessage(content=decision.final_answer)
            state["messages"].append(final_msg)
            state["inner_messages"].append(final_msg)
        return Command(update=state, goto="__end__")

    async def db_writer_node(
        self, state: AgentState, config: RunnableConfig
    ) -> Command[Literal["planner_agent"]]:
        """
        从 state["db_records"] 中取出一条记录，调用 record_event 写入占位 DB。
        """
        queue = state.get("db_records", [])
        if not queue:
            return Command(update=state, goto="planner_agent")

        record = queue.pop(0)
        state["db_records"] = queue

        state, msg = await record_event(state, config, record)
        log = {"message": f"DB 记录写入: {msg}", "done": True}
        logs = state.get("logs", [])
        logs.append(log)
        state["logs"] = logs

        return Command(update=state, goto="planner_agent")

    async def note_writer_node(
        self, state: AgentState, config: RunnableConfig
    ) -> Command[Literal["planner_agent"]]:
        """
        从 state["notes"] 中取出一条笔记，调用 write_note 写入文件。
        """
        notes = state.get("notes", [])
        if not notes:
            return Command(update=state, goto="planner_agent")

        note = notes.pop(0)
        state["notes"] = notes

        path = note.get("path", "consultation_note.md")
        content = note.get("content", "")

        state, msg = await write_note(state, config, path=path, content=content)
        logs = state.get("logs", [])
        logs.append({"message": f"笔记写入: {msg}", "done": True})
        state["logs"] = logs

        return Command(update=state, goto="planner_agent")

    async def knowledge_node(
        self, state: AgentState, config: RunnableConfig
    ) -> Command[Literal["planner_agent"]]:
        """
        简单知识库查询节点：
        - 从 state["context"]["knowledge_query"] 或最近用户消息中提取问题；
        - 调用 query_knowledge；
        - 将结果作为一条内部 AIMessage 写入 inner_messages，供下一轮 Planner 使用。
        """
        question = state.get("context", {}).get("knowledge_query", "")

        if not question:
            # 若没有显式 query，则退回最近一条用户消息
            for msg in reversed(state.get("messages", []) or []):
                if isinstance(msg, HumanMessage):
                    question = msg.content
                    break

        if not question:
            return Command(update=state, goto="planner_agent")

        state, kb_text = await query_knowledge(state, config, question)

        kb_msg = AIMessage(
            content=f"[KnowledgeBase] 以下是与当前问题相关的检索结果，供内部规划使用：\n{kb_text}",
            name="knowledge_tool",
        )
        state["inner_messages"].append(kb_msg)
        # 是否对用户可见可按需决定，这里只写入 inner_messages

        logs = state.get("logs", [])
        logs.append(
            {
                "message": "知识库查询已完成",
                "done": True,
                "meta": {"question": question},
            }
        )
        state["logs"] = logs

        return Command(update=state, goto="planner_agent")

    # === 图构建与调用接口 ======================================================

    def _build_graph(self):
        workflow = StateGraph(AgentState)

        workflow.add_node("initial_setup", self.initial_setup_node)
        workflow.add_node("front_agent", self.front_agent_node)
        workflow.add_node("planner_agent", self.planner_agent_node)
        workflow.add_node("db_writer", self.db_writer_node)
        workflow.add_node("note_writer", self.note_writer_node)
        workflow.add_node("knowledge_node", self.knowledge_node)

        workflow.add_edge(START, "initial_setup")

        return workflow.compile()

    async def ainvoke(self, state: AgentState, config: Optional[Dict[str, Any]] = None) -> AgentState:
        """对外统一异步调用入口。"""
        config = config or {}
        if "configurable" not in config:
            config["configurable"] = {}
        return await self.graph.ainvoke(state, config)


# 导出一个默认图实例，方便直接复用
consultation_graph = ConsultationGraph().graph

