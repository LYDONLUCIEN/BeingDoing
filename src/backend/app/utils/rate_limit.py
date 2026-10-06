"""
轻量内存滑动窗口限流（2026-10-06）

用途：validate/activate 等输码端点防暴力猜码（新券码 Q-8 位变短后降低试探成本）。

实现要点：
- 每个key（建议 "bucket:ip"）维护时间戳 deque，滑出窗口外的丢弃
- 命中即记账（允许时也记录），超出窗口限额返回 False
- 单进程内存实现：多 worker / 多实例部署不共享计数，届时需换 Redis；
  当前 start.sh 单 uvicorn 进程，够用
- 同步方法无 await：asyncio 单事件循环内原子，无需加锁
"""

from __future__ import annotations

import time
from collections import deque
from typing import Dict

# 全局限流器注册表（bucket → key → 时间戳队列）
_buckets: Dict[str, Dict[str, deque]] = {}
# 空队列兜底清理：每 N 次调用清扫一次已空 key，防内存无界增长
_GC_INTERVAL = 1024
_gc_counter = 0


def hit(key: str, bucket: str, limit: int, window_seconds: float) -> bool:
    """记一次命中并判断是否放行

    Args:
        key: 限流主体（如客户端 IP）
        bucket: 端点桶名（如 "coupon_validate"，不同端点互不影响）
        limit: 窗口内允许次数
        window_seconds: 窗口秒数

    Returns:
        True=放行（已记账）；False=超限（本次不计，避免污染窗口）
    """
    global _gc_counter
    now = time.monotonic()
    slot = _buckets.setdefault(bucket, {})
    q = slot.get(key)
    if q is None:
        q = deque()
        slot[key] = q

    # 丢弃滑出窗口的旧命中
    while q and now - q[0] > window_seconds:
        q.popleft()

    if len(q) >= limit:
        return False
    q.append(now)

    _gc_counter += 1
    if _gc_counter >= _GC_INTERVAL:
        _gc_counter = 0
        for b in _buckets.values():
            for k in [k for k, v in b.items() if not v]:
                del b[k]
    return True


def reset() -> None:
    """清空全部计数（测试用）"""
    global _gc_counter
    _buckets.clear()
    _gc_counter = 0


def client_ip(headers, client) -> str:
    """从 FastAPI Request 提取客户端 IP（x-forwarded-for 优先，兼容网关代理）

    Args:
        headers: request.headers（需支持 .get）
        client: request.client（需支持 .host）

    Returns:
        客户端 IP（取不到返回 ""，由调用方决定兜底键）
    """
    forwarded = (headers.get("x-forwarded-for") or "").split(",")
    if forwarded and forwarded[0].strip():
        return forwarded[0].strip()
    if client and getattr(client, "host", None):
        return client.host
    return ""
