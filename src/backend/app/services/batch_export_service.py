"""
批量导出服务（admin 按报告维度，聚合各 phase 的会话）

每个 report 产出三类产物：
  1. ``raw`` —— 各 phase 的完整 JSON 源文件（含 anchor、对话全文、结论、题库等，
     即 ``{step_id}__{session_id}.json`` 的内容，外加 report 元信息），文件名
     ``raw/{step_id}__{session_id}.json``。
  2. ``md`` —— 提取纯净对话与结论的 Markdown，仅保留角色 + 正文 + 阶段结论，
     不含时间戳、token_usage 等噪音。文件名 ``report_<report_id>.md``。
  3. ``stats`` —— 统计 JSON。每 phase：AI 字数 / 用户字数 / 消息数 / 用时 /
     token 消耗（prompt/completion/total/cache）。文件名 ``stats.json``。

导出规则（重要）：
  - 遍历每个 step 的 ``session_ids``，而非只看 ``selected_session_id``。
  - 选会话优先级：``selected_session_id`` > ``session_ids`` 的最后一个（最新一次）。
  - 因此 rumination 走到中途（有 session 未 select）也能导出。
  - 完全没有 session 的 step 不输出。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from app.utils.report_registry import STEP_IDS, ReportRegistry
from app.utils.helpers import parse_iso_to_utc
from app.utils.rumination_export import (
    build_rumination_tables,
    build_summary,
    load_raw_rumination_progress,
    slice_conversation_by_step,
)

logger = logging.getLogger(__name__)

# 中文阶段名映射
PHASE_LABEL_CN: Dict[str, str] = {
    "values": "价值观",
    "strengths": "优势",
    "interests": "热爱",
    "purpose": "使命",
    "rumination": "沉淀",
}

# 单次批量导出硬上限
MAX_BATCH_REPORTS = 50

# 消息角色 -> 中文
ROLE_CN = {
    "user": "用户",
    "assistant": "助手",
    "system": "系统",
    "tool": "工具",
    "conclusion_card": "结论卡片",
}

# markdown 正文里只保留这些角色的消息（其余如 system/tool 视为噪音过滤掉）
MD_ROLES_KEEP = {"user", "assistant", "conclusion_card"}

# token 统计涉及的字段
TOKEN_FIELDS = (
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "prompt_cache_hit_tokens",
    "prompt_cache_miss_tokens",
)

# 活跃时长计算的会话超时阈值：相邻消息间隔超过此值视为用户离开，不计入。
# 30 分钟是行业默认（GA/Mixpanel 等会话统计同口径），可正确剔除「跨天回来改」。
SESSION_GAP_MAX_SECONDS = 1800


class BatchExportService:
    """批量导出服务：按 report 聚合各 phase 数据，产出 raw JSON + 纯净 Markdown + 统计。"""

    def __init__(self) -> None:
        self.registry = ReportRegistry()

    async def collect_report_export(
        self,
        report_id: str,
        fmt: str = "md",
    ) -> Optional[List[Tuple[str, bytes]]]:
        """
        收集单个 report 的全部导出文件。

        Args:
            report_id: 报告 ID
            fmt: 兼容旧参数；当前实现固定同时产出 raw JSON + md + stats，仅做校验。

        Returns:
            ``[(zip_inner_path, file_bytes), ...]``；report 不存在返回 None。
        """
        fmt_norm = (fmt or "md").strip().lower()
        if fmt_norm not in ("md", "txt"):
            fmt_norm = "md"

        record = self.registry.get_report_by_id(report_id)
        if not record:
            logger.warning("批量导出：report 不存在，跳过: %s", report_id)
            return None

        files: List[Tuple[str, bytes]] = []

        # 解析每个 step 实际要导出的 session（selected 优先，否则 session_ids 最后一个）
        phase_sessions: List[Tuple[str, int, str, bool]] = []  # (step_id, seq, session_id, is_selected)
        seq = 0
        for step_id in STEP_IDS:
            step = record.get("steps", {}).get(step_id) or {}
            session_ids = step.get("session_ids") or []
            selected = step.get("selected_session_id")
            chosen = self._pick_session(selected, session_ids)
            if not chosen:
                continue
            seq += 1
            phase_sessions.append((step_id, seq, chosen, bool(selected)))

        # —— 产物 1：各 phase 完整 JSON 源文件 ——
        # 用于统计的中间结果
        per_phase_stats: List[dict] = []
        for step_id, _, session_id, is_selected in phase_sessions:
            raw = self._load_step_session_json(report_id, step_id, session_id)
            if raw is None:
                raw = {
                    "report_id": report_id,
                    "step_id": step_id,
                    "session_id": session_id,
                    "error": "源对话文件缺失",
                }
                per_phase_stats.append(
                    self._empty_phase_stat(step_id, session_id, is_selected, missing=True)
                )
            else:
                raw.setdefault("report_id", report_id)
                raw.setdefault("report_activation_code", record.get("activation_code"))
                raw.setdefault("report_user_id", record.get("user_id"))
                raw.setdefault(
                    "report_anchor_summary",
                    (record.get("steps", {}).get(step_id) or {}).get("anchor_summary"),
                )
                raw.setdefault("report_final_conclusion", record.get("final_conclusion"))
                raw.setdefault("report_step_is_selected", is_selected)
                per_phase_stats.append(
                    self._compute_phase_stat(step_id, session_id, is_selected, raw)
                )

            inner_path = f"raw/{step_id}__{session_id}.json"
            files.append((inner_path, json.dumps(raw, ensure_ascii=False, indent=2).encode("utf-8")))

        # —— 产物 2：纯净 Markdown ——
        md_content = self._build_clean_markdown(
            report_id=report_id,
            record=record,
            phase_sessions=phase_sessions,
        )
        ext = "md" if fmt_norm == "md" else "txt"
        files.append((f"report_{report_id}.{ext}", md_content.encode("utf-8")))

        # —— 产物 3：统计 JSON ——
        stats = self._build_stats(report_id=report_id, record=record, per_phase=per_phase_stats)
        files.append(("stats.json", json.dumps(stats, ensure_ascii=False, indent=2).encode("utf-8")))

        # —— 产物 4：rumination 表格 JSON（结构化 step1~7 表格 + 前置 keywords） ——
        rumination_tables = build_rumination_tables(report_id, registry=self.registry)
        files.append((
            "rumination_tables.json",
            json.dumps(rumination_tables, ensure_ascii=False, indent=2).encode("utf-8"),
        ))

        # —— 产物 5：结论汇总 JSON（report 级 + 5 phase conclusion_final） ——
        summary = build_summary(report_id, registry=self.registry)
        files.append((
            "summary.json",
            json.dumps(summary, ensure_ascii=False, indent=2).encode("utf-8"),
        ))

        # —— 产物 6：rumination_progress.json 原样打包（完整溯源） ——
        raw_progress = load_raw_rumination_progress(report_id, registry=self.registry)
        if raw_progress is not None:
            files.append((
                "raw/rumination_progress.json",
                json.dumps(raw_progress, ensure_ascii=False, indent=2).encode("utf-8"),
            ))

        return files

    # ------------------------------------------------------------------
    # 会话选取
    # ------------------------------------------------------------------

    @staticmethod
    def _pick_session(selected: Optional[str], session_ids: List[str]) -> Optional[str]:
        """优先 selected；否则取 session_ids 最后一个（最新会话）；都没有返回 None。"""
        sel = (selected or "").strip()
        if sel:
            return sel
        ids = [s for s in (session_ids or []) if isinstance(s, str) and s.strip()]
        return ids[-1] if ids else None

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------

    def _compute_phase_stat(
        self,
        step_id: str,
        session_id: str,
        is_selected: bool,
        raw: dict,
    ) -> dict:
        """计算单个 phase 的统计指标。"""
        msgs = raw.get("messages") or []
        ai_chars = 0
        user_chars = 0
        msg_counts: Dict[str, int] = {}
        token_acc: Dict[str, int] = {f: 0 for f in TOKEN_FIELDS}
        has_token = False
        timestamps: List[str] = []

        for m in msgs:
            if not isinstance(m, dict):
                continue
            role = m.get("role") or "unknown"
            msg_counts[role] = msg_counts.get(role, 0) + 1

            content = m.get("content")
            text = self._content_to_text(content)
            if role == "assistant":
                ai_chars += len(text)
            elif role == "user":
                user_chars += len(text)

            tu = m.get("token_usage")
            if isinstance(tu, dict):
                has_token = True
                for f in TOKEN_FIELDS:
                    v = tu.get(f)
                    if isinstance(v, (int, float)):
                        token_acc[f] += int(v)

            ts = m.get("created_at")
            if isinstance(ts, str) and ts:
                timestamps.append(ts)

        duration_seconds = self._compute_duration_seconds(timestamps)

        return {
            "step_id": step_id,
            "step_label_cn": PHASE_LABEL_CN.get(step_id, step_id),
            "session_id": session_id,
            "is_selected_session": is_selected,
            "is_completed": is_selected,  # selected 视为该阶段已确认完成
            "message_count": len(msgs),
            "message_count_by_role": msg_counts,
            "ai_chars": ai_chars,
            "user_chars": user_chars,
            "total_dialogue_chars": ai_chars + user_chars,
            "duration_seconds": duration_seconds,
            "duration_human": self._humanize_duration(duration_seconds),
            "first_message_at": timestamps[0] if timestamps else None,
            "last_message_at": timestamps[-1] if timestamps else None,
            "token_usage": token_acc if has_token else None,
            "conclusion_state": (raw.get("metadata") or {}).get("conclusion_state"),
            "has_conclusion_final": bool((raw.get("metadata") or {}).get("conclusion_final")),
        }

    def _empty_phase_stat(
        self,
        step_id: str,
        session_id: str,
        is_selected: bool,
        missing: bool = False,
    ) -> dict:
        return {
            "step_id": step_id,
            "step_label_cn": PHASE_LABEL_CN.get(step_id, step_id),
            "session_id": session_id,
            "is_selected_session": is_selected,
            "is_completed": is_selected,
            "message_count": 0,
            "message_count_by_role": {},
            "ai_chars": 0,
            "user_chars": 0,
            "total_dialogue_chars": 0,
            "duration_seconds": 0,
            "duration_human": "0 min",
            "first_message_at": None,
            "last_message_at": None,
            "token_usage": None,
            "source_missing": missing,
        }

    def _build_stats(self, report_id: str, record: dict, per_phase: List[dict]) -> dict:
        """组装整份 stats.json。"""
        total_ai = sum(p.get("ai_chars", 0) for p in per_phase)
        total_user = sum(p.get("user_chars", 0) for p in per_phase)
        total_msgs = sum(p.get("message_count", 0) for p in per_phase)
        total_dur = sum(p.get("duration_seconds", 0) for p in per_phase)
        total_token: Dict[str, int] = {f: 0 for f in TOKEN_FIELDS}
        token_present = False
        for p in per_phase:
            tu = p.get("token_usage")
            if not tu:
                continue
            token_present = True
            for f in TOKEN_FIELDS:
                total_token[f] += int(tu.get(f, 0))

        return {
            "report_id": report_id,
            "user_id": record.get("user_id"),
            "activation_code": record.get("activation_code"),
            "report_status": record.get("status"),
            "report_created_at": record.get("created_at"),
            "report_updated_at": record.get("updated_at"),
            "report_final_conclusion": record.get("final_conclusion"),
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total_phases_exported": len(per_phase),
                "completed_phases": sum(1 for p in per_phase if p.get("is_completed")),
                "total_messages": total_msgs,
                "total_ai_chars": total_ai,
                "total_user_chars": total_user,
                "total_dialogue_chars": total_ai + total_user,
                "total_duration_seconds": total_dur,
                "total_duration_human": self._humanize_duration(total_dur),
                "total_token_usage": total_token if token_present else None,
            },
            "phases": per_phase,
        }

    @staticmethod
    def _content_to_text(content) -> str:
        """把消息 content（可能是 str / list[fragment] / dict）转成纯文本用于字数统计。"""
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for c in content:
                if isinstance(c, dict):
                    parts.append(c.get("text") or "")
                else:
                    parts.append(str(c))
            return "".join(parts)
        if isinstance(content, dict):
            return content.get("text") or str(content)
        return str(content)

    @staticmethod
    def _compute_duration_seconds(timestamps: List[str]) -> int:
        """
        计算「活跃会话时长」（秒）。

        算法：消息按时间排序，累加相邻消息的时间间隔；若某段间隔超过
        ``SESSION_GAP_MAX_SECONDS``（默认 30 分钟），视为用户离开，该段不计入。
        这样可正确处理「用户跨天/跨周回来 new chat 或重新填写」的场景——
        首尾直接相减会把离开的几十小时也算进去，活跃时长只计真实对话时间。

        数据依据：跨天会话首尾相减可达数千~数万分钟，30min 超时切分后均回落
        到个位~百分钟量级，与连续会话（两种口径一致）的规模吻合。
        """
        if len(timestamps) < 2:
            return 0
        try:
            pts = []
            for ts in timestamps:
                if not isinstance(ts, str) or not ts:
                    continue
                pts.append(parse_iso_to_utc(ts))
            if len(pts) < 2:
                return 0
            pts.sort()
            total = 0
            for i in range(1, len(pts)):
                gap = (pts[i] - pts[i - 1]).total_seconds()
                if 0 < gap <= SESSION_GAP_MAX_SECONDS:
                    total += gap
            return int(total)
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _humanize_duration(seconds: int) -> str:
        """把秒数转成分钟单位的简短表达，如 ``64.0 min``、``200.2 min``。"""
        if seconds <= 0:
            return "0 min"
        return f"{seconds / 60:.1f} min"

    # ------------------------------------------------------------------
    # Markdown
    # ------------------------------------------------------------------

    def _load_step_session_json(self, report_id: str, step_id: str, session_id: str) -> Optional[dict]:
        """读取 report 目录下 {step_id}__{session_id}.json 源文件。"""
        file_path = self.registry.get_step_session_file(report_id, step_id, session_id)
        if not file_path.is_file():
            return None
        try:
            return json.loads(file_path.read_text(encoding="utf-8") or "{}")
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("批量导出：源 JSON 解析失败: %s err=%s", file_path, e)
            return None

    def _build_clean_markdown(
        self,
        report_id: str,
        record: dict,
        phase_sessions: List[Tuple[str, int, str, bool]],
    ) -> str:
        """生成纯净 Markdown：报告头 + 每个 phase 的「结论 + 对话」。"""
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S") + " UTC"
        lines: List[str] = []
        lines.append(f"# 寻录探索报告 - {report_id}")
        lines.append("")
        lines.append(f"- 用户ID: {record.get('user_id') or ''}")
        lines.append(f"- 激活码: {record.get('activation_code') or ''}")
        lines.append(f"- 报告状态: {record.get('status') or ''}")
        lines.append(f"- 导出时间: {now_str}")
        lines.append("")

        final_conc = record.get("final_conclusion")
        if final_conc:
            lines.append("## 报告最终结论")
            lines.append("")
            lines.append(self._stringify(final_conc))
            lines.append("")

        if not phase_sessions:
            lines.append("（本报告暂无已完成的探索阶段）")
            return "\n".join(lines).rstrip() + "\n"

        for step_id, seq, session_id, is_selected in phase_sessions:
            label_cn = PHASE_LABEL_CN.get(step_id, step_id)
            title = f"## {seq}. {label_cn}（{step_id}）"
            if not is_selected:
                # 标注该阶段为「进行中」（有会话但未确认选定）
                title += "  ⚠️ 进行中（未确认）"
            lines.append(title)
            lines.append("")

            raw = self._load_step_session_json(report_id, step_id, session_id)
            if raw is None:
                lines.append("> （该阶段对话源文件缺失）")
                lines.append("")
                continue

            # rumination 走特殊渲染：前置结论 + 每个 step 的（表格 + 对话切片）
            if step_id == "rumination":
                self._render_rumination_md(lines, report_id, raw)
                continue

            # 其他 phase：结论 + 完整对话
            conclusion_text = self._extract_phase_conclusion(raw)
            if conclusion_text:
                lines.append("### 结论")
                lines.append("")
                lines.append(conclusion_text)
                lines.append("")

            lines.append("### 对话记录")
            lines.append("")
            self._render_dialogue_md(lines, raw.get("messages") or [])

        return "\n".join(lines).rstrip() + "\n"

    def _render_dialogue_md(self, lines: List[str], msgs: list) -> None:
        """把消息列表渲染为 md 对话段落（就地追加到 lines）。"""
        dialogue_lines: List[str] = []
        for m in msgs:
            if not isinstance(m, dict):
                continue
            role = m.get("role") or ""
            if role not in MD_ROLES_KEEP:
                continue
            content = m.get("content")
            text = self._stringify(content)
            if not text.strip():
                continue
            if role == "conclusion_card":
                continue
            speaker = ROLE_CN.get(role, role)
            dialogue_lines.append(f"**{speaker}**：{text}")
            dialogue_lines.append("")
        if dialogue_lines:
            lines.extend(dialogue_lines)
        else:
            lines.append("> （本阶段无对话记录）")
            lines.append("")

    # rumination step 状态标注（md 用）
    _STEP_STATUS_MD = {
        "submitted": "✅ 已提交",
        "submitted_empty": "✅ 已提交（筛选后 0 行）",
        "skipped": "⏭ 已跳过",
        "not_reached": "— 未进行",
    }

    def _render_rumination_md(self, lines: List[str], report_id: str, raw: dict) -> None:
        """渲染 rumination 章节：前置结论 + 每个 step（表格 + 对话切片）。

        rumination 全局结论不在此处（留在 md 顶部「报告最终结论」）。
        """
        tables = build_rumination_tables(report_id, registry=self.registry)

        # —— 前置结论（4 phase keywords） ——
        prereq = tables.get("prerequisites") or {}
        if any(prereq.values()):
            lines.append("### 前置结论")
            lines.append("")
            phase_label = {
                "values": "价值观",
                "strengths": "优势",
                "interests": "热爱",
                "purpose": "使命",
            }
            for ph in ("values", "strengths", "interests", "purpose"):
                kws = prereq.get(ph) or []
                if kws:
                    lines.append(f"- {phase_label.get(ph, ph)}：{('、'.join(kws))}")
            lines.append("")

        # —— step3 组合矩阵 / 讨论结论（若存在，放在 step3 之前作为元信息） ——
        combo_matrix = tables.get("combo_matrix")
        combo_conclusions = tables.get("combo_conclusions")

        # —— 按 step 渲染（表格 + 对话切片） ——
        steps_data = tables.get("steps") or {}
        msgs = raw.get("messages") or []
        sliced = slice_conversation_by_step(msgs)
        unified = sliced.get("_unified")  # 老数据兜底

        # step 中文标题（1~4 仅数字，按设计；5/6/7 也只数字）
        for step_no in range(1, 8):
            sk = str(step_no)
            sd = steps_data.get(sk) or {}
            status = sd.get("status") or "not_reached"
            row_count = sd.get("row_count", 0)
            status_cn = self._STEP_STATUS_MD.get(status, status)
            title = f"### Step {step_no}（{row_count} 行，{status_cn}）"
            lines.append(title)
            lines.append("")

            # 表格（submitted 有行才渲染）
            rows = sd.get("rows") or []
            cols = sd.get("columns") or []
            if rows and cols:
                self._render_table_md(lines, cols, rows)
                lines.append("")

            # step3 特殊：组合矩阵 + 讨论结论（仅 step3 且有数据时）
            if step_no == 3 and combo_matrix:
                lines.append("**组合矩阵：**")
                lines.append("")
                self._render_table_md(
                    lines,
                    ["combo_id", "passion_name", "strength_name"],
                    combo_matrix,
                )
                lines.append("")
            if step_no == 3 and combo_conclusions:
                lines.append("**组合讨论结论：**")
                lines.append("")
                lines.append(self._stringify(combo_conclusions))
                lines.append("")

            # 对话切片
            lines.append("#### 对话记录")
            lines.append("")
            step_msgs = sliced.get(sk) if not unified else None
            if unified:
                # 老数据：首个有内容的 step 放完整对话，其余不再重复
                if step_no == 1:
                    lines.append("> 该会话为旧格式，对话未按步骤细分，完整对话如下：")
                    lines.append("")
                    self._render_dialogue_md(lines, unified)
                else:
                    lines.append("> （完整对话见 Step 1）")
                    lines.append("")
            elif step_msgs:
                self._render_dialogue_md(lines, step_msgs)
            else:
                lines.append("> （本步骤无对话记录）")
                lines.append("")

    def _render_table_md(self, lines: List[str], columns: List[str], rows: List[dict]) -> None:
        """把行数据渲染成 markdown 表格（就地追加到 lines）。

        长文本单元格内的换行替换为空格，避免破坏 md 表格格式。
        """
        if not columns or not rows:
            return
        header = "| " + " | ".join(self._md_cell(c) for c in columns) + " |"
        sep = "| " + " | ".join("---" for _ in columns) + " |"
        lines.append(header)
        lines.append(sep)
        for row in rows:
            if not isinstance(row, dict):
                continue
            cells = [self._md_cell(row.get(c)) for c in columns]
            lines.append("| " + " | ".join(cells) + " |")

    @staticmethod
    def _md_cell(value) -> str:
        """转义单元格值：换行→空格，| 转义，None→空串。"""
        if value is None:
            return ""
        s = value if isinstance(value, str) else str(value)
        s = s.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").replace("|", "\\|")
        return s.strip()

    def _extract_phase_conclusion(self, raw: dict) -> str:
        """从 phase 源文件中提取结论文本：优先 conclusion_final，回退最后一张 conclusion_card。"""
        meta = raw.get("metadata") or {}
        final = meta.get("conclusion_final")
        if final:
            return self._stringify(final)
        for m in reversed(raw.get("messages") or []):
            if not isinstance(m, dict):
                continue
            if m.get("role") == "conclusion_card":
                payload = m.get("card_payload")
                if payload:
                    return self._stringify(payload)
                content = m.get("content")
                if content:
                    return self._stringify(content)
        return ""

    @staticmethod
    def _stringify(value) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, (dict, list)):
            try:
                return json.dumps(value, ensure_ascii=False, indent=2)
            except (TypeError, ValueError):
                return str(value)
        return str(value)
