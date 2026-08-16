"""
LLM 用量记录与 Admin 统计查询

记录侧：record_llm_usage 由 provider 层在每次调用成功后触发（尽力而为，绝不抛出阻断主流程）
查询侧：summary / users / calls 三个 admin 看板查询，时间口径 Asia/Shanghai 日历日（同漏斗统计）
"""

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select

from app.core.llmapi.usage_context import get_llm_usage_context
from app.models.database import AsyncSessionLocal
from app.models.llm_usage import LlmUsageLog
from app.models.user import User
from app.utils.llm_pricing import SH_TZ, compute_cost

logger = logging.getLogger(__name__)


def _as_utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _sh_range_to_utc_naive(start: date, end: date) -> Tuple[datetime, datetime]:
    """Shanghai 日历日闭区间 → UTC naive 半开区间（供 SQL 比较）"""
    start_utc = _as_utc_naive(datetime.combine(start, time.min, tzinfo=SH_TZ))
    end_utc = _as_utc_naive(datetime.combine(end + timedelta(days=1), time.min, tzinfo=SH_TZ))
    return start_utc, end_utc


def extract_usage_numbers(usage: Optional[dict]) -> Dict[str, int]:
    """从 OpenAI 兼容 usage dict 提取规范化计数（cache 字段缺失时按 miss=prompt 兜底）"""
    usage = usage or {}

    def _i(v: Any) -> int:
        try:
            return int(v or 0)
        except (TypeError, ValueError):
            return 0

    prompt = _i(usage.get("prompt_tokens"))
    hit = _i(usage.get("prompt_cache_hit_tokens"))
    miss = _i(usage.get("prompt_cache_miss_tokens"))
    if prompt and not (hit or miss):
        miss = prompt  # 无缓存字段（如 Kimi/Qwen）→ 全部按未命中计
    completion = _i(usage.get("completion_tokens"))
    details = usage.get("completion_tokens_details") or {}
    reasoning = _i(details.get("reasoning_tokens") if isinstance(details, dict) else 0)
    return {
        "prompt_tokens": prompt,
        "cache_hit_tokens": hit,
        "cache_miss_tokens": miss,
        "completion_tokens": completion,
        "reasoning_tokens": reasoning,
    }


async def record_llm_usage(
    *,
    provider: Optional[str],
    model: Optional[str],
    usage: Optional[dict],
) -> None:
    """记录一次 LLM 调用用量（含落库时定价）。任何异常仅记日志，不影响主流程。"""
    try:
        nums = extract_usage_numbers(usage)
        if not (nums["prompt_tokens"] or nums["completion_tokens"]):
            return  # 无用量信息（如流式未拿到 usage chunk）不记录
        now = datetime.now(timezone.utc)
        cost, is_peak = compute_cost(
            model,
            nums["cache_hit_tokens"],
            nums["cache_miss_tokens"],
            nums["completion_tokens"],
            now,
        )
        ctx = get_llm_usage_context() or {}
        async with AsyncSessionLocal() as db:
            db.add(
                LlmUsageLog(
                    user_id=ctx.get("user_id"),
                    session_id=ctx.get("session_id"),
                    activation_code=ctx.get("activation_code"),
                    scene=(ctx.get("scene") or "unknown")[:50],
                    provider=(provider or None) and str(provider)[:32],
                    model=(model or None) and str(model)[:64],
                    prompt_tokens=nums["prompt_tokens"],
                    cache_hit_tokens=nums["cache_hit_tokens"],
                    cache_miss_tokens=nums["cache_miss_tokens"],
                    completion_tokens=nums["completion_tokens"],
                    reasoning_tokens=nums["reasoning_tokens"],
                    cost_yuan=cost,
                    is_peak=is_peak,
                    created_at=now.replace(tzinfo=None),
                )
            )
            await db.commit()
    except Exception:
        logger.exception("记录 LLM 用量失败（已忽略，不影响主流程）")


