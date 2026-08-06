"""
漏斗统计服务（ADR-0013，事件时间口径）

口径定义见 CONTEXT.md「统计看板」节：
- 各环节独立计数「该环节事件发生在选定时段内的人/次数」，不做 Cohort
- 试用开聊 = 用户首个 values 轮次（不按当前 code_type，试用码升级后会变 full）
- 完成10轮 = 每用户第 10 条 values 轮次的时间
- 付费 = paid/granted 且未退款订单（refunding/refunded 天然排除），按 paid_at
- 得到报告 = 审核通过（含自动批复；祖父豁免回退报告创建时间）
- 实收（纯利润）= Σ amount_paid；理论收益 = Σ amount_original
- 时区：入参为 Asia/Shanghai 日历日，DB 时间为 UTC，统一换算

PV / 日活无历史数据，自 017_analytics_events 上线起统计。
"""

import json
import logging
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import select

from app.models.analytics import AnalyticsChatTurn, AnalyticsEvent
from app.models.database import AsyncSessionLocal
from app.models.payment import PaymentOrder
from app.models.user import User
from app.utils.helpers import parse_iso_to_utc
from app.utils.report_registry import ReportRegistry
from app.utils.report_review import REVIEW_STATUS_APPROVED, get_review_status
from app.utils.simple_activation_manager import get_simple_base_dir

logger = logging.getLogger(__name__)

# Asia/Shanghai 固定 UTC+8（无夏令时）
SH_TZ = timezone(timedelta(hours=8))

# 退款单从收益与付费人数中剔除：仅计 paid/granted（refunding/refunded 排除）
PAID_STATUSES = ("paid", "granted")

# 单次查询最大跨度（防滥用）
MAX_RANGE_DAYS = 732


