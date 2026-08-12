"""
Rumination v4 Service（2026-08-06 版，ADR-0015：用户主导结论卡 + 独立后台平衡点判定）

combo_session 管理:
- CRUD(create / get / list / delete / patch)
- 结论卡: 仅 hypothesis 一字段,完全由用户手写/修改(主对话 AI 不再写卡)
- 平衡点判定: 用户点「确认」→ 独立后台 AI(run_balance_judge)判定并落库
  {balance_found, balance_fail_reason};聊/改即作废,需重新确认
- 判定状态机: analyzing / done / failed(+ 无记录 = 未判定)
- 后台 30 轮滚动摘要

已删除(ADR-0015): chips 协议解析、tool 调用协议、出卡双信号、兜底出卡、
fields_collected/motivation/work_purposes/passion_mark/timing_mark 字段。

存储: data/simple/reports/{report_id}/rumination_v4_progress.json (独立文件,与 v3 物理隔离)
删除 = 从 combo_sessions 数组移除该元素(含 messages,彻底消失)
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.domain.rumination_v4_prompt import (
    render_balance_judge_prompt,
    render_mega_prompt,
    render_summarizer_prompt,
)

logger = logging.getLogger(__name__)

# 触发阈值
SUMMARIZE_EVERY_N_ROUNDS = 30  # 每 30 轮触发滚动摘要
NO_CONCLUSION_NUDGE_N_ROUNDS = 50  # (预留)50 轮未出结论 → 软提醒

# 判定 LLM 调用参数与重试次数(首次 + 1 次自动重试 = 共 2 次尝试)
BALANCE_JUDGE_MAX_ATTEMPTS = 2

# 进行中的判定任务注册表: key = f"{report_id}:{combo_id}"
# 仅本进程内存;进程重启后 analyzing 态由 sweep_orphan_analysis 自愈为 failed
_LIVE_ANALYSIS_TASKS: Dict[str, asyncio.Task] = {}


def analysis_task_key(report_id: str, combo_id: str) -> str:
    return f"{report_id}:{combo_id}"


# ── 数据 schema(参考 wiki/开发文档/0707-tag1.6.0.md 第三节;2026-08-06 瘦身)───
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
        # 开场弹窗是否已展示(2026-08-10:每激活码的 rumination report 首次进入 v4 页面弹一次)
        "intro_shown": False,
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
        "conclusion_card": None,
        # 平衡点判定状态(None = 未判定):
        # {"status": analyzing|done|failed, "balance_found": bool|None,
        #  "balance_fail_reason": str|None, "started_at", "finished_at", "error"}
        "balance_analysis": None,
        "user_skipped": False,  # 用户手动跳过(卡保留,可逆;重新确认即恢复)
    }


def _new_card(hypothesis: str) -> Dict[str, Any]:
    now = _now_iso()
    return {
        "hypothesis": hypothesis,
        "balance_found": None,
        "balance_fail_reason": None,
        "created_at": now,
        "updated_at": now,
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
    """补全缺失字段。2026-08-06 起(ADR-0015)旧数据的 fields_collected、
    conclusion_card 多余字段(motivation 等)直接忽略,不做迁移。"""
    base = default_state()
    base.update(data)
    base["schema_version"] = 4
    if not isinstance(base.get("combo_sessions"), list):
        base["combo_sessions"] = []
    for c in base["combo_sessions"]:
        if isinstance(c, dict):
            c.pop("fields_collected", None)  # 已废弃字段,读取即清理
            c.setdefault("balance_analysis", None)
            card = c.get("conclusion_card")
            if isinstance(card, dict):
                # 旧卡瘦身:只保留现行字段
                c["conclusion_card"] = {
                    "hypothesis": card.get("hypothesis"),
                    "balance_found": card.get("balance_found"),
                    "balance_fail_reason": card.get("balance_fail_reason"),
                    "created_at": card.get("created_at"),
                    "updated_at": card.get("updated_at"),
                }
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
def mark_intro_shown(reports_root: Path, report_id: str) -> Dict[str, Any]:
    """标记 v4 开场弹窗已展示(纯 UI 标记,幂等)。"""
    state = load_v4_state(reports_root, report_id)
    state["intro_shown"] = True
    save_v4_state(reports_root, report_id, state)
    return state


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
        "balance_analysis": c.get("balance_analysis"),
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
    自动从 final_selection 移除;若删的是 active,active 指向最近一个或 None。
    分析中删除:允许,判定任务写盘前会因 combo 不存在而丢弃结果。"""
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


