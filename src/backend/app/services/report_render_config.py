"""报告 PDF 渲染引擎运行时配置（ADR-0019）。

admin 在报告页可切换渲染引擎（简洁版 weasyprint / 设计版 xunlu），即时生效、
无需重启。配置持久化在 data/report_render_config.json；优先级：
运行时配置 > 环境变量 RENDER_ENGINE > 默认 weasyprint。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from app.config.settings import settings
from app.utils.data_paths import get_project_data_dir

logger = logging.getLogger(__name__)

VALID_ENGINES = ("weasyprint", "xunlu")
_CONFIG_FILENAME = "report_render_config.json"

# mtime 缓存：避免每次渲染都读盘；文件被 PUT 改写后 mtime 变化即失效
_cache_engine: Optional[str] = None
_cache_mtime: Optional[float] = None


def _config_path() -> Path:
    return get_project_data_dir() / _CONFIG_FILENAME


def get_render_engine() -> str:
    """当前生效的渲染引擎（运行时配置 > env > 默认）。异常时回退 env。"""
    global _cache_engine, _cache_mtime
    path = _config_path()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        _cache_engine, _cache_mtime = None, None
        return settings.RENDER_ENGINE
    if _cache_mtime == mtime and _cache_engine in VALID_ENGINES:
        return _cache_engine
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        engine = str((data or {}).get("engine") or "").strip()
        if engine in VALID_ENGINES:
            _cache_engine, _cache_mtime = engine, mtime
            return engine
        logger.warning("渲染引擎配置非法（%r），回退 RENDER_ENGINE", engine)
    except Exception:
        logger.exception("渲染引擎配置读取失败: %s", path)
    _cache_engine, _cache_mtime = None, None
    return settings.RENDER_ENGINE


def set_render_engine(engine: str) -> None:
    """写入运行时引擎配置（仅接受 VALID_ENGINES）。"""
    engine = (engine or "").strip()
    if engine not in VALID_ENGINES:
        raise ValueError(f"非法渲染引擎: {engine!r}（可选 {'/'.join(VALID_ENGINES)}）")
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"engine": engine}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    global _cache_engine, _cache_mtime
    _cache_engine, _cache_mtime = None, None
    logger.info("报告渲染引擎已切换: %s", engine)
