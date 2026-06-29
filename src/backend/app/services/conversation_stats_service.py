"""
对话每轮平均时长统计服务（admin 后台用）。

==========================================================================
【设计说明】
- 在线部分（admin 接口）：直接从 session 对话历史算，复用 ExportService 的数据加载逻辑
  （ExportService.collect_export_data），不经过 T1 导出文件的正则解析。
- 离线部分（scripts/conversation_stats.py）：解析 T1 导出的 md/txt 文件，供批量/历史分析。
  两处的"切轮 + 时长计算"逻辑抽公共函数 compute_turn_stats_from_messages，保证一致。

【"一轮"界定规则（冻结）】
1. 按"用户消息"切轮：每出现一条 role=user 的消息算一轮的开始。
2. 每轮时长 = 下一轮 user 消息时间戳 - 本轮 user 消息时间戳（秒）。
3. 最后一轮没有"下一轮"，用该轮最后一条 AI(assistant) 消息时间戳收尾；
   若无 assistant 消息，则该轮不计入时长（但计轮数）。
4. 跨 phase 的首尾消息时长可能异常大：单轮时长 > 2 小时（7200s）视为异常，
   计入轮数但时长不计入总时长/平均（在 per_phase 中标注 skipped_long_turns）。
5. 缺时间戳的 user 消息 -> 跳过该轮且 warning（不计轮数、不计时长）。
==========================================================================
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.services.export_service import ExportService
from app.utils.report_registry import ReportRegistry, STEP_IDS

logger = logging.getLogger(__name__)

# 中文阶段名映射（与 batch_export_service 保持一致）
PHASE_LABEL_CN: Dict[str, str] = {
    "values": "价值观",
    "strengths": "优势",
    "interests": "热爱",
    "purpose": "使命",
    "rumination": "沉淀",
}

# 单轮时长异常阈值（秒）——超过 2 小时视为跨 phase 异常
ABNORMAL_TURN_THRESHOLD_SECONDS = 2 * 60 * 60


def _parse_timestamp(ts: Optional[str]) -> Optional[datetime]:
    """
    解析时间戳字符串为 datetime（容忍多种格式）。

    Args:
        ts: 时间戳字符串（ISO 格式或带时区）

    Returns:
        datetime 对象；解析失败或输入为空返回 None。
    """
    if not ts or not isinstance(ts, str):
        return None
    raw = ts.strip()
    if not raw:
        return None
    # 兼容以 Z 结尾的 UTC 时间
    try:
        # datetime.fromisoformat 在 py311+ 支持 Z 后缀，但 py310 不支持
        normalized = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
        dt = datetime.fromisoformat(normalized)
        # naive datetime 补 UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        logger.warning("时间戳解析失败: %s", raw)
        return None


def compute_turn_stats_from_messages(
    messages: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    从消息列表计算每轮时长统计（核心公共函数，在线/离线共用）。

    Args:
        messages: 消息列表，每条含 role / created_at(或 timestamp) / content。
                  消息顺序应按时间先后排列。

    Returns:
        统计字典：
        - turns: 计入时长的轮数
        - total_seconds: 计入的总时长（秒）
        - avg_seconds: 平均每轮时长（秒）
        - skipped_no_ts: 因缺时间戳跳过的轮数
        - skipped_long_turns: 因时长异常(>2h)跳过的轮数
        - total_turns_seen: 实际识别到的 user 消息总数（含跳过的）
    """
    # 按 created_at 或 timestamp 字段取时间戳
    def _get_ts(msg: Dict[str, Any]) -> Optional[str]:
        return msg.get("created_at") or msg.get("timestamp")

    # 第一步：识别所有 user 消息的时间戳，构成"轮次起点"列表
    user_turn_starts: List[Tuple[int, datetime]] = []
    skipped_no_ts = 0
    for idx, msg in enumerate(messages):
        role = (msg.get("role") or "").strip().lower()
        if role != "user":
            continue
        ts_str = _get_ts(msg)
        dt = _parse_timestamp(ts_str)
        if dt is None:
            # 缺时间戳 -> 跳过该轮且 warning
            skipped_no_ts += 1
            logger.warning("user 消息缺少有效时间戳，跳过该轮: idx=%s ts=%s", idx, ts_str)
            continue
        user_turn_starts.append((idx, dt))

    if not user_turn_starts:
        return {
            "turns": 0,
            "total_seconds": 0.0,
            "avg_seconds": 0.0,
            "skipped_no_ts": skipped_no_ts,
            "skipped_long_turns": 0,
            "total_turns_seen": skipped_no_ts,
        }

    total_turns_seen = len(user_turn_starts) + skipped_no_ts

    # 第二步：计算每轮时长
    valid_durations: List[float] = []
    skipped_long_turns = 0

    for i, (idx, start_dt) in enumerate(user_turn_starts):
        if i + 1 < len(user_turn_starts):
            # 有下一轮 -> 时长 = 下一轮起点 - 本轮起点
            _, next_dt = user_turn_starts[i + 1]
            duration = (next_dt - start_dt).total_seconds()
        else:
            # 最后一轮 -> 用本轮最后一条 assistant 消息时间戳收尾
            end_dt: Optional[datetime] = None
            # 从当前 user 消息往后扫到下一个 user 消息（或列表末尾）之间的 assistant 消息
            next_user_idx = (
                user_turn_starts[i + 1][0] if i + 1 < len(user_turn_starts) else len(messages)
            )
            for j in range(idx, next_user_idx):
                m = messages[j]
                if (m.get("role") or "").strip().lower() == "assistant":
                    dt = _parse_timestamp(_get_ts(m))
                    if dt:
                        end_dt = dt  # 取最后一条有时间戳的 assistant
            if end_dt is None:
                # 无 assistant 消息或无时间戳 -> 不计入时长（但轮数在 total_turns_seen 中已体现）
                continue
            duration = (end_dt - start_dt).total_seconds()

        # 异常时长过滤
        if duration > ABNORMAL_TURN_THRESHOLD_SECONDS:
            skipped_long_turns += 1
            logger.warning(
                "单轮时长异常(>2h)，跳过: idx=%s duration=%.0f秒", idx, duration
            )
            continue

        # 负时长（时钟回拨等）也跳过
        if duration < 0:
            skipped_long_turns += 1
            logger.warning("单轮时长为负(时钟回拨?)，跳过: idx=%s duration=%.0f秒", idx, duration)
            continue

        valid_durations.append(duration)

    turns = len(valid_durations)
    total_seconds = sum(valid_durations) if valid_durations else 0.0
    avg_seconds = (total_seconds / turns) if turns > 0 else 0.0

    return {
        "turns": turns,
        "total_seconds": round(total_seconds, 2),
        "avg_seconds": round(avg_seconds, 2),
        "skipped_no_ts": skipped_no_ts,
        "skipped_long_turns": skipped_long_turns,
        "total_turns_seen": total_turns_seen,
    }


