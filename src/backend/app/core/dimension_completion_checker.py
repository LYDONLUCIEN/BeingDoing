"""
维度探索完成检测：基于对话历史判断是否已得出该维度的结论，并生成结论卡片内容。
"""
import json
import re
from typing import Any, Dict, List, Optional

from app.core.llmapi import get_default_llm_provider, LLMMessage
from app.domain.conclusion_card_goals import (
    cap_strengths_keywords_list,
    get_conclusion_card_goal,
    get_conclusion_rules,
    get_goal_prompt_hint,
)
from app.domain.conclusion_card_payload import (
    build_conclusion_json_schema_instructions,
    merge_conclusion_payload,
)
from app.domain.dimension_completion import get_dimension_config

# 结论卡专用：勿复用主对话 system（含 STATE_JSON 与流程），避免干扰纯 JSON 输出或诱发多余协议块。
_CONCLUSION_GENERATION_SYSTEM = (
    "你是与来访者一对一谈话的职业咨询师。"
    "当前任务：根据用户消息里提供的对话记录，输出**一条**合法 JSON 对象（结论卡字段），不要输出任何 JSON 以外的文字。"
    "其中 summary 要像当面收口：直接对「你」说话，简短、有温度；禁止元叙述（如「从对话可见」「综上所述」「作为模型/AI」）、"
    "禁止内部推理、分析报告体或提纲式分条评析。"
    "keywords 与扩展字段必须严格来自用户已明确说出的内容，禁止编造。"
)

CONCLUSION_CONTEXT_MAX_MESSAGES = 60
CONCLUSION_CONTEXT_MAX_CHARS = 12000
CONCLUSION_BASIC_INFO_MAX_CHARS = 1200
CONCLUSION_PRIOR_CONTEXT_MAX_CHARS = 2200


def _clip_text(text: str, limit: int) -> str:
    s = (text or "").strip()
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def _build_conclusion_conv_text(conversation_history: List[Dict[str, str]]) -> str:
    """结论生成上下文：扩大窗口但设字符预算，兼顾质量与成本。"""
    recent = conversation_history[-CONCLUSION_CONTEXT_MAX_MESSAGES:]
    text = "\n\n".join(
        f"{m.get('role', 'user')}: {m.get('content', '')}" for m in recent
    )
    return _clip_text(text, CONCLUSION_CONTEXT_MAX_CHARS)


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


def build_conclusion_generation_messages(
    phase: str,
    conversation_history: List[Dict[str, str]],
    prior_conclusion: Optional[Dict] = None,
    *,
    basic_info: str = "",
    prior_context: str = "",
) -> Optional[List[LLMMessage]]:
    """
    构造「生成结论卡 JSON」的 LLM 消息（与 check_dimension_complete 内生成段一致）。
    用于确认稿流式接口；不包含「是否已完成探索」判定。
    """
    config = get_dimension_config(phase)
    if not config or len(conversation_history) < 2:
        return None
    conv_text = _build_conclusion_conv_text(conversation_history)
    label = config.get("label", phase)
    goal = config.get("goal", "")
    summary_hint = config.get("summary_prompt_hint", "")
    style_rules = config.get("summary_style_rules") or []
    style_examples = config.get("summary_style_examples") or []
    goal_hint = get_goal_prompt_hint(phase)
    basic_info_clean = _clip_text(basic_info or "", CONCLUSION_BASIC_INFO_MAX_CHARS)
    prior_context_clean = _clip_text(prior_context or "", CONCLUSION_PRIOR_CONTEXT_MAX_CHARS)

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
# 【zkx】 高冗余，且有冲突，后面要求进制自创，这里允许进行改写。
#     values_extra = ""
#     if phase == "values":
#         values_extra = """

# 【values 阶段特别要求】
# 请从用户对话中寻找 5 个核心价值观关键词。
# 1) 尽可能只使用用户亲口提到的原词，优先保留用户原话；
# 2) 实在没有足够原词时，再进行同义词改写；
# 3) 尽量是精准的 2~4 字词语（如：诚实、成长、家庭、自由）。"""

    conclusion_rules = get_conclusion_rules(phase)
    anti_fabrication = """
【硬性约束 - 严禁杜撰】
- keywords 必须且只能从对话中用户明确说出的词汇提取，严禁自创、同义替换或凭空添加
- 若用户未提到足够关键词，宁可减少数量也不要杜撰
- 结论内容必须符合本维度的 dimension_goal，且与用户实际表达一致
【命名约束】keywords 数组中每一项必须是单一概念词（或本阶段要求的单一短语），不得使用「/、或、以及、&、|」并列多个候选。若对话中出现近义词而未明确取舍，宁可拆成多条并在 summary 中说明用户偏好，也不要在单条内并列多个候选。"""
    schema_instructions = build_conclusion_json_schema_instructions(phase)
    tone_tight = """
【summary 口吻（须严格遵守）】
- 面向对方，用「你」作主语，优先输出 2-4 段自然段；允许洞察与建议，但禁止编造事实。
- 不要使用：从对话中/可以发现/综上所述/小结如下/模型/AI/助手/用户表示（改用「你」）等措辞。
- 可用 **关键词** 与 keywords 列表对应；避免「第一点…第二点…」式罗列，除非用户对话里本来就是列表语境。
"""
    style_rules_block = ""
    if isinstance(style_rules, list) and style_rules:
        rule_lines = [f"- {str(x).strip()}" for x in style_rules if str(x).strip()]
        if rule_lines:
            style_rules_block = "【本阶段文风规则】\n" + "\n".join(rule_lines)

    style_examples_block = ""
    if isinstance(style_examples, list) and style_examples:
        ex_lines = [str(x).strip() for x in style_examples if str(x).strip()]
        if ex_lines:
            style_examples_block = (
                "【本阶段文风示例（仅用于风格参考，不可照抄具体事实）】\n"
                + "\n\n".join(f"示例{i+1}：{v}" for i, v in enumerate(ex_lines[:2]))
            )

    context_blocks: List[str] = []
    if basic_info_clean:
        context_blocks.append(f"【用户基础信息】\n{basic_info_clean}")
    if prior_context_clean:
        context_blocks.append(f"【前序阶段结论（供参考）】\n{prior_context_clean}")
    context_blocks.append(f"【当前阶段对话内容】\n---\n{conv_text}\n---")
    composed_context = "\n\n".join(context_blocks)

    summary_prompt = f"""基于以下对话，生成「{label}」维度的探索结论汇总。{prior_hint}
{composed_context}

该维度的目标：{goal}
{summary_hint}
{goal_hint}

【本阶段结论卡规则】
{conclusion_rules}
{anti_fabrication}
{tone_tight}
{style_rules_block}
{style_examples_block}
{schema_instructions}"""
# 【zkx】 高冗余，且有冲突，后面要求进制自创，这里允许进行改写。去除了{values_extra}
    return [
        LLMMessage(role="system", content=_CONCLUSION_GENERATION_SYSTEM),
        LLMMessage(role="user", content=summary_prompt),
    ]