def _as_utc(dt: datetime) -> datetime:
    """DB 读出的 naive datetime 一律视为 UTC。"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _sh_range_to_utc(start: date, end: date) -> Tuple[datetime, datetime]:
    """Shanghai 日历日闭区间 → UTC naive 半开区间 [start_utc, end_utc)（供 SQL 比较）。"""
    start_utc = (
        datetime.combine(start, time.min, tzinfo=SH_TZ)
        .astimezone(timezone.utc)
        .replace(tzinfo=None)
    )
    end_utc = (
        datetime.combine(end + timedelta(days=1), time.min, tzinfo=SH_TZ)
        .astimezone(timezone.utc)
        .replace(tzinfo=None)
    )
    return start_utc, end_utc


def _bucket_label(dt: datetime, granularity: str) -> str:
    sh = _as_utc(dt).astimezone(SH_TZ)
    return sh.strftime("%Y-%m") if granularity == "month" else sh.strftime("%Y-%m-%d")


def _make_bucket_labels(start: date, end: date, granularity: str) -> List[str]:
    labels: List[str] = []
    if granularity == "month":
        cur = date(start.year, start.month, 1)
        last = date(end.year, end.month, 1)
        while cur <= last:
            labels.append(cur.strftime("%Y-%m"))
            cur = date(cur.year + 1, 1, 1) if cur.month == 12 else date(cur.year, cur.month + 1, 1)
    else:
        cur = start
        while cur <= end:
            labels.append(cur.isoformat())
            cur += timedelta(days=1)
    return labels


class _EventBuckets:
    """按 bucket 聚合：计数型事件流 + 去重型事件流。"""

    def __init__(self, labels: List[str]):
        self.labels = labels
        self._count: Dict[str, Dict[str, int]] = {label: defaultdict(int) for label in labels}
        self._dedup: Dict[str, Dict[str, Set[str]]] = {label: defaultdict(set) for label in labels}

    def add(self, metric: str, dt: datetime, granularity: str) -> None:
        label = _bucket_label(dt, granularity)
        if label in self._count:
            self._count[label][metric] += 1

    def add_dedup(self, metric: str, key: str, dt: datetime, granularity: str) -> None:
        label = _bucket_label(dt, granularity)
        if label in self._dedup:
            self._dedup[label][metric].add(key)

    def total(self, metric: str) -> int:
        return sum(bucket.get(metric, 0) for bucket in self._count.values())

    def total_dedup(self, metric: str) -> int:
        merged: Set[str] = set()
        for bucket in self._dedup.values():
            merged |= bucket.get(metric, set())
        return len(merged)

    def series_row(self, label: str, metrics: List[str], dedup_metrics: List[str]) -> Dict[str, int]:
        row: Dict[str, int] = {}
        for m in metrics:
            row[m] = self._count[label].get(m, 0)
        for m in dedup_metrics:
            row[m] = len(self._dedup[label].get(m, set()))
        return row


class AnalyticsFunnelService:
    """漏斗级统计（admin 看板）"""

    @staticmethod
    async def get_funnel_stats(
        start: date,
        end: date,
        granularity: str = "day",
    ) -> Dict[str, Any]:
        if granularity not in ("day", "month"):
            raise ValueError("granularity 仅支持 day / month")
        if end < start:
            raise ValueError("end 不能早于 start")
        if (end - start).days > MAX_RANGE_DAYS:
            raise ValueError(f"查询跨度不能超过 {MAX_RANGE_DAYS} 天")

        start_utc, end_utc = _sh_range_to_utc(start, end)
        labels = _make_bucket_labels(start, end, granularity)
        buckets = _EventBuckets(labels)

        # ── 1. DB 侧事件：PV/UV、注册、日活 ──
        async with AsyncSessionLocal() as db:
            ev_result = await db.execute(
                select(AnalyticsEvent).where(
                    AnalyticsEvent.created_at >= start_utc,
                    AnalyticsEvent.created_at < end_utc,
                )
            )
            for ev in ev_result.scalars().all():
                dt = ev.created_at
                if not dt:
                    continue
                if ev.event_type == "page_view":
                    buckets.add("pv", dt, granularity)
                    uv_key = ev.visitor_id or ev.user_id or f"event:{ev.id}"
                    buckets.add_dedup("uv", uv_key, dt, granularity)
                elif ev.event_type == "auth_active":
                    buckets.add("active_events", dt, granularity)
                    if ev.user_id:
                        buckets.add_dedup("active_users", ev.user_id, dt, granularity)

            user_result = await db.execute(
                select(User.id, User.created_at).where(
                    User.created_at >= start_utc,
                    User.created_at < end_utc,
                )
            )
            for uid, created in user_result.all():
                if created:
                    buckets.add("registrations", created, granularity)

            # 付费订单（paid/granted，剔除退款）
            order_result = await db.execute(
                select(PaymentOrder).where(
                    PaymentOrder.status.in_(PAID_STATUSES),
                    PaymentOrder.paid_at.isnot(None),
                    PaymentOrder.paid_at >= start_utc,
                    PaymentOrder.paid_at < end_utc,
                )
            )
            orders = order_result.scalars().all()

        # ── 2. 付费人数 / 咨询人数 / 实收 / 理论收益 ──
        by_product: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"orders": 0, "actual_cents": 0, "theoretical_cents": 0}
        )
        for order in orders:
            dt = order.paid_at
            if not dt:
                continue
            buckets.add_dedup("paid_users", order.user_id, dt, granularity)
            if order.product_type == "consultation":
                buckets.add_dedup("consultation_users", order.user_id, dt, granularity)
            p = by_product[order.product_type]
            p["orders"] += 1
            p["actual_cents"] += int(order.amount_paid or 0)
            p["theoretical_cents"] += int(order.amount_original or 0)

        # 金额按 bucket 累计（单独通道，非事件计数）
        revenue_by_bucket: Dict[str, Dict[str, int]] = {
            label: {"actual_cents": 0, "theoretical_cents": 0} for label in labels
        }
        for order in orders:
            if not order.paid_at:
                continue
            label = _bucket_label(order.paid_at, granularity)
            if label in revenue_by_bucket:
                revenue_by_bucket[label]["actual_cents"] += int(order.amount_paid or 0)
                revenue_by_bucket[label]["theoretical_cents"] += int(order.amount_original or 0)

        # ── 3. values 轮次：试用开聊 / 完成10轮（需全量历史定首个/第10个，再看落点） ──
        await AnalyticsFunnelService._collect_values_milestones(buckets, granularity)

        # ── 4. 报告：审核通过人数（JSON registry） ──
        AnalyticsFunnelService._collect_report_approved(buckets, start_utc, end_utc, granularity)

        # ── 5. 激活码：累计 + 分型 + 时段内新增（JSON） ──
        activation_codes = AnalyticsFunnelService._collect_activation_codes(start_utc, end_utc)

        # ── 汇总输出 ──
        trends = []
        for label in labels:
            row = buckets.series_row(
                label,
                metrics=["pv", "registrations", "active_events"],
                dedup_metrics=[
                    "uv",
                    "active_users",
                    "trial_started",
                    "values_10_completed",
                    "paid_users",
                    "consultation_users",
                    "report_approved_users",
                ],
            )
            row["actual_cents"] = revenue_by_bucket[label]["actual_cents"]
            row["theoretical_cents"] = revenue_by_bucket[label]["theoretical_cents"]
            trends.append({"date": label, **row})

        return {
            "range": {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "granularity": granularity,
            },
            "funnel": {
                "pv": buckets.total("pv"),
                "uv": buckets.total_dedup("uv"),
                "registrations": buckets.total("registrations"),
                "trial_started": buckets.total_dedup("trial_started"),
                "values_10_completed": buckets.total_dedup("values_10_completed"),
                "paid_users": buckets.total_dedup("paid_users"),
                "report_approved_users": buckets.total_dedup("report_approved_users"),
            },
            "daily_active": {
                "total_events": buckets.total("active_events"),
                "unique_users": buckets.total_dedup("active_users"),
            },
            "activation_codes": activation_codes,
            "consultation_users": buckets.total_dedup("consultation_users"),
            "revenue": {
                "actual_cents": sum(b["actual_cents"] for b in revenue_by_bucket.values()),
                "theoretical_cents": sum(b["theoretical_cents"] for b in revenue_by_bucket.values()),
                "by_product": dict(by_product),
            },
            "trends": trends,
        }

    # ──────────────── values 里程碑 ────────────────

    @staticmethod
    async def _collect_values_milestones(buckets: _EventBuckets, granularity: str) -> None:
        """每用户 values 轮次排序：首条→试用开聊；第 10 条→完成10轮。

        轮次权威源 = analytics_chat_turns（record_chat_turn 每轮必落）。
        session→user 映射：ReportRegistry steps.values.session_ids 优先，
        其次 Session 表/activations.json/logs 目录（_get_session_metadata_map）。
        """
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(
                    AnalyticsChatTurn.session_id,
                    AnalyticsChatTurn.created_at,
                )
                .where(AnalyticsChatTurn.dimension.like("values%"))
                .order_by(AnalyticsChatTurn.created_at.asc())
            )
            turns = [(sid, dt) for sid, dt in result.all() if sid and dt]
        if not turns:
            return

        session_ids = list({sid for sid, _ in turns})
        session_user = await AnalyticsFunnelService._resolve_session_users(session_ids)

        per_user: Dict[str, List[datetime]] = defaultdict(list)
        for sid, dt in turns:
            uid = session_user.get(sid) or f"session:{sid}"
            # 历史数据存在 naive/aware 混存，统一归一到 aware UTC 再排序
            per_user[uid].append(_as_utc(dt))

        for uid, times in per_user.items():
            times.sort()
            if times:
                buckets.add_dedup("trial_started", uid, times[0], granularity)
            if len(times) >= 10:
                buckets.add_dedup("values_10_completed", uid, times[9], granularity)

    @staticmethod
    async def _resolve_session_users(session_ids: List[str]) -> Dict[str, Optional[str]]:
        """session_id → user_id。registry 优先，其次 _get_session_metadata_map。"""
        mapping: Dict[str, Optional[str]] = {}
        try:
            registry = ReportRegistry()
            for report in registry.list_reports():
                uid = (report.get("user_id") or "").strip()
                if not uid:
                    continue
                steps = report.get("steps") or {}
                for step in steps.values():
                    for sid in (step or {}).get("session_ids") or []:
                        if sid in session_ids:
                            mapping.setdefault(sid, uid)
        except Exception:
            logger.exception("funnel: registry session→user 解析失败")

        missing = [sid for sid in session_ids if sid not in mapping]
        if missing:
            try:
                from app.services.analytics_service import AnalyticsService

                meta_map = await AnalyticsService._get_session_metadata_map(missing)
                for sid, meta in meta_map.items():
                    if meta.get("user_id"):
                        mapping[sid] = meta["user_id"]
            except Exception:
                logger.exception("funnel: metadata session→user 解析失败")
        return mapping

    # ──────────────── 报告审核通过 ────────────────

    @staticmethod
    def _collect_report_approved(
        buckets: _EventBuckets,
        start_utc: datetime,
        end_utc: datetime,
        granularity: str,
    ) -> None:
        """得到报告 = 审核通过（含自动批复；祖父豁免回退报告创建时间），按用户去重。"""
        try:
            registry = ReportRegistry()
            for record in registry.list_reports():
                if get_review_status(record) != REVIEW_STATUS_APPROVED:
                    continue
                uid = (record.get("user_id") or "").strip()
                if not uid:
                    continue
                ts_raw = (record.get("reviewed_at") or "").strip() or (
                    record.get("created_at") or ""
                ).strip()
                if not ts_raw:
                    continue
                try:
                    ts = parse_iso_to_utc(ts_raw)
                except ValueError:
                    continue
                ts_naive = ts.replace(tzinfo=None)
                if start_utc <= ts_naive < end_utc:
                    buckets.add_dedup("report_approved_users", uid, ts, granularity)
        except Exception:
            logger.exception("funnel: 报告审核通过统计失败")

    # ──────────────── 激活码 ────────────────

    @staticmethod
    def _collect_activation_codes(start_utc: datetime, end_utc: datetime) -> Dict[str, int]:
        """累计总数（trial/full 分型）+ 时段内新增（按 created_at）。"""
        total = trial = full = new_in_range = 0
        try:
            act_file = get_simple_base_dir() / "activations.json"
            if act_file.is_file():
                raw = json.loads(act_file.read_text(encoding="utf-8") or "{}")
                for rec in (raw or {}).values():
                    if not isinstance(rec, dict):
                        continue
                    total += 1
                    if (rec.get("code_type") or "full") == "trial":
                        trial += 1
                    else:
                        full += 1
                    created = (rec.get("created_at") or "").strip()
                    if not created:
                        continue
                    try:
                        dt = parse_iso_to_utc(created).replace(tzinfo=None)
                    except ValueError:
                        continue
                    if start_utc <= dt < end_utc:
                        new_in_range += 1
        except Exception:
            logger.exception("funnel: 激活码统计失败")
        return {"total": total, "trial": trial, "full": full, "new_in_range": new_in_range}