class LlmUsageStatsService:
    """Admin token 统计查询（仅 super_admin 入口调用）"""

    @staticmethod
    def _range_filter(
        start: Optional[date], end: Optional[date]
    ) -> Tuple[date, date, datetime, datetime]:
        today = datetime.now(SH_TZ).date()
        end = end or today
        start = start or today - timedelta(days=29)
        if end < start:
            raise ValueError("end 不能早于 start")
        if (end - start).days > 366:
            raise ValueError("查询跨度不能超过 366 天")
        start_utc, end_utc = _sh_range_to_utc_naive(start, end)
        return start, end, start_utc, end_utc

    @staticmethod
    async def get_summary(start: Optional[date], end: Optional[date]) -> Dict[str, Any]:
        """总览：总量 + 分场景 + 按天趋势 + 峰谷拆分"""
        start, end, start_utc, end_utc = LlmUsageStatsService._range_filter(start, end)
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(LlmUsageLog).where(
                    LlmUsageLog.created_at >= start_utc,
                    LlmUsageLog.created_at < end_utc,
                )
            )
            rows = result.scalars().all()

        def _empty_agg() -> Dict[str, Any]:
            return {
                "calls": 0,
                "prompt_tokens": 0,
                "cache_hit_tokens": 0,
                "cache_miss_tokens": 0,
                "completion_tokens": 0,
                "reasoning_tokens": 0,
                "cost_yuan": 0.0,
                "cost_known": False,  # 是否存在已计价记录
            }

        def _add(agg: Dict[str, Any], r: LlmUsageLog) -> None:
            agg["calls"] += 1
            agg["prompt_tokens"] += r.prompt_tokens or 0
            agg["cache_hit_tokens"] += r.cache_hit_tokens or 0
            agg["cache_miss_tokens"] += r.cache_miss_tokens or 0
            agg["completion_tokens"] += r.completion_tokens or 0
            agg["reasoning_tokens"] += r.reasoning_tokens or 0
            if r.cost_yuan is not None:
                agg["cost_yuan"] += r.cost_yuan
                agg["cost_known"] = True

        total = _empty_agg()
        by_scene: Dict[str, Dict[str, Any]] = {}
        by_day: Dict[str, Dict[str, Any]] = {}
        peak_agg = _empty_agg()
        off_peak_agg = _empty_agg()
        for r in rows:
            _add(total, r)
            _add(by_scene.setdefault(r.scene or "unknown", _empty_agg()), r)
            if r.created_at:
                sh = r.created_at.replace(tzinfo=timezone.utc).astimezone(SH_TZ)
                day_agg = by_day.setdefault(sh.strftime("%Y-%m-%d"), _empty_agg())
                _add(day_agg, r)
            _add(peak_agg if r.is_peak else off_peak_agg, r)

        def _round(agg: Dict[str, Any]) -> Dict[str, Any]:
            agg = dict(agg)
            agg["cost_yuan"] = round(agg["cost_yuan"], 4)
            p = agg["prompt_tokens"]
            agg["cache_hit_rate"] = (
                round(agg["cache_hit_tokens"] / p, 4) if p else None
            )
            return agg

        return {
            "range": {"start": start.isoformat(), "end": end.isoformat()},
            "total": _round(total),
            "by_scene": [
                {"scene": k, **_round(v)}
                for k, v in sorted(by_scene.items(), key=lambda kv: -kv[1]["cost_yuan"])
            ],
            "by_day": [
                {"date": k, **_round(v)} for k, v in sorted(by_day.items())
            ],
            "peak": _round(peak_agg),
            "off_peak": _round(off_peak_agg),
        }

    @staticmethod
    async def get_users(
        start: Optional[date],
        end: Optional[date],
        page: int = 1,
        page_size: int = 50,
        q: Optional[str] = None,
    ) -> Dict[str, Any]:
        """按用户聚合（user_id 缺失时按 activation_code 归属），按成本降序分页"""
        _, _, start_utc, end_utc = LlmUsageStatsService._range_filter(start, end)
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(LlmUsageLog).where(
                    LlmUsageLog.created_at >= start_utc,
                    LlmUsageLog.created_at < end_utc,
                )
            )
            rows = result.scalars().all()
            # 用户名/邮箱映射
            user_ids = {r.user_id for r in rows if r.user_id}
            user_map: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
            if user_ids:
                u_result = await db.execute(
                    select(User.id, User.username, User.email).where(User.id.in_(user_ids))
                )
                for uid, username, email in u_result.all():
                    user_map[uid] = (username, email)

        groups: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            key = f"u:{r.user_id}" if r.user_id else (
                f"c:{r.activation_code}" if r.activation_code else "unknown"
            )
            g = groups.setdefault(
                key,
                {
                    "user_id": r.user_id,
                    "activation_code": r.activation_code,
                    "calls": 0,
                    "prompt_tokens": 0,
                    "cache_hit_tokens": 0,
                    "completion_tokens": 0,
                    "cost_yuan": 0.0,
                    "cost_known": False,
                    "scenes": set(),
                    "last_active_at": None,
                },
            )
            g["calls"] += 1
            g["prompt_tokens"] += r.prompt_tokens or 0
            g["cache_hit_tokens"] += r.cache_hit_tokens or 0
            g["completion_tokens"] += r.completion_tokens or 0
            if r.cost_yuan is not None:
                g["cost_yuan"] += r.cost_yuan
                g["cost_known"] = True
            if r.scene:
                g["scenes"].add(r.scene)
            if not g["activation_code"] and r.activation_code:
                g["activation_code"] = r.activation_code
            if r.created_at and (g["last_active_at"] is None or r.created_at > g["last_active_at"]):
                g["last_active_at"] = r.created_at

        items: List[Dict[str, Any]] = []
        for g in groups.values():
            username = email = None
            if g["user_id"] and g["user_id"] in user_map:
                username, email = user_map[g["user_id"]]
            items.append(
                {
                    "user_id": g["user_id"],
                    "activation_code": g["activation_code"],
                    "username": username,
                    "email": email,
                    "calls": g["calls"],
                    "prompt_tokens": g["prompt_tokens"],
                    "cache_hit_tokens": g["cache_hit_tokens"],
                    "completion_tokens": g["completion_tokens"],
                    "total_tokens": g["prompt_tokens"] + g["completion_tokens"],
                    "cost_yuan": round(g["cost_yuan"], 4) if g["cost_known"] else None,
                    "scenes": sorted(g["scenes"]),
                    "last_active_at": g["last_active_at"].isoformat() if g["last_active_at"] else None,
                }
            )

        if q:
            ql = q.lower()
            items = [
                it
                for it in items
                if ql in str(it.get("username") or "").lower()
                or ql in str(it.get("email") or "").lower()
                or ql in str(it.get("user_id") or "").lower()
                or ql in str(it.get("activation_code") or "").lower()
            ]
        items.sort(key=lambda it: -(it["cost_yuan"] or 0))
        total = len(items)
        page = max(1, page)
        start_i = (page - 1) * page_size
        return {
            "records": items[start_i : start_i + page_size],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @staticmethod
    async def get_calls(
        start: Optional[date],
        end: Optional[date],
        page: int = 1,
        page_size: int = 50,
        user_id: Optional[str] = None,
        scene: Optional[str] = None,
    ) -> Dict[str, Any]:
        """单次调用明细（按时间倒序分页）"""
        _, _, start_utc, end_utc = LlmUsageStatsService._range_filter(start, end)
        conds = [
            LlmUsageLog.created_at >= start_utc,
            LlmUsageLog.created_at < end_utc,
        ]
        if user_id:
            conds.append(LlmUsageLog.user_id == user_id)
        if scene:
            conds.append(LlmUsageLog.scene == scene)
        async with AsyncSessionLocal() as db:
            total = (
                await db.execute(select(func.count(LlmUsageLog.id)).where(*conds))
            ).scalar() or 0
            page = max(1, page)
            result = await db.execute(
                select(LlmUsageLog)
                .where(*conds)
                .order_by(LlmUsageLog.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            rows = result.scalars().all()
        return {
            "records": [
                {
                    "id": r.id,
                    "user_id": r.user_id,
                    "session_id": r.session_id,
                    "activation_code": r.activation_code,
                    "scene": r.scene,
                    "provider": r.provider,
                    "model": r.model,
                    "prompt_tokens": r.prompt_tokens,
                    "cache_hit_tokens": r.cache_hit_tokens,
                    "cache_miss_tokens": r.cache_miss_tokens,
                    "completion_tokens": r.completion_tokens,
                    "reasoning_tokens": r.reasoning_tokens,
                    "cost_yuan": r.cost_yuan,
                    "is_peak": bool(r.is_peak),
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ],
            "total": int(total),
            "page": page,
            "page_size": page_size,
        }
