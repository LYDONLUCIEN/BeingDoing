"""
智能体状态定义

双轨设计：
- messages: 对前端用户可见的消息（由 user_agent 节点写入）
- inner_messages: 供思考链（reasoning/observation）使用的内部消息，不直接暴露给用户
- logs: 过程日志，供前端展示进度/调试
"""
from typing import TypedDict, List, Dict, Optional, Any
from app.core.llmapi.base import LLMMessage


class AgentState(TypedDict, total=False):
    """智能体状态（total=False 便于渐进式增加字段）"""
    # === 用户可见（前端展示）===
    messages: List[LLMMessage]

    # === 内部消息（思考链使用，不直接给用户）===
    inner_messages: List[LLMMessage]

    # === 过程日志（前端可做进度条/调试）===
    logs: List[Dict[str, Any]]

    # === 上下文与步骤 ===
    context: Dict[str, Any]
    current_step: str  # 步骤 id，见 app.domain.steps（FLOW_STEPS）

    # === 工具 ===
    tools_used: List[str]
    tool_results: List[Dict[str, Any]]

    # === 输入与身份 ===
    user_input: Optional[str]
    user_id: Optional[str]
    session_id: Optional[str]

    # === 循环控制 ===
    iteration_count: int
    should_continue: bool

    # === 思考链输出（由 user_agent 转为 messages）===
    final_response: Optional[str]
    error: Optional[str]

    # === 可选：答题卡元信息（供前端渲染「问题/答案卡片」）===
    # 由智能体在合适的时机填入，例如：
    # {"question_step": "values_exploration", "user_answer_summary": "...对当前答案的概括..."}
    answer_card: Dict[str, Any]

    # === 建议标签（3个简短建议回答方向）===
    suggestions: List[str]

    # === 题目进度管理 ===
    # 存储当前步骤的题目进度信息
    # {"current_question_id": int, "current_question_index": int, "is_answer_sufficient": bool}
    question_progress: Dict[str, Any]

    # === 可选：流式 SSE 推送队列（真流式时由 stream 端点注入）===
    stream_queue: Any  # asyncio.Queue[str | None]，reasoning 节点边生成边 put(chunk)，端点消费    # === 可选：持久化队列（中优先级改进预留）===
    db_records: List[Dict[str, Any]]
    notes: List[Dict[str, Any]]
