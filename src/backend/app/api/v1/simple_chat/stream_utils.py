"""
SSE 流处理工具：隐藏协议块过滤、STATE_JSON 解析、JSON 提取。
"""
import json
import re
from typing import Callable, Dict, Optional, Sequence, Tuple


def extract_json_object(text: str) -> Optional[Dict]:
    """从文本中提取首个 JSON object。"""
    if not text:
        return None
    s = text.strip()
    start = s.find("{")
    end = s.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(s[start : end + 1])
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


def extract_state_content_tokens(text: str) -> Optional[Dict]:
    """从约定 token 中提取状态与展示文案。"""
    if not text:
        return None
    s = text.strip()
    state_match = re.search(r"<STATE>\s*(confirmed|rejected|continue)\s*</STATE>", s, flags=re.IGNORECASE)
    content_match = re.search(r"<CONTENT>\s*(.*?)\s*</CONTENT>", s, flags=re.IGNORECASE | re.DOTALL)
    if not state_match:
        return None
    state = (state_match.group(1) or "").strip().lower()
    content = (content_match.group(1) or "").strip() if content_match else ""
    return {"state": state, "content": content}


def looks_like_markdown_table(text: str) -> bool:
    if not text:
        return False
    has_row = bool(re.search(r"^\s*\|.+\|\s*$", text, flags=re.MULTILINE))
    has_sep = bool(re.search(r"^\s*\|[\s:\-|]+\|\s*$", text, flags=re.MULTILINE))
    return has_row and has_sep


def split_visible_reply_and_row_state(raw_text: str) -> tuple[str, Optional[Dict]]:
    """从模型输出拆分可见文本与 [ROW_STATE_JSON] … 块（子步 3 逐行解锁）。

    用 regex 先剥离所有已闭合的 ROW_STATE_JSON 块，取最后一个有内容的块解析。
    """
    if not raw_text:
        return "", None
    start_marker = "[ROW_STATE_JSON]"
    end_marker = "[/ROW_STATE_JSON]"
    import re
    # 收集所有已闭合的 ROW_STATE_JSON 块内容（取最后一个有内容的）
    last_json_str: Optional[str] = None
    for m in re.finditer(
        re.escape(start_marker) + r"(.*?)" + re.escape(end_marker),
        raw_text,
        flags=re.DOTALL,
    ):
        candidate = m.group(1).strip()
        if candidate:
            last_json_str = candidate
    # 从文本中移除所有已闭合块
    visible = re.sub(
        re.escape(start_marker) + r".*?" + re.escape(end_marker),
        "",
        raw_text,
        flags=re.DOTALL,
    ).strip()
    if not last_json_str:
        return visible, None
    try:
        obj = json.loads(last_json_str)
        return visible, obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, TypeError):
        return visible, None


STEP3_HYP_JSON_START = "[STEP3_HYP_JSON]"
STEP3_HYP_JSON_END = "[/STEP3_HYP_JSON]"


def extract_step3_hyp_json(raw_text: str) -> tuple[str, list[str], Optional[int]]:
    """从 [STEP3_HYP_JSON] 块提取假设与目标行，返回 (清理后文本, 候选列表, row 或 None)。"""
    if not raw_text:
        return "", [], None
    import re

    row: Optional[int] = None
    candidates: list[str] = []
    visible = raw_text
    for m in re.finditer(
        re.escape(STEP3_HYP_JSON_START) + r"(.*?)" + re.escape(STEP3_HYP_JSON_END),
        raw_text,
        flags=re.DOTALL,
    ):
        json_str = m.group(1).strip()
        if not json_str:
            continue
        try:
            obj = json.loads(json_str)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(obj, dict):
            continue
        raw_cands = obj.get("candidates")
        if isinstance(raw_cands, list):
            parsed = [str(c).strip() for c in raw_cands if str(c).strip()]
            if parsed:
                candidates = parsed
        raw_row = obj.get("row")
        if raw_row is not None:
            try:
                row = int(raw_row)
            except (TypeError, ValueError):
                row = None
    visible = re.sub(
        re.escape(STEP3_HYP_JSON_START) + r".*?" + re.escape(STEP3_HYP_JSON_END),
        "",
        visible,
        flags=re.DOTALL,
    ).strip()
    return visible, candidates, row


