"""
维度探索完成检测：基于对话历史判断是否已得出该维度的结论，并生成结论卡片内容。
"""
import json
import re
from typing import Dict, List, Optional

from app.core.llmapi import get_default_llm_provider, LLMMessage
from app.domain.dimension_completion import get_dimension_config


async def detect_explicit_completion(
    phase: str,
    user_message: str,
    conversation_history: List[Dict[str, str]],
) -> bool:
    """
    检测用户输入是否明确表示该维度答案已确定、无需再讨论。
    若检测到，则直接弹出结论卡片，无需等待轮数。
    """
    if not user_message or len(user_message.strip()) < 3:
        return False

    config = get_dimension_config(phase)
    if not config:
        return False

    label = config.get("label", phase)
    goal = config.get("goal", "")

    llm = get_default_llm_provider()
    prompt = f"""你是一位职业咨询师。用户刚才的回复是：
「{user_message.strip()}」

该维度的探索目标是：{goal}

请判断：用户是否明确表示此维度的答案已确定、肯定、无需再讨论？且其回答内容形式上符合该维度的目标答案？

例如：用户说"就是这样了""我确定""没问题""这就是我的答案""可以了""就这些"；
或"我已经明确答案了""我认为这个维度已经没有必要再聊了""请输出答题卡"等。
若对话中已有实质内容，且用户明确表示无需再讨论，则返回 true。

请严格判断，只有明确确认时才返回 true。

用 JSON 回复：{{"explicit_complete": true 或 false}}
只输出 JSON。"""

    messages = [LLMMessage(role="user", content=prompt)]
    response = await llm.chat(messages, temperature=0.1)
    text = (response.content or "").strip()

    try:
        obj = json.loads(text)
        return bool(obj.get("explicit_complete"))
    except json.JSONDecodeError:
        json_match = re.search(r'"explicit_complete"\s*:\s*true', text)
        return bool(json_match)


def _should_run_completion_check(
    user_count: int,
    conclusion_shown_at: Optional[int],
    *,
    include_explicit: bool = False,
    explicit_result: bool = False,
) -> bool:
    """
    判断是否应执行维度完成检测（复用逻辑）。

    Args:
        user_count: 用户消息总数
        conclusion_shown_at: 上次展示结论时的用户消息数，None 表示从未展示
        include_explicit: 是否考虑显式完成（由调用方结合 detect_explicit_completion 处理）
        explicit_result: 显式完成检测结果（当 include_explicit 时有效）

    Returns:
        是否应运行 check_dimension_complete
    """
    if include_explicit and explicit_result:
        return True
    if conclusion_shown_at is not None:
        return user_count - conclusion_shown_at >= 3
    return user_count >= 5


async def check_dimension_complete(
    phase: str,
    conversation_history: List[Dict[str, str]],
    prior_conclusion: Optional[Dict] = None,
) -> Optional[Dict]:
    """
    判断对话是否已达到该维度的探索结论；若达到则生成结论卡片。

    prior_conclusion: 上一轮后台检测得出的结论；若提供则跳过完成判定，直接综合本轮用户输入重新生成。

    Returns:
        None 表示未完成。
        dict: {
            "ai_summary": str,
            "dimension_goal": str,
            "final_answer": str,
        }
    """
    config = get_dimension_config(phase)
    if not config:
        return None

    if len(conversation_history) < 2:
        return None

    # 格式化最近对话（最多 20 条）
    recent = conversation_history[-20:]
    conv_text = "\n\n".join(
        f"{m.get('role', 'user')}: {m.get('content', '')}" for m in recent
    )

    llm = get_default_llm_provider()
    label = config.get("label", phase)
    goal = config.get("goal", "")
    criteria = config.get("completion_criteria", "")

    # 若有 prior_conclusion，则跳过完成判定，直接进入生成
    if not prior_conclusion:
        check_prompt = f"""你是一位职业咨询师。请判断以下对话是否已经完成「{label}」维度的探索。

该维度的目标：{goal}
完成标准：{criteria}

请严格依据完成标准判断。只有用户已明确确认、或咨询师已给出清晰总结且用户认可时，才视为完成。

对话内容：
---
{conv_text}
---

请用 JSON 回复，格式：{{"complete": true 或 false, "reason": "简短理由"}}
只输出 JSON，不要其他内容。"""

        messages = [
            LLMMessage(role="user", content=check_prompt),
        ]
        response = await llm.chat(messages, temperature=0.1)
        text = (response.content or "").strip()

        try:
            obj = json.loads(text)
            if not obj.get("complete"):
                return None
        except json.JSONDecodeError:
            json_match = re.search(r"\{[^{}]*\"complete\"\s*:\s*(?:true|false)[^{}]*\}", text)
            if json_match:
                try:
                    obj = json.loads(json_match.group())
                    if not obj.get("complete"):
                        return None
                except json.JSONDecodeError:
                    return None
            else:
                return None

    # 已判定完成，生成结论卡片内容
    summary_hint = config.get("summary_prompt_hint", "")

    prior_hint = ""
    if prior_conclusion:
        prior_summary = prior_conclusion.get("summary") or prior_conclusion.get("ai_summary", "")
        prior_kw = prior_conclusion.get("keywords") or []
        prior_str = f"{prior_summary}\n关键词: {', '.join(prior_kw) if isinstance(prior_kw, list) else prior_kw}"
        prior_hint = f"""

【重要】上一轮已得出初步结论，用户本轮又补充了内容。请综合本轮用户输入与已有结论，生成更新后的最终结论。

上一轮结论：
---
{prior_str}
---

"""

    summary_prompt = f"""基于以下对话，生成「{label}」维度的探索结论汇总。{prior_hint}

该维度的目标：{goal}
{summary_hint}

请用温暖、专业、包容的语气，像一位可靠的咨询师对用户说话。不要用冷冰冰的「AI 分析」口吻，而是表示这是对话的汇总。

请按以下结构输出（用 --- 分隔两部分）：
1. 汇总文案：将「本环节目标」与「你的发现」合并成一段话，直接对用户说。例如：「在这个环节里，我们希望能了解你的核心价值观。通过对话，我们可以看到你拥有**诚实**、**持续成长**、**家庭优先**等特质。」——用 **关键词** 的 Markdown 格式标出核心词，方便前端渲染。语气温馨、可靠、有同理心。
2. 关键词列表：用逗号分隔，如：诚实, 持续成长, 家庭优先（仅列出核心关键词，3-10 个）

只输出内容，用 --- 分隔两部分。不要加标题或编号。"""

    summary_messages = [
        LLMMessage(role="user", content=summary_prompt),
    ]
    summary_response = await llm.chat(summary_messages, temperature=0.3)
    summary_text = (summary_response.content or "").strip()

    parts = [p.strip() for p in re.split(r"\n---+\n", summary_text, maxsplit=1)]
    summary = parts[0] if len(parts) > 0 else summary_text
    keywords_str = parts[1] if len(parts) > 1 else ""
    keywords = [k.strip() for k in keywords_str.split(",") if k.strip()] if keywords_str else []
    if not keywords and summary:
        # 从 **x** 中解析关键词作为后备
        keywords = re.findall(r"\*\*([^*]+)\*\*", summary)

    return {
        "summary": summary,
        "keywords": keywords,
        # 兼容旧字段
        "ai_summary": summary,
        "dimension_goal": "",
        "final_answer": ", ".join(keywords) if keywords else summary,
    }
