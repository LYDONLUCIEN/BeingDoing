"""
维度探索完成检测：基于对话历史判断是否已得出该维度的结论，并生成结论卡片内容。
"""
import json
import re
from typing import Dict, List, Optional

from app.core.llmapi import get_default_llm_provider, LLMMessage
from app.domain.conclusion_card_goals import (
    get_conclusion_card_goal,
    get_goal_prompt_hint,
    get_conclusion_rules,
)
from app.domain.dimension_completion import get_dimension_config


def _normalize_keyword_list(items: List[str], *, limit: int = 5) -> List[str]:
    """标准化关键词列表：去重、去空、保序。"""
    seen = set()
    result: List[str] = []
    for raw in items:
        item = (raw or "").strip()
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
        if len(result) >= limit:
            break
    return result


def _extract_enum_keywords(text: str) -> List[str]:
    """从“1. xxx 2. yyy”这类枚举文本中提取关键词。"""
    if not text:
        return []
    candidates = re.findall(r"(?:^|\n)\s*\d+[\.、]\s*\**([^*\n]+?)\**\s*(?=$|\n)", text)
    return _normalize_keyword_list(candidates, limit=5)


def _extract_delimited_keywords(text: str) -> List[str]:
    """从“自由，成长，学习，助人，探索自我”这类分隔文本中提取关键词。"""
    if not text:
        return []
    cleaned = text
    focus_match = re.search(r"(?:就是|是|我的价值观是|关键词是)\s*(.+?)(?:这就是|不用探索|我很明确|。|$)", cleaned)
    if focus_match:
        cleaned = focus_match.group(1)
    cleaned = re.sub(r"[。！？!?\r\t]", " ", cleaned)
    cleaned = re.sub(
        r"(我的|就是|包括|分别是|是|有|价值观|关键词|这就是|以上|顺序|按顺序|不用探索了|我很明确|我认为|我觉得|我想|不好|不是|属于我)",
        " ",
        cleaned,
    )
    parts = re.split(r"[,\n，、；;|/]+", cleaned)
    candidates: List[str] = []
    for p in parts:
        token = (p or "").strip(" ：:\"'“”‘’()（）[]【】")
        if not token:
            continue
        if token in {"我", "你", "他", "她", "它"}:
            continue
        if token.startswith("我 "):
            token = token[2:].strip()
        if token.startswith("我"):
            token = token[1:].strip()
        if not token:
            continue
        if len(token) > 16:
            continue
        # 过滤明显确认语，避免把“没问题”当关键词
        if token in {"没问题", "对的", "可以", "确认", "好的", "好", "是的", "不好"}:
            continue
        candidates.append(token)
    return _normalize_keyword_list(candidates, limit=5)


def _extract_locked_values_keywords(conversation_history: List[Dict[str, str]]) -> Optional[List[str]]:
    """
    从会话中提取用户已明确确认的 5 个价值观词，用于强一致约束。
    优先从用户消息提取，其次从助手“1. xxx”确认列表提取。
    """
    # 1) 优先从用户消息逆序查找
    for m in reversed(conversation_history[-30:]):
        if (m.get("role") or "") != "user":
            continue
        content = (m.get("content") or "").strip()
        if not content:
            continue
        kws = _extract_delimited_keywords(content)
        if len(kws) >= 5:
            return kws[:5]

    # 2) 回退：从助手枚举确认文本提取
    for m in reversed(conversation_history[-30:]):
        if (m.get("role") or "") != "assistant":
            continue
        content = (m.get("content") or "").strip()
        if not content:
            continue
        kws = _extract_enum_keywords(content)
        if len(kws) >= 5:
            return kws[:5]

    return None


def _build_goal_fallback_summary(phase: str, keywords: List[str]) -> str:
    goal = get_conclusion_card_goal(phase)
    objective = goal.get("objective", "")
    if keywords:
        return (
            f"本维度结论已完成，当前输出聚焦于：{objective}。"
            f"最终确认关键词为：{'、'.join([f'**{k}**' for k in keywords])}。"
        )
    return f"本维度结论已完成，当前输出聚焦于：{objective}。"


def _validate_keywords_by_goal(
    phase: str,
    keywords: List[str],
    *,
    locked_keywords: Optional[List[str]] = None,
) -> List[str]:
    goal = get_conclusion_card_goal(phase)
    validation = goal.get("validation") or {}
    min_k = int(validation.get("min_keywords", 1))
    max_k = int(validation.get("max_keywords", 10))
    strict = bool(validation.get("strict_match_user_confirmed_keywords", False))

    normalized = _normalize_keyword_list(keywords, limit=max(max_k, 1))
    if strict and locked_keywords:
        return locked_keywords
    if len(normalized) < min_k and locked_keywords:
        return locked_keywords
    return normalized[:max_k] if normalized else (locked_keywords or [])


