"""
Per-user async queue for combo guide generation.

In-memory, single-process. Enforces per-user concurrency limit
and deduplicates in-flight combo_ids.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, Optional, Set

logger = logging.getLogger(__name__)

_MAX_CONCURRENT_PER_USER = 3
_TASK_TIMEOUT = 60  # seconds


class ComboGuideQueue:
    """Per-user queue with semaphore-based concurrency + in-flight dedup."""

    def __init__(self) -> None:
        self._sems: Dict[str, asyncio.Semaphore] = {}
        self._in_flight: Dict[str, Set[str]] = {}
        self._lock = asyncio.Lock()

    def _get_sem(self, user_id: str) -> asyncio.Semaphore:
        if user_id not in self._sems:
            self._sems[user_id] = asyncio.Semaphore(_MAX_CONCURRENT_PER_USER)
        return self._sems[user_id]

    def _get_in_flight(self, user_id: str) -> Set[str]:
        if user_id not in self._in_flight:
            self._in_flight[user_id] = set()
        return self._in_flight[user_id]

    async def enqueue(
        self,
        user_id: str,
        combo_id: str,
        generate_fn,
    ) -> bool:
        """Enqueue a generation task. Returns True if actually executed, False if dedup'd."""
        async with self._lock:
            in_flight = self._get_in_flight(user_id)
            if combo_id in in_flight:
                return False
            in_flight.add(combo_id)

        sem = self._get_sem(user_id)
        await sem.acquire()
        try:
            await asyncio.wait_for(generate_fn(), timeout=_TASK_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning("combo guide timed out: user=%s combo=%s", user_id, combo_id)
        except Exception:
            logger.exception("combo guide failed: user=%s combo=%s", user_id, combo_id)
        finally:
            async with self._lock:
                self._get_in_flight(user_id).discard(combo_id)
            sem.release()
        return True

    async def is_in_flight(self, user_id: str, combo_id: str) -> bool:
        async with self._lock:
            return combo_id in self._get_in_flight(user_id)


_queue = ComboGuideQueue()


def get_combo_guide_queue() -> ComboGuideQueue:
    return _queue
