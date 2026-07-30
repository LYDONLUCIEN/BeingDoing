"""
Rumination v4 Service

combo_session 管理:
- CRUD(create / get / list / delete / patch)
- tool handler(update_field / save_conclusion_card)
- 平衡点(balance_found / balance_fail_reason)与再评估闸
- 兜底机制(双信号监测 + 异步补全)
- chips 候选隐藏块解析([STEP3_HYP_JSON])
- 后台 30 轮滚动摘要

实施契约: wiki/开发文档/7-25-rumination-v4-实施口径.md §2.2

存储: data/simple/reports/{report_id}/rumination_v4_progress.json (独立文件,与 v3 物理隔离)
删除 = 从 combo_sessions 数组移除该元素(含 messages,彻底消失)
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.domain.rumination_v4_prompt import (
    render_conclusion_prompt,
    render_mega_prompt,
    render_summarizer_prompt,
)

logger = logging.getLogger(__name__)

# ── 协议常量(与 prompt 双信号约定一致)─────────────────────────────────
CONCLUSION_READY_MARKER = "<<CONCLUSION_READY>>"
# 用户可见话术的锚点短语(后端包含监测;旧句式「现在我为你总结了 N 个假设」已废弃)
CONCLUSION_VISIBLE_PHRASE_KEYWORDS = ("整理成了结论卡",)
# tool call 隐藏块标记
TOOL_BLOCK_REGEX = re.compile(r"```tool\s*(\{.*?\})\s*```", re.DOTALL)

# chips 候选隐藏块协议(复用 v3 同款,后端解析、前端渲染为可点击选项)
HYP_JSON_START = "[STEP3_HYP_JSON]"
HYP_JSON_END = "[/STEP3_HYP_JSON]"

# SSE 流式隐藏块标记(跨 chunk 过滤,复用 v3 stream_utils):
# tool 块 / chips 候选块 / 结论就绪标记在流式阶段即对前端隐藏,落库前再统一剥离解析
STREAM_HIDDEN_BLOCK_MARKERS: Tuple[Tuple[str, str], ...] = (
    ("```tool", "```"),
    (HYP_JSON_START, HYP_JSON_END),
    (CONCLUSION_READY_MARKER, CONCLUSION_READY_MARKER),
)
HYP_JSON_BLOCK_REGEX = re.compile(
    re.escape(HYP_JSON_START) + r"(.*?)" + re.escape(HYP_JSON_END), re.DOTALL
)
# 候选最短字数门槛(v3 为 20,v4 放宽到 10;过短的多为纯标签,无画面感)
HYP_CANDIDATE_MIN_LEN = 10

# 触发阈值
SUMMARIZE_EVERY_N_ROUNDS = 30  # 每 30 轮触发滚动摘要
NO_TOOL_SOFT_NUDGE_N_ROUNDS = 15  # (预留)15 轮无 tool 调用 → 软提醒
NO_CONCLUSION_NUDGE_N_ROUNDS = 50  # 50 轮未出结论卡 → 软提醒


# ── 数据 schema(参考 wiki/开发文档/0707-tag1.6.0.md 第三节)─────────────
def default_state(matrix_snapshot: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """v4 全局 rumination_state 默认值。"""
    return {
        "schema_version": 4,
        "matrix_snapshot": matrix_snapshot or {"passions": [], "strengths": []},
        "combo_sessions": [],
        "active_combo_id": None,
        "final_selection": {
            "selected_combo_ids": [],
            "submitted": False,
            "submitted_at": None,
        },
        "main_section": "matrix",
    }


def new_combo_session(
    combo_id: str,
    passion: str,
    strengths: List[str],
) -> Dict[str, Any]:
    """新建单个 combo_session。"""
    now = _now_iso()
    return {
        "combo_id": combo_id,
        "passion": passion,
        "strengths": list(strengths),
        "created_at": now,
        "updated_at": now,
        "status": "discussing",  # discussing | concluded | abandoned
        "messages": [],
        "summary": None,
        "summary_last_round": 0,
        "fields_collected": {
            "motivation": None,
            "hypothesis": None,
            "work_purposes": None,
            "passion_mark": None,
            "timing_mark": None,
            "balance_found": None,
            "balance_fail_reason": None,
        },
        "conclusion_card": None,
        "user_skipped": False,  # 用户手动跳过(卡保留,可逆;置 concluded 即恢复)
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── 存储 IO ─────────────────────────────────────────────────────────────
def _v4_progress_file(reports_root: Path, report_id: str) -> Path:
    """v4 使用独立文件 rumination_v4_progress.json，与 v3 的 rumination_progress.json
    物理隔离。这样同一 report 在 v3/v4 间切换时，两版本数据互不覆盖。"""
    return reports_root / report_id / "rumination_v4_progress.json"


def load_v4_state(reports_root: Path, report_id: str) -> Dict[str, Any]:
    """加载 v4 state。文件不存在或损坏 → 返回默认 v4 state。"""
    path = _v4_progress_file(reports_root, report_id)
    if not path.is_file():
        return default_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return default_state()
    if not isinstance(data, dict):
        return default_state()
    # 归一化(补缺字段);v4 独立文件，不再需要 schema_version 兼容判断
    return _normalize_v4_state(data)


def save_v4_state(reports_root: Path, report_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
    """持久化 v4 state(整文件覆盖写,单文件原子性)。"""
    path = _v4_progress_file(reports_root, report_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    state["schema_version"] = 4
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)  # 原子替换
    return state


def _normalize_v4_state(data: Dict[str, Any]) -> Dict[str, Any]:
    """补全缺失字段。"""
    base = default_state()
    base.update(data)
    base["schema_version"] = 4
    if not isinstance(base.get("combo_sessions"), list):
        base["combo_sessions"] = []
    if not isinstance(base.get("final_selection"), dict):
        base["final_selection"] = {
            "selected_combo_ids": [],
            "submitted": False,
            "submitted_at": None,
        }
    if base.get("main_section") not in ("matrix", "combo_session", "final_selection", "end"):
        base["main_section"] = "matrix"
    return base


# ── combo_session 操作 ─────────────────────────────────────────────────
def list_combos(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """列出所有 combo_session 的元信息(不含 messages)。"""
    out = []
    for c in state.get("combo_sessions") or []:
        out.append(_combo_meta(c))
    return out


def _combo_meta(c: Dict[str, Any]) -> Dict[str, Any]:
    """combo_session 的元信息(给 tag 条/列表用)。"""
    return {
        "combo_id": c.get("combo_id"),
        "passion": c.get("passion"),
        "strengths": c.get("strengths") or [],
        "status": c.get("status"),
        "created_at": c.get("created_at"),
        "updated_at": c.get("updated_at"),
        "has_card": bool(c.get("conclusion_card")),
        "round_count": _count_user_rounds(c.get("messages") or []),
        "user_skipped": bool(c.get("user_skipped")),
    }


def _count_user_rounds(messages: List[Dict[str, Any]]) -> int:
    """统计用户消息数(每条 user 消息 = 1 轮)。"""
    return sum(1 for m in messages if m.get("role") == "user")


def find_combo(state: Dict[str, Any], combo_id: str) -> Optional[Dict[str, Any]]:
    for c in state.get("combo_sessions") or []:
        if c.get("combo_id") == combo_id:
            return c
    return None


def next_combo_id(state: Dict[str, Any]) -> str:
    """生成下一个自增 combo_id(从 1 开始,允许重复子集)。"""
    existing = state.get("combo_sessions") or []
    max_n = 0
    for c in existing:
        cid = str(c.get("combo_id") or "")
        m = re.match(r"^combo_(\d+)$", cid)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"combo_{max_n + 1}"


MAX_COMBOS = 10  # 组合数量上限


def _combo_key(passion: str, strengths: List[str]) -> str:
    """组合的唯一键:passion + 排序后的 strengths(严格集合相等判定)。"""
    return f"{passion.strip()}||{'|'.join(sorted(s.strip() for s in strengths))}"


def find_duplicate_combo(
    state: Dict[str, Any], passion: str, strengths: List[str]
) -> Optional[Dict[str, Any]]:
    """严格集合相等判重:同 passion + 同 strengths 集合 → 返回已存在的 combo,否则 None。"""
    target = _combo_key(passion, strengths)
    for c in state.get("combo_sessions") or []:
        if _combo_key(c.get("passion") or "", c.get("strengths") or []) == target:
            return c
    return None


def create_combo(
    reports_root: Path,
    report_id: str,
    passion: str,
    strengths: List[str],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """创建新 combo_session,设为 active,返回 (state, combo_session)。
    校验:10 上限 + 严格集合判重(重复时抛 ValueError)。"""
    state = load_v4_state(reports_root, report_id)
    existing = state.get("combo_sessions") or []
    if len(existing) >= MAX_COMBOS:
        raise ValueError(f"组合已达上限({MAX_COMBOS}个),请删除已有组合后再新建")
    dup = find_duplicate_combo(state, passion, strengths)
    if dup:
        raise ValueError("已存在相同的热爱+优势组合,请切换或调整优势")
    cid = next_combo_id(state)
    combo = new_combo_session(cid, passion, strengths)
    state.setdefault("combo_sessions", []).append(combo)
    state["active_combo_id"] = cid
    state["main_section"] = "combo_session"
    save_v4_state(reports_root, report_id, state)
    return state, combo


def build_opening_text(passion: str, strengths: List[str]) -> str:
    """生成引导语开场(固定模板 + 个性化占位)。"""
    strengths_str = "、".join(strengths)
    return (
        f"好的,我们就来聊聊「{passion}」+「{strengths_str}」这个组合。\n\n"
        f"在正式展开之前,我想先听听你 —— 是什么吸引你把这个热爱和这几个优势放在一起?"
        f"可以告诉我一个具体的场景,或者一个让你心动的瞬间吗?"
    )


def create_and_start(
    reports_root: Path,
    report_id: str,
    passion: str,
    strengths: List[str],
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """原子操作:创建 combo + 生成引导语开场,返回 (state, combo, opening_msg)。
    - 校验 10 上限 + 严格集合判重(重复/超限抛 ValueError)
    - 创建后立即追加 assistant 开场消息
    """
    state, combo = create_combo(reports_root, report_id, passion, strengths)
    opening_text = build_opening_text(passion, strengths)
    append_message(state, combo["combo_id"], "assistant", opening_text)
    save_v4_state(reports_root, report_id, state)
    # 重新加载拿带 ts 的消息
    state = load_v4_state(reports_root, report_id)
    combo = find_combo(state, combo["combo_id"])
    opening_msg = combo["messages"][-1] if combo.get("messages") else None
    return state, combo, opening_msg


def delete_combo(reports_root: Path, report_id: str, combo_id: str) -> Dict[str, Any]:
    """硬删除 combo_session(从数组移除,含 messages,彻底消失)。
    自动从 final_selection 移除;若删的是 active,active 指向最近一个或 None。"""
    state = load_v4_state(reports_root, report_id)
    before = len(state.get("combo_sessions") or [])
    state["combo_sessions"] = [
        c for c in (state.get("combo_sessions") or []) if c.get("combo_id") != combo_id
    ]
    if len(state["combo_sessions"]) == before:
        raise ValueError(f"combo_id 不存在: {combo_id}")
    # 收敛 final_selection
    fs = state.get("final_selection") or {}
    sel = fs.get("selected_combo_ids") or []
    fs["selected_combo_ids"] = [x for x in sel if x != combo_id]
    state["final_selection"] = fs
    # 收敛 active
    if state.get("active_combo_id") == combo_id:
        remaining = state.get("combo_sessions") or []
        state["active_combo_id"] = remaining[-1].get("combo_id") if remaining else None
        if state["active_combo_id"] is None:
            state["main_section"] = "matrix"
    save_v4_state(reports_root, report_id, state)
    return state


def set_active_combo(reports_root: Path, report_id: str, combo_id: str) -> Dict[str, Any]:
    """切换 active combo(前端 tag 条点击)。"""
    state = load_v4_state(reports_root, report_id)
    if not find_combo(state, combo_id):
        raise ValueError(f"combo_id 不存在: {combo_id}")
    state["active_combo_id"] = combo_id
    state["main_section"] = "combo_session"
    save_v4_state(reports_root, report_id, state)
    return state


def append_message(
    state: Dict[str, Any], combo_id: str, role: str, content: str
) -> Optional[Dict[str, Any]]:
    """向 combo_session 追加一条消息(role ∈ user/assistant/system)。"""
    combo = find_combo(state, combo_id)
    if not combo:
        return None
    combo.setdefault("messages", []).append(
        {"role": role, "content": content, "ts": _now_iso()}
    )
    combo["updated_at"] = _now_iso()
    return combo


# ── tool call 协议解析 ─────────────────────────────────────────────────
def parse_tool_blocks(text: str) -> Tuple[str, List[Dict[str, Any]]]:
    """从 LLM 文本回复中提取隐藏 ```tool``` JSON 块。
    返回 (clean_visible_text, [tool_call_dict, ...])。
    """
    tools: List[Dict[str, Any]] = []
    cleaned = text
    for m in list(TOOL_BLOCK_REGEX.finditer(text)):
        raw = m.group(1).strip()
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict) and obj.get("tool"):
                tools.append(obj)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    # 移除所有 ```tool``` 块
    cleaned = TOOL_BLOCK_REGEX.sub("", text).strip()
    return cleaned, tools


def detect_conclusion_signals(text: str) -> Dict[str, bool]:
    """双信号监测。
    返回 {"hidden": bool, "visible": bool}。
    - hidden: 文本中包含 <<CONCLUSION_READY>> 标记
    - visible: 文本中包含锚点短语「整理成了结论卡」
    """
    hidden = CONCLUSION_READY_MARKER in text
    visible = any(k in text for k in CONCLUSION_VISIBLE_PHRASE_KEYWORDS)
    return {"hidden": hidden, "visible": visible}


# ── chips 候选隐藏块解析 ──────────────────────────────────────────────
def extract_hyp_candidates(text: str) -> Tuple[str, List[str]]:
    """从回复文本解析 chips 候选隐藏块 [STEP3_HYP_JSON]...[/STEP3_HYP_JSON]。

    协议复用 v3 同款(参考 app.api.v1.simple_chat.stream_utils.extract_step3_hyp_json),
    sanitize 逻辑参考 v3 rumination_step3_flow.sanitize_hyp_candidates,
    字数门槛由 20 放宽到 10(实施口径 §2.2)。

    Args:
        text: LLM 完整回复文本

    Returns:
        (剥离隐藏块后的可见文本, 候选假设列表)
    """
    if not text:
        return "", []
    candidates: List[str] = []
    for m in HYP_JSON_BLOCK_REGEX.finditer(text):
        raw = (m.group(1) or "").strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if not isinstance(obj, dict):
            continue
        raw_cands = obj.get("candidates")
        if not isinstance(raw_cands, list):
            continue
        for c in raw_cands:
            t = str(c or "").strip()
            if not t or len(t) < HYP_CANDIDATE_MIN_LEN:
                continue
            if t not in candidates:  # 去重保序
                candidates.append(t)
    visible = HYP_JSON_BLOCK_REGEX.sub("", text).strip()
    return visible, candidates


# ── tool handler ───────────────────────────────────────────────────────
VALID_FIELDS = (
    "motivation",
    "hypothesis",
    "work_purposes",
    "passion_mark",
    "timing_mark",
    "balance_found",
    "balance_fail_reason",
)


def _reset_balance_on_hypothesis_change(
    combo: Dict[str, Any], old_hyp: Any, new_hyp: Any
) -> None:
    """平衡再评估闸(实施口径 §1-新5):hypothesis 内容变化 → balance 两字段置 None。
    fields_collected 与已存在的 conclusion_card 同步重置。"""
    if old_hyp == new_hyp:
        return
    fc = combo.setdefault("fields_collected", {})
    fc["balance_found"] = None
    fc["balance_fail_reason"] = None
    card = combo.get("conclusion_card")
    if isinstance(card, dict):
        card["balance_found"] = None
        card["balance_fail_reason"] = None


def apply_tool_call(
    state: Dict[str, Any],
    combo_id: str,
    tool_call: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """执行一个 tool_call,返回 (conclusion_card_event, error)。
    - update_field: 透明更新 fields_collected,无事件
    - save_conclusion_card: 校验 hypothesis 已填 → 写 conclusion_card → 返回事件
    """
    combo = find_combo(state, combo_id)
    if not combo:
        return None, f"combo_id 不存在: {combo_id}"
    name = (tool_call.get("tool") or "").strip()
    if name == "update_field":
        field = (tool_call.get("field") or "").strip()
        value = tool_call.get("value")
        if field not in VALID_FIELDS:
            return None, f"未知字段: {field}"
        if field == "hypothesis":
            # 平衡再评估闸:hypothesis 变更 → balance 两字段置 None
            _reset_balance_on_hypothesis_change(
                combo, (combo.get("fields_collected") or {}).get("hypothesis"), value
            )
        combo.setdefault("fields_collected", {})[field] = value
        combo["updated_at"] = _now_iso()
        return None, None
    if name == "save_conclusion_card":
        fields = tool_call.get("fields") or {}
        if not isinstance(fields, dict):
            return None, "fields 必须是对象"
        # 校验 hypothesis(必填)
        hyp = fields.get("hypothesis")
        if not _hyp_filled(hyp):
            # 退一步:检查 fields_collected 中是否已有 hypothesis
            existing = (combo.get("fields_collected") or {}).get("hypothesis")
            if not _hyp_filled(existing):
                return None, "hypothesis 未填,无法生成结论卡"
            # 用已有的
            fields.setdefault("hypothesis", existing)
        # 合并到 fields_collected(其他字段也更新)
        # 平衡再评估闸:捕获合并前的旧 hypothesis,变化且本次未显式给 balance_found → 重置
        existing_card = combo.get("conclusion_card") or {}
        old_hyp = existing_card.get("hypothesis") or (
            (combo.get("fields_collected") or {}).get("hypothesis")
        )
        fc = combo.setdefault("fields_collected", {})
        for k in VALID_FIELDS:
            if k in fields and fields[k] is not None:
                fc[k] = fields[k]
        hyp_changed = fields.get("hypothesis") is not None and fields.get("hypothesis") != old_hyp
        if hyp_changed and "balance_found" not in fields:
            fc["balance_found"] = None
            fc["balance_fail_reason"] = None
        # 构造 conclusion_card
        card = {
            "hypothesis": fc.get("hypothesis"),
            "motivation": fc.get("motivation"),
            "work_purposes": fc.get("work_purposes"),
            "passion_mark": fc.get("passion_mark"),
            "timing_mark": fc.get("timing_mark"),
            "balance_found": fc.get("balance_found"),
            "balance_fail_reason": fc.get("balance_fail_reason"),
            "created_at": existing_card.get("created_at") or _now_iso(),
            "updated_at": _now_iso(),
        }
        combo["conclusion_card"] = card
        # 出卡 = 草案,不强制 concluded(2026-07-27 交互口径):
        # 对话不锁定,用户点「确认」后才置 concluded 进终选池;
        # AI 本轮已迭代卡 → 清除「再聊聊」不满意反馈标记
        combo.pop("reopen_feedback", None)
        combo["updated_at"] = _now_iso()
        return card, None
    return None, f"未知 tool: {name}"


def _hyp_filled(hyp: Any) -> bool:
    """hypothesis 是否非空(支持 str 与 dict)。"""
    if hyp is None:
        return False
    if isinstance(hyp, str):
        return bool(hyp.strip())
    if isinstance(hyp, dict):
        return any(bool(v) for v in hyp.values())
    return False


def patch_conclusion_card(
    reports_root: Path,
    report_id: str,
    combo_id: str,
    fields: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """用户直接编辑结论卡文本(走 PATCH 端点,不绕道 LLM)。"""
    state = load_v4_state(reports_root, report_id)
    combo = find_combo(state, combo_id)
    if not combo:
        raise ValueError(f"combo_id 不存在: {combo_id}")
    if combo.get("status") == "abandoned":
        raise ValueError("abandoned(已跳过)的 combo 不可直接编辑结论卡,请先恢复确认")
    card = combo.get("conclusion_card") or {
        "hypothesis": None,
        "motivation": None,
        "work_purposes": None,
        "passion_mark": None,
        "timing_mark": None,
        "balance_found": None,
        "balance_fail_reason": None,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    old_hyp = card.get("hypothesis")
    for k in VALID_FIELDS:
        if k in fields:
            card[k] = fields[k]
    if not _hyp_filled(card.get("hypothesis")):
        raise ValueError("hypothesis 不可清空")
    # 平衡再评估闸:hypothesis 变化且本次未显式给 balance_found → 重置
    if "hypothesis" in fields and card.get("hypothesis") != old_hyp:
        if "balance_found" not in fields:
            card["balance_found"] = None
            card["balance_fail_reason"] = None
    card["updated_at"] = _now_iso()
    combo["conclusion_card"] = card
    # 不强制 concluded:草案期用户手动编辑 ≠ 确认,确认动作统一走 set_combo_status
    combo["updated_at"] = _now_iso()
    save_v4_state(reports_root, report_id, state)
    return state, card


def set_combo_status(
    reports_root: Path, report_id: str, combo_id: str, status: str
) -> Dict[str, Any]:
    """更新 combo_session 状态(discussing/concluded/abandoned)。
    实施口径 §1-新4:abandoned(跳过)不再清空结论卡,仅置 user_skipped=True(可逆);
    concluded(确认)清除 user_skipped。终选只出现 concluded 卡。
    2026-07-27 交互口径:concluded → discussing(用户点「再聊聊」)时写入 reopen_feedback,
    供 build_chat_messages 注入 LLM 上下文(用户对当前结论不满意,继续打磨);
    AI 下次 save_conclusion_card 迭代卡后自动清除。"""
    state = load_v4_state(reports_root, report_id)
    combo = find_combo(state, combo_id)
    if not combo:
        raise ValueError(f"combo_id 不存在: {combo_id}")
    status = (status or "").strip().lower()
    if status not in ("concluded", "abandoned", "discussing"):
        raise ValueError(f"非法 status: {status}")
    prev_status = combo.get("status")
    if status == "abandoned":
        combo["user_skipped"] = True  # 卡内容保留,UI 删除线 + 灰色标记
    else:
        combo["user_skipped"] = False  # concluded/discussing 都清除跳过标记
    if prev_status == "concluded" and status == "discussing" and combo.get("conclusion_card"):
        combo["reopen_feedback"] = (
            "用户看过结论卡后选择「再聊聊」,表示对当前结论还不够满意,希望继续打磨。"
            "请先询问用户:觉得这版结论哪里不合适、缺了什么、或者哪里不打动你?"
            "再根据用户的回答迭代,准备好后重新调 save_conclusion_card 更新结论卡。"
        )
    if status == "concluded":
        combo.pop("reopen_feedback", None)  # 确认即闭环,清除反馈标记
    combo["status"] = status
    combo["updated_at"] = _now_iso()
    save_v4_state(reports_root, report_id, state)
    return state


# ── final_selection(第 8 步)──────────────────────────────────────────
def update_final_selection(
    reports_root: Path,
    report_id: str,
    selected_combo_ids: List[str],
) -> Dict[str, Any]:
    """第 8 步:更新选定的 1-3 个 combo_id(后端校验数量与 status)。"""
    state = load_v4_state(reports_root, report_id)
    fs = state.setdefault("final_selection", {})
    # 防御层：已最终提交的终选不可再改（路由层另有 locked 断言，双保险）
    if fs.get("submitted"):
        raise ValueError("最终选择已提交并锁定，不能再修改")
    if not isinstance(selected_combo_ids, list):
        raise ValueError("selected_combo_ids 必须是数组")
    if len(selected_combo_ids) < 1 or len(selected_combo_ids) > 3:
        raise ValueError("必须选定 1-3 个组合")
    # 校验所有 combo 存在且为已确认结论卡(终选只出现 concluded 且未跳过的卡)
    valid_ids = set()
    for c in state.get("combo_sessions") or []:
        if (
            c.get("conclusion_card")
            and c.get("status") == "concluded"
            and not c.get("user_skipped")
        ):
            valid_ids.add(c.get("combo_id"))
    for cid in selected_combo_ids:
        if cid not in valid_ids:
            raise ValueError(f"combo {cid} 不存在或未确认结论卡")
    fs = state.setdefault("final_selection", {})
    fs["selected_combo_ids"] = selected_combo_ids
    fs["submitted"] = False
    state["main_section"] = "final_selection"
    save_v4_state(reports_root, report_id, state)
    return state


def submit_final_selection(reports_root: Path, report_id: str) -> Dict[str, Any]:
    """第 8 步最终提交(锁定)。"""
    state = load_v4_state(reports_root, report_id)
    fs = state.setdefault("final_selection", {})
    sel = fs.get("selected_combo_ids") or []
    if not (1 <= len(sel) <= 3):
        raise ValueError("必须选定 1-3 个组合")
    fs["submitted"] = True
    fs["submitted_at"] = _now_iso()
    state["main_section"] = "end"
    save_v4_state(reports_root, report_id, state)
    return state


# ── 后台摘要任务 ────────────────────────────────────────────────────────
async def maybe_summarize_combo(
    state: Dict[str, Any],
    combo_id: str,
    llm,
) -> Optional[str]:
    """检查 combo 是否达到摘要阈值(每 30 轮),若是则触发滚动摘要。
    返回新摘要(若有),否则 None。state 不落盘(由调用方负责)。"""
    combo = find_combo(state, combo_id)
    if not combo:
        return None
    messages = combo.get("messages") or []
    user_rounds = _count_user_rounds(messages)
    last_summary_round = int(combo.get("summary_last_round") or 0)
    if user_rounds - last_summary_round < SUMMARIZE_EVERY_N_ROUNDS:
        return None
    # 构造最近对话文本(自上次摘要之后的所有消息)
    prev_summary = combo.get("summary")
    recent = _messages_to_text(messages, since_round=last_summary_round)
    if not recent.strip():
        return None
    from app.core.llmapi import LLMMessage
    prompt = render_summarizer_prompt(prev_summary, recent)
    try:
        resp = await llm.chat([LLMMessage(role="system", content=prompt)], temperature=0.3, max_tokens=600)
        new_summary = (resp.content or "").strip()
        if new_summary:
            combo["summary"] = new_summary
            combo["summary_last_round"] = user_rounds
            return new_summary
    except Exception as e:
        logger.warning("rumination v4 摘要失败 combo=%s: %s", combo_id, e)
    return None


def _messages_to_text(messages: List[Dict[str, Any]], since_round: int = 0) -> str:
    """把 messages 转成可读文本,可指定从第几轮开始(用于摘要增量)。"""
    lines = []
    user_count = 0
    for m in messages:
        role = m.get("role")
        content = m.get("content") or ""
        if role == "user":
            user_count += 1
            if user_count <= since_round:
                continue
        if role in ("user", "assistant"):
            tag = "用户" if role == "user" else "引导师"
            lines.append(f"{tag}: {content}")
    return "\n".join(lines)


def build_chat_messages(
    combo: Dict[str, Any],
    user_input: str,
    user_context: str = "",
    values_keywords: Optional[List[str]] = None,
) -> Tuple[List[Any], str]:
    """拼装发给 LLM 的消息列表 = [system: mega-prompt] + 摘要注入 + 最近对话 + 用户最新输入。

    Args:
        combo: combo_session 对象
        user_input: 用户最新输入
        user_context: 用户背景(basic_info + 前四阶段结论卡全量,由 routes 装配)
        values_keywords: 用户 values 真实关键词;None/空 → prompt 省略价值观块

    返回 (LLMMessage 列表, 系统提示词)。"""
    from app.core.llmapi import LLMMessage
    passion = combo.get("passion") or ""
    strengths = combo.get("strengths") or []
    sys_prompt = render_mega_prompt(passion, strengths, user_context, values_keywords)
    messages: List[LLMMessage] = [LLMMessage(role="system", content=sys_prompt)]
    # 摘要以 system 消息注入
    summary = combo.get("summary")
    if summary:
        messages.append(LLMMessage(role="system", content=f"【历史对话摘要】\n{summary}"))
    # 草案卡注入(2026-07-27 交互口径):出卡不锁定,草案期每轮把当前卡内容告诉 AI;
    # 若用户点了「再聊聊」,附带 reopen_feedback(用户对当前结论不满意,先问哪里不合适)。
    # 已确认(concluded)时不注入——对话已锁定;解锁后状态回 discussing 自然恢复注入。
    card = combo.get("conclusion_card")
    if (
        isinstance(card, dict)
        and _hyp_filled(card.get("hypothesis"))
        and combo.get("status") != "concluded"
    ):
        hyp = card.get("hypothesis")
        if isinstance(hyp, dict):
            hyp = "\n".join(str(v) for v in hyp.values() if v)
        note_parts: List[str] = []
        feedback = combo.get("reopen_feedback")
        if feedback:
            note_parts.append(f"【重要】{feedback}")
        note_parts.append(
            "【当前结论草案(用户尚未确认)】\n"
            f"{hyp}\n"
            "以上是当前版本的结论卡草案,对话围绕它继续打磨:\n"
            "- 用户提出新的方向想法时,按 chips 协议重新给出 2 条候选假设(跟随在可见正文之后);\n"
            "- 达成新的共识时调 save_conclusion_card 迭代卡,并同时输出可见话术说明你改了什么、邀请确认;\n"
            "- 不要重复提交相同内容;隐藏块不能单独成一条回复,必须配可见正文。"
        )
        messages.append(LLMMessage(role="system", content="\n\n".join(note_parts)))
    # 最近 30 轮对话(若已摘要则取摘要之后的;否则取全部最近 30 轮)
    all_msgs = combo.get("messages") or []
    last_summary_round = int(combo.get("summary_last_round") or 0)
    recent = _select_recent_dialog(all_msgs, last_summary_round, 30)
    for m in recent:
        content = m.get("content") or ""
        if not content.strip():
            continue  # 跳过空消息(历史上 tool-only 轮次可能落盘过空 assistant 消息),避免污染上下文
        messages.append(LLMMessage(role=m.get("role"), content=content))
    # 用户最新输入
    messages.append(LLMMessage(role="user", content=user_input))
    return messages, sys_prompt


def _select_recent_dialog(
    messages: List[Dict[str, Any]],
    since_round: int,
    max_rounds: int,
) -> List[Dict[str, Any]]:
    """从 messages 中选取最近 N 轮对话(用户+助手成对)。"""
    out: List[Dict[str, Any]] = []
    user_count = 0
    # 反向遍历找最近 max_rounds 轮
    recent_slice: List[Dict[str, Any]] = []
    for m in reversed(messages):
        if m.get("role") == "user":
            user_count += 1
        recent_slice.append(m)
        if user_count >= max_rounds:
            break
    # 过滤掉 since_round 之前的(若摘要覆盖到 since_round)
    # 简化:若 since_round > 0,直接用 since_round 之后的(从后往前数 max_rounds*2 条)
    recent_slice.reverse()
    if since_round > 0:
        # 只保留 since_round 之后的 user 消息及其后的 assistant
        kept: List[Dict[str, Any]] = []
        uc = 0
        for m in recent_slice:
            if m.get("role") == "user":
                uc += 1
            kept.append(m)
        # 简单返回全部 recent_slice(已限制在 max_rounds 内)
        return recent_slice
    return recent_slice


# ── 兜底机制(双信号)──────────────────────────────────────────────────
async def fallback_generate_conclusion(
    combo: Dict[str, Any],
    llm,
    values_keywords: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """兜底:LLM 忘输出 <<CONCLUSION_READY>>,但有用户可见锚点话术(或反之)。
    用独立 conclusion prompt + 摘要,重新生成结论卡(含 balance 两字段)。
    """
    passion = combo.get("passion") or ""
    strengths = combo.get("strengths") or []
    summary = combo.get("summary") or _messages_to_text(combo.get("messages") or [])
    prompt = render_conclusion_prompt(passion, strengths, summary, values_keywords)
    from app.core.llmapi import LLMMessage
    try:
        resp = await llm.chat(
            [LLMMessage(role="system", content=prompt)],
            temperature=0.4,
            max_tokens=800,
        )
        raw = (resp.content or "").strip()
        # 去掉可能的 ```json``` 包裹
        raw = re.sub(r"^```json\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        card = json.loads(raw)
        if not isinstance(card, dict):
            return None
        if not _hyp_filled(card.get("hypothesis")):
            return None
        # balance 两字段规范化:balance_found 只接受 true/false/null;
        # 非 false 时 fail_reason 无意义,统一置 None
        if not isinstance(card.get("balance_found"), bool):
            card["balance_found"] = None
        if card["balance_found"] is False:
            card["balance_fail_reason"] = card.get("balance_fail_reason") or None
        else:
            card["balance_fail_reason"] = None
        card["created_at"] = _now_iso()
        card["updated_at"] = _now_iso()
        return card
    except Exception as e:
        logger.warning("rumination v4 兜底结论生成失败 combo=%s: %s", combo.get("combo_id"), e)
        return None
