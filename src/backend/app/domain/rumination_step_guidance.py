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

# 1–7 子步；默认仅第 4 步（工作目的 / 价值观）使用 LLM，其余固定文案
STEP_OPENING_MODE: Dict[int, OpeningMode] = {
    1: "fixed",
    2: "fixed",
    3: "fixed",
    4: "llm",
    5: "fixed",
    6: "fixed",
    7: "fixed",
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
        "带「个人事业」「职业路径」色块的是两类不同取向；在「假设」列里选一条，或选「暂未选定」「其他」自填。"
        "若暂不选定可先点确认查看引导；至少一行需为有效假设后才能进入价值观筛选。有疑问就点行，在右边跟我说。"
    ),
    4: (
        "左侧表格已增加「工作目的」列（约 {row_count} 行）。请结合您的价值观为每一行选择最贴近的一项，"
        "或选「都不符合」「其他」。可点行在右侧提问；选完后点「确认」。"
    ),
    5: (
        "现在要感受每个方向对你的驱动力：左侧 {row_count} 行，请在「激情标记」里选「忍不住想做」或「应该做」。"
        "选好后点「确认」即可。"
    ),
    6: (
        "结合你现在的处境，判断每个方向是「现在」就能迈出第一步，还是更适合放在「未来」。"
        "左侧 {row_count} 行选完后点「确认」，我们会生成最终方向表。"
    ),
    7: (
        "左侧是收束后的方向列表（{row_count} 行）。请点击整行点选 1–3 个你最认同的方向，点表格「确认」后在右侧查看结论卡；"
        "仍可在对话里随时问我。"
    ),
}

# 第 4 步 LLM：对齐产品文档「价值过滤」引导要点
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
    step = max(1, min(7, int(filter_step)))
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

    # 第 2 步：优先用当前 progress.filter_table，避免快照 initial 未随第 1 步重提交流更新导致 row_count 偏小
    if (
        step == 2
        and int(progress.get("filter_step") or 0) == 2
        and isinstance(progress.get("filter_table"), list)
        and (progress.get("filter_table") or [])
    ):
        rows = list(progress["filter_table"])

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
    step = max(1, min(7, int(filter_step)))
    return STEP_OPENING_MODE.get(step, "fixed")


def render_fixed_opening_zh(filter_step: int, ctx: RuminationOpeningContext) -> str:
    step = max(1, min(7, int(filter_step)))
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
    step = max(1, min(7, int(filter_step)))
    if step == 4:
        return build_step_6_opening_llm_messages(ctx)
    raise ValueError(f"rumination opening llm not implemented for step {step}")


# ---------------------------------------------------------------------------
# 主对话 system 提示词末尾注入：按筛选子步追加一小段「当前环节侧重」（暖提示，非题库）
# 留空字符串表示该步不注入。编辑文案只改本字典即可。
# ---------------------------------------------------------------------------
RUMINATION_CHAT_STEP_ADDON_ZH: Dict[int, str] = {
    1: "用户正在完成「热爱×优势」组合表与优势标记。请语气温和，一次只回应一件事；若对方问表格操作，用简短步骤说明，不要代替对方做选择。",
    2: "用户正在浏览或修订每行「匹配性」判断。请帮助对方澄清犹豫点，不急于推进到下一步。",
    3: "用户正在为每行选择方向假设（个人事业/职业路径等）。若对方纠结，可帮其区分两类取向的差异，不替选答案。",
    4: "用户正在为每行选择「工作目的」与价值观的对应关系。可提醒对方对照其价值观关键词，语气耐心，不催促一次性改完。",
    5: "用户正在标注每行方向的「激情标记」。帮助对方分辨「忍不住想做」与「应该做」的身体感受差异。",
    6: "用户正在判断每行方向更适合「现在」还是「未来」起步。可帮其看见现实条件与心之所向的张力，不替做决定。",
    7: "用户正在从收束列表中点选最认同的 1–3 个方向。请尊重对方节奏，可总结差异点协助取舍，不夸大某一选项。",
}

RUMINATION_CHAT_STEP_ADDON_EN: Dict[int, str] = {
    1: "The user is filling the passion×strength grid and strength tags. Stay warm; one focus per reply. If they ask how the table works, give short steps—do not choose for them.",
    2: "The user is reviewing or editing per-row “fit” judgments. Help clarify doubts; do not rush the next step.",
    3: "The user is picking direction hypotheses per row. If they hesitate, contrast the two orientations without picking an answer for them.",
    4: "The user is mapping each row to a work-purpose / values option. Gently remind them of their values keywords; be patient.",
    5: "The user is marking passion signals per row. Help them sense the difference between “can’t help but want” vs “should do.”",
    6: "The user is labeling whether each direction fits “now” or “later.” Hold the tension between reality and desire; do not decide for them.",
    7: "The user is selecting 1–3 final directions. Respect their pace; summarize contrasts to support choice without hyping one option.",
}


def get_rumination_chat_step_addon(filter_step: int, locale: str = "zh") -> str:
    """供主对话 system 模板注入；filter_step 非法或文案为空则返回空串。"""
    step = max(1, min(7, int(filter_step)))
    loc = (locale or "zh").strip().lower()
    if loc.startswith("en"):
        text = RUMINATION_CHAT_STEP_ADDON_EN.get(step, "")
    else:
        text = RUMINATION_CHAT_STEP_ADDON_ZH.get(step, "")
    return (text or "").strip()
