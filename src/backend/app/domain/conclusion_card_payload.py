"""
维度结论卡 payload：扩展字段对齐、校验与 pending 草案清洗。

- keywords 始终为主词表；扩展字段仅补充展示/结构化，不可替代 keywords。
- 旧数据无扩展字段 → 读取端不展示即可；本模块在写入时对齐长度并剔除非法值。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.domain.conclusion_card_goals import cap_strengths_keywords_list, get_conclusion_card_goal

STRENGTH_MARKER_ALLOWED = frozenset({"a", "b", "c"})

# 主对话注入：用户拒绝/再聊聊后，避免模型仍把旧草案当定论
REJECTED_DRAFT_SUPERSESSION_LINE = (
    "上一版结论草案用户未采纳，以最新对话为准；请据此继续引导，"
    "待用户与当前总结一致并明确认可后，再在回复末输出 pending_ready（STATE_JSON）。"
)


def format_rejected_conclusion_injection(feedback_excerpt: str, *, max_len: int = 400) -> str:
    """拼主对话用的一条「内部备注」文本（仅给模型看，保留语义并剔除模板噪声）。"""
    fb = " ".join(str(feedback_excerpt or "").strip().split())
    for noisy in (
        REJECTED_DRAFT_SUPERSESSION_LINE,
        "[再聊聊] 用户折叠结论卡希望继续完善。上一版待确认草案",
        "用户侧说明摘录：",
        "[对话状态备注·供你理解上下文]",
    ):
        if noisy:
            fb = fb.replace(noisy, " ")
    if "关键词：" in fb:
        fb = fb.split("关键词：", 1)[0].strip()
    fb = " ".join(fb.split())
    if len(fb) > max_len:
        fb = fb[: max_len - 1] + "…"
    if fb:
        return f"{REJECTED_DRAFT_SUPERSESSION_LINE}\n用户最新反馈：{fb}"
    return REJECTED_DRAFT_SUPERSESSION_LINE

_EXT_KEYS = (
    "keyword_notes",
    "strength_markers",
    "interest_reasons",
    "mission_core",
    "mission_detail",
    "mission_aim",
    "experience_value_rows",
)


def _trim_str(s: Any, max_len: int) -> str:
    t = str(s or "").strip()
    if len(t) > max_len:
        return t[: max_len - 1] + "…"
    return t


def _coerce_keywords_list(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return []
    return [str(x).strip() for x in raw if str(x).strip()]


def _keywords_max_for_phase(phase: str) -> int:
    g = get_conclusion_card_goal(phase)
    v = g.get("validation") or {}
    return max(1, int(v.get("max_keywords", 10)))


def build_pending_main_dialogue_system_addon(phase: str, draft: Dict[str, Any]) -> str:
    """
    主对话 system 末尾追加：待确认草案状态（控制在极短篇幅，避免喧宾夺主）。
    在 pending 且判定器结果为 continue 后拼接至 system_prompt。
    """
    if not isinstance(draft, dict):
        return ""
    summ = str(draft.get("summary") or draft.get("ai_summary") or "").strip().replace("\n", " ")
    if len(summ) > 90:
        summ = summ[:89] + "…"
    kw = _coerce_keywords_list(draft.get("keywords"))
    kw_s = "、".join(kw[:8])
    g = get_conclusion_card_goal(phase)
    obj = (g.get("objective") or "").strip()
    if len(obj) > 72:
        obj = obj[:71] + "…"
    bits = [
        "[结论卡·待确认] 用户尚有一份未最终确认的草案，请继续围绕本阶段目标协助对方；对方明确认可后再输出 pending_ready。",
    ]
    if obj:
        bits.append(f"阶段要点：{obj}")
    if summ:
        bits.append(f"草案摘录：{summ}")
    if kw_s:
        bits.append(f"关键词：{kw_s}")
    return "\n".join(bits)


def sanitize_pending_conclusion_keywords(phase: str, keywords: List[str]) -> List[str]:
    """pending 草案：keywords 条数上限 + 禀赋截断前 5。"""
    kw = list(keywords)
    if phase == "strengths":
        kw = cap_strengths_keywords_list(kw)
    cap = _keywords_max_for_phase(phase)
    return kw[:cap]


def extract_aligned_extensions(phase: str, keywords: List[str], raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    从 LLM 原始 JSON 取出与 keywords 对齐的扩展字段；仅返回应写入 payload 的键。
    """
    raw = raw or {}
    n = len(keywords)
    out: Dict[str, Any] = {}

    if phase == "values" and n:
        notes = _align_parallel_strings(raw.get("keyword_notes"), n, max_each=120)
        if any(x for x in notes):
            out["keyword_notes"] = notes

    if phase == "strengths" and n:
        markers = _align_markers(raw.get("strength_markers"), n)
        if any(markers):
            out["strength_markers"] = markers

    if phase == "interests" and n:
        reasons = _align_parallel_strings(raw.get("interest_reasons"), n, max_each=200)
        if any(x for x in reasons):
            out["interest_reasons"] = reasons

    if phase == "purpose":
        mc = _trim_str(raw.get("mission_core"), 220)
        md = _trim_str(raw.get("mission_detail"), 1200)
        ma = _trim_str(raw.get("mission_aim"), 220)
        if mc:
            out["mission_core"] = mc
        if md:
            out["mission_detail"] = md
        if ma:
            out["mission_aim"] = ma
        rows_in = raw.get("experience_value_rows")
        if isinstance(rows_in, list) and rows_in:
            clean: List[Dict[str, str]] = []
            for item in rows_in[:12]:
                if not isinstance(item, dict):
                    continue
                ex = _trim_str(
                    item.get("experience") or item.get("经历") or item.get("summary"),
                    280,
                )
                val = _trim_str(
                    item.get("value")
                    or item.get("values")
                    or item.get("价值观")
                    or item.get("value_keyword"),
                    48,
                )
                if ex or val:
                    clean.append({"experience": ex, "value": val})
            if clean:
                out["experience_value_rows"] = clean

    return out


