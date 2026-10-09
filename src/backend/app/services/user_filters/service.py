"""用户筛选执行器（ADR-0023）：两层执行。

SQL 下推条件先收窄 → 内存过滤器精筛 → （列表场景）分页切片。
存在内存过滤器时分页退化为「全量拉取 + 过滤后切片」，total 为精筛后总数；
当前用户量级（数百）无感，数万用户时再上预聚合（ADR-0023 非目标）。
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import User
from app.services.user_filters.registry import FILTER_REGISTRY, validate_filters

logger = logging.getLogger(__name__)

# code_kind 档位排序（ADR-0023）：名下非 consumed 码取最高档
_CODE_KIND_RANK = {"full": 2, "trial": 1}
_RANK_TO_KIND = {2: "full", 1: "trial"}


class FilterContext:
    """内存过滤器的数据上下文，惰性构建（仅在用到对应维度时才加载 JSON）"""

    def __init__(
        self,
        code_kind_map: Optional[Dict[str, str]] = None,
        stage_map: Optional[Dict[str, str]] = None,
    ) -> None:
        # 传入预置 map 可跳过 JSON 加载（测试注入用）
        self._code_kind_map = code_kind_map
        self._stage_map = stage_map

    def code_kind_of(self, user_id: str) -> str:
        """名下非 consumed 激活码的最高档：full > trial > none（过期计入）"""
        if self._code_kind_map is None:
            self._code_kind_map = self._build_code_kind_map()
        return self._code_kind_map.get(user_id, "none")

    def stage_of(self, user_id: str) -> str:
        """探索三态：not_started / exploring / report_unlocked（多 record 取最前进度）"""
        if self._stage_map is None:
            self._stage_map = self._build_stage_map()
        return self._stage_map.get(user_id, "not_started")

    @staticmethod
    def _build_code_kind_map() -> Dict[str, str]:
        from app.utils.simple_activation_manager import (
            ActivationStatus,
            SimpleActivationManager,
        )

        best: Dict[str, int] = {}
        for _code, rec in SimpleActivationManager().list_activations().items():
            uid = (rec.owner_user_id or "").strip()
            if not uid:
                continue
            if rec.status in (ActivationStatus.CONSUMED.value, ActivationStatus.DELETED.value):
                continue  # consumed 已消耗进他人升级、deleted 已回收，均不计入持有
            rank = _CODE_KIND_RANK.get(getattr(rec, "code_type", "full") or "full", 2)
            if rank > best.get(uid, 0):
                best[uid] = rank
        return {uid: _RANK_TO_KIND[r] for uid, r in best.items()}

    @staticmethod
    def _build_stage_map() -> Dict[str, str]:
        from app.utils.report_registry import ReportRegistry, compute_explore_resume

        best: Dict[str, str] = {}
        for record in ReportRegistry().list_reports():
            uid = (record.get("user_id") or "").strip()
            if not uid:
                continue
            stage = (
                "report_unlocked"
                if compute_explore_resume(record).get("report_unlocked")
                else "exploring"
            )
            if best.get(uid) != "report_unlocked":
                best[uid] = stage
        return best


def strip_empty_filters(filters: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """剔除空值（None/空串/空数组/空 dict），空选 = 不限"""
    if not filters:
        return {}
    cleaned = {}
    for key, value in filters.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        cleaned[key] = value
    return cleaned


async def filter_users(
    session: AsyncSession,
    filters: Optional[Dict[str, Any]],
    page: Optional[int] = None,
    page_size: Optional[int] = None,
    ctx: Optional[FilterContext] = None,
) -> Tuple[List[User], int]:
    """按 filters 筛选用户，返回 (users, total)。

    Args:
        session: 数据库会话
        filters: 筛选条件 {key: value}（空值已在外层剔除亦可，此处幂等再剔一次）
        page / page_size: 分页参数；均为 None 时不分页（导出场景全量取）
        ctx: 内存过滤器数据上下文（默认新建，惰性加载 JSON；测试可注入预置 map）

    Raises:
        ValueError: filters 校验失败（端点层转 400）
    """
    filters = strip_empty_filters(filters)
    validate_filters(filters)

    base = select(User).options(selectinload(User.profile))
    memory_preds: List[Callable[[str], bool]] = []
    ctx = ctx or FilterContext()

    for key, value in filters.items():
        spec = FILTER_REGISTRY[key]
        if spec.layer == "sql":
            base = spec.apply_sql(base, value)
        else:
            memory_preds.append(spec.build_predicate(value, ctx))

    base = base.order_by(User.created_at.desc())

    if not memory_preds:
        # 纯 SQL：数据库层 count + 分页（ctx 未使用，不会触发 JSON 加载）
        count_q = select(func.count()).select_from(User)
        for key, value in filters.items():
            count_q = FILTER_REGISTRY[key].apply_sql(count_q, value)
        total = (await session.execute(count_q)).scalar() or 0
        stmt = base
        if page is not None and page_size is not None:
            stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await session.execute(stmt)
        return list(result.scalars().all()), total

    # 含内存过滤器：全量取 SQL 候选 → 内存精筛 → 切片
    result = await session.execute(base)
    users = [u for u in result.scalars().all() if all(p(u.id) for p in memory_preds)]
    total = len(users)
    if page is not None and page_size is not None:
        users = users[(page - 1) * page_size : page * page_size]
    return users, total
