"""
LLM 费率表与成本计算（人民币元 / 百万 tokens）

- 内置 DeepSeek 官方费率（含 2026-08-17 起的峰谷定价），可按模型 + 生效时间段版本化
- 高峰时段默认北京时间 9:00-12:00、14:00-18:00（settings.LLM_PEAK_HOURS 可改）
- 整表可用 settings.LLM_PRICING_JSON 覆盖/增补（JSON 结构同 DEFAULT_PRICING），
  改价改 .env 重启即可，无需改代码
- 费率表未覆盖的模型返回 cost=None（落库为 NULL，admin 页面显示「—」）

费率结构：
{
  "<model>": [
    {  # 时间段规则，按 from/until 界定（Asia/Shanghai ISO 时间，可省略表示不限）
      "from": "2026-08-17T00:00:00+08:00",
      "until": null,
      "peak":     {"hit": 0.30, "miss": 9.0, "out": 27.0},   # 高峰价；省略则与 off_peak 同价
      "off_peak": {"hit": 0.15, "miss": 4.5, "out": 13.5}
    },
    ...
  ]
}
hit = 百万缓存命中输入价，miss = 百万缓存未命中输入价，out = 百万输出价（元）
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from app.config.settings import settings

logger = logging.getLogger(__name__)

# Asia/Shanghai 固定 UTC+8（无夏令时），与 analytics_funnel_service.SH_TZ 同口径
SH_TZ = timezone(timedelta(hours=8))

# 2026-08-17 00:00（北京时间）DeepSeek 新价生效点
_V4_PRICE_SWITCH = "2026-08-17T00:00:00+08:00"

# 内置费率表（元 / 百万 tokens）
DEFAULT_PRICING: Dict[str, List[dict]] = {
    # 官方定价页（api-docs.deepseek.com）：
    # 8-17 前：pro 命中 0.025 / 未命中 3 / 输出 6（无峰谷）
    # 8-17 起峰谷：pro 峰 0.30/9.0/27.0，谷 0.15/4.5/13.5
    "deepseek-v4-pro": [
        {
            "until": _V4_PRICE_SWITCH,
            "off_peak": {"hit": 0.025, "miss": 3.0, "out": 6.0},
        },
        {
            "from": _V4_PRICE_SWITCH,
            "peak": {"hit": 0.30, "miss": 9.0, "out": 27.0},
            "off_peak": {"hit": 0.15, "miss": 4.5, "out": 13.5},
        },
    ],
    # 8-17 前：flash 命中 0.02 / 未命中 1 / 输出 2
    # 8-17 起峰谷：flash 峰 0.10/3.0/9.0，谷 0.05/1.5/4.5
    "deepseek-v4-flash": [
        {
            "until": _V4_PRICE_SWITCH,
            "off_peak": {"hit": 0.02, "miss": 1.0, "out": 2.0},
        },
        {
            "from": _V4_PRICE_SWITCH,
            "peak": {"hit": 0.10, "miss": 3.0, "out": 9.0},
            "off_peak": {"hit": 0.05, "miss": 1.5, "out": 4.5},
        },
    ],
}

# 旧模型别名 → 费率表键（deepseek-chat/reasoner 已停服，仅兜底历史调用按 flash 价估）
MODEL_ALIASES = {
    "deepseek-chat": "deepseek-v4-flash",
    "deepseek-reasoner": "deepseek-v4-flash",
}

_cached_windows: Optional[List[Tuple[int, int]]] = None


def parse_peak_windows(spec: Optional[str] = None) -> List[Tuple[int, int]]:
    """解析峰时配置 "09:00-12:00,14:00-18:00" → [(540,720),(840,1080)]（分钟数，Asia/Shanghai）"""
    global _cached_windows
    use_cache = spec is None
    if use_cache and _cached_windows is not None:
        return _cached_windows
    if spec is None:
        spec = getattr(settings, "LLM_PEAK_HOURS", None) or "09:00-12:00,14:00-18:00"
    windows: List[Tuple[int, int]] = []
    for part in str(spec).split(","):
        part = part.strip()
        if not part or "-" not in part:
            continue
        try:
            start_s, end_s = part.split("-", 1)
            sh, sm = start_s.strip().split(":")
            eh, em = end_s.strip().split(":")
            windows.append((int(sh) * 60 + int(sm), int(eh) * 60 + int(em)))
        except (ValueError, AttributeError):
            logger.warning("LLM_PEAK_HOURS 片段无法解析，已忽略: %s", part)
    if use_cache:
        _cached_windows = windows
    return windows


def is_peak_time(dt: Optional[datetime] = None) -> bool:
    """判断时刻（默认现在）是否处于高峰时段（按 Asia/Shanghai 墙钟）"""
    dt = dt or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    sh = dt.astimezone(SH_TZ)
    minutes = sh.hour * 60 + sh.minute
    return any(start <= minutes < end for start, end in parse_peak_windows())


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s))
        return dt if dt.tzinfo else dt.replace(tzinfo=SH_TZ)
    except ValueError:
        logger.warning("费率表时间无法解析，已忽略: %s", s)
        return None


def load_pricing_table() -> Dict[str, List[dict]]:
    """加载费率表：内置默认 + LLM_PRICING_JSON 覆盖/增补（按 model 键整体替换）"""
    table: Dict[str, List[dict]] = {k: list(v) for k, v in DEFAULT_PRICING.items()}
    raw = getattr(settings, "LLM_PRICING_JSON", None)
    if raw:
        try:
            override = json.loads(raw)
            if isinstance(override, dict):
                for model, rules in override.items():
                    if isinstance(rules, list):
                        table[str(model)] = rules
        except (json.JSONDecodeError, TypeError):
            logger.warning("LLM_PRICING_JSON 解析失败，使用内置费率表")
    return table


def _match_rule(rules: List[dict], dt: datetime) -> Optional[dict]:
    """按调用时刻匹配时间段规则（Asia/Shanghai 口径比较）"""
    sh = dt.astimezone(SH_TZ) if dt.tzinfo else dt.replace(tzinfo=timezone.utc).astimezone(SH_TZ)
    for rule in rules:
        start = _parse_iso(rule.get("from"))
        end = _parse_iso(rule.get("until"))
        if start and sh < start:
            continue
        if end and sh >= end:
            continue
        return rule
    return None


def resolve_pricing_key(model: Optional[str]) -> Optional[str]:
    """模型名 → 费率表键（精确 → 别名 → None）"""
    if not model:
        return None
    table = load_pricing_table()
    if model in table:
        return model
    alias = MODEL_ALIASES.get(model)
    if alias and alias in table:
        return alias
    # 大小写不敏感兜底
    low = model.lower()
    for key in table:
        if key.lower() == low:
            return key
    return None


def compute_cost(
    model: Optional[str],
    cache_hit_tokens: int,
    cache_miss_tokens: int,
    completion_tokens: int,
    dt: Optional[datetime] = None,
) -> Tuple[Optional[float], bool]:
    """
    计算单次调用预估成本（元）。

    Returns:
        (cost_yuan, is_peak)：费率表未覆盖该模型时 cost_yuan=None
    """
    dt = dt or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    peak = is_peak_time(dt)

    key = resolve_pricing_key(model)
    if not key:
        return None, peak
    rule = _match_rule(load_pricing_table()[key], dt)
    if not rule:
        return None, peak
    rates = rule.get("peak") if peak else None
    rates = rates or rule.get("off_peak")
    if not rates:
        return None, peak

    cost = (
        (cache_hit_tokens or 0) * float(rates.get("hit", 0))
        + (cache_miss_tokens or 0) * float(rates.get("miss", 0))
        + (completion_tokens or 0) * float(rates.get("out", 0))
    ) / 1_000_000
    return round(cost, 6), peak
