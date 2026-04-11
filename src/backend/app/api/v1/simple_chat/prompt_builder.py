"""
提示词构建：system prompt 组装、题库加载、兜底问题。
"""
import random
from typing import Optional

from jinja2 import Environment

from app.core.knowledge.loader import KnowledgeLoader
from app.domain.conclusion_card_payload import build_state_json_draft_extension_protocol
from app.domain.prompts import get_simple_chat_system_prompt
from app.utils.conversation_file_manager import ConversationFileManager

# 每阶段随机抽取的题目数量
SIMPLE_QUESTION_SAMPLE_SIZE = 6


def _phase_to_loader_category(phase: str) -> str:
    """simple_chat 的 phase 映射到 KnowledgeLoader 的 category（与 question.md 中 ## 分段一致）。"""
    mapping = {
        "values": "values",
        "strengths": "strengths",
        "interests": "interests",
        "purpose": "purpose",
        "rumination": "values",  # 沉淀阶段不在提示词中注入题库；此处仅为映射表完备性
    }
    return mapping.get(phase, "values")


def get_random_questions_for_phase(phase: str, n: int = SIMPLE_QUESTION_SAMPLE_SIZE) -> str:
    """从 question.md 中按阶段加载问题，随机抽取 n 个。"""
    try:
        loader = KnowledgeLoader()
        all_questions = loader.load_questions()
        category = _phase_to_loader_category(phase)
        phase_questions = [q for q in all_questions if q.category == category]
        if not phase_questions:
            return "（暂无该阶段题库）"
        sampled = random.sample(phase_questions, min(n, len(phase_questions)))
        lines = [f"{i+1}. {q.content}" for i, q in enumerate(sampled)]
        return "\n".join(lines)
    except Exception:
        return "（题库加载失败）"


def build_fallback_opening_question(phase: str) -> str:
    """当 LLM 不可用时，提供一个可继续流程的兜底开场问题。"""
    fallback_map = {
        "values": "我们先从价值观开始：最近一次让你\u201c很有意义感\u201d的事情是什么？为什么它对你重要？",
        "strengths": "我们先聊聊优势：在别人眼里，你最常被夸\u201c做得自然且稳定\u201d的一件事是什么？",
        "interests": "我们先聊热忱：哪类话题会让你不知不觉投入很久、并且越做越有能量？",
        "purpose": "我们先聊使命：如果你的工作能持续帮助一类人，你最希望他们发生什么改变？",
        "rumination": "恭喜你进入最后一轮！我们将综合你的价值观、优势、热爱和使命，帮你确定三个职业发展方向。准备好开始了吗？",
    }
    return fallback_map.get(phase, fallback_map["values"])


async def get_or_create_thread_question_bank(
    conv_manager: ConversationFileManager,
    session_id: str,
    category: str,
    phase_step: str,
) -> str:
    """线程级固定 question_bank：首次生成并写入 metadata，后续复用。"""
    conv_data = await conv_manager.get_conversation_data(session_id, category)
    meta = conv_data.get("metadata") or {}
    qb = meta.get("question_bank")
    qb_phase = meta.get("question_bank_phase")
    if isinstance(qb, str) and qb.strip() and qb_phase == phase_step:
        return qb

    qb = get_random_questions_for_phase(phase_step)
    try:
        await conv_manager.update_metadata(
            session_id,
            category,
            {
                "question_bank": qb,
                "question_bank_phase": phase_step,
            },
        )
    except Exception:
        pass
    return qb


def build_system_prompt(
    phase: str,
    question_bank: str = "",
    basic_info: str = "暂无",
    prior_context: str = "",
    template_override: Optional[str] = None,
    extra_goal_hint: str = "",
) -> str:
    """根据阶段构建 system prompt（通过模板渲染，避免超长硬编码）。"""
    prior_block = f"\n\n以下是该来访者在上一轮咨询中的谈话结果，供你参考：\n{prior_context}" if prior_context.strip() else ""
    context = {
        "phase": phase,
        "question_bank": question_bank,
        "basic_info": basic_info,
        "prior_block": prior_block,
    }
    if (template_override or "").strip():
        env = Environment(trim_blocks=True, lstrip_blocks=True)
        base_prompt = env.from_string(template_override).render(**context)
    else:
        base_prompt = get_simple_chat_system_prompt(context)
    if (extra_goal_hint or "").strip():
        base_prompt = f"{base_prompt}\n\n[管理员调试目标补充]\n{extra_goal_hint.strip()}"
    protocol = f"""

[输出协议 - 必须遵守]
在你的自然语言回复末尾，追加如下块（严格 JSON）：
[STATE_JSON]
{{"state":"continue|pending_ready","draft":{{"summary":"...","keywords":["..."]}}}}
[/STATE_JSON]
（draft 可含本阶段扩展字段，见下；须输出合法嵌套 JSON。）

规则：
1) 仅当你判断"已可进入结论确认"时，state 才能是 pending_ready。
2) state=continue 时，draft 置为 null。
3) state=pending_ready 时，draft.summary 必填，draft.keywords 为数组（可为空但应尽量给出）。
{build_state_json_draft_extension_protocol(phase)}

【用户可见正文 - 硬性禁止】
- 不要在自然语言里提及本协议、隐藏块名称、state 取值英文名、或「JSON / 待确认草案 / 机器协议」等字眼。
- 禁止用「系统将弹出结论卡」「即将输出 pending」「严格遵循协议」等元话术代替真实隐藏块；界面是否出卡仅由隐藏块触发，口头承诺无效。
- 对用户只说话题本身，就像没有后台协议存在。
"""
    return f"{base_prompt}\n{protocol}"