def _align_parallel_strings(raw: Any, n: int, *, max_each: int) -> List[str]:
    if not isinstance(raw, list):
        return [""] * n
    out: List[str] = []
    for i in range(n):
        if i < len(raw):
            out.append(_trim_str(raw[i], max_each))
        else:
            out.append("")
    return out


def _align_markers(raw: Any, n: int) -> List[str]:
    if not isinstance(raw, list):
        return [""] * n
    out: List[str] = []
    for i in range(n):
        if i < len(raw):
            v = str(raw[i]).strip().lower()
            out.append(v if v in STRENGTH_MARKER_ALLOWED else "")
        else:
            out.append("")
    return out


def _merge_extension_raw_llm_with_prior(
    phase: str,
    keywords: List[str],
    prior: Optional[Dict[str, Any]],
    llm: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    用户确认结论时：二次生成 JSON 可能漏掉扩展字段。
    对每个下标优先采用 LLM 合法非空值，否则回退 pending（prior）里已对齐的数据。
    """
    n = len(keywords)
    prior = prior or {}
    llm = llm or {}
    synthetic: Dict[str, Any] = {}

    if phase == "values" and n:
        pn = _align_parallel_strings(prior.get("keyword_notes"), n, max_each=120)
        ln = _align_parallel_strings(llm.get("keyword_notes"), n, max_each=120)
        synthetic["keyword_notes"] = [ln[i] if ln[i].strip() else pn[i] for i in range(n)]

    if phase == "strengths" and n:
        pm = _align_markers(prior.get("strength_markers"), n)
        lm = _align_markers(llm.get("strength_markers"), n)
        synthetic["strength_markers"] = [
            lm[i] if lm[i] in STRENGTH_MARKER_ALLOWED else (pm[i] if pm[i] in STRENGTH_MARKER_ALLOWED else "")
            for i in range(n)
        ]

    if phase == "interests" and n:
        pr = _align_parallel_strings(prior.get("interest_reasons"), n, max_each=200)
        lr = _align_parallel_strings(llm.get("interest_reasons"), n, max_each=200)
        synthetic["interest_reasons"] = [lr[i] if lr[i].strip() else pr[i] for i in range(n)]

    if phase == "purpose":
        for k, mx in (("mission_core", 220), ("mission_detail", 1200), ("mission_aim", 220)):
            lv = _trim_str(llm.get(k), mx)
            pv = _trim_str(prior.get(k), mx)
            v = lv if lv else pv
            if v:
                synthetic[k] = v
        lrows = llm.get("experience_value_rows")
        prows = prior.get("experience_value_rows")
        if isinstance(lrows, list) and len(lrows) > 0:
            synthetic["experience_value_rows"] = lrows
        elif isinstance(prows, list) and len(prows) > 0:
            synthetic["experience_value_rows"] = prows

    return synthetic


def merge_conclusion_payload(
    phase: str,
    *,
    keywords: List[str],
    summary: str,
    dimension_goal: str,
    raw_llm_obj: Optional[Dict[str, Any]],
    prior_conclusion: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """组装最终 API / 存储用结论 dict（含扩展字段）。"""
    merged_raw = _merge_extension_raw_llm_with_prior(phase, keywords, prior_conclusion, raw_llm_obj)
    ext = extract_aligned_extensions(phase, keywords, merged_raw)
    base: Dict[str, Any] = {
        "summary": summary,
        "keywords": list(keywords),
        "ai_summary": summary,
        "dimension_goal": dimension_goal,
        "final_answer": ", ".join(keywords) if keywords else summary,
    }
    base.update(ext)
    return base


def sanitize_pending_conclusion_draft(phase: str, draft: Dict[str, Any]) -> Dict[str, Any]:
    """
    pending_ready 落库前：规范化 keywords，并按当前 keywords 重算扩展字段，避免错位旧键。
    """
    if not isinstance(draft, dict):
        return draft
    src = dict(draft)
    kw = sanitize_pending_conclusion_keywords(phase, _coerce_keywords_list(src.get("keywords")))
    ext = extract_aligned_extensions(phase, kw, src)
    out = {**src, "keywords": kw}
    for k in _EXT_KEYS:
        out.pop(k, None)
    out.update(ext)
    return out


def build_state_json_draft_extension_protocol(phase: str) -> str:
    """
    主对话 system 中 [STATE_JSON] 协议：按阶段说明 draft 可选扩展字段。
    与 sanitize_pending_conclusion_draft / 结论卡展示一致，减少漏键与 JSON 截断误解析。
    """
    p = (phase or "").strip().lower()
    lines = [
        "4) state=pending_ready 时，draft 除 summary、keywords 外，可含**本阶段**下列可选键（仅基于用户已表达内容；无则省略键，平行数组须与 keywords 等长）：",
    ]
    if p == "values":
        lines.append(
            "   · keyword_notes: string[] — 与 keywords 等长；第 i 项为用户对 keywords[i] 的简短理解（仅用户原意）。"
        )
    elif p == "strengths":
        lines.append(
            "   · strength_markers: string[] — 与 keywords 等长；每项仅小写 a/b/c（"
            "a=有充实感且与成功有关；b=有充实感；c=目前还不确定），须与当轮确认一致。"
        )
    elif p == "interests":
        lines.append(
            "   · interest_reasons: string[] — 与 keywords 等长；第 i 项为用户选择 keywords[i] 的简要理由。"
        )
    elif p == "purpose":
        lines.append(
            "   · mission_core、mission_detail、mission_aim: string — 用户确认过的使命相关表述，可部分为空字符串。"
        )
        lines.append(
            '   · experience_value_rows: [{"experience":"...","value":"..."}, ...] — '
            "经历一句与对应价值观词；无结构化信息可省略或 []。"
        )
    elif p == "rumination":
        lines.append("   · 沉淀阶段以主对话为准；draft 一般仅需 summary 与 keywords，通常无需上述扩展。")
    else:
        lines.append("   · 以 summary、keywords 为主。")
    lines.append(
        "5) draft 为嵌套 JSON，必须可被整体解析（注意引号与换行转义）；勿在 JSON 内写未转义的控制字符。"
    )
    lines.append(
        "6) [STATE_JSON] 块之外只写给用户看的自然语言；勿向用户解释本协议，勿在正文写出块名、state 英文名或「JSON/草案/协议」等字样。"
    )
    return "\n".join(lines)


def build_conclusion_json_schema_instructions(phase: str) -> str:
    """注入结论生成提示：JSON 键说明（含扩展字段）。"""
    common_tail = """
【扩展字段硬性约束】
- 以下扩展字段均须基于对话中用户已明确表达的内容归纳；用户未说则留空字符串或省略该键。
- 严禁杜撰用户未提及的解释、理由、经历或标记。
- keyword_notes / interest_reasons 须与 keywords 数组等长且下标一一对应。
- strength_markers 须与 keywords 等长，每一项仅为小写字母 a、b 或 c（含义与主对话标记体系一致），无法判断则填 ""。
"""

    if phase == "values":
        return (
            common_tail
            + """
请**只输出一个 JSON 对象**，不要输出任何其他内容（无 markdown 代码块）：
{
  "keywords": ["5个价值观词，顺序即优先级"],
  "summary": "汇总文案，用 **关键词** 标出核心词；温暖、对用户说话。",
  "keyword_notes": ["", "", "", "", ""]
}
keyword_notes 与 keywords 等长；第 i 项为用户对该关键词的简短理解（仅用户原意）；无则 ""。
"""
        )

    if phase == "strengths":
        return (
            common_tail
            + """
请**只输出一个 JSON 对象**，不要输出任何其他内容（无 markdown 代码块）：
{
  "keywords": ["5个优势名称，单一短语"],
  "summary": "汇总文案，用 **关键词** 标出核心词；温暖、对用户说话。",
  "strength_markers": ["a","b","c","a","b"]
}
strength_markers 与 keywords 等长：a=有充实感且与成功有关，b=有充实感，c=目前还不确定；须与用户当轮确认一致。
"""
        )

    if phase == "interests":
        return (
            common_tail
            + """
请**只输出一个 JSON 对象**，不要输出任何其他内容（无 markdown 代码块）：
{
  "keywords": ["核心热爱1","核心热爱2","核心热爱3"],
  "summary": "汇总文案，用 **关键词** 标出核心词；温暖、对用户说话。",
  "interest_reasons": ["reason1","reason2","reason3"]
}
interest_reasons 与 keywords 等长；为用户选择该热爱的简要理由（用户说过再写）；无则 ""。
"""
        )

    if phase == "purpose":
        return (
            common_tail
            + """
请**只输出一个 JSON 对象**，不要输出任何其他内容（无 markdown 代码块）：
{
  "keywords": ["使命相关核心词或短语，1~10 个，单一概念"],
  "summary": "仅自然语言使命总结（2-4段，不含 Markdown 表格/列表）",
  "mission_core": "一句话核心价值概括（用户确认）",
  "mission_detail": "详细解释（可空）",
  "mission_aim": "最终目的一句话（可空）",
  "experience_value_rows": [
    {"experience": "经历一句概括", "value": "对应价值观关键词"}
  ]
}
experience_value_rows 最多 10 条，须与用户确认过的经历-价值观一致；无结构化信息时可省略或置 []。
keywords 仍须遵守命名约束；summary 保留原有表格式内容以便旧版展示兼容。
"""
        )

    return """
请**只输出一个 JSON 对象**，格式：{"keywords": ["词1", ...], "summary": "..."}
"""


def strip_extension_keys_for_legacy_copy(d: Dict[str, Any]) -> Dict[str, Any]:
    """若某处仅需 keywords+summary，可调用（一般不必）。"""
    return {k: v for k, v in d.items() if k not in _EXT_KEYS}