async def detect_explicit_completion(
    phase: str,
    user_message: str,
    conversation_history: List[Dict[str, str]],
    llm_provider=None,
    vip_level: int = 1,
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

    llm = llm_provider or get_default_llm_provider(vip_level=vip_level)
    prompt = f"""你是一位职业咨询师。用户刚才的回复是：
「{user_message.strip()}」

该维度的探索目标是：{goal}

请判断：用户是否明确表示此维度的答案已确定、肯定、无需再讨论？且其回答内容形式上符合该维度的目标答案？

例如：用户说"就是这样了""我确定""没问题""这就是我的答案""可以了""就这些"；
或"我已经明确答案了""我认为这个维度已经没有必要再聊了""请输出答题卡"等。
若对话中已有实质内容，且用户明确表示无需再讨论，则返回 true。
请严格判断，只有明确确认时，或者用户针对探索目标内容给出了符合目标的结论性答案，才能返回 true。

用 JSON 回复：{{"explicit_complete": true 或 false}}
只输出 JSON。"""

    messages = [LLMMessage(role="user", content=prompt)]
    try:
        response = await llm.chat(messages, temperature=0.1, response_format={"type": "json_object"})
    except TypeError:
        response = await llm.chat(messages, temperature=0.1)
    text = (response.content or "").strip()
    text_clean = text
    if "```json" in text:
        text_clean = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        parts = text.split("```")
        if len(parts) >= 2:
            text_clean = parts[1].strip()
    try:
        obj = json.loads(text_clean)
        return bool(obj.get("explicit_complete"))
    except (json.JSONDecodeError, TypeError):
        return False


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
    vip_level: int = 1,
    llm_provider=None,
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

    llm = llm_provider or get_default_llm_provider(vip_level=vip_level)
    label = config.get("label", phase)
    goal = config.get("goal", "")
    criteria = config.get("completion_criteria", "")
    # 不再使用正则提取关键词，全部交由 AI 从对话中判断
    locked_keywords = None

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

        messages = [LLMMessage(role="user", content=check_prompt)]
        try:
            response = await llm.chat(messages, temperature=0.1, response_format={"type": "json_object"})
        except TypeError:
            response = await llm.chat(messages, temperature=0.1)
        text = (response.content or "").strip()
        text_clean = text
        if "```json" in text:
            text_clean = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            parts = text.split("```")
            if len(parts) >= 2:
                text_clean = parts[1].strip()
        try:
            obj = json.loads(text_clean)
            if not obj.get("complete"):
                return None
        except (json.JSONDecodeError, TypeError):
            return None

    # 已判定完成，生成结论卡片内容
    summary_hint = config.get("summary_prompt_hint", "")
    goal_hint = get_goal_prompt_hint(phase)

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
    values_extra = ""
    if phase == "values":
        values_extra = """

【values 阶段特别要求】
请从用户对话中寻找 5 个核心价值观关键词。
1) 尽可能只使用用户亲口提到的原词，优先保留用户原话；
2) 实在没有足够原词时，再进行同义词改写；
3) 尽量是精准的 2~4 字词语（如：诚实、成长、家庭、自由）。"""

    conclusion_rules = get_conclusion_rules(phase)
    anti_fabrication = """
【硬性约束 - 严禁杜撰】
- keywords 必须且只能从对话中用户明确说出的词汇提取，严禁自创、同义替换或凭空添加
- 若用户未提到足够关键词，宁可减少数量也不要杜撰
- 结论内容必须符合本维度的 dimension_goal，且与用户实际表达一致"""
    summary_prompt = f"""基于以下对话，生成「{label}」维度的探索结论汇总。{prior_hint}{values_extra}

该维度的目标：{goal}
{summary_hint}
{goal_hint}

【本阶段结论卡规则】
{conclusion_rules}
{anti_fabrication}

请用温暖、专业、包容的语气，像一位可靠的咨询师对用户说话。不要用冷冰冰的「AI 分析」口吻。

请**只输出一个 JSON 对象**，严格按以下格式，不要输出任何其他内容（无前后说明、无 markdown 代码块标记）：
{{"keywords": ["词1", "词2", ...], "summary": "汇总文案：用 **关键词** 标出核心词。"}}"""

    summary_messages = [
        LLMMessage(role="user", content=summary_prompt),
    ]
    try:
        summary_response = await llm.chat(
            summary_messages, temperature=0.3,
            response_format={"type": "json_object"},
        )
    except TypeError:
        summary_response = await llm.chat(summary_messages, temperature=0.3)
    summary_text = (summary_response.content or "").strip()

    summary = ""
    keywords: List[str] = []
    text_clean = summary_text.strip()
    if "```json" in text_clean:
        text_clean = text_clean.split("```json")[1].split("```")[0].strip()
    elif "```" in text_clean:
        text_clean = text_clean.split("```")[1].split("```")[0].strip()
    try:
        obj = json.loads(text_clean)
        if isinstance(obj, dict):
            raw_kw = obj.get("keywords")
            keywords = [str(k).strip() for k in raw_kw if k] if isinstance(raw_kw, list) else []
            summary = (obj.get("summary") or "").strip()
    except (json.JSONDecodeError, TypeError):
        summary = summary_text
        keywords = []

    keywords = _validate_keywords_by_goal(phase, keywords, locked_keywords=None)

    if not summary:
        summary = _build_goal_fallback_summary(phase, keywords)

    dimension_goal = config.get("goal", "") or ""
    return {
        "summary": summary,
        "keywords": keywords,
        "ai_summary": summary,
        "dimension_goal": dimension_goal,
        "final_answer": ", ".join(keywords) if keywords else summary,
    }
