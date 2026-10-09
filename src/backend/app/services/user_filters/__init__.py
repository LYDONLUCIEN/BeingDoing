"""用户筛选系统（ADR-0023）：过滤器注册表 + schema 下发 + 两层执行器。

- 注册表（registry）：声明式定义全部用户过滤器（key/label/类型/选项/执行层/apply）。
- 执行器（service）：SQL 下推条件先收窄 → 内存过滤器精筛 → 分页切片。

筛选语义（系统级，所有消费方一致）：
- 过滤器内部多值 = OR；过滤器之间 = AND；空选/未传 = 不限。

消费方：admin 用户管理页（GET /admin/users）、数据导出（POST /admin/users/export），
schema 经 GET /admin/filters/schema 下发，前端 FilterBar 组件按 schema 渲染。
"""

from app.services.user_filters.registry import (
    FILTER_REGISTRY,
    FilterSpec,
    get_filter_schema,
    validate_filters,
)
from app.services.user_filters.service import filter_users, strip_empty_filters

__all__ = [
    "FILTER_REGISTRY",
    "FilterSpec",
    "filter_users",
    "get_filter_schema",
    "strip_empty_filters",
    "validate_filters",
]
