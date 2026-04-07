"""
沉淀（rumination）筛选子步：进入该步时的右侧引导语配置。

- opening_mode：fixed=使用下方固定模板（前端模拟流式）；llm=走后端流式生成。
- 切换某步是否用 AI：只改 STEP_OPENING_MODE 中对应数字即可。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from app.core.llmapi.base import LLMMessage

OpeningMode = Literal["fixed", "llm"]

# 1–9 子步；默认仅第 6 步（工作目的 / 价值观）使用 LLM，其余固定文案
STEP_OPENING_MODE: Dict[int, OpeningMode] = {
    1: "fixed",
    2: "fixed",
    3: "fixed",
    4: "fixed",
    5: "fixed",
    6: "llm",
    7: "fixed",
    8: "fixed",
    9: "fixed",
}

# 固定引导模板。可用占位符：{row_count} {values_keywords} {table_json}
STEP_OPENING_FIXED_ZH: Dict[int, str] = {
    1: (
        "先帮你把「热爱」和「优势」排成左侧这张表，一共 {row_count} 行组合。"
        "请在本页为每一行选好「优势标记」，全部选完后点「确认」，我们再一起做匹配分析。"
    ),
    2: (
        "我已经为每个组合写好了「匹配性」说明，共 {row_count} 行。"
        "你可以浏览左侧；若有不同意见，直接在「匹配性」列改选即可。点某一行可以在右侧随时问我；"
        "都满意后点「确认」，进入下一环节。"
    ),
    3: (
        "接下来是为每个组合生成具体方向假设，左侧约 {row_count} 行。"
        "带「个人事业」「职业路径」色块的是两类不同取向；在「假设」列里选一条，或选「待定」「其他」自填。"
        "有疑问就点行，在右边跟我说。"
    ),
    4: (
        "请继续把还没选定的假设补齐（左侧仍约 {row_count} 行），可以选推荐、待定或自定义。"
        "全部选完后请点「确认」，进入下一轮整理。"
    ),
    5: (
        "这是假设确认的最后一轮（{row_count} 行）。请尽量做出选择；实在纠结可以选「待定」。"
        "整表确认后，我们会进入与价值观相关的筛选。"
    ),
    7: (
        "现在要感受每个方向对你的驱动力：左侧 {row_count} 行，请在「激情标记」里选「忍不住想做」或「应该做」。"
        "选好后点「确认」即可。"
    ),
    8: (
        "结合你现在的处境，判断每个方向是「现在」就能迈出第一步，还是更适合放在「未来」。"
        "左侧 {row_count} 行选完后点「确认」，我们会生成最终方向表。"
    ),
    9: (
        "筛选结果已经收束在左侧这张最终表（{row_count} 个方向）。"
        "你可以先通读，有需要就在对话里跟我聊；按页面提示用结论卡或文字完成确认即可。"
    ),
}

# 第 6 步 LLM：对齐产品文档「价值过滤」引导要点
STEP_6_OPENING_SYSTEM_ZH = (
    "你是职业规划咨询师，语气亲切、专业、一次只说清一件事。"
    "当前用户处于「价值过滤」环节：表格里每一行有一个已选定的职业方向假设，并新增「工作目的」列，"
    "需从用户的价值观关键词中选择最贴近的一项，或选「都不符合」「其他」。"
    "请根据下面给出的用户价值观关键词与表格 JSON，写一段开场引导语（纯文本，不要用 Markdown 标题符号）："
    "1）告知表格新增了「工作目的」列；2）引导用户思考每个假设能传递哪种价值观；"
    "3）说明可选用户给出的关键词或「无/都不符合」类选项；4）可点行在对话里提问；5）选完后点确认。"
    "篇幅控制在 120–220 字，不要编造表格里没有的列名或行内容。"
)

STEP_6_OPENING_USER_TEMPLATE_ZH = (
    "用户可选的价值观关键词（节选）：{values_keywords}\n"
    "当前表格行数：{row_count}\n"
    "当前表格数据（JSON，可能截断）：\n{table_json}\n\n"
    "请直接输出给用户的引导语正文，不要加角色自称前缀。"
)


@dataclass
class RuminationOpeningContext:
    filter_step: int
    row_count: int
    values_keywords: str
    table_json: str
    rows: List[Any]


def build_opening_context(
    *,
    filter_step: int,
    progress: Dict[str, Any],
    values_list: List[str],
) -> RuminationOpeningContext:
    """从 progress 快照读取当前子步表格，供固定文案格式化或 LLM 提示词使用。"""
    step = max(1, min(9, int(filter_step)))
    snapshots = progress.get("filter_step_snapshots") or {}
    sk = str(step)
    ent = snapshots.get(sk) or {}
    rows = ent.get("submitted")
    if rows is None:
        rows = ent.get("initial")
    if not isinstance(rows, list):
        rows = []
    if not rows and int(progress.get("filter_step") or 0) == step:
        ft = progress.get("filter_table")
        if isinstance(ft, list):
            rows = ft

    row_count = len(rows)
    values_keywords = "、".join(values_list[:12]) if values_list else ""
    try:
        table_json = json.dumps(rows, ensure_ascii=False) if rows else "[]"
    except (TypeError, ValueError):
        table_json = "[]"
    max_len = 12000
    if len(table_json) > max_len:
        table_json = table_json[:max_len] + "…（已截断）"

    return RuminationOpeningContext(
        filter_step=step,
        row_count=row_count,
        values_keywords=values_keywords or "（暂无关键词，可引导用户依表头选择）",
        table_json=table_json,
        rows=rows,
    )


def get_opening_mode(filter_step: int) -> OpeningMode:
    step = max(1, min(9, int(filter_step)))
    return STEP_OPENING_MODE.get(step, "fixed")


def render_fixed_opening_zh(filter_step: int, ctx: RuminationOpeningContext) -> str:
    step = max(1, min(9, int(filter_step)))
    template = STEP_OPENING_FIXED_ZH.get(step, "")
    if not template:
        return "请查看左侧表格，按提示完成本步选择后点击「确认」。"
    return template.format(
        row_count=ctx.row_count,
        values_keywords=ctx.values_keywords,
        table_json=ctx.table_json,
    )


def build_step_6_opening_llm_messages(ctx: RuminationOpeningContext) -> List[LLMMessage]:
    user = STEP_6_OPENING_USER_TEMPLATE_ZH.format(
        values_keywords=ctx.values_keywords,
        row_count=ctx.row_count,
        table_json=ctx.table_json,
    )
    return [
        LLMMessage(role="system", content=STEP_6_OPENING_SYSTEM_ZH),
        LLMMessage(role="user", content=user),
    ]


def build_opening_llm_messages(filter_step: int, ctx: RuminationOpeningContext) -> List[LLMMessage]:
    """
    按子步组装 LLM 消息。新增「某步改用 AI 引导」时在此分支实现对应提示词即可。
    """
    step = max(1, min(9, int(filter_step)))
    if step == 6:
        return build_step_6_opening_llm_messages(ctx)
    raise ValueError(f"rumination opening llm not implemented for step {step}")
