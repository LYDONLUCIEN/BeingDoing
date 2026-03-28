"""
管理员调试策略开关。

目标：
- 将“管理员调试特权”集中到统一策略层，避免散落判断
- 通过环境变量实现一键启停（生产环境默认关闭）
"""

from app.config.settings import settings


def is_admin_debug_policy_enabled() -> bool:
    """总开关：关闭后所有管理员调试特权不可用。"""
    return bool(getattr(settings, "ADMIN_DEBUG_POLICY_ENABLED", False))


def is_admin_debug_workspace_enabled() -> bool:
    """常驻工作区开关（受总开关约束）。"""
    return is_admin_debug_policy_enabled() and bool(
        getattr(settings, "ADMIN_DEBUG_WORKSPACE_ENABLED", True)
    )


def is_admin_sandbox_enabled() -> bool:
    """SBX 调试沙箱开关（受总开关约束）。"""
    return is_admin_debug_policy_enabled() and bool(
        getattr(settings, "ADMIN_SANDBOX_ENABLED", True)
    )
