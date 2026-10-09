"""用户过滤器注册表（ADR-0023）。

每个过滤器声明：key / label / 类型 / 选项 / 执行层（sql | memory）/ apply 函数。

- ``apply_sql(stmt, value) -> stmt``：SQL 下推过滤器，作用于 ``select(User)``
  或 ``select(func.count()).select_from(User)`` 两种语句（只可追加 where/join）。
- ``build_predicate(value, ctx) -> Callable[[str], bool]``：内存过滤器，
  谓词入参为 user_id，数据来自 ``FilterContext``（激活码 JSON / report record.json）。

新增筛选维度 = 在此注册一项 + 写好 apply 函数，前端经 schema 下发零改动。
"""

from dataclasses import dataclass
from datetime import datetime as dt
from typing import Any, Callable, Dict, List, Literal, Optional

from sqlalchemy import and_, exists, or_

from app.models.payment import PaymentOrder
from app.models.user import USER_TYPES, User, UserProfile

FilterType = Literal["multi_enum", "enum", "date_range", "text"]
Layer = Literal["sql", "memory"]

# 已付费口径（ADR-0023）：存在 status ∈ {paid, granted} 订单。
# partially_refunded / refunded 不计入（有意口径：退款单视为未留存付费）。
PAID_ORDER_STATUSES = ("paid", "granted")


@dataclass(frozen=True)
class FilterOption:
    value: str
    label: str


@dataclass(frozen=True)
class FilterSpec:
    """单个用户过滤器的声明式定义"""

    key: str
    label: str
    type: FilterType
    layer: Layer
    options: Optional[tuple] = None  # tuple[FilterOption, ...]，enum 类必填
    apply_sql: Optional[Callable[[Any, Any], Any]] = None
    build_predicate: Optional[Callable[[Any, Any], Callable[[str], bool]]] = None


# ─── SQL 下推过滤器 ────────────────────────────────────────────


def _apply_q(stmt, value: str):
    pattern = f"%{value.strip()}%"
    return stmt.where(or_(User.email.ilike(pattern), User.username.ilike(pattern)))


def _apply_user_type(stmt, value: List[str]):
    return stmt.where(User.user_type.in_(value))


def _apply_account_status(stmt, value: str):
    if value == "active":
        return stmt.where(and_(User.is_active.is_(True), User.deleted_at.is_(None)))
    if value == "inactive":
        return stmt.where(and_(User.is_active.is_(False), User.deleted_at.is_(None)))
    # deleted
    return stmt.where(User.deleted_at.isnot(None))


def _apply_profile_completed(stmt, value: str):
    return stmt.join(UserProfile, UserProfile.user_id == User.id).where(
        UserProfile.profile_completed.is_(value == "completed")
    )


def _apply_paid_status(stmt, value: List[str]):
    paid_cond = exists().where(
        and_(
            PaymentOrder.user_id == User.id,
            PaymentOrder.status.in_(PAID_ORDER_STATUSES),
        )
    )
    wants = set(value)
    if wants == {"paid"}:
        return stmt.where(paid_cond)
    if wants == {"unpaid"}:
        return stmt.where(~paid_cond)
    return stmt  # 两档全选 = 不限


def _apply_created_range(stmt, value: Dict[str, str]):
    # 非法日期静默忽略（沿用 UserDB.list_users 既有口径）
    after = (value.get("after") or "").strip()
    before = (value.get("before") or "").strip()
    if after:
        try:
            stmt = stmt.where(User.created_at >= dt.fromisoformat(after))
        except ValueError:
            pass
    if before:
        try:
            stmt = stmt.where(User.created_at <= dt.fromisoformat(before))
        except ValueError:
            pass
    return stmt


# ─── 内存过滤器（谓词入参为 user_id，数据来自 FilterContext） ────


def _build_code_kind_predicate(value: List[str], ctx):
    wanted = set(value)

    def pred(user_id: str) -> bool:
        return ctx.code_kind_of(user_id) in wanted

    return pred


def _build_stage_predicate(value: List[str], ctx):
    wanted = set(value)

    def pred(user_id: str) -> bool:
        return ctx.stage_of(user_id) in wanted

    return pred


# ─── 注册表（dict 插入序 = schema 下发/前端展示顺序） ─────────────

