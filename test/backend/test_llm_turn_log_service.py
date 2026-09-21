"""LLM per-turn 诊断日志服务测试（llm_turn_log_service）。

覆盖：append / 查询筛选 / 分页 / 详情全文 / 保留期清理。
存储目录通过 monkeypatch 隔离到 tmp_path，不污染真实 data/。
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

import app.services.llm_turn_log_service as svc


@pytest.fixture()
def log_dir(tmp_path, monkeypatch):
    d = tmp_path / "llm_turns"
    monkeypatch.setattr(svc, "get_llm_turn_logs_dir", lambda: d)
    return d


def _entry(**kw) -> dict:
    base = {
        "user_id": "u1",
        "activation_code": "CODE123456",
        "session_id": "sess-1",
        "thread_id": "thread-1",
        "phase": "values",
        "scene": "chat",
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "outcome": svc.OUTCOME_OK,
        "finish_reason": "stop",
        "retry_count": 0,
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        "reasoning_content": "思维链全文",
        "content": "正文全文",
    }
    base.update(kw)
    return base


def test_append_and_query_roundtrip(log_dir: Path):
    svc.append_turn_log(_entry())
    svc.append_turn_log(_entry(outcome=svc.OUTCOME_EMPTY_FAILED, retry_count=1))

    files = list(log_dir.glob("llm_turns-*.jsonl"))
    assert len(files) == 1
    lines = files[0].read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    rec = json.loads(lines[0])
    assert rec["id"] and rec["ts"]

    res = svc.query_turn_logs()
    assert res["total"] == 2
    # 倒序：最新（empty_failed）在前
    assert res["items"][0]["outcome"] == svc.OUTCOME_EMPTY_FAILED
    # 列表为摘要视图：不带全文字段，带字符数与预览
    assert "reasoning_content" not in res["items"][0]
    assert "content" not in res["items"][0]
    assert res["items"][0]["reasoning_chars"] == len("思维链全文")
    assert res["items"][0]["content_preview"]


def test_query_filters(log_dir: Path):
    svc.append_turn_log(_entry(activation_code="AAAAAAAAAA"))
    svc.append_turn_log(_entry(activation_code="BBBBBBBBBB", outcome=svc.OUTCOME_PARTIAL))

    assert svc.query_turn_logs(activation_code="aaaaaaaaaa")["total"] == 1  # 大小写不敏感
    assert svc.query_turn_logs(outcome=svc.OUTCOME_PARTIAL)["total"] == 1
    assert svc.query_turn_logs(session_id="thread-1")["total"] == 2  # thread_id 也匹配
    assert svc.query_turn_logs(session_id="nope")["total"] == 0
    assert svc.query_turn_logs(user_id="u1")["total"] == 2
    assert svc.query_turn_logs(user_id="u2")["total"] == 0


def test_query_pagination(log_dir: Path):
    for i in range(5):
        svc.append_turn_log(_entry(content=f"正文{i}"))
    page1 = svc.query_turn_logs(page=1, page_size=2)
    page3 = svc.query_turn_logs(page=3, page_size=2)
    assert page1["total"] == 5
    assert len(page1["items"]) == 2
    assert len(page3["items"]) == 1


def test_get_turn_detail_full_text(log_dir: Path):
    svc.append_turn_log(_entry())
    item = svc.query_turn_logs()["items"][0]
    detail = svc.get_turn_detail(item["id"])
    assert detail is not None
    assert detail["reasoning_content"] == "思维链全文"
    assert detail["content"] == "正文全文"
    assert svc.get_turn_detail("not-exist") is None
    assert svc.get_turn_detail("") is None


def test_cleanup_expired_logs(log_dir: Path):
    log_dir.mkdir(parents=True, exist_ok=True)
    today = date.today()
    old = today - timedelta(days=40)
    recent = today - timedelta(days=5)
    (log_dir / f"llm_turns-{old.isoformat()}.jsonl").write_text('{"id":"old"}\n', encoding="utf-8")
    (log_dir / f"llm_turns-{recent.isoformat()}.jsonl").write_text(
        '{"id":"new"}\n', encoding="utf-8"
    )
    (log_dir / "other-file.txt").write_text("keep", encoding="utf-8")

    removed = svc.cleanup_expired_logs(retention_days=30)
    assert removed == 1
    assert not (log_dir / f"llm_turns-{old.isoformat()}.jsonl").exists()
    assert (log_dir / f"llm_turns-{recent.isoformat()}.jsonl").exists()
    assert (log_dir / "other-file.txt").exists()
    # retention<=0 不删
    assert svc.cleanup_expired_logs(retention_days=0) == 0


def test_append_never_raises(log_dir: Path):
    # 不可序列化对象也不允许抛异常阻断主流程
    svc.append_turn_log(_entry(content=object()))
    # 目录不可写（文件占位的同名路径）也不抛
    blocker = log_dir.parent / "llm_turns_block"
    import app.services.llm_turn_log_service as svc2

    blocker.write_text("x", encoding="utf-8")
    orig = svc2.get_llm_turn_logs_dir
    svc2.get_llm_turn_logs_dir = lambda: blocker / "sub"
    try:
        svc.append_turn_log(_entry())
    finally:
        svc2.get_llm_turn_logs_dir = orig
