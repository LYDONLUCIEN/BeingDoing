"""
题目流程辅助函数：处理题目加载、进度更新、充分性判断等
"""
import json
from typing import Any, Dict, List, Optional, Tuple
from app.domain.question_progress import StepProgress, QuestionProgress, ProgressManager
from app.domain.step_guidance import get_step_theory, get_question_guidance
from app.domain.question_goals import get_question_goal
from app.domain.steps import STEP_TO_CATEGORY
from app.core.agent.state import AgentState
from app.services.question_service import QuestionService

# 跳过/下一题意图关键词
SKIP_KEYWORDS = ["下一题", "跳过", "不想回答", "换一题", "下一个", "不想说", "不知道怎么回答", "算了"]


def detect_skip_intent(user_input: str) -> bool:
    """检测用户是否有跳过当前题目的意图"""
    if not user_input:
        return False
    trimmed = user_input.strip()
    if len(trimmed) <= 15:
        return any(kw in trimmed for kw in SKIP_KEYWORDS)
    return False


def initialize_step_if_needed(
    state: AgentState,
    session_id: str,
    step_id: str
) -> Tuple[AgentState, StepProgress]:
    """
    初始化步骤进度（如果尚未初始化）
    返回: (state, step_progress)
    """
    # 从 session metadata 加载进度
    # 这里简化处理，实际应该从数据库加载
    question_progress_data = state.get("question_progress", {})

    if step_id in question_progress_data:
        # 已初始化，直接加载
        step_progress = StepProgress(**question_progress_data[step_id])
        return state, step_progress

    # 未初始化，创建新的进度
    category = STEP_TO_CATEGORY.get(step_id, "")
    if not category:
        # 不是探索步骤（如combination、refinement），不需要题目进度
        return state, None

    # 加载该步骤的所有题目（同步方法，返回 List[Dict]）
    question_service = QuestionService()
    questions = question_service.get_questions_by_category(category)

    # 初始化进度（questions 已经是 dict 列表，键为 "id" 和 "content"）
    step_progress = ProgressManager.initialize_step_progress(
        step_id=step_id,
        category=category,
        questions=[{"id": q["id"], "content": q["content"]} for q in questions]
    )

    # 保存到state
    question_progress_data[step_id] = step_progress.model_dump()
    state["question_progress"] = question_progress_data

    return state, step_progress


def get_current_question_state(step_progress: StepProgress) -> Dict:
    """
    获取当前题目状态
    返回: {
        "需要步骤介绍": bool,
        "需要题目引导": bool,
        "题目对象": QuestionProgress,
        "题目索引": int
    }
    """
    if not step_progress:
        return {
            "need_step_intro": False,
            "need_question_guidance": False,
            "current_question": None,
            "current_index": -1
        }

    need_step_intro = not step_progress.is_intro_shown
    current_question = step_progress.current_question

    if not current_question:
        # 所有题目都完成了
        return {
            "need_step_intro": need_step_intro,
            "need_question_guidance": False,
            "current_question": None,
            "current_index": -1,
            "all_completed": True
        }

    need_question_guidance = current_question.status == "not_started"

    return {
        "need_step_intro": need_step_intro,
        "need_question_guidance": need_question_guidance,
        "current_question": current_question,
        "current_index": step_progress.current_question_index,
        "all_completed": False
    }


def generate_step_intro_message(step_id: str) -> str:
    """生成步骤介绍消息"""
    theory = get_step_theory(step_id)
    return f"""# 欢迎来到：{theory['purpose']}

{theory['theory']}

现在，让我们开始探索之旅。准备好了吗？"""


def generate_question_guidance_message(
    category: str,
    question_id: int,
    question_content: str
) -> str:
    """生成题目引导消息"""
    guidance = get_question_guidance(category, question_id)
    return f"""{guidance}

**题目**: {question_content}

请慢慢思考，分享你的真实想法。"""