def extract_step3_hyp_output(raw_text: str) -> tuple[str, list[str], Optional[int]]:
    """解析子步 3 假设输出：优先 STEP3_HYP_JSON，兼容 legacy [HYP_CANDIDATE] 块。"""
    visible, candidates, row = extract_step3_hyp_json(raw_text)
    if candidates:
        return visible, candidates, row
    visible_legacy, legacy_cands = extract_hyp_candidates(raw_text)
    return visible_legacy, legacy_cands, None


def extract_hyp_candidates(raw_text: str) -> tuple[str, list[str]]:
    """从模型输出提取 [HYP_CANDIDATE]...[/HYP_CANDIDATE] 块，返回 (清理后文本, 候选假设列表)。"""
    if not raw_text:
        return "", []
    start_marker = "[HYP_CANDIDATE]"
    end_marker = "[/HYP_CANDIDATE]"
    candidates: list[str] = []
    txt = raw_text
    while True:
        s = txt.find(start_marker)
        e = txt.find(end_marker)
        if s < 0 or e < 0 or e <= s:
            break
        candidate = txt[s + len(start_marker) : e].strip()
        if candidate:
            candidates.append(candidate)
        txt = txt[:s] + txt[e + len(end_marker) :]
    return txt.strip(), candidates


def split_visible_reply_and_state(raw_text: str) -> tuple[str, Optional[Dict]]:
    """
    从模型输出中拆分用户可见文本和状态 JSON。
    格式：
      ...用户可见文本...
      [STATE_JSON]
      {...}  <!-- draft 内可嵌套对象，禁止用 \\{.*?\\} 非贪婪匹配，否则会截断在首个 } -->
      [/STATE_JSON]
    """
    if not raw_text:
        return "", None
    start_marker = "[STATE_JSON]"
    end_marker = "[/STATE_JSON]"
    start = raw_text.rfind(start_marker)
    end = raw_text.rfind(end_marker)
    if start < 0 or end < 0 or end <= start:
        return raw_text.strip(), None
    json_part = raw_text[start + len(start_marker) : end].strip()
    visible = raw_text[:start].rstrip()
    try:
        obj = json.loads(json_part)
        return visible, obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, TypeError):
        return (visible if visible else raw_text.strip()), None


def strip_hidden_blocks_for_stream(
    raw_text: str,
    block_markers: Sequence[Tuple[str, str]],
) -> str:
    """
    流式展示时隐藏协议块（可配置起止标记）：
    - 去掉已闭合 start...end
    - 若出现未闭合 start，从 start 起全部截断
    - 末尾若是 start 的前缀片段，先暂存不输出，避免闪现
    """
    if not raw_text:
        return ""
    txt = raw_text
    for start_marker, end_marker in block_markers:
        if not start_marker or not end_marker:
            continue
        txt = re.sub(
            f"{re.escape(start_marker)}.*?{re.escape(end_marker)}",
            "",
            txt,
            flags=re.DOTALL,
        )
        start = txt.find(start_marker)
        if start >= 0:
            txt = txt[:start]
        hold = 0
        max_k = min(len(start_marker) - 1, len(txt))
        for k in range(max_k, 0, -1):
            if txt.endswith(start_marker[:k]):
                hold = k
                break
        if hold:
            txt = txt[:-hold]
    return txt


def build_stream_hidden_block_filter(
    block_markers: Sequence[Tuple[str, str]],
) -> Callable[[str], str]:
    """
    构建"累计文本 -> 本次可见增量"的过滤器。
    通过闭包持有已输出内容，确保 SSE chunk 增量一致。
    """
    emitted_visible = ""

    def consume(cumulative_raw_text: str) -> str:
        nonlocal emitted_visible
        visible = strip_hidden_blocks_for_stream(cumulative_raw_text, block_markers)
        if len(visible) <= len(emitted_visible):
            return ""
        delta = visible[len(emitted_visible) :]
        emitted_visible = visible
        return delta

    return consume


def normalize_token_usage(usage: Optional[dict]) -> dict:
    usage = usage or {}
    in_tokens = int(usage.get("prompt_tokens") or 0)
    out_tokens = int(usage.get("completion_tokens") or 0)
    total = int(usage.get("total_tokens") or (in_tokens + out_tokens))
    result = {
        "prompt_tokens": in_tokens,
        "completion_tokens": out_tokens,
        "total_tokens": total,
    }
    if "prompt_cache_hit_tokens" in usage:
        result["prompt_cache_hit_tokens"] = usage["prompt_cache_hit_tokens"]
    if "prompt_cache_miss_tokens" in usage:
        result["prompt_cache_miss_tokens"] = usage["prompt_cache_miss_tokens"]
    return result