FILTER_REGISTRY: Dict[str, FilterSpec] = {
    spec.key: spec
    for spec in [
        FilterSpec(
            key="q",
            label="关键词",
            type="text",
            layer="sql",
            apply_sql=_apply_q,
        ),
        FilterSpec(
            key="user_type",
            label="用户类型",
            type="multi_enum",
            layer="sql",
            options=(
                FilterOption("real", "真实用户"),
                FilterOption("beta", "内测用户"),
                FilterOption("test", "测试账号"),
                FilterOption("admin", "管理员"),
            ),
            apply_sql=_apply_user_type,
        ),
        FilterSpec(
            key="account_status",
            label="账号状态",
            type="enum",
            layer="sql",
            options=(
                FilterOption("active", "活跃"),
                FilterOption("inactive", "已禁用"),
                FilterOption("deleted", "已注销"),
            ),
            apply_sql=_apply_account_status,
        ),
        FilterSpec(
            key="profile_completed",
            label="资料完成度",
            type="enum",
            layer="sql",
            options=(
                FilterOption("completed", "已填写"),
                FilterOption("incomplete", "未填写"),
            ),
            apply_sql=_apply_profile_completed,
        ),
        FilterSpec(
            key="paid_status",
            label="付费状态",
            type="multi_enum",
            layer="sql",
            options=(
                FilterOption("unpaid", "未付费"),
                FilterOption("paid", "已付费"),
            ),
            apply_sql=_apply_paid_status,
        ),
        FilterSpec(
            key="code_kind",
            label="激活码类型",
            type="multi_enum",
            layer="memory",
            options=(
                FilterOption("none", "无码"),
                FilterOption("trial", "试用码"),
                FilterOption("full", "完整码"),
            ),
            build_predicate=_build_code_kind_predicate,
        ),
        FilterSpec(
            key="stage",
            label="探索阶段",
            type="multi_enum",
            layer="memory",
            options=(
                FilterOption("not_started", "未开始"),
                FilterOption("exploring", "探索中"),
                FilterOption("report_unlocked", "已出报告"),
            ),
            build_predicate=_build_stage_predicate,
        ),
        FilterSpec(
            key="created_range",
            label="注册时间",
            type="date_range",
            layer="sql",
            apply_sql=_apply_created_range,
        ),
    ]
}


def get_filter_schema() -> List[Dict[str, Any]]:
    """注册表的序列化视图（GET /admin/filters/schema 下发，不含函数）"""
    return [
        {
            "key": spec.key,
            "label": spec.label,
            "type": spec.type,
            "options": (
                [{"value": o.value, "label": o.label} for o in spec.options]
                if spec.options
                else None
            ),
        }
        for spec in FILTER_REGISTRY.values()
    ]


def validate_filters(filters: Dict[str, Any]) -> None:
    """校验 filters 结构（未知 key / 类型不符 / 非法枚举值 → ValueError，端点转 400）"""
    for key, value in filters.items():
        spec = FILTER_REGISTRY.get(key)
        if spec is None:
            raise ValueError(f"未知筛选字段: {key}")
        if spec.type == "multi_enum":
            if not isinstance(value, list) or not value:
                raise ValueError(f"{key} 需为非空数组")
            allowed = {o.value for o in spec.options}
            bad = [v for v in value if not isinstance(v, str) or v not in allowed]
            if bad:
                raise ValueError(f"{key} 含非法值: {bad}")
        elif spec.type == "enum":
            allowed = {o.value for o in spec.options}
            if not isinstance(value, str) or value not in allowed:
                raise ValueError(f"{key} 仅支持 {'/'.join(sorted(allowed))}")
        elif spec.type == "text":
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{key} 需为非空字符串")
        elif spec.type == "date_range":
            if not isinstance(value, dict) or not (
                (value.get("after") or "").strip() or (value.get("before") or "").strip()
            ):
                raise ValueError(f"{key} 需含 after/before 至少其一")


# user_type 合法值兼容导出（admin 端点旧校验沿用）
__all__ = [
    "FILTER_REGISTRY",
    "FilterOption",
    "FilterSpec",
    "PAID_ORDER_STATUSES",
    "USER_TYPES",
    "get_filter_schema",
    "validate_filters",
]