def finalize_conclusion_from_summary_text(
    phase: str,
    summary_text: str,
    prior_conclusion: Optional[Dict] = None,
) -> Optional[Dict]:
    """将模型输出的正文解析为结论卡 payload（与 check_dimension_complete 尾部逻辑一致）。"""
    config = get_dimension_config(phase)
    if not config:
        return None
    summary = ""
    keywords: List[str] = []
    raw_obj: Optional[Dict[str, Any]] = None
    text_clean = (summary_text or "").strip()
    if "```json" in text_clean:
        text_clean = text_clean.split("```json")[1].split("```")[0].strip()
    elif "```" in text_clean:
        text_clean = text_clean.split("```")[1].split("```")[0].strip()
    try:
        obj = json.loads(text_clean)
        if isinstance(obj, dict):
            raw_obj = obj
            raw_kw = obj.get("keywords")
            keywords = [str(k).strip() for k in raw_kw if k] if isinstance(raw_kw, list) else []
            summary = (obj.get("summary") or "").strip()
    except (json.JSONDecodeError, TypeError):
        summary = summary_text
        keywords = []
        raw_obj = None

    if phase == "strengths":
        keywords = cap_strengths_keywords_list(keywords)
    keywords = _validate_keywords_by_goal(phase, keywords, locked_keywords=None)

    if not summary:
        summary = _build_goal_fallback_summary(phase, keywords)

    dimension_goal = config.get("goal", "") or ""
    return merge_conclusion_payload(
        phase,
        keywords=keywords,
        summary=summary,
        dimension_goal=dimension_goal,
        raw_llm_obj=raw_obj,
        prior_conclusion=prior_conclusion if isinstance(prior_conclusion, dict) else None,
    )


def _validate_keywords_by_goal(
    phase: str,
    keywords: List[str],
    *,
    locked_keywords: Optional[List[str]] = None,
) -> List[str]:
    goal = get_conclusion_card_goal(phase)
    validation = goal.get("validation") or {}
    min_k = int(validation.get("min_keywords", 1))
    max_k = int(validation.get("max_keywords", 5))
    strict = bool(validation.get("strict_match_user_confirmed_keywords", False))

    normalized = _normalize_keyword_list(keywords, limit=max(max_k, 1))
    if strict and locked_keywords:
        return locked_keywords
    if len(normalized) < min_k and locked_keywords:
        return locked_keywords
    return normalized[:max_k] if normalized else (locked_keywords or [])


async def check_dimension_complete(
    phase: str,
    conversation_history: List[Dict[str, str]],
    prior_conclusion: Optional[Dict] = None,
    vip_level: int = 1,
    llm_provider=None,
    *,
    skip_completion_check: bool = False,
    basic_info: str = "",
    prior_context: str = "",
) -> Optional[Dict]:
    """
    判断对话是否已达到该维度的探索结论；若达到则生成结论卡片。

    prior_conclusion: 上一轮后台检测得出的结论；若提供则跳过完成判定，直接综合本轮用户输入重新生成。
    skip_completion_check: 为 True 时跳过「是否已完成探索」判定，直接生成结论 JSON（用于用户主动点「确认稿」等兜底，勿滥用）。

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

    conv_text = _build_conclusion_conv_text(conversation_history)

    llm = llm_provider or get_default_llm_provider(vip_level=vip_level)
    label = config.get("label", phase)
    goal = config.get("goal", "")
    criteria = config.get("completion_criteria", "")
    # 不再使用正则提取关键词，全部交由 AI 从对话中判断
    locked_keywords = None

    # 若有 prior_conclusion 或 skip_completion_check，则跳过完成判定，直接进入生成
    skip_gate = bool(prior_conclusion) or skip_completion_check
    if not skip_gate:
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

    # 已判定完成，生成结论卡片内容（与确认稿流式共用同一套 prompt / 解析）
    gen_messages = build_conclusion_generation_messages(
        phase,
        conversation_history,
        prior_conclusion,
        basic_info=basic_info,
        prior_context=prior_context,
    )
    if not gen_messages:
        return None
    try:
        summary_response = await llm.chat(
            gen_messages,
            temperature=0.3,
            response_format={"type": "json_object"},
        )
    except TypeError:
        summary_response = await llm.chat(gen_messages, temperature=0.3)
    summary_text = (summary_response.content or "").strip()
    return finalize_conclusion_from_summary_text(phase, summary_text, prior_conclusion)
