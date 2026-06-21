"""子步 3 表格操作与假设候选（HYP_CANDIDATE）流程辅助。

表格操作（选「无」、填假设、重新生成）经 /message/stream 发给 AI；
AI 输出 [HYP_CANDIDATE] 块由 stream_utils.extract_hyp_candidates 解析。

设计原则：
- 程序只做确定性判断（表格操作、点选行、cursor、已解锁行范围）。
- 何时出假设、无点选时讨论哪一行，交给 AI（主对话 + fallback 上下文 retry）。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.utils.rumination_ops import is_rumination_step3_row_hypothesis_complete

HYP_FIELD = "用户确认的假设"

STEP3_GUIDE_PHRASE = "你可以点击下方的建议快速填入左侧表格"
# matrix 模式专用引导句（结论卡而非表格）。AI 输出 chips 时配合说出此句，
# 后端 guide_phrase_present_in_reply 检测到此句 + 无 chips → 触发 fallback retry。
STEP3_GUIDE_PHRASE_MATRIX = "你可以点击下方的建议快速填入左侧结论卡"
# 所有引导句集合（用于检测与过滤）
_STEP3_GUIDE_PHRASES = (STEP3_GUIDE_PHRASE, STEP3_GUIDE_PHRASE_MATRIX)


def sanitize_hyp_candidates(candidates: List[str]) -> List[str]:
    """过滤误解析为候选的内容（如引导语本身、过短占位）。"""
    out: list[str] = []
    for c in candidates or []:
        t = str(c or "").strip()
        if not t:
            continue
        if any(p in t for p in _STEP3_GUIDE_PHRASES):
            continue
        if len(t) < 6:
            continue
        out.append(t)
    return out


def guide_phrase_present_in_reply(*texts: str) -> bool:
    """在原始或清洗后的回复中检测引导语（清洗可能移除含引导语的协议块）。
    同时识别 discussion（左侧表格）与 matrix（左侧结论卡）两套引导句。"""
    for text in texts:
        if not text:
            continue
        if any(p in text for p in _STEP3_GUIDE_PHRASES):
            return True
    return False


def row_hyp(row: Dict[str, Any]) -> str:
    return str(row.get(HYP_FIELD) or "").strip()


def row_fields_line(row: Dict[str, Any]) -> str:
    passion = str(row.get("热爱") or "").strip()
    strength = str(row.get("优势") or "").strip()
    return f"热爱：{passion or '（未填）'} / 优势：{strength or '（未填）'}"


def get_step3_row_passion_strength(
    filter_table: List[Any],
    row_index: Optional[int],
) -> tuple[str, str]:
    """从 filter_table 取指定行的热爱/优势；无效索引返回空串。"""
    if not isinstance(filter_table, list) or row_index is None:
        return "", ""
    if not (0 <= row_index < len(filter_table)):
        return "", ""
    row = filter_table[row_index]
    if not isinstance(row, dict):
        return "", ""
    passion = str(row.get("热爱") or "").strip()
    strength = str(row.get("优势") or "").strip()
    return passion, strength


def step3_unlocked_row_max_index(cursor: int, filter_table: List[Any]) -> int:
    """已解锁行的最大 index（含当前 cursor 行）：与前端 rowIdx <= rowCursor 一致。"""
    if not isinstance(filter_table, list) or not filter_table:
        return -1
    n = len(filter_table)
    if cursor >= n:
        return n - 1
    return max(0, min(cursor, n - 1))


def format_step3_unlocked_rows_block(filter_table: List[Any], cursor: int) -> str:
    """已解锁、可重新讨论的行摘要（供 AI 从对话中识别「第几行」）。"""
    if not isinstance(filter_table, list) or not filter_table:
        return ""
    max_idx = step3_unlocked_row_max_index(cursor, filter_table)
    if max_idx < 0:
        return ""
    lines: list[str] = []
    for i in range(0, max_idx + 1):
        row = filter_table[i] if isinstance(filter_table[i], dict) else {}
        p = str(row.get("热爱") or "").strip() or "（未填）"
        s = str(row.get("优势") or "").strip() or "（未填）"
        h = str(row.get(HYP_FIELD) or "").strip()
        if not h:
            h = "（未填）"
        elif len(h) > 40:
            h = h[:37] + "..."
        lines.append(f"第 {i + 1} 行（index={i}）：热爱={p} / 优势={s} / 假设={h}")
    if not lines:
        return ""
    return (
        "[内部·子步3已解锁行]\n"
        "以下行用户可在左侧表格查看；任意已解锁行均可重新讨论或重新生成假设。\n"
        "若用户未点选表格但在对话中提到某行或某组热爱×优势，请据此识别目标行。\n"
        + "\n".join(lines)
    )


def resolve_step3_explicit_row_index(
    *,
    filter_table: List[Any],
    rumination_row_index: Optional[int],
    step3_action_row: Optional[int],
) -> Optional[int]:
    """程序明确知道的目标行：点选行或表格操作行（不含 cursor 兜底）。"""
    if not isinstance(filter_table, list):
        return None
    if step3_action_row is not None and 0 <= step3_action_row < len(filter_table):
        return int(step3_action_row)
    if rumination_row_index is not None and 0 <= rumination_row_index < len(filter_table):
        return int(rumination_row_index)
    return None


def resolve_step3_cursor_row_index(
    filter_table: List[Any],
    cursor: int,
) -> Optional[int]:
    """当前推进行（system 注入 [内部·子步3当前行] 用）。"""
    if not isinstance(filter_table, list) or not filter_table:
        return None
    if 0 <= cursor < len(filter_table):
        return int(cursor)
    if cursor >= len(filter_table):
        return len(filter_table) - 1
    return None


def resolve_step3_target_row_index(
    *,
    filter_table: List[Any],
    cursor: int,
    rumination_row_index: Optional[int],
    step3_action_row: Optional[int],
) -> Optional[int]:
    """显式行优先，否则 cursor（用于日志 / 显式 fallback）。"""
    explicit = resolve_step3_explicit_row_index(
        filter_table=filter_table,
        rumination_row_index=rumination_row_index,
        step3_action_row=step3_action_row,
    )
    if explicit is not None:
        return explicit
    return resolve_step3_cursor_row_index(filter_table, cursor)


def resolve_step3_prompt_mode(
    *,
    step3_table_action: Optional[str],
) -> str:
    """forward | discuss"""
    action = (step3_table_action or "").strip()
    if action in ("select_none", "fill_hypothesis"):
        return "forward"
    return "discuss"


_FORWARD_TABLE_MARKERS = ("[表格操作·选无]", "[表格操作·填假设]")


def _llm_message_role(msg: Any) -> str:
    if isinstance(msg, dict):
        return str(msg.get("role") or "")
    return str(getattr(msg, "role", None) or "")


def _llm_message_content(msg: Any) -> str:
    if isinstance(msg, dict):
        return str(msg.get("content") or "")
    return str(getattr(msg, "content", None) or "")


def count_discuss_user_turns_since_last_forward(llm_messages: list) -> int:
    """自上次表格推进（选无/填假设）以来，用户普通 discuss 消息条数（不含表格操作）。"""
    count = 0
    for msg in reversed(llm_messages or []):
        if _llm_message_role(msg) != "user":
            continue
        content = _llm_message_content(msg)
        if any(marker in content for marker in _FORWARD_TABLE_MARKERS):
            break
        if "[表格操作·重新生成]" in content:
            break
        count += 1
    return count


def visible_reply_suggests_hyp_delivery(visible_reply: str) -> bool:
    """可见回复不像「纯提问」：不以问号结尾。"""
    text = (visible_reply or "").strip()
    if not text:
        return False
    return not (text.endswith("?") or text.endswith("？"))


def should_trigger_hyp_candidate_fallback(
    *,
    hyp_candidates: List[str],
    step3_table_action: Optional[str],
    step3_prompt_mode: str,
    visible_reply: str = "",
    explicit_row_index: Optional[int] = None,
    discuss_user_turns_since_forward: int = 0,
    guide_phrase_present: bool = False,
) -> bool:
    """主回复未解析出有效 hyp_candidates 时，是否触发兜底 retry（分层触发，避免 discuss 每轮都 retry）。"""
    effective = sanitize_hyp_candidates(hyp_candidates)
    if len(effective) >= 2:
        return False
    if step3_table_action in ("select_none", "fill_hypothesis"):
        return False
    if step3_prompt_mode == "forward":
        return False
    if step3_prompt_mode != "discuss":
        return False

    has_guide = guide_phrase_present or guide_phrase_present_in_reply(visible_reply)

    # 第一层：高置信 — 必 retry
    if step3_table_action == "regenerate_hyp":
        return True
    if explicit_row_index is not None:
        return True
    if has_guide:
        return True
    # 原候选有内容但 sanitize 后为空（如引导语被误包进 HYP_CANDIDATE）
    if hyp_candidates and not effective:
        return True

    # 第二层：用户已聊过 + 回复不像纯提问
    if (
        discuss_user_turns_since_forward >= 1
        and visible_reply_suggests_hyp_delivery(visible_reply)
    ):
        return True

    return False


def count_step3_confirmed_rows(filter_table: List[Any]) -> int:
    """测试/统计：已填写假设的行数。"""
    if not isinstance(filter_table, list):
        return 0
    return sum(
        1
        for r in filter_table
        if isinstance(r, dict)
        and is_rumination_step3_row_hypothesis_complete(r.get(HYP_FIELD))
    )


def validate_step3_hyp_target_row(
    row_index: Optional[int],
    cursor: int,
    filter_table: List[Any],
) -> Optional[int]:
    """校验 AI/显式声明的行号是否在已解锁范围内；无效则返回 None。"""
    if row_index is None or not isinstance(filter_table, list):
        return None
    try:
        idx = int(row_index)
    except (TypeError, ValueError):
        return None
    max_idx = step3_unlocked_row_max_index(cursor, filter_table)
    if max_idx < 0:
        return None
    if 0 <= idx <= max_idx:
        return idx
    return None


def is_strict_hyp_candidate_retry(*texts: str) -> bool:
    """主回复已含引导语却无有效假设 → strict retry（必须 function call 出假设+行号）。"""
    return guide_phrase_present_in_reply(*texts)


def resolve_step3_hyp_delivery(
    *,
    candidates: List[str],
    cursor: int,
    filter_table: List[Any],
    explicit_row_index: Optional[int],
    ai_declared_row: Optional[int],
) -> tuple[Optional[int], bool]:
    """解析假设应填入的行号。

    Returns:
        (hyp_target_row, hyp_row_unresolved)
        - 无 candidates 时 (None, False)
        - 有 candidates 但无法确定合法行时 (None, True)
    """
    if not candidates:
        return None, False

    if explicit_row_index is not None:
        validated = validate_step3_hyp_target_row(explicit_row_index, cursor, filter_table)
        if validated is not None:
            return validated, False

    if ai_declared_row is not None:
        validated = validate_step3_hyp_target_row(ai_declared_row, cursor, filter_table)
        if validated is not None:
            return validated, False

    return None, True


def parse_step3_hyp_tool_call(tool_calls: Optional[List[Any]]) -> tuple[list[str], Optional[int]]:
    """从 function call 解析 submit_step3_hypotheses 的参数。"""
    if not tool_calls:
        return [], None
    for tc in tool_calls:
        if isinstance(tc, dict):
            fn = tc.get("function") or {}
            name = str(fn.get("name") or "")
            args_raw = fn.get("arguments") or ""
        else:
            fn = getattr(tc, "function", None)
            name = getattr(fn, "name", "") if fn else ""
            args_raw = getattr(fn, "arguments", "") if fn else ""
        if name != "submit_step3_hypotheses":
            continue
        try:
            args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(args, dict):
            continue
        raw_cands = args.get("candidates")
        candidates: list[str] = []
        if isinstance(raw_cands, list):
            candidates = [str(c).strip() for c in raw_cands if str(c).strip()]
        row: Optional[int] = None
        if args.get("row") is not None:
            try:
                row = int(args["row"])
            except (TypeError, ValueError):
                row = None
        if candidates:
            return candidates, row
    return [], None