# ── 结论卡(用户主导)与平衡点判定 ────────────────────────────────────────
def _hyp_filled(hyp: Any) -> bool:
    """hypothesis 是否非空(兼容读取旧 dict 形态)。"""
    if hyp is None:
        return False
    if isinstance(hyp, str):
        return bool(hyp.strip())
    if isinstance(hyp, dict):
        return any(bool(v) for v in hyp.values())
    return False


def invalidate_balance_analysis(combo: Dict[str, Any]) -> None:
    """聊/改即作废(ADR-0015):清除判定记录与卡上的 balance 字段(灯灭)。"""
    combo["balance_analysis"] = None
    card = combo.get("conclusion_card")
    if isinstance(card, dict):
        card["balance_found"] = None
        card["balance_fail_reason"] = None


def is_analyzing(combo: Optional[Dict[str, Any]]) -> bool:
    return bool(combo) and (combo.get("balance_analysis") or {}).get("status") == "analyzing"


def patch_conclusion_card(
    reports_root: Path,
    report_id: str,
    combo_id: str,
    hypothesis: str,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """用户直接编辑结论卡(走 PATCH 端点,不绕道 LLM)。

    2026-08-06(ADR-0015):
    - 卡仅 hypothesis 一字段;允许从无到有首次填写,禁止清空
    - hypothesis 变更 → 作废旧判定(灯灭);若已确认(concluded) → 退回 discussing(未确认态)
    - 分析中拒绝编辑(路由层另有 409,双保险)
    """
    state = load_v4_state(reports_root, report_id)
    combo = find_combo(state, combo_id)
    if not combo:
        raise ValueError(f"combo_id 不存在: {combo_id}")
    if combo.get("status") == "abandoned":
        raise ValueError("abandoned(已跳过)的 combo 不可直接编辑结论卡,请先恢复确认")
    if is_analyzing(combo):
        raise ValueError("正在分析中,请稍后再编辑")
    new_hyp = (hypothesis or "").strip()
    if not new_hyp:
        raise ValueError("hypothesis 不可清空")
    card = combo.get("conclusion_card")
    old_hyp = (card or {}).get("hypothesis")
    if isinstance(old_hyp, dict):  # 旧 dict 形态归一为字符串再比较
        old_hyp = "\n".join(str(v) for v in old_hyp.values() if v)
    if card is None:
        card = _new_card(new_hyp)
        combo["conclusion_card"] = card
    elif (old_hyp or "").strip() != new_hyp:
        card["hypothesis"] = new_hyp
        card["updated_at"] = _now_iso()
        # 改即作废:清判定;已确认卡退回未确认态,需重新点「确认」触发重判
        invalidate_balance_analysis(combo)
        if combo.get("status") == "concluded":
            combo["status"] = "discussing"
    combo["updated_at"] = _now_iso()
    save_v4_state(reports_root, report_id, state)
    return state, card


def set_combo_status(
    reports_root: Path, report_id: str, combo_id: str, status: str
) -> Dict[str, Any]:
    """更新 combo_session 状态(discussing/concluded/abandoned)。

    2026-08-06(ADR-0015):
    - concluded(确认)统一走 confirm 端点(含判定);此处仅作双保险:
      无已完成判定记录的 concluded 请求一律拒绝
    - abandoned(跳过)不清空结论卡,仅置 user_skipped=True(可逆)
    - concluded → discussing(用户点「再聊聊」)写入 reopen_feedback 注入 LLM 上下文,
      并作废旧判定(聊即作废)
    """
    state = load_v4_state(reports_root, report_id)
    combo = find_combo(state, combo_id)
    if not combo:
        raise ValueError(f"combo_id 不存在: {combo_id}")
    status = (status or "").strip().lower()
    if status not in ("concluded", "abandoned", "discussing"):
        raise ValueError(f"非法 status: {status}")
    if is_analyzing(combo):
        raise ValueError("正在分析中,请稍后再操作")
    if status == "concluded":
        analysis = combo.get("balance_analysis") or {}
        if analysis.get("status") != "done":
            raise ValueError("确认结论卡请走 confirm 端点(含平衡点判定)")
    prev_status = combo.get("status")
    if status == "abandoned":
        combo["user_skipped"] = True  # 卡内容保留,UI 删除线 + 灰色标记
    else:
        combo["user_skipped"] = False  # concluded/discussing 都清除跳过标记
    if prev_status == "concluded" and status == "discussing" and combo.get("conclusion_card"):
        # 再聊聊:旧判定作废(灯灭),注入不满意反馈供 AI 继续打磨
        invalidate_balance_analysis(combo)
        combo["reopen_feedback"] = (
            "用户看过结论卡后选择「再聊聊」,表示对当前结论还不够满意,希望继续打磨。"
            "请先询问用户:觉得这版结论哪里不合适、缺了什么、或者哪里不打动你?"
            "再根据用户的回答继续探讨;有新的共识时,引导用户更新左侧结论卡后重新点击「确认」。"
        )
    combo["status"] = status
    combo["updated_at"] = _now_iso()
    save_v4_state(reports_root, report_id, state)
    return state


def confirm_conclusion_card(
    reports_root: Path, report_id: str, combo_id: str
) -> Tuple[Dict[str, Any], Dict[str, Any], str]:
    """用户点「确认」(ADR-0015):置 concluded + analyzing,返回 (state, combo, started_at)。

    判定本身由 run_balance_judge 在 SSE 流内执行;本函数只做状态前置与落盘。
    跳过卡恢复确认同样走这里(清除 user_skipped)。
    """
    state = load_v4_state(reports_root, report_id)
    combo = find_combo(state, combo_id)
    if not combo:
        raise ValueError(f"combo_id 不存在: {combo_id}")
    if is_analyzing(combo):
        raise ValueError("正在分析中,请勿重复点击")
    card = combo.get("conclusion_card")
    if not isinstance(card, dict) or not _hyp_filled(card.get("hypothesis")):
        raise ValueError("结论卡为空,请先填写假设方向再确认")
    started_at = _now_iso()
    combo["status"] = "concluded"
    combo["user_skipped"] = False
    combo.pop("reopen_feedback", None)  # 确认即闭环,清除反馈标记
    combo["balance_analysis"] = {
        "status": "analyzing",
        "balance_found": None,
        "balance_fail_reason": None,
        "started_at": started_at,
        "finished_at": None,
        "error": None,
    }
    combo["updated_at"] = started_at
    save_v4_state(reports_root, report_id, state)
    return state, combo, started_at


def register_analysis_task(report_id: str, combo_id: str, task: asyncio.Task) -> None:
    _LIVE_ANALYSIS_TASKS[analysis_task_key(report_id, combo_id)] = task


def unregister_analysis_task(report_id: str, combo_id: str, task: asyncio.Task) -> None:
    key = analysis_task_key(report_id, combo_id)
    if _LIVE_ANALYSIS_TASKS.get(key) is task:
        _LIVE_ANALYSIS_TASKS.pop(key, None)


def get_live_analysis_task(report_id: str, combo_id: str) -> Optional[asyncio.Task]:
    return _LIVE_ANALYSIS_TASKS.get(analysis_task_key(report_id, combo_id))


def sweep_orphan_analysis(state: Dict[str, Any], report_id: str) -> bool:
    """孤儿判定自愈:analyzing 但本进程无存活任务(断连/重启) → 置 failed(可重试)。
    返回是否有改动(有改动时调用方负责落盘)。"""
    changed = False
    for c in state.get("combo_sessions") or []:
        analysis = (c or {}).get("balance_analysis") or {}
        if analysis.get("status") != "analyzing":
            continue
        task = _LIVE_ANALYSIS_TASKS.get(analysis_task_key(report_id, str(c.get("combo_id"))))
        if task is None or task.done():
            analysis["status"] = "failed"
            analysis["error"] = "分析中断,请点击重试"
            analysis["finished_at"] = _now_iso()
            c["balance_analysis"] = analysis
            changed = True
    return changed


def _build_judge_dialog_text(combo: Dict[str, Any]) -> str:
    """构造判定输入的对话文本:有摘要 = 摘要 + 摘要后消息;否则全量对话。"""
    messages = combo.get("messages") or []
    summary = (combo.get("summary") or "").strip()
    last_round = int(combo.get("summary_last_round") or 0)
    recent = _messages_to_text(messages, since_round=last_round if summary else 0)
    if summary:
        return f"【早期对话摘要】\n{summary}\n\n【近期对话】\n{recent}"
    return recent


async def run_balance_judge(
    reports_root: Path,
    report_id: str,
    combo_id: str,
    llm,
    started_at: str,
) -> Dict[str, Any]:
    """独立后台平衡点判定(ADR-0015)。

    输入 = 热爱/优势组合 + 用户确认的 hypothesis + 完整对话(超长时摘要压缩早期)。
    输出 {balance_found, balance_fail_reason} 落库(combo.balance_analysis + card 同步)。
    失败自动重试 1 次(共 2 次尝试);仍失败 → status=failed(用户可点重试)。

    防御:combo 已被删除 / started_at 与当前记录不一致(已有更新的判定) → 丢弃结果。
    返回最终的 balance_analysis 字典。
    """
    state = load_v4_state(reports_root, report_id)
    combo = find_combo(state, combo_id)
    if not combo:
        return {"status": "failed", "error": "combo 已删除"}
    card = combo.get("conclusion_card") or {}
    hypothesis = card.get("hypothesis")
    if isinstance(hypothesis, dict):
        hypothesis = "\n".join(str(v) for v in hypothesis.values() if v)
    dialog_text = _build_judge_dialog_text(combo)
    prompt = render_balance_judge_prompt(
        combo.get("passion") or "", combo.get("strengths") or [], hypothesis or "", dialog_text
    )

    result: Optional[Dict[str, Any]] = None
    last_error: Optional[str] = None
    from app.core.llmapi import LLMMessage
    for attempt in range(1, BALANCE_JUDGE_MAX_ATTEMPTS + 1):
        try:
            resp = await llm.chat(
                [LLMMessage(role="system", content=prompt)],
                temperature=0.3,
                max_tokens=400,
            )
            raw = (resp.content or "").strip()
            raw = re.sub(r"^```json\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            obj = json.loads(raw)
            if not isinstance(obj, dict):
                raise ValueError("判定输出不是 JSON 对象")
            balance_found = obj.get("balance_found")
            if not isinstance(balance_found, bool):
                balance_found = None
            fail_reason = obj.get("balance_fail_reason") if balance_found is False else None
            if fail_reason is not None:
                fail_reason = str(fail_reason).strip() or None
            result = {"balance_found": balance_found, "balance_fail_reason": fail_reason}
            break
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            logger.warning(
                "rumination v4 平衡点判定失败 combo=%s attempt=%d: %s", combo_id, attempt, e
            )

    # 写盘前防御性重载:combo 可能已被删除,或已有更新的判定起跑
    state = load_v4_state(reports_root, report_id)
    combo = find_combo(state, combo_id)
    if not combo:
        logger.info("rumination v4 判定写盘前 combo 已删除,丢弃结果 combo=%s", combo_id)
        return {"status": "failed", "error": "combo 已删除"}
    current = combo.get("balance_analysis") or {}
    if current.get("started_at") != started_at:
        logger.info("rumination v4 判定结果过期,丢弃 combo=%s", combo_id)
        return current

    finished_at = _now_iso()
    if result is not None:
        current.update(
            {
                "status": "done",
                "balance_found": result["balance_found"],
                "balance_fail_reason": result["balance_fail_reason"],
                "finished_at": finished_at,
                "error": None,
            }
        )
        card = combo.get("conclusion_card")
        if isinstance(card, dict):
            card["balance_found"] = result["balance_found"]
            card["balance_fail_reason"] = result["balance_fail_reason"]
            card["updated_at"] = finished_at
    else:
        current.update(
            {
                "status": "failed",
                "finished_at": finished_at,
                "error": last_error or "判定失败",
            }
        )
    combo["balance_analysis"] = current
    combo["updated_at"] = finished_at
    save_v4_state(reports_root, report_id, state)
    return current


def pending_judged_combo_ids(state: Dict[str, Any]) -> List[str]:
    """「完成并继续」门槛(ADR-0015):已确认(concluded 且未跳过)但判定未完成的 combo。
    未完成 = 无判定记录 / analyzing / failed。已跳过、讨论中的卡不参与检查。"""
    out: List[str] = []
    for c in state.get("combo_sessions") or []:
        if c.get("status") != "concluded" or c.get("user_skipped"):
            continue
        analysis = c.get("balance_analysis") or {}
        if analysis.get("status") != "done":
            out.append(str(c.get("combo_id")))
    return out


# ── final_selection(第 8 步)──────────────────────────────────────────
def update_final_selection(
    reports_root: Path,
    report_id: str,
    selected_combo_ids: List[str],
) -> Dict[str, Any]:
    """第 8 步:更新选定的 1-3 个 combo_id(后端校验数量、status 与判定完成度)。"""
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
    # ADR-0015 门槛:所有已确认卡必须判定完成
    pending = pending_judged_combo_ids(state)
    if pending:
        raise ValueError("有结论卡正在分析中,请稍后")
    fs = state.setdefault("final_selection", {})
    fs["selected_combo_ids"] = selected_combo_ids
    fs["submitted"] = False
    state["main_section"] = "final_selection"
    save_v4_state(reports_root, report_id, state)
    return state


def submit_final_selection(reports_root: Path, report_id: str) -> Dict[str, Any]:
    """第 8 步最终提交(锁定)。ADR-0015:所有已确认卡必须判定完成。"""
    state = load_v4_state(reports_root, report_id)
    pending = pending_judged_combo_ids(state)
    if pending:
        raise ValueError("有结论卡正在分析中,请稍后")
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
    """把 messages 转成可读文本,可指定从第几轮开始(用于摘要增量/判定输入)。"""
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
    # 结论卡现状注入(2026-08-06, ADR-0015):卡由用户自己填写,AI 只读不写;
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
            "【当前结论卡(由用户本人填写)】\n"
            f"{hyp}\n"
            "以上是用户目前写在结论卡上的方向。对话围绕它继续打磨:\n"
            "- 用户提出新的方向想法时,继续按流程探讨细化;\n"
            "- 达成新的共识时,引导用户更新左侧结论卡并重新点击「确认」。"
        )
        messages.append(LLMMessage(role="system", content="\n\n".join(note_parts)))
    # 最近 30 轮对话(若已摘要则取摘要之后的;否则取全部最近 30 轮)
    all_msgs = combo.get("messages") or []
    last_summary_round = int(combo.get("summary_last_round") or 0)
    recent = _select_recent_dialog(all_msgs, last_summary_round, 30)
    for m in recent:
        content = m.get("content") or ""
        if not content.strip():
            continue  # 跳过空消息,避免污染上下文
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
    user_count = 0
    recent_slice: List[Dict[str, Any]] = []
    for m in reversed(messages):
        if m.get("role") == "user":
            user_count += 1
        recent_slice.append(m)
        if user_count >= max_rounds:
            break
    recent_slice.reverse()
    return recent_slice
