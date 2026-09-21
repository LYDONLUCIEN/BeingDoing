"""主聊天流「空 content 当失败」测试（2026-09-21 空回复事故修复）。

口径：
- 可见正文为空 → 后端推 retrying 告知事件并原样重试 1 次；
- 重试成功 → 正常 done + 落助手消息，turn 日志 outcome=empty_content_retried_ok；
- 重试仍空 → 推 error(type=empty_response)，不落助手消息、不推 done，
  turn 日志 outcome=empty_content_failed；
- 手动「重新尝试」重发同一用户消息 → 5 分钟内不重复落盘（重试去重）。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest
from fastapi.testclient import TestClient

from app.api.v1.auth import get_current_user
from app.main import app
import app.api.v1.simple_chat_routes as simple_chat_api
import app.services.llm_turn_log_service as turn_log_svc
import app.utils.simple_activation_manager as activation_manager_mod
from app.utils.simple_activation_manager import SimpleActivationManager

TEST_USER = {
    "user_id": "pytest-empty-reply-user",
    "email": "pytest-empty-reply@example.com",
}
REPORT_ID = "mock-report-empty-reply"
THREAD_ID = "t_empty_reply_001"


class FakeDialogueLLM:
    """按 attempts 序列依次模拟每次 chat_stream 调用。"""

    def __init__(self, attempts: List[List[Any]]):
        self._attempts = list(attempts)
        self.calls = 0
        self._last_stream_usage: Optional[dict] = None
        self._last_stream_finish_reason: Optional[str] = "stop"
        self.provider_name = "deepseek"
        self.model = "deepseek-v4-flash"

    async def chat(self, messages, temperature=0.7, response_format=None, max_tokens=None):
        return SimpleNamespace(content="非流式回复", usage={})

    async def chat_stream(self, messages, temperature=0.7, max_tokens=None):
        idx = min(self.calls, len(self._attempts) - 1)
        self.calls += 1
        self._last_stream_usage = {"prompt_tokens": 10, "completion_tokens": 5}
        for ev in self._attempts[idx]:
            yield ev


def _think_only_attempt() -> List[Any]:
    """模拟「只吐思维链、content 为空」的一次流。"""
    return [
        {"_t": "think_start"},
        {"_t": "think_chunk", "content": "模型在思考但没有写出正文"},
        {"_t": "think_end", "content": "模型在思考但没有写出正文"},
    ]


def _normal_attempt(reply: str = "这是可见的回复。") -> List[Any]:
    return [
        {"_t": "think_start"},
        {"_t": "think_chunk", "content": "先想一想"},
        {"_t": "think_end", "content": "先想一想"},
        reply,
    ]


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture()
def seeded_env(tmp_path, monkeypatch):
    simple_root = tmp_path / "simple"
    reports_root = simple_root / "reports"
    rdir = reports_root / REPORT_ID
    rdir.mkdir(parents=True, exist_ok=True)

    record = {
        "report_id": REPORT_ID,
        "activation_code": "MOCKPLACEHOLDER",
        "user_id": TEST_USER["user_id"],
        "created_at": "2026-09-21T00:00:00+00:00",
        "updated_at": "2026-09-21T00:00:00+00:00",
        "status": "in_progress",
        "final_conclusion": None,
        "steps": {
            step: {
                "step_id": step,
                "selected_session_id": THREAD_ID if step == "values" else None,
                "locked": False,
                "session_ids": [THREAD_ID] if step == "values" else [],
                "updated_at": "2026-09-21T00:00:00+00:00",
            }
            for step in ["values", "strengths", "interests", "purpose", "rumination"]
        },
    }
    (rdir / "record.json").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    thread_data = {
        "report_id": REPORT_ID,
        "session_id": THREAD_ID,
        "category": f"values__{THREAD_ID}",
        "messages": [
            {
                "id": "m0",
                "role": "assistant",
                "content": "开场：我们来聊聊你的价值观。",
                "thread_id": THREAD_ID,
                "step_id": "values",
                "agent_id": "coach",
                "event": "assistant_reply",
                "created_at": "2026-09-21T00:00:00+00:00",
            }
        ],
        "metadata": {
            "created_at": "2026-09-21T00:00:00+00:00",
            "updated_at": "2026-09-21T00:00:00+00:00",
            "conclusion_state": "none",
            "thread_completed": False,
        },
    }
    (rdir / f"values__{THREAD_ID}.json").write_text(
        json.dumps(thread_data, ensure_ascii=False), encoding="utf-8"
    )

    monkeypatch.setattr(activation_manager_mod, "get_simple_base_dir", lambda: simple_root)
    app.dependency_overrides[get_current_user] = lambda: TEST_USER

    manager = SimpleActivationManager(base_dir=str(simple_root))
    rec = manager.create_activation(mode="values", ttl_minutes=180, code_type="full")
    manager.claim_owner(rec.code, TEST_USER)
    record["activation_code"] = rec.code
    (rdir / "record.json").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(simple_chat_api, "_trigger_anchor_refiner", lambda *a, **k: None)
    monkeypatch.setattr(
        simple_chat_api, "_get_reasoning_llm_provider", lambda vip_level=1: object()
    )

    # turn 日志隔离到 tmp
    turn_dir = tmp_path / "llm_turns"
    monkeypatch.setattr(turn_log_svc, "get_llm_turn_logs_dir", lambda: turn_dir)

    yield {
        "client": TestClient(app),
        "headers": {"Authorization": "Bearer fake-token"},
        "activation_code": rec.code,
        "thread_file": rdir / f"values__{THREAD_ID}.json",
        "turn_dir": turn_dir,
    }
    app.dependency_overrides.clear()


def _stream_events(client: TestClient, headers, payload) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    with client.stream(
        "POST", "/api/v1/simple-chat/message/stream", json=payload, headers=headers
    ) as resp:
        assert resp.status_code == 200
        for line in resp.iter_lines():
            if not line:
                continue
            text = line.decode("utf-8") if isinstance(line, bytes) else line
            if not text.startswith("data: "):
                continue
            events.append(json.loads(text[6:]))
    return events


def _read_turn_logs(turn_dir: Path) -> List[Dict[str, Any]]:
    logs: List[Dict[str, Any]] = []
    for p in sorted(turn_dir.glob("llm_turns-*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                logs.append(json.loads(line))
    return logs


def test_empty_reply_retried_then_success(seeded_env, monkeypatch):
    """第一次空 content（只吐思维链）→ 推 retrying → 第二次成功 → 正常 done。"""
    llm = FakeDialogueLLM([_think_only_attempt(), _normal_attempt()])
    monkeypatch.setattr(simple_chat_api, "_get_dialogue_llm_provider", lambda vip_level=1: llm)

    events = _stream_events(
        seeded_env["client"],
        seeded_env["headers"],
        {
            "activation_code": seeded_env["activation_code"],
            "phase": "values",
            "thread_id": THREAD_ID,
            "message": "我在意成长和意义。",
        },
    )
    assert llm.calls == 2
    assert any(e.get("retrying") is True and e.get("reason") == "empty_content" for e in events)
    done = [e for e in events if e.get("done") is True]
    assert done and done[-1]["response"] == "这是可见的回复。"
    # 不重试就没有第二次 think_start 之后的 chunk——确认正文来自第二次调用
    assert any(e.get("chunk") == "这是可见的回复。" for e in events)

    # 助手消息落盘（可见正文）
    msgs = _read_json(seeded_env["thread_file"])["messages"]
    assistant = [m for m in msgs if m.get("role") == "assistant" and m.get("event") == "assistant_reply"]
    assert assistant[-1]["content"] == "这是可见的回复。"

    # turn 日志：重试成功分类 + 首次空轮全文保留
    logs = _read_turn_logs(seeded_env["turn_dir"])
    assert len(logs) == 1
    assert logs[0]["outcome"] == turn_log_svc.OUTCOME_EMPTY_RETRIED_OK
    assert logs[0]["retry_count"] == 1
    assert logs[0]["model"] == "deepseek-v4-flash"
    assert logs[0]["attempts"][0]["reasoning_content"] == "模型在思考但没有写出正文"
    assert logs[0]["attempts"][0]["content"] == ""


def test_empty_reply_still_empty_after_retry(seeded_env, monkeypatch):
    """两次皆空 → 推 error(type=empty_response)，不推 done、不落助手消息。"""
    llm = FakeDialogueLLM([_think_only_attempt(), _think_only_attempt()])
    monkeypatch.setattr(simple_chat_api, "_get_dialogue_llm_provider", lambda vip_level=1: llm)

    events = _stream_events(
        seeded_env["client"],
        seeded_env["headers"],
        {
            "activation_code": seeded_env["activation_code"],
            "phase": "values",
            "thread_id": THREAD_ID,
            "message": "随便说点什么。",
        },
    )
    assert llm.calls == 2
    assert any(e.get("retrying") is True for e in events)
    assert not any(e.get("done") is True for e in events)
    errs = [e for e in events if e.get("error")]
    assert errs, "应下发 error 事件"
    err_detail = json.loads(errs[-1]["error"])
    assert err_detail["type"] == "empty_response"

    # 不落新的助手消息（种子里只有开场那条 assistant）
    msgs = _read_json(seeded_env["thread_file"])["messages"]
    assert [m for m in msgs if m.get("role") == "assistant"][-1]["id"] == "m0"
    # 用户消息已落盘（先落用户消息再调模型，语义不变）
    assert any(m.get("role") == "user" and m.get("content") == "随便说点什么。" for m in msgs)

    logs = _read_turn_logs(seeded_env["turn_dir"])
    assert len(logs) == 1
    assert logs[0]["outcome"] == turn_log_svc.OUTCOME_EMPTY_FAILED
    assert logs[0]["retry_count"] == 1


def test_normal_reply_logged_ok(seeded_env, monkeypatch):
    """正常一轮：一次成功、无 retrying，turn 日志 outcome=ok。"""
    llm = FakeDialogueLLM([_normal_attempt()])
    monkeypatch.setattr(simple_chat_api, "_get_dialogue_llm_provider", lambda vip_level=1: llm)

    events = _stream_events(
        seeded_env["client"],
        seeded_env["headers"],
        {
            "activation_code": seeded_env["activation_code"],
            "phase": "values",
            "thread_id": THREAD_ID,
            "message": "正常问题。",
        },
    )
    assert llm.calls == 1
    assert not any(e.get("retrying") for e in events)
    assert any(e.get("done") is True for e in events)

    logs = _read_turn_logs(seeded_env["turn_dir"])
    assert len(logs) == 1
    assert logs[0]["outcome"] == turn_log_svc.OUTCOME_OK
    assert logs[0]["content"] == "这是可见的回复。"


def test_retry_resend_same_user_message_deduped(seeded_env, monkeypatch):
    """手动重试重发同一用户消息：5 分钟内最后一条相同 user 消息不重复落盘。"""
    llm = FakeDialogueLLM([_think_only_attempt(), _think_only_attempt()])
    monkeypatch.setattr(simple_chat_api, "_get_dialogue_llm_provider", lambda vip_level=1: llm)

    payload = {
        "activation_code": seeded_env["activation_code"],
        "phase": "values",
        "thread_id": THREAD_ID,
        "message": "同样的话",
    }
    _stream_events(seeded_env["client"], seeded_env["headers"], payload)  # 第一次（失败）
    _stream_events(seeded_env["client"], seeded_env["headers"], payload)  # 手动重试

    msgs = _read_json(seeded_env["thread_file"])["messages"]
    user_msgs = [m for m in msgs if m.get("role") == "user" and m.get("content") == "同样的话"]
    assert len(user_msgs) == 1, "重试去重：相同 user 消息不应重复落盘"


def test_different_message_not_deduped(seeded_env, monkeypatch):
    """不同内容正常落盘，不被去重误伤。"""
    llm = FakeDialogueLLM([_normal_attempt(), _normal_attempt()])
    monkeypatch.setattr(simple_chat_api, "_get_dialogue_llm_provider", lambda vip_level=1: llm)

    for text in ("第一句话", "第二句话"):
        _stream_events(
            seeded_env["client"],
            seeded_env["headers"],
            {
                "activation_code": seeded_env["activation_code"],
                "phase": "values",
                "thread_id": THREAD_ID,
                "message": text,
            },
        )
    msgs = _read_json(seeded_env["thread_file"])["messages"]
    user_contents = [m.get("content") for m in msgs if m.get("role") == "user"]
    assert user_contents == ["第一句话", "第二句话"]
