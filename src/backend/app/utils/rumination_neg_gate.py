"""
沉淀子步 2/3/5/6：首次表格确认前的「否定/标记」闸门（程序检测 + 可选 LLM）。

- 不落 submitted，仅写入 progress.pending_table_submit + rumination_neg_state。
- 用户选择「继续」或「结束讨论」后由 resolve 端点带 neg_force_commit 重入正式 submit。
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from app.core.llmapi.base import LLMMessage

logger = logging.getLogger(__name__)

NEG_GATED_STEPS = frozenset({2, 3, 5, 6})

OTHER_TOKEN = "__RUMINATION_OTHER__"


def _row_summary(row: Dict[str, Any]) -> str:
    parts = []
    for k in ("热爱", "优势", "用户确认的假设", "匹配性", "工作目的", "激情标记", "现实标记"):
        v = row.get(k)
        if v is not None and str(v).strip():
            parts.append(f"{k}：{str(v).strip()}")
    return "；".join(parts) if parts else str(row.get("id", ""))


def collect_step2_mismatches(table_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in table_data:
        if not isinstance(r, dict):
            continue
        if str(r.get("匹配性") or "").strip() == "不匹配":
            out.append(
                {
                    "id": str(r.get("id", "")),
                    "line": _row_summary(r),
                    "热爱": str(r.get("热爱") or ""),
                    "优势": str(r.get("优势") or ""),
                }
            )
    return out


def collect_step5_should_do(table_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in table_data:
        if not isinstance(r, dict):
            continue
        if str(r.get("激情标记") or "").strip() == "应该做":
            out.append(
                {
                    "id": str(r.get("id", "")),
                    "line": _row_summary(r),
                    "热爱": str(r.get("热爱") or ""),
                    "优势": str(r.get("优势") or ""),
                    "假设": str(r.get("用户确认的假设") or ""),
                }
            )
    return out


def collect_step6_future(table_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in table_data:
        if not isinstance(r, dict):
            continue
        if str(r.get("现实标记") or "").strip() == "未来":
            out.append(
                {
                    "id": str(r.get("id", "")),
                    "line": _row_summary(r),
                    "热爱": str(r.get("热爱") or ""),
                    "优势": str(r.get("优势") or ""),
                    "假设": str(r.get("用户确认的假设") or ""),
                }
            )
    return out


def _is_pending_label(s: str) -> bool:
    t = (s or "").strip()
    return t in ("", "暂未选定", "待定")


def collect_step3_hypothesis_candidates(table_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """需做「是否符合假设定义」检测的行：非「假设1/假设2」内置选项的文案（含自填、其他）。"""
    out: List[Dict[str, Any]] = []
    for r in table_data:
        if not isinstance(r, dict):
            continue
        hyp = str(r.get("用户确认的假设") or "").strip()
        if _is_pending_label(hyp):
            continue
        h1 = str(r.get("假设1") or "").strip()
        h2 = str(r.get("假设2") or "").strip()
        if h1 and h2 and (hyp == h1 or hyp == h2):
            continue
        out.append(
            {
                "id": str(r.get("id", "")),
                "line": _row_summary(r),
                "热爱": str(r.get("热爱") or ""),
                "优势": str(r.get("优势") or ""),
                "假设": hyp,
            }
        )
    return out


STEP3_LLM_SYSTEM = """你是职业探索表格质检助手。判断每条「假设」是否符合定义。
定义：假设需描述「想做的事」本身，要具体、有画面感，通常包含角色、对象、动作、目的等要素，让用户能想象出实际场景，且应指向可长期投入、持续运营的职业或项目；避免只有抽象标签或职位名称。
只输出 JSON 数组，元素形如 {"id":"行id","invalid":true|false,"reason":"一句中文"}。不要其它文字。"""


async def llm_flag_step3_hypotheses(llm: Any, rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], bool]:
    """返回 (invalid_rows子集, llm_failed)。timeout 视为失败。"""
    if not rows:
        return [], False
    try:
        brief = [
            {"id": r["id"], "热爱": r.get("热爱", ""), "优势": r.get("优势", ""), "假设": r.get("假设", "")}
            for r in rows
        ]
        user = json.dumps(brief, ensure_ascii=False)
        msgs = [
            LLMMessage(role="system", content=STEP3_LLM_SYSTEM),
            LLMMessage(role="user", content=user),
        ]
        # 该质检仅用于闸门辅助，超时后会自动降级；避免拖慢第三轮提交主链路
        resp = await asyncio.wait_for(llm.chat(msgs, temperature=0.2, max_tokens=800), timeout=8.0)
        raw = (resp.content or "").strip()
        start = raw.find("[")
        end = raw.rfind("]")
        if start >= 0 and end > start:
            raw = raw[start : end + 1]
        data = json.loads(raw)
        if not isinstance(data, list):
            return [], True
        invalid_ids = {str(x.get("id")) for x in data if isinstance(x, dict) and x.get("invalid")}
        invalid_rows = [r for r in rows if str(r.get("id")) in invalid_ids]
        return invalid_rows, False
    except Exception as e:
        logger.warning("rumination step3 hypothesis LLM gate failed: %s", e)
        return [], True


def build_injection_zh(step: int, kind: str, items: List[Dict[str, Any]], llm_failed: bool) -> str:
    """注入主对话 system 末尾的补充段（探索中）。"""
    lines = "\n".join(f"{i + 1}. {it.get('line', '')}" for i, it in enumerate(items[:12]))
    if llm_failed:
        return (
            "\n【沉淀·表格跟进（自动判断暂不可用）】\n"
            "你刚提交了本步表格，系统暂时没完成自动假设检测。\n"
            "请用温和、拟人的语气，邀请对方就**不太有把握**的假设逐条聊清楚是否符合「具体、有画面、可长期投入」；一次只问一个问题。\n"
            f"可参考的表格条目摘要：\n{lines}\n"
            "强调：热爱、优势等前提来自前序确认，当前讨论不修改这些前提字段。\n"
            "禁止在这里推进到结论卡或最终确认；结束时只提醒点击右上角「结束讨论」回到左侧表格继续修改。"
        )
    if kind == "mismatch":
        tail = "对方把一些热爱-优势组合标为「不匹配」，请按 new-rumination-3 步骤二：一次一问，探因、谈可能性，再确认是否保留不匹配。"
    elif kind == "hypothesis_def":
        tail = "对方有部分假设可能不符合定义（含自填），请按 new-rumination-3 步骤三：一次一问，引导完善，不要代替对方下结论。"
    elif kind == "should_do":
        tail = "对方把部分假设标为「应该做」，请按 new-rumination-3 步骤五：一次一问，探因并确认是否仍保留。"
    elif kind == "future":
        tail = "对方把部分假设标为「未来」，请按 new-rumination-3 步骤六：一次一问，谈原因与当下可积累。"
    else:
        tail = "请结合下列表格摘要，一次一问陪伴用户澄清。"
    return (
        f"\n【沉淀·待跟进标记项】\n{tail}\n条目：\n{lines}\n"
        "提醒：不要改动表格里的热爱、优势等前提条件；若讨论充分，请只引导点击右上角「结束讨论」回到左侧表格修改。不要在当前对话中推进到结论卡。"
    )


def build_opening_user_visible_zh(step: int, kind: str, items: List[Dict[str, Any]], llm_failed: bool) -> str:
    """右侧首条助手可见开场（用户选深入讨论后由前端插入）。"""
    if llm_failed:
        return (
            "刚才系统在对你的假设做快速检查时稍微卡了一下，没关系的～\n"
            "如果你愿意，我们可以从你最拿不准的那一条开始，一条条聊聊它是不是足够具体、能不能想象出你在做的画面。\n"
            "这轮先不改热爱、优势等前提字段。你想先聊哪一条？讨论完请点右上角「结束讨论」提交。"
        )
    if kind == "mismatch":
        intro = "我注意到你在表格里标了一些「不匹配」的热爱-优势组合，我想陪你一点点看过去。"
    elif kind == "hypothesis_def":
        intro = "我注意到有少数假设可能需要再具体一点，我们一起把它说得更像「你想做的事」本身，好吗？"
    elif kind == "should_do":
        intro = "我注意到你把一些方向标成了「应该做」，我想陪你看看这背后更多是外界的期待，还是也有一点内心的火花。"
    elif kind == "future":
        intro = "我注意到你把一些方向标成了「未来」，我们可以聊聊现在还缺什么、以及有没有现在就能开始的一小步。"
    else:
        intro = "关于你刚才表格里标出的部分，我想和你多聊几句。"
    first = items[0].get("line", "") if items else ""
    return (
        f"{intro}\n我们先从这一条开始好吗？\n{first}\n"
        "（先不改热爱、优势等前提字段；聊完请点右上角「结束讨论」。）"
    )


def build_bar_copy_zh(kind: str, items: List[Dict[str, Any]], llm_failed: bool) -> str:
    """内嵌条说明文案（非弹窗）。"""
    n = len(items)
    if llm_failed:
        return (
            "系统刚才没能自动完成假设检查。你可以选「继续进入下一步」直接推进；"
            "或选「深入讨论」，在右侧和我慢慢聊你不确定的条目。当前讨论不修改热爱、优势等前提字段。"
        )
    if kind == "mismatch":
        head = f"注意到你标记了以下「不匹配」的项（共 {n} 条）："
    elif kind == "hypothesis_def":
        head = f"以下假设可能需要再具体一点（共 {n} 条）："
    elif kind == "should_do":
        head = f"注意到你标记了以下「应该做」的项（共 {n} 条）："
    elif kind == "future":
        head = f"注意到你标记了以下「未来」的项（共 {n} 条）："
    else:
        head = "注意到以下条目："
    body = "\n".join(f"{i + 1}. {it.get('line', '')}" for i, it in enumerate(items[:8]))
    return (
        f"{head}\n{body}\n\n"
        "要针对这些多聊几句，还是直接进入下一步？（不修改表格里的热爱、优势等前提字段）"
    )


async def try_build_neg_gate_response(
    *,
    step: int,
    table_data: List[Dict[str, Any]],
    llm: Any,
    selected_row_ids: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """
    若本步应弹出闸门，返回 dict：confirm_ui, neg_state, pending_payload。
    否则返回 None。
    """
    if step not in NEG_GATED_STEPS or not table_data:
        return None

    kind = ""
    items: List[Dict[str, Any]] = []
    llm_failed = False

    if step == 2:
        items = collect_step2_mismatches(table_data)
        kind = "mismatch"
    elif step == 5:
        items = collect_step5_should_do(table_data)
        kind = "should_do"
    elif step == 6:
        items = collect_step6_future(table_data)
        kind = "future"
    elif step == 3:
        cand = collect_step3_hypothesis_candidates(table_data)
        if not cand:
            return None
        flagged, llm_failed = await llm_flag_step3_hypotheses(llm, cand)
        kind = "hypothesis_def"
        if llm_failed:
            items = list(cand)
        else:
            items = list(flagged)
        if not items:
            return None
    else:
        return None

    if step in (2, 5, 6) and not items:
        return None

    inj = build_injection_zh(step, kind, items, llm_failed)
    opening = build_opening_user_visible_zh(step, kind, items, llm_failed)
    bar = build_bar_copy_zh(kind, items, llm_failed)

    neg_state: Dict[str, Any] = {
        "status": "awaiting_choice",
        "step": step,
        "kind": kind,
        "items": items[:20],
        "llm_failed": llm_failed,
        "injection_zh": inj,
        "opening_zh": opening,
        "bar_copy_zh": bar,
    }
    pending: Dict[str, Any] = {
        "step": step,
        "table_data": table_data,
    }
    if selected_row_ids:
        pending["selected_row_ids"] = selected_row_ids
    confirm = {
        "filter_step": step,
        "kind": kind,
        "items": items[:20],
        "bar_copy_zh": bar,
        "llm_failed": llm_failed,
    }
    return {"neg_state": neg_state, "pending": pending, "confirm": confirm}
