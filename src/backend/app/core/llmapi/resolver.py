"""
LLM 配置解析器（DB-first + .env 兜底 + TTL 缓存）。

被 factory 透明调用。核心约束：factory 是同步函数，被 8+ 处同步调用，
所以本模块必须提供同步读路径，不能依赖 asyncio。

策略：
- 同步读：用独立 sync engine 周期性 SELECT，结果存内存快照。
- 缓存 TTL=30s；admin 写操作后主动 invalidate，确保配置变更即时生效。
- 失败兜底：DB 出错时保留上次快照；快照空则用 .env 派生（与原 factory._get_vip_provider_config 一致）。
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import create_engine, select as sa_select
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.models.database import get_database_url
from app.models.llm_model_config import LlmModelConfig, UserLlmModelConfig
from app.utils import llm_config_crypto

logger = logging.getLogger(__name__)

_CACHE_TTL_SEC = 30.0


@dataclass
class ResolvedConfig:
    provider: str
    model: str
    base_url: Optional[str]
    api_key: Optional[str]
    config_id: Optional[str]  # DB 命中时有值；env 兜底时为 None
    source: str  # "db" | "env" | "env_vip1" | "env_vip2"


class _Snapshot:
    """内存快照。immutable-after-build。"""

    def __init__(self) -> None:
        self.default: Optional[ResolvedConfig] = None
        self.by_user: dict[str, ResolvedConfig] = {}
        # 命中的 DB 配置（用于 vip 桥接判断）
        self.has_db_default: bool = False


# module-level state
_snapshot_lock = threading.Lock()
_snapshot: Optional[_Snapshot] = None
_snapshot_ts: float = 0.0
_sync_engine = None
_sync_engine_lock = threading.Lock()


def _get_sync_engine():
    """惰性创建同步 engine。把异步 driver 换成同步 driver。"""
    global _sync_engine
    if _sync_engine is not None:
        return _sync_engine
    with _sync_engine_lock:
        if _sync_engine is None:
            url = get_database_url()
            if url.startswith("sqlite+aiosqlite"):
                url = url.replace("sqlite+aiosqlite", "sqlite", 1)
            elif url.startswith("postgresql+asyncpg"):
                url = url.replace("postgresql+asyncpg", "postgresql+psycopg2", 1)
            _sync_engine = create_engine(url, future=True)
        return _sync_engine


def _from_env_default() -> ResolvedConfig:
    """从 .env 生成默认 ResolvedConfig（与原 factory 行为一致）。"""
    provider = (settings.LLM_PROVIDER or "openai").lower()
    model = settings.LLM_MODEL or "gpt-4"
    if provider == "deepseek":
        api_key = settings.DEEPSEEK_API_KEY
        base_url = settings.LLM_BASE_URL or "https://api.deepseek.com"
    elif provider == "kimi":
        api_key = getattr(settings, "KIMI_API_KEY", None)
        base_url = getattr(settings, "KIMI_BASE_URL", None)
    elif provider == "qwen":
        api_key = getattr(settings, "QWEN_API_KEY", None)
        base_url = getattr(settings, "QWEN_BASE_URL", None)
    else:  # openai 或未知
        api_key = settings.OPENAI_API_KEY
        base_url = settings.LLM_BASE_URL
    return ResolvedConfig(
        provider=provider,
        model=model,
        base_url=base_url,
        api_key=api_key,
        config_id=None,
        source="env",
    )


def _from_env_vip(vip_level: int) -> ResolvedConfig:
    """VIP 分流（保留原 .env 行为）。"""
    from app.core.llmapi.factory import _get_vip_provider_config

    provider, model, api_key, base_url = _get_vip_provider_config(vip_level)
    return ResolvedConfig(
        provider=provider or "openai",
        model=model or settings.LLM_MODEL or "gpt-4",
        base_url=base_url,
        api_key=api_key,
        config_id=None,
        source="env_vip1" if vip_level == 1 else "env_vip2",
    )


def _row_to_resolved(row: LlmModelConfig) -> ResolvedConfig:
    return ResolvedConfig(
        provider=row.provider,
        model=row.model,
        base_url=row.base_url,
        api_key=llm_config_crypto.decrypt(row.api_key_enc),
        config_id=row.id,
        source="db",
    )


def _refresh_snapshot_blocking() -> None:
    """同步刷新快照。在 _snapshot_lock 内调用。任何异常吞掉，保留旧快照。"""
    global _snapshot, _snapshot_ts
    try:
        eng = _get_sync_engine()
        new_snap = _Snapshot()
        with Session(eng) as session:
            # 默认：is_default=True and enabled=True；否则任一 enabled=True
            stmt = sa_select(LlmModelConfig).where(LlmModelConfig.enabled.is_(True))
            rows = list(session.execute(stmt).scalars().all())
            configs: dict[str, ResolvedConfig] = {}
            default_row: Optional[LlmModelConfig] = None
            for row in rows:
                configs[row.id] = _row_to_resolved(row)
                if row.is_default:
                    default_row = row
            # 没有显式默认 → 取第一个 enabled
            if default_row is None and rows:
                default_row = rows[0]
            if default_row is not None:
                new_snap.default = configs[default_row.id]
                new_snap.has_db_default = True
            # 用户绑定
            bind_stmt = sa_select(UserLlmModelConfig)
            for bind in session.execute(bind_stmt).scalars().all():
                rc = configs.get(bind.config_id)
                if rc is not None:
                    new_snap.by_user[bind.user_id] = rc
        _snapshot = new_snap
        _snapshot_ts = time.monotonic()
    except Exception as e:
        logger.warning("LLM 配置 resolver DB 读取失败，保留旧快照: %s", e)


def _ensure_fresh() -> None:
    """过期则刷新。线程安全。"""
    global _snapshot_ts
    now = time.monotonic()
    if _snapshot is not None and (now - _snapshot_ts) <= _CACHE_TTL_SEC:
        return
    with _snapshot_lock:
        # double-check
        if _snapshot is not None and (time.monotonic() - _snapshot_ts) <= _CACHE_TTL_SEC:
            return
        _refresh_snapshot_blocking()


def invalidate_cache() -> None:
    """admin 写后调用，强制下次重新读 DB。"""
    global _snapshot, _snapshot_ts
    with _snapshot_lock:
        _snapshot = None
        _snapshot_ts = 0.0


def get_default_config() -> ResolvedConfig:
    """默认配置（DB 优先；空则 .env 兜底）。"""
    _ensure_fresh()
    snap = _snapshot
    if snap is not None and snap.default is not None:
        return snap.default
    return _from_env_default()


def get_config_for_user(user_id: Optional[str]) -> ResolvedConfig:
    """按用户取配置：有绑定走绑定，否则默认。user_id 为 None 直接返回默认。"""
    if not user_id:
        return get_default_config()
    _ensure_fresh()
    snap = _snapshot
    if snap is not None:
        rc = snap.by_user.get(user_id)
        if rc is not None:
            return rc
    return get_default_config()


def get_config_for_vip(vip_level: int) -> ResolvedConfig:
    """
    VIP 桥接：当前仍走 .env（保留 VIP1/VIP2 原行为）。
    将来若 admin 要按 VIP 分流，可在此查 DB。
    """
    return _from_env_vip(vip_level)