def _aggregate_phase_stats(
    per_phase: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    聚合 per_phase 列表为总计统计。

    Args:
        per_phase: 各 phase 的统计字典列表

    Returns:
        总计统计字典
    """
    total_turns = sum(p.get("turns", 0) for p in per_phase)
    total_seconds = sum(p.get("total_seconds", 0) for p in per_phase)
    avg_seconds = (total_seconds / total_turns) if total_turns > 0 else 0.0
    total_skipped_no_ts = sum(p.get("skipped_no_ts", 0) for p in per_phase)
    total_skipped_long = sum(p.get("skipped_long_turns", 0) for p in per_phase)
    return {
        "total_turns": total_turns,
        "total_seconds": round(total_seconds, 2),
        "avg_seconds": round(avg_seconds, 2),
        "total_minutes": round(total_seconds / 60.0, 1),
        "avg_minutes": round(avg_seconds / 60.0, 1),
        "skipped_no_ts": total_skipped_no_ts,
        "skipped_long_turns": total_skipped_long,
    }


def _build_reminder_text(
    total_turns: int,
    avg_minutes: float,
    total_minutes: float,
    label: str,
) -> str:
    """
    生成中文提醒文案。

    Args:
        total_turns: 总轮数
        avg_minutes: 平均每轮分钟数
        total_minutes: 总时长分钟数
        label: 用户/报告标识（如用户名或 report_id）

    Returns:
        提醒文案字符串
    """
    return (
        f"用户 {label} 本次探索共 {total_turns} 轮对话，"
        f"平均每轮 {avg_minutes:.1f} 分钟，总时长 {total_minutes:.0f} 分钟。"
    )


class ConversationStatsService:
    """对话每轮平均时长统计服务（admin 后台用）。"""

    def __init__(self) -> None:
        """初始化，复用 ExportService 和 ReportRegistry。"""
        self.export_service = ExportService()
        self.registry = ReportRegistry()

    # ── 在线：按 user_id 聚合 ──────────────────────────────────

    async def compute_by_user(self, user_id: str) -> Dict[str, Any]:
        """
        聚合该用户所有 report 的 5 phase 对话统计。

        遍历 ReportRegistry 中 user_id 匹配的所有 report，
        对每个 report 的每个 selected_session 取对话历史，按 phase 计算统计。

        Args:
            user_id: 用户 ID

        Returns:
            统计结果字典（含 total_turns / avg_minutes / total_minutes /
            per_phase / reminder_text）
        """
        all_phase_stats: List[Dict[str, Any]] = []
        report_count = 0

        for report in self.registry.list_reports():
            if (report.get("user_id") or "") != user_id:
                continue
            report_count += 1
            report_id = report.get("report_id") or ""
            phase_stats = await self._collect_report_phase_stats(report_id)
            all_phase_stats.extend(phase_stats)

        aggregated = _aggregate_phase_stats(all_phase_stats)
        aggregated["per_phase"] = all_phase_stats
        aggregated["report_count"] = report_count
        aggregated["reminder_text"] = _build_reminder_text(
            aggregated["total_turns"],
            aggregated["avg_minutes"],
            aggregated["total_minutes"],
            user_id[:8] if len(user_id) > 8 else user_id,
        )
        return aggregated

    # ── 在线：按 report_id 聚合 ────────────────────────────────

    async def compute_by_report(self, report_id: str) -> Dict[str, Any]:
        """
        遍历该 report 的 5 个 selected_session，聚合统计。

        Args:
            report_id: 报告 ID

        Returns:
            统计结果字典
        """
        record = self.registry.get_report_by_id(report_id)
        if not record:
            logger.warning("统计：report 不存在: %s", report_id)
            return {
                "total_turns": 0,
                "total_seconds": 0.0,
                "avg_seconds": 0.0,
                "total_minutes": 0.0,
                "avg_minutes": 0.0,
                "skipped_no_ts": 0,
                "skipped_long_turns": 0,
                "per_phase": [],
                "report_count": 0,
                "reminder_text": f"报告 {report_id} 不存在或无数据。",
            }

        user_id = record.get("user_id") or ""
        phase_stats = await self._collect_report_phase_stats(report_id)
        aggregated = _aggregate_phase_stats(phase_stats)
        aggregated["per_phase"] = phase_stats
        aggregated["report_count"] = 1
        label = user_id[:8] if user_id and len(user_id) > 8 else (user_id or report_id[:8])
        aggregated["reminder_text"] = _build_reminder_text(
            aggregated["total_turns"],
            aggregated["avg_minutes"],
            aggregated["total_minutes"],
            label,
        )
        return aggregated

    # ── 内部：收集单个 report 的 5 phase 统计 ──────────────────

    async def _collect_report_phase_stats(
        self,
        report_id: str,
    ) -> List[Dict[str, Any]]:
        """
        收集单个 report 的 5 phase 对话统计。

        Args:
            report_id: 报告 ID

        Returns:
            per_phase 统计列表，每项含 phase_id / phase_name / turns / avg_minutes 等
        """
        result: List[Dict[str, Any]] = []
        for step_id in STEP_IDS:
            session_id = self.registry.get_selected_session(report_id, step_id)
            if not session_id:
                # 未完成 phase，跳过
                continue
            phase_stat = await self._compute_single_phase(
                report_id=report_id,
                step_id=step_id,
                session_id=session_id,
            )
            result.append(phase_stat)
        return result

    async def _compute_single_phase(
        self,
        report_id: str,
        step_id: str,
        session_id: str,
    ) -> Dict[str, Any]:
        """
        计算单个 phase（单个 session）的对话统计。

        复用 ExportService.collect_export_data 加载对话历史，
        再调 compute_turn_stats_from_messages 计算统计。

        Args:
            report_id: 报告 ID（用于查 user_id）
            step_id: 阶段 ID
            session_id: 会话 ID

        Returns:
            单 phase 统计字典
        """
        phase_name = PHASE_LABEL_CN.get(step_id, step_id)
        # 取 user_id（record 中）
        record = self.registry.get_report_by_id(report_id)
        user_id = (record or {}).get("user_id") or ""

        messages: List[Dict[str, Any]] = []
        try:
            data = await self.export_service.collect_export_data(
                user_id=user_id,
                session_id=session_id,
            )
            conv_history = data.get("conversation_history")
            if not isinstance(conv_history, dict):
                conv_history = {}
            # 合并所有 category 的消息并按时间戳排序
            all_msgs: List[Dict[str, Any]] = []
            for _cat, msgs in conv_history.items():
                if isinstance(msgs, list):
                    all_msgs.extend(msgs)
            # 按时间戳排序（尽力而为，无时间戳的排最后）
            def _sort_key(m: Dict[str, Any]) -> str:
                return m.get("created_at") or m.get("timestamp") or ""
            all_msgs.sort(key=_sort_key)
            messages = all_msgs
        except Exception as e:
            logger.exception(
                "统计：收集 phase 会话数据失败: report=%s step=%s err=%s",
                report_id,
                step_id,
                e,
            )

        stats = compute_turn_stats_from_messages(messages)
        avg_minutes = stats["avg_seconds"] / 60.0
        total_minutes = stats["total_seconds"] / 60.0
        return {
            "phase_id": step_id,
            "phase_name": phase_name,
            "session_id": session_id,
            "turns": stats["turns"],
            "avg_seconds": stats["avg_seconds"],
            "total_seconds": stats["total_seconds"],
            "avg_minutes": round(avg_minutes, 1),
            "total_minutes": round(total_minutes, 1),
            "skipped_no_ts": stats["skipped_no_ts"],
            "skipped_long_turns": stats["skipped_long_turns"],
            "total_turns_seen": stats["total_turns_seen"],
            "message_count": len(messages),
        }