def should_show_answer_card(
    step_progress: StepProgress,
    conversation_history: List[Dict],
    force_regenerate_card: bool = False,
) -> Tuple[bool, str]:
    """
    判断是否应该展示 answer_card

    返回: (should_show, reason)

    判断标准（基于题目目标配置）：
    1. 对话轮数达到 min_turns 以上
    2. 用户回答包含具体例子和感受（sufficiency_hints）
    3. 不超过 max_turns（避免过度挖掘）
    4. force_regenerate_card=True 时强制生成（用于"继续讨论"后的首次消息）
    """
    current_question = step_progress.current_question
    if not current_question:
        return False, "无当前题目"

    # v2.7: 如果是强制重新生成模式，且至少有一轮对话，直接返回 True
    if force_regenerate_card and current_question.turn_count > 0:
        return True, "继续讨论后重新生成答题卡"

    turn_count = current_question.turn_count

    # 获取题目目标配置
    goal = get_question_goal(step_progress.category, current_question.question_id)
    min_turns = goal.get("min_turns", 2) if goal else 2
    max_turns = goal.get("max_turns", 5) if goal else 5
    hints = goal.get("sufficiency_hints", []) if goal else []
    # 如果没有配置 hints，使用默认关键词
    if not hints:
        hints = ["因为", "比如", "例如", "感觉", "觉得", "体验", "经历", "让我", "的时候"]

    # 最少轮数检查
    if turn_count < min_turns:
        return False, "对话轮数不足，需要继续挖掘"

    # 最多轮数检查
    if turn_count >= max_turns:
        return True, "对话轮数已达上限，总结回答"

    # 分析最近的对话内容
    recent_messages = conversation_history[-4:] if len(conversation_history) >= 4 else conversation_history
    user_messages = [msg for msg in recent_messages if msg.get("role") == "user"]

    if not user_messages:
        return False, "无用户输入"

    # 简单启发式判断：用户回答长度和关键词
    latest_user_msg = user_messages[-1].get("content", "")

    # 太短的回答
    if len(latest_user_msg) < 30:
        return False, "回答过于简短"

    # 包含充分性关键词
    has_concrete = any(kw in latest_user_msg for kw in hints)

    if turn_count >= (min_turns + 1) and has_concrete:
        return True, "回答充分，包含具体例子和感受"

    return False, "需要继续挖掘更多细节"


def extract_user_answer_summary(conversation_history: List[Dict]) -> str:
    """
    从对话历史中提取用户答案摘要
    """
    user_messages = [
        msg.get("content", "")
        for msg in conversation_history
        if msg.get("role") == "user"
    ]

    if not user_messages:
        return ""

    # 简单拼接最近的用户输入
    return " ".join(user_messages[-3:])


def update_question_progress(
    step_progress: StepProgress,
    action: str,
    conversation_history: List[Dict] = None
) -> StepProgress:
    """
    更新题目进度

    action:
    - "mark_intro_shown": 标记步骤介绍已展示
    - "start_question": 开始当前题目
    - "increment_turn": 增加对话轮数
    - "complete_question": 完成当前题目
    - "next_question": 移动到下一题
    """
    if action == "mark_intro_shown":
        step_progress.is_intro_shown = True

    elif action == "start_question":
        if step_progress.current_question:
            step_progress.current_question.status = "in_progress"

    elif action == "increment_turn":
        if step_progress.current_question:
            step_progress.current_question.turn_count += 1

    elif action == "complete_question":
        if step_progress.current_question:
            step_progress.current_question.status = "completed"
            if conversation_history:
                step_progress.current_question.user_answer = extract_user_answer_summary(conversation_history)

    elif action == "next_question":
        step_progress.move_to_next_question()

    return step_progress


def save_step_progress_to_state(state: AgentState, step_progress: StepProgress) -> AgentState:
    """保存步骤进度到state"""
    question_progress_data = state.get("question_progress", {})
    question_progress_data[step_progress.step_id] = step_progress.model_dump()
    state["question_progress"] = question_progress_data
    return state


# 类别标签（中文显示用）
CATEGORY_LABELS = {
    "values": "价值观",
    "strengths": "才能",
    "interests": "兴趣与热情",
}


async def generate_answer_card_analysis(
    category: str,
    question_id: int,
    question_content: str,
    conversation_history: List[Dict],
) -> Dict[str, Any]:
    """
    调用 LLM 为答题卡生成结构化分析。

    返回:
        {
            "ai_summary": str,     # 1-2句核心观点概括
            "ai_analysis": str,    # 深层分析
            "key_insights": list,  # 3-5个关键洞察短语
        }

    LLM 调用失败时 fallback 到简单文本提取。
    """
    from app.core.llmapi import get_default_llm_provider, LLMMessage
    from app.domain.prompts import get_answer_card_prompt
    from app.domain.question_goals import get_question_goal

    question_goal = get_question_goal(category, question_id)

    # 格式化对话历史为文本
    conversation_text = ""
    for msg in conversation_history:
        role_label = "用户" if msg.get("role") == "user" else "咨询师"
        conversation_text += f"{role_label}：{msg.get('content', '')}\n"

    prompt_content = get_answer_card_prompt({
        "category_label": CATEGORY_LABELS.get(category, category),
        "question_content": question_content,
        "question_goal": question_goal,
        "conversation_text": conversation_text,
    })

    llm = get_default_llm_provider()
    messages = [
        LLMMessage(role="system", content=prompt_content),
        LLMMessage(role="user", content="请生成答题卡总结。"),
    ]

    try:
        response = await llm.chat(messages, temperature=0.5)
        raw = (response.content or "").strip()
        # 处理 markdown 代码块包裹
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        data = json.loads(raw)
        return {
            "ai_summary": data.get("ai_summary", ""),
            "ai_analysis": data.get("ai_analysis", ""),
            "key_insights": data.get("key_insights", []),
        }
    except Exception:
        # Fallback：使用简单提取
        user_answer = extract_user_answer_summary(conversation_history)
        return {
            "ai_summary": user_answer[:100] if user_answer else "",
            "ai_analysis": "",
            "key_insights": [],
        }
