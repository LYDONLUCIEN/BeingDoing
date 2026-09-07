"""
LLM 余额监控（当前仅支持 DeepSeek）

定时查询 DeepSeek 官方余额接口（GET {base_url}/user/balance），
余额低于告警阈值时给所有 super_admin 发站内信提醒充值（llm_balance_low）。

幂等：同一天（北京时间）只提醒一次——以当天是否已存在
llm_balance_low 通知为准，避免服务重启/补跑造成刷屏。

key/base_url 走 resolver.get_default_config()（DB 优先 + .env 兜底），
兼容 admin 后台「模型配置」页改 key 的场景。
"""
import logging
from datetime import datetime, time, timezone
from typing import Any, Dict, Optional

import httpx
from sqlalchemy import func, select

from app.config.settings import settings
from app.core.llmapi import resolver
from app.models.database import AsyncSessionLocal
from app.models.feedback import Notification
from app.services.feedback_service import SHANGHAI_TZ, _get_super_admin_ids

logger = logging.getLogger(__name__)

BALANCE_LOW_NOTIFICATION_TYPE = "llm_balance_low"
BALANCE_LOW_TITLE = "DeepSeek 余额不足提醒"

_REQUEST_TIMEOUT = 10.0


def _base_result() -> Dict[str, Any]:
    return {
        "available": False,
        "total_balance": None,
        "currency": None,
        "threshold": settings.LLM_BALANCE_ALERT_THRESHOLD,
        "is_low": False,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "error": None,
    }


async def query_llm_balance() -> Dict[str, Any]:
    """查询当前默认 LLM 提供商的账户余额（目前仅支持 DeepSeek）。

    Returns:
        {
            "available": bool,        # 是否成功取到余额
            "total_balance": float,   # 可用余额（元）
            "currency": str,          # 币种
            "threshold": float,       # 告警阈值（元）
            "is_low": bool,           # 是否低于阈值
            "checked_at": str,        # ISO 时间
            "error": Optional[str],   # 失败原因
        }
    """
    result = _base_result()
    try:
        cfg = resolver.get_default_config()
    except Exception as e:
        result["error"] = f"读取 LLM 配置失败: {e}"
        logger.warning("llm balance query: resolve config failed: %s", e)
        return result

    if (cfg.provider or "").lower() != "deepseek":
        result["error"] = f"当前提供商为 {cfg.provider}，余额查询仅支持 DeepSeek"
        return result
    if not cfg.api_key:
        result["error"] = "DeepSeek API key 未配置"
        return result

    base_url = (cfg.base_url or "https://api.deepseek.com").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            resp = await client.get(
                f"{base_url}/user/balance",
                headers={"Authorization": f"Bearer {cfg.api_key}"},
            )
        if resp.status_code != 200:
            result["error"] = f"DeepSeek 余额接口返回 HTTP {resp.status_code}"
            logger.warning("llm balance query: HTTP %s", resp.status_code)
            return result
        payload = resp.json()
    except Exception as e:
        result["error"] = f"DeepSeek 余额接口请求失败: {type(e).__name__}: {e}"
        logger.warning("llm balance query failed: %s", e)
        return result

    infos = payload.get("balance_infos") or []
    # 汇总 CNY 余额（grant + topped_up）
    total = 0.0
    currency: Optional[str] = None
    for info in infos:
        cur = info.get("currency")
        if cur and cur != "CNY":
            continue
        currency = cur or currency
        try:
            total += float(info.get("total_balance") or 0)
        except (TypeError, ValueError):
            continue

    result.update(
        available=True,
        total_balance=round(total, 2),
        currency=currency or "CNY",
        is_low=total < settings.LLM_BALANCE_ALERT_THRESHOLD,
    )
    return result


async def scan_llm_balance() -> Dict[str, Any]:
    """定时 job 入口：查余额，低于阈值时站内信提醒所有 super_admin（当天幂等）。

    Returns:
        {"available": bool, "is_low": bool, "notified": N, "skipped_already_notified": bool}
    """
    stats: Dict[str, Any] = {
        "available": False,
        "is_low": False,
        "notified": 0,
        "skipped_already_notified": False,
    }
    balance = await query_llm_balance()
    stats["available"] = balance["available"]
    stats["is_low"] = balance["is_low"]

    if not balance["available"]:
        # 查询失败（网络/401 等）只记日志，不发通知
        logger.warning("llm balance scan: query failed: %s", balance.get("error"))
        return stats
    if not balance["is_low"]:
        logger.info(
            "llm balance scan: balance %.2f >= threshold %.2f, ok",
            balance["total_balance"],
            balance["threshold"],
        )
        return stats

    now = datetime.now(timezone.utc)
    today_start = datetime.combine(
        now.astimezone(SHANGHAI_TZ).date(), time(0, 0, 0), tzinfo=SHANGHAI_TZ
    ).astimezone(timezone.utc)

    async with AsyncSessionLocal() as db:
        # 幂等：今天（北京时间）已提醒过则跳过
        exists_q = await db.execute(
            select(func.count(Notification.id)).where(
                Notification.type == BALANCE_LOW_NOTIFICATION_TYPE,
                Notification.created_at >= today_start,
            )
        )
        if int(exists_q.scalar_one()) > 0:
            stats["skipped_already_notified"] = True
            logger.info("llm balance scan: already notified today, skip")
            return stats

        admin_ids = await _get_super_admin_ids(db)
        if not admin_ids:
            logger.warning("llm balance scan: no super_admin found, skip notify")
            return stats

        content = (
            f"DeepSeek 账户当前可用余额 ¥{balance['total_balance']:.2f}，"
            f"已低于告警阈值 ¥{balance['threshold']:.2f}。\n\n"
            "欠费将导致所有 AI 对话、报告生成等服务中断，"
            "请尽快前往 DeepSeek 开放平台（platform.deepseek.com）充值。"
        )
        for admin_id in admin_ids:
            db.add(
                Notification(
                    user_id=admin_id,
                    type=BALANCE_LOW_NOTIFICATION_TYPE,
                    title=BALANCE_LOW_TITLE,
                    content=content,
                    read_at=None,
                )
            )
            stats["notified"] += 1
        await db.commit()

    logger.info(
        "llm balance scan done: balance=%.2f threshold=%.2f notified=%s",
        balance["total_balance"],
        balance["threshold"],
        stats["notified"],
    )
    return stats
