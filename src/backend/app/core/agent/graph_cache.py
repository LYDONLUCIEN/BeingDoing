"""
Graph 缓存池 - 带过期机制的内存管理

特性：
- 按 session_id 缓存 Graph 实例
- 自动过期（TTL，可配置）
- LRU 淘汰策略（当达到最大缓存数量时）
- 线程安全（使用 asyncio.Lock）
- 统计监控（命中率、淘汰数等）
"""
import asyncio
import json
import threading
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
from pathlib import Path

from app.config.settings import settings
from app.core.agent.graph import create_agent_graph
from app.core.agent.config import AgentRunConfig


class CachedGraph:
    """缓存的 Graph 实例"""

    def __init__(self, graph, config: AgentRunConfig):
        self.graph = graph
        self.config = config
        self.created_at = datetime.utcnow()
        self.last_used = datetime.utcnow()

    def mark_used(self):
        """标记为已使用（更新 last_used 时间）"""
        self.last_used = datetime.utcnow()

    def to_dict(self):
        """序列化为字典（用于调试）"""
        return {
            "created_at": self.created_at.isoformat(),
            "last_used": self.last_used.isoformat(),
            "config": self.config,
        }

    def is_expired(self, ttl_minutes: int) -> bool:
        """检查是否过期"""
        expiry = self.last_used + timedelta(minutes=ttl_minutes)
        return datetime.utcnow() > expiry


class GraphCache:
    """
    Graph 缓存池

    使用示例：
        cache = GraphCache()
        graph = cache.get(session_id, config)
        if graph is None:
            graph = create_agent_graph(config)
            cache.set(session_id, graph, config)
    """

    def __init__(
        self,
        ttl_minutes: Optional[int] = None,
        max_size: Optional[int] = None,
    ):
        """
        初始化 Graph 缓存

        Args:
            ttl_minutes: 过期时间（分钟），None 则从配置读取
            max_size: 最大缓存数量，None 则从配置读取
        """
        self.ttl_minutes = ttl_minutes or settings.GRAPH_CACHE_TTL_MINUTES
        self.max_size = max_size or settings.GRAPH_CACHE_MAX_SIZE

        # {session_id: CachedGraph}
        self._cache: Dict[str, CachedGraph] = {}

        # threading.Lock 用于线程安全
        self._lock = threading.Lock()

        # 统计信息
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "expirations": 0,
        }

    def get(self, session_id: str, config: Optional[AgentRunConfig] = None):
        """
        获取缓存的 Graph

        Args:
            session_id: 会话 ID
            config: AgentRunConfig（用于创建新 Graph）

        Returns:
            Graph 实例，如果不存在或过期则返回 None
        """
        if not settings.GRAPH_CACHE_ENABLED:
            self._stats["misses"] += 1
            return None

        with self._lock:  # 确保线程安全
            now = datetime.utcnow()

            # 检查缓存是否存在
            if session_id not in self._cache:
                self._stats["misses"] += 1
                return None

            cached = self._cache[session_id]

            # 检查是否过期
            if cached.is_expired(self.ttl_minutes):
                del self._cache[session_id]
                self._stats["expirations"] += 1
                self._stats["misses"] += 1
                return None

            # 更新最后使用时间（滑动过期）
            cached.mark_used()
            self._stats["hits"] += 1

            return cached.graph

    def set(self, session_id: str, graph, config: AgentRunConfig):
        """
        缓存 Graph 实例

        Args:
            session_id: 会话 ID
            graph: Graph 实例
            config: AgentRunConfig
        """
        if not settings.GRAPH_CACHE_ENABLED:
            return

        with self._lock:
            # LRU 淘汰：如果超过最大大小，删除最旧的
            if len(self._cache) >= self.max_size:
                # 找出最久未使用的 session
                oldest_session = min(
                    self._cache.items(),
                    key=lambda x: x[1].last_used
                )[0]
                del self._cache[oldest_session]
                self._stats["evictions"] += 1

            self._cache[session_id] = CachedGraph(graph, config)

    def remove(self, session_id: str):
        """手动移除缓存"""
        with self._lock:
            self._cache.pop(session_id, None)

    def cleanup_expired(self):
        """
        清理所有过期的缓存

        Returns:
            清理的缓存数量
        """
        with self._lock:
            now = datetime.utcnow()
            expired_sessions = [
                sid for sid, cached in self._cache.items()
                if cached.is_expired(self.ttl_minutes)
            ]

            for sid in expired_sessions:
                del self._cache[sid]
                self._stats["expirations"] += 1

            return len(expired_sessions)

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self._lock:
            total_requests = self._stats["hits"] + self._stats["misses"]
            hit_rate = self._stats["hits"] / total_requests if total_requests > 0 else 0

            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "ttl_minutes": self.ttl_minutes,
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "evictions": self._stats["evictions"],
                "expirations": self._stats["expirations"],
                "hit_rate": f"{hit_rate:.1%}",
            }

    async def start_cleanup_task(self, interval_minutes: Optional[int] = None):
        """
        启动后台清理任务

        Args:
            interval_minutes: 清理间隔（分钟），None 则从配置读取
        """
        interval = interval_minutes or settings.GRAPH_CACHE_CLEANUP_INTERVAL_MINUTES

        async def cleanup_loop():
            while True:
                try:
                    await asyncio.sleep(interval * 60)
                    cleaned = self.cleanup_expired()
                    if cleaned > 0:
                        print(f"[GraphCache] 清理了 {cleaned} 个过期缓存")
                        # 同时打印统计信息
                        stats = self.get_stats()
                        print(f"[GraphCache] 统计: {stats}")
                except asyncio.CancelledError:
                    print("[GraphCache] 清理任务已取消")
                    break
                except Exception as e:
                    print(f"[GraphCache] 清理任务异常: {e}")

        # 创建后台任务
        task = asyncio.create_task(cleanup_loop())
        return task


# 全局 Graph 缓存实例
_graph_cache: Optional[GraphCache] = None


def get_graph_cache() -> GraphCache:
    """获取全局 Graph 缓存实例（单例模式）"""
    global _graph_cache
    if _graph_cache is None:
        _graph_cache = GraphCache()
    return _graph_cache


def get_or_create_graph(session_id: str, graph_factory, config: AgentRunConfig):
    """
    获取或创建 Graph（缓存优先）

    Args:
        session_id: 会话 ID
        graph_factory: Graph 创建函数 (create_agent_graph)
        config: AgentRunConfig

    Returns:
        Graph 实例
    """
    cache = get_graph_cache()
    graph = cache.get(session_id, config)

    if graph is None:
        graph = graph_factory(config)
        cache.set(session_id, graph, config)

    return graph
