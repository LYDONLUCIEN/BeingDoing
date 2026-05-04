"""
沉淀子步 2/3/5/6：首次表格确认前的「否定/标记」闸门（程序检测 + 可选 LLM）。

- 不落 submitted，仅写入 progress.pending_table_submit + rumination_neg_state。
- 用户选择「继续」或「结束讨论」后由 resolve 端点带 neg_force_commit 重入正式 submit。

v2: 按字段级模板展示否定条目，替代整行摘要（new-rumination-3.md 口径）。
v3: 每个步骤拥有独立的 system 片段（rumination_prompt_strings.DEEP_CHAT_STEP_SYSTEM_MAP），
    注入时先拼步骤专属 system 片段，再追加条目列表，确保逐条处理不跳步。
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from app.core.llmapi.base import LLMMessage
from app.domain.rumination_step_guidance import get_deep_chat_step_system

logger = logging.getLogger(__name__)

NEG_GATED_STEPS = frozenset({2, 3, 5, 6})

OTHER_TOKEN = "__RUMINATION_OTHER__"


# ---------------------------------------------------------------------------
# 字段级摘要：按步骤分别提取关键字段，避免整行噪音
# ---------------------------------------------------------------------------

def _format_mismatch_item(r: Dict[str, Any]) -> str:
    """步骤 2 不匹配条目：仅展示 热爱 vs 优势。"""
    passion = str(r.get("热爱") or "").strip()
    strength = str(r.get("优势") or "").strip()
    return f"热爱「{passion}」 Vs 优势「{strength}」"


def _format_hypothesis_item(r: Dict[str, Any]) -> str:
    """步骤 3 假设定义不符条目：展示 假设文本 + 对应热爱/优势。"""
    passion = str(r.get("热爱") or "").strip()
    strength = str(r.get("优势") or "").strip()
    hypo = str(r.get("假设") or "").strip()
    return f"假设「{hypo}」（热爱：{passion}；优势：{strength}）"


def _format_should_do_item(r: Dict[str, Any]) -> str:
    """步骤 5 应该做条目：展示 假设文本。"""
    hypo = str(r.get("假设") or "").strip()
    passion = str(r.get("热爱") or "").strip()
    strength = str(r.get("优势") or "").strip()
    return f"假设「{hypo}」（热爱：{passion}；优势：{strength}）"


def _format_future_item(r: Dict[str, Any]) -> str:
    """步骤 6 未来条目：展示 假设文本。"""
    hypo = str(r.get("假设") or "").strip()
    passion = str(r.get("热爱") or "").strip()
    strength = str(r.get("优势") or "").strip()
    return f"假设「{hypo}」（热爱：{passion}；优势：{strength}）"


def _item_label(kind: str, item: Dict[str, Any]) -> str:
    """根据步骤类型返回字段级展示文案。"""
    if kind == "mismatch":
        return _format_mismatch_item(item)
    if kind == "hypothesis_def":
        return _format_hypothesis_item(item)
    if kind == "should_do":
        return _format_should_do_item(item)
    if kind == "future":
        return _format_future_item(item)
    # 兜底：拼接非空字段
    return str(item.get("id", ""))


def _item_struct_lines(kind: str, item: Dict[str, Any]) -> List[str]:
    """返回结构化字段行（用于弹窗/系统注入，避免整行噪音）。"""
    passion = str(item.get("热爱") or "").strip() or "（未填写）"
    strength = str(item.get("优势") or "").strip() or "（未填写）"
    hypo = str(item.get("假设") or "").strip() or "（未填写）"

    if kind == "mismatch":
        return [f"热爱：{passion}", f"优势：{strength}"]
    if kind in ("hypothesis_def", "should_do", "future"):
        return [f"假设：{hypo}", f"热爱：{passion}", f"优势：{strength}"]
    return [str(item.get("label") or item.get("line") or item.get("id") or "")]


# ---------------------------------------------------------------------------
# 数据采集（与旧版一致，保留 line 字段供过渡；新增字段级展示字段）
# ---------------------------------------------------------------------------

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
                    "label": _format_mismatch_item(r),
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
                    "label": _format_should_do_item(r),
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
                    "label": _format_future_item(r),
                    "热爱": str(r.get("热爱") or ""),
                    "优势": str(r.get("优势") or ""),
                    "假设": str(r.get("用户确认的假设") or ""),
                }
            )
    return out


def _is_pending_label(s: str) -> bool:
    t = (s or "").strip()
    # 当前文案「无」，兼容旧值「暂未选定」「待定」
    return t in ("", "暂未选定", "待定", "无")


def collect_step3_pending_rows(table_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """选了「无」/空/待定/暂未选定的行 — 必须进入深度讨论。"""
    out: List[Dict[str, Any]] = []
    for r in table_data:
        if not isinstance(r, dict):
            continue
        hyp = str(r.get("用户确认的假设") or "").strip()
        if not _is_pending_label(hyp):
            continue
        out.append(
            {
                "id": str(r.get("id", "")),
                "line": _row_summary(r),
                "label": _format_hypothesis_item(r),
                "热爱": str(r.get("热爱") or ""),
                "优势": str(r.get("优势") or ""),
                "假设": hyp,
                "_kind": "pending",
            }
        )
    return out


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
                "label": _format_hypothesis_item(r),
                "热爱": str(r.get("热爱") or ""),
                "优势": str(r.get("优势") or ""),
                "假设": hyp,
                "_kind": "custom",
            }
        )
    return out


# ---------------------------------------------------------------------------
# LLM 步骤 3 假设质检（不变）
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 注入 system prompt 末尾的补充段（字段级模板）
# ---------------------------------------------------------------------------

def _item_lines(kind: str, items: List[Dict[str, Any]], limit: int = 12) -> str:
    """将条目列表按字段级直角引号格式化为编号列表。"""
    return "\n".join(f"{i + 1}. {_item_label(kind, it)}" for i, it in enumerate(items[:limit]))
    return "\n".join(blocks)


def build_injection_zh(step: int, kind: str, items: List[Dict[str, Any]], llm_failed: bool) -> str:
    """注入主对话 system 末尾的补充段（探索中）。

    v3: 使用步骤差异化 system 片段替代旧版统一模板。
    结构：[步骤专属 system 片段] + [条目编号列表] + [结束引导提示]

    步骤专属 system 片段包含：
    - 步骤角色定位与目标
    - 字段上下文模板（本步关注哪些字段、哪些不可修改）
    - 逐条处理流程约束（防跳步）
    - 禁止行为清单
    """
    # 获取步骤专属 system 片段
    step_system = get_deep_chat_step_system(step, llm_failed=llm_failed)

    # 格式化条目列表
    lines = _item_lines(kind, items)

    # 对话风格与边界约束（所有步骤共用）
    style_guard = (
        "回复风格要求：\n"
        "- 语气温和、简洁，优先短段落；\n"
        "- 一次只问一个问题，不要连发多问；\n"
        "- 每轮回复最多出现一个问号（? 或 ？）；\n"
        "- 引用条目时优先使用字段名（热爱/优势/假设），不要整段复读；\n"
        "- 每条讨论结束后明确提示「这条我们聊完了」，再进入下一条。"
    )

    # 通用结束引导提示
    closing = "讨论充分后，请只引导点击右上角「结束讨论」回到左侧表格修改。不要在当前对话中推进到结论卡。"

    if step_system:
        # v3 路径：使用步骤专属 system 片段 + 条目列表
        return (
            f"\n{step_system}\n\n"
            f"待讨论条目（按序逐条进行）：\n{lines}\n\n"
            f"{style_guard}\n\n"
            f"提醒：{closing}"
        )
    else:
        # 降级路径：步骤不在映射中（理论上不应发生）
        logger.warning("rumination neg gate: step %d not in DEEP_CHAT_STEP_SYSTEM_MAP, using fallback", step)
        return (
            f"\n【沉淀·待跟进标记项】\n"
            "请一次一问陪伴用户澄清以下条目，逐一讨论不跳过。\n"
            f"条目：\n{lines}\n{closing}"
        )


# ---------------------------------------------------------------------------
# 用户可见开场语（字段级模板，参考 new-rumination-3.md 口径）
# ---------------------------------------------------------------------------

def build_opening_user_visible_zh(step: int, kind: str, items: List[Dict[str, Any]], llm_failed: bool) -> str:
    """右侧首条助手可见开场（用户选深入讨论后由前端插入）。

    按步骤分别采用参考文档口径，从第一条条目的关键字段开始引入。
    """
    if llm_failed:
        return (
            "刚才系统在对你的假设做快速检查时稍微卡了一下，没关系的～\n"
            "如果你愿意，我们可以从你最拿不准的那一条开始，一条条聊聊它是不是足够具体、能不能想象出你在做的画面。\n"
            "这轮先不改热爱、优势等前提字段。你想先聊哪一条？讨论完请点右上角「结束讨论」提交。"
        )

    if not items:
        return (
            "关于你刚才表格里标出的部分，我想和你多聊几句。"
            "不过目前没有具体的条目需要讨论，你可以直接点击右上角「结束讨论」继续。"
        )

    first_label = _item_label(kind, items[0])
    first_lines = _item_struct_lines(kind, items[0])
    first_block = "\n".join(f"- {line}" for line in first_lines)

    if kind == "mismatch":
        return (
            "你好呀，很高兴和你一起聊聊这张表格里的「热爱」与「优势」。\n"
            "我们会一个一个来看，你只需要跟着我的问题慢慢想就好。\n\n"
            "先看第 1 条：\n"
            f"{first_block}\n\n"
            "为了更清楚地理解你的判断，我想先问问——你觉得这个组合为什么「不匹配」呢？"
        )
    if kind == "hypothesis_def":
        return (
            "你好呀，很高兴和你一起梳理这份职业探索表格。\n"
            "我注意到有几条「假设」还可以再具体一些，我们一条条来完善。\n\n"
            "先看第 1 条：\n"
            f"{first_block}\n\n"
            "关于这一条假设，我想请你回想一下：当你说到你的热爱和优势时，"
            "你脑海里有没有浮现出一个更具体的、你每天都在做的事情的场景？"
        )
    if kind == "should_do":
        return (
            "你好呀！很高兴能和你一起聊聊这些职业发展的可能性。\n"
            "在接下来的对话中，我会针对你标记为「应该做」的每个假设，"
            "陪你一起探索背后的原因——看看它们到底是来自外界的「应该」，"
            "还是内心深处其实「忍不住想做」。\n\n"
            "先看第 1 条：\n"
            f"{first_block}\n\n"
            "你说这件事更像是「应该做」，我想先好奇一下——"
            "让你觉得「这更像任务而不是享受」的部分，具体是什么？"
        )
    if kind == "future":
        return (
            "你好呀！很高兴和你一起梳理这些「未来」规划。\n"
            "今天我们会一个一个来看你标记为「未来」的职业可能性，"
            "聊一聊背后的原因，也看看有没有一些现在就可以着手的小动作。\n\n"
            "先看第 1 条：\n"
            f"{first_block}\n\n"
            "你把它归为「未来」，觉得还需要积累或等待时机。"
            "我想先好奇一下——你觉得目前还缺少哪些具体的积累或条件？"
        )

    # 兜底
    return (
        "关于你刚才表格里标出的部分，我想和你多聊几句。\n"
        f"我们先从这一条开始好吗？\n{first_label}\n"
        "（先不改热爱、优势等前提字段；聊完请点右上角「结束讨论」。）"
    )


# ---------------------------------------------------------------------------
# 弹窗/条带文案（字段级模板）
# ---------------------------------------------------------------------------

def build_bar_copy_zh(kind: str, items: List[Dict[str, Any]], llm_failed: bool) -> str:
    """内嵌条说明文案（非弹窗）。按步骤分别展示字段级条目列表。"""
    n = len(items)

    if llm_failed:
        return (
            "系统刚才没能自动完成假设检查。\n"
            "你可以直接「进入下一步」，也可以点「深入讨论」，我们在右侧把不确定的条目逐一聊清楚。"
        )

    if kind == "mismatch":
        head = f"我注意到你标记了以下「不匹配」的项（共 {n} 条）："
        explain = "我们可以一起分析背后的原因、影响，以及是否存在调整后的匹配可能。"
    elif kind == "hypothesis_def":
        head = "我注意到，你写的这几条职业假设，与我们通常理解的（比如具体、可检验、有边界）有一些不同。对于这些内容，我想带你深入探讨，发掘出你可能还没意识到的可能性。"
        explain = "我们会基于你的热爱和优势，逐条把假设聊得更具体。"
    elif kind == "should_do":
        head = f"我注意到你标记了以下「应该做」的项（共 {n} 条）："
        explain = "我们可以一起看看这些选择背后是外界期待，还是也存在内在驱动力。"
    elif kind == "future":
        head = f"我注意到你标记了以下「未来」的项（共 {n} 条）："
        explain = "我们可以一起梳理：哪些条件还缺，哪些小步其实现在就能开始。"
    else:
        head = "我注意到以下条目："
        explain = "如果你愿意，我们可以逐条深入讨论。"

    body = _item_lines(kind, items, limit=8)

    return (
        f"{head}\n\n"
        f"待讨论条目：\n{body}\n\n"
        f"{explain}\n"
        "如果你愿意，点击「深入讨论」；也可以直接「进入下一步」。"
    )


# ---------------------------------------------------------------------------
# 闸门入口（不变）
# ---------------------------------------------------------------------------

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
        pending_rows = collect_step3_pending_rows(table_data)
        cand = collect_step3_hypothesis_candidates(table_data)
        kind = "hypothesis_def"
        llm_reviewed: List[Dict[str, Any]] = []
        if cand:
            flagged, llm_failed = await llm_flag_step3_hypotheses(llm, cand)
            if llm_failed:
                llm_reviewed = list(cand)
            else:
                llm_reviewed = list(flagged)
        # pending 行强制讨论 + LLM 判定的不合格行
        items = pending_rows + llm_reviewed
        if not items:
            return None
    else:
        return None

    if step in (2, 5, 6) and not items:
        return None

    # 重新生成 label（LLM 筛选后的 items 仍然携带原始字段，直接格式化即可）
    for item in items:
        if "label" not in item:
            item["label"] = _item_label(kind, item)

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


# ---------------------------------------------------------------------------
# 筛选结果为零的兜底弹窗（step 1/2/3 过滤后 0 条）
# ---------------------------------------------------------------------------

_ZERO_BAR_COPY: Dict[str, str] = {
    "zero_strength": (
        "看起来你把所有优势都标记为了「不确定」，"
        "这意味着暂时没有可继续的方向进入下一步。\n\n"
        "我们可以聊聊为什么这些方向暂时不确定，或者你也可以回到表格重新选择。"
    ),
    "zero_match": (
        "所有热爱和优势组合都被标记为「不匹配」，暂时无法进入假设生成环节。\n\n"
        "我们可以一起讨论：是都不匹配，还是需要调整判断标准？"
    ),
    "zero_valid": (
        "所有假设行都标记了「无」，暂时无法进入价值观筛选。\n\n"
        "我们可以聊聊是什么让你对目前的假设都还不确定。"
    ),
    "zero_value": (
        "价值观筛选后没有匹配的方向，暂时无法继续。\n\n"
        "我们可以聊聊为什么这些假设都不太符合你的核心价值观。"
    ),
}

_ZERO_OPENING: Dict[str, str] = {
    "zero_strength": (
        "你好呀，我注意到你把所有的优势都标记为了「不确定」。\n"
        "这完全没问题——有时候我们对自己的优势习以为常，反而意识不到它就是优势。\n\n"
        "我们可以聊聊：在做这些事情的时候，有没有哪些是你觉得特别自然、不费力的？"
        "讨论完请点右上角「结束讨论」回到表格。"
    ),
    "zero_match": (
        "你好呀，我注意到你把所有热爱与优势的组合都标记为了「不匹配」。\n"
        "这其实很值得聊聊——也许它们不是真的不匹配，而是匹配的方式和你想象的不太一样。\n\n"
        "我们可以逐条看看：第一个「不匹配」的组合，当时你心里是怎么想的？"
        "讨论完请点右上角「结束讨论」回到表格。"
    ),
    "zero_valid": (
        "你好呀，我注意到你对所有生成的职业假设都选择了「无」。\n"
        "这很正常——也许这些假设没有击中你心里真正想做的事。\n\n"
        "我们可以聊聊：如果不考虑任何限制，你最想做的三件事是什么？"
        "讨论完请点右上角「结束讨论」回到表格。"
    ),
    "zero_value": (
        "你好呀，价值观筛选后暂时没有匹配的方向。\n"
        "这可能意味着目前的假设方向和你的核心价值观之间还有些距离。\n\n"
        "我们可以聊聊：对你来说最重要的价值观是什么？"
        "讨论完请点右上角「结束讨论」回到表格。"
    ),
}

_ZERO_INJECTION_SUFFIX = (
    "\n\n回复风格要求：\n"
    "- 语气温和、简洁，优先短段落；\n"
    "- 一次只问一个问题，不要连发多问；\n"
    "- 引导用户重新审视被过滤的内容，帮助发现遗漏的可能性。\n\n"
    "讨论充分后，请只引导点击右上角「结束讨论」回到左侧表格修改。"
)


def build_zero_results_gate(
    *,
    step: int,
    initial_rows: List[Dict[str, Any]],
    kind: str,
) -> Dict[str, Any]:
    """筛选结果为零时的兜底弹窗包（与 neg_gate gate_pkg 结构一致，同步，无需 LLM）。"""
    bar = _ZERO_BAR_COPY.get(kind, _ZERO_BAR_COPY["zero_strength"])
    opening = _ZERO_OPENING.get(kind, _ZERO_OPENING["zero_strength"])

    # injection: 步骤专属 system（如有）+ zero_results 后缀
    step_system = get_deep_chat_step_system(step, llm_failed=False)
    inj = (f"\n{step_system}\n\n" if step_system else "") + _ZERO_INJECTION_SUFFIX

    neg_state: Dict[str, Any] = {
        "status": "awaiting_choice",
        "step": step,
        "kind": kind,
        "items": [],
        "llm_failed": False,
        "injection_zh": inj,
        "opening_zh": opening,
        "bar_copy_zh": bar,
    }
    pending: Dict[str, Any] = {
        "step": step,
        "table_data": initial_rows,
    }
    confirm = {
        "filter_step": step,
        "kind": kind,
        "items": [],
        "bar_copy_zh": bar,
        "llm_failed": False,
    }
    return {"neg_state": neg_state, "pending": pending, "confirm": confirm}
