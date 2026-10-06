"""
轻量内存限流测试（rate_limit，2026-10-06）

覆盖：
1. 窗口内限额放行/超限拒绝
2. 不同 key（IP）/不同 bucket 互不影响
3. 窗口滑出后名额恢复（monkeypatch time.monotonic 推进时间）
4. 超限命中不记账（污染窗口防护）
5. client_ip 提取（x-forwarded-for 优先 / 直连 / 兜底空串）
"""

from app.utils import rate_limit
from app.utils.rate_limit import client_ip, hit, reset


class FakeClient:
    def __init__(self, host):
        self.host = host


class FakeHeaders:
    def __init__(self, data):
        self._data = data

    def get(self, key, default=None):
        return self._data.get(key, default)


def setup_method():
    reset()


def test_within_limit_then_exceed():
    """10 次/分钟：前 10 次放行，第 11 次拒绝"""
    for i in range(10):
        assert hit("1.2.3.4", "validate", limit=10, window_seconds=60) is True
    assert hit("1.2.3.4", "validate", limit=10, window_seconds=60) is False


def test_keys_isolated():
    """不同 IP 互不影响；同 IP 不同 bucket 互不影响"""
    assert hit("1.1.1.1", "validate", limit=1, window_seconds=60) is True
    assert hit("1.1.1.1", "validate", limit=1, window_seconds=60) is False
    assert hit("2.2.2.2", "validate", limit=1, window_seconds=60) is True
    assert hit("1.1.1.1", "activate", limit=1, window_seconds=60) is True


def test_window_slides(monkeypatch):
    """窗口滑出后名额恢复"""
    t = 100.0
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: t)
    assert hit("3.3.3.3", "validate", limit=2, window_seconds=60) is True
    assert hit("3.3.3.3", "validate", limit=2, window_seconds=60) is True
    assert hit("3.3.3.3", "validate", limit=2, window_seconds=60) is False
    # 推进 61 秒：最早一次命中滑出窗口，名额恢复 1 个
    t = 161.0
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: t)
    assert hit("3.3.3.3", "validate", limit=2, window_seconds=60) is True


def test_rejected_hit_not_recorded(monkeypatch):
    """超限的命中不记账：窗口滑出判定只看放行过的命中"""
    t = 0.0
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: t)
    assert hit("4.4.4.4", "v", limit=1, window_seconds=60) is True
    for _ in range(5):
        assert hit("4.4.4.4", "v", limit=1, window_seconds=60) is False
        t += 1  # 拒绝的 5 次都在窗口内，均不记账
        monkeypatch.setattr(rate_limit.time, "monotonic", lambda: t)
    t = 61.0  # 唯一一次放行滑出窗口 → 恢复
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: t)
    assert hit("4.4.4.4", "v", limit=1, window_seconds=60) is True


def test_client_ip_extraction():
    """x-forwarded-for 优先（取第一段），无代理头时取 client.host，均无返回空串"""
    assert (
        client_ip(FakeHeaders({"x-forwarded-for": "5.5.5.5, 6.6.6.6"}), FakeClient("7.7.7.7"))
        == "5.5.5.5"
    )
    assert client_ip(FakeHeaders({}), FakeClient("7.7.7.7")) == "7.7.7.7"
    assert client_ip(FakeHeaders({}), None) == ""
