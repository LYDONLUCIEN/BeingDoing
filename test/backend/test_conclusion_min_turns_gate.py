"""
结论卡最小出卡轮数门控 + 手动出卡端点测试（2026-08-25 口径）。

口径：
- 四阶段所有用户前 10 轮（用户消息条数，含当前条）不出卡：模型输出 pending_ready 也拦截；
- 第 11 轮起放开模型自觉出卡；
- 满 11 轮且 state=none 时可走 POST /simple-chat/conclusion/request 手动生成草案卡；
- admin 调试工作区（_can_bypass_flow_limits）不受限。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from app.api.v1.auth import get_current_user
from app.main import app
import app.api.v1.simple_chat_routes as simple_chat_api
import app.utils.simple_activation_manager as activation_manager_mod
from app.utils.simple_activation_manager import SimpleActivationManager


TEST_USER = {
    "user_id": "pytest-gate-user",
    "email": "pytest-gate@example.com",
}
REPORT_ID = "mock-report-gate-001"
THREAD_ID = "t_gate_test_001"

FAKE_CARD = {
    "summary": "你重视成长、创新、意义感、身心健康、心流。",
    "keywords": ["成长", "创新", "意义感", "身心健康", "心流"],
}


class FakeDialogueLLM:
    def __init__(self, stream_reply: str = "", chat_reply: str = "测试回复"):
        self.stream_reply = stream_reply
        self.chat_reply = chat_reply
        self._last_stream_usage = None

    async def chat(self, messages, temperature=0.7, response_format=None, max_tokens=None):
        return SimpleNamespace(content=self.chat_reply, usage={})

    async def chat_stream(self, messages, temperature=0.7, max_tokens=None):
        if self.stream_reply:
            yield self.stream_reply


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_thread_messages(user_turns: int) -> List[Dict[str, Any]]:
    """构造 user_turns 条用户消息的对话历史（assistant/user 交替，以 assistant 开场）。"""
    msgs: List[Dict[str, Any]] = [
        {
            "id": "m0",
            "role": "assistant",
            "content": "开场：我们来聊聊你的价值观。",
            "thread_id": THREAD_ID,
            "step_id": "values",
            "agent_id": "coach",
            "event": "assistant_reply",
            "created_at": "2026-08-25T00:00:00Z",
        }
    ]
    for i in range(user_turns):
        msgs.append(
            {
                "id": f"u{i+1}",
                "role": "user",
                "content": f"第 {i+1} 条用户回答：我在意成长与意义。",
                "thread_id": THREAD_ID,
                "step_id": "values",
                "agent_id": None,
                "event": "user_message",
                "created_at": f"2026-08-25T00:{i:02d}:00Z",
            }
        )
        msgs.append(
            {
                "id": f"a{i+1}",
                "role": "assistant",
                "content": f"追问 {i+1}：还有呢？",
                "thread_id": THREAD_ID,
                "step_id": "values",
                "agent_id": "coach",
                "event": "assistant_reply",
                "created_at": f"2026-08-25T00:{i:02d}:30Z",
            }
        )
    return msgs


@pytest.fixture()
def seeded_env(tmp_path, monkeypatch):
    """按 user_turns 参数化种子：fresh values 线程，conclusion_state=none。"""

    def _seed(user_turns: int) -> Dict[str, Any]:
        simple_root = tmp_path / "simple"
        reports_root = simple_root / "reports"
        rdir = reports_root / REPORT_ID
        rdir.mkdir(parents=True, exist_ok=True)

        record = {
            "report_id": REPORT_ID,
            "activation_code": "MOCKPLACEHOLDER",
            "user_id": TEST_USER["user_id"],
            "created_at": "2026-08-25T00:00:00Z",
            "updated_at": "2026-08-25T00:00:00Z",
            "status": "in_progress",
            "final_conclusion": None,
            "steps": {
                step: {
                    "step_id": step,
                    "selected_session_id": THREAD_ID if step == "values" else None,
                    "locked": False,
                    "session_ids": [THREAD_ID] if step == "values" else [],
                    "updated_at": "2026-08-25T00:00:00Z",
                }
                for step in ["values", "strengths", "interests", "purpose", "rumination"]
            },
        }
        (rdir / "record.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        thread_data = {
            "report_id": REPORT_ID,
            "session_id": THREAD_ID,
            "category": f"values__{THREAD_ID}",
            "messages": _build_thread_messages(user_turns),
            "metadata": {
                "created_at": "2026-08-25T00:00:00Z",
                "updated_at": "2026-08-25T00:00:00Z",
                "conclusion_state": "none",
                "thread_completed": False,
            },
        }
        (rdir / f"values__{THREAD_ID}.json").write_text(
            json.dumps(thread_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        monkeypatch.setattr(activation_manager_mod, "get_simple_base_dir", lambda: simple_root)
        app.dependency_overrides[get_current_user] = lambda: TEST_USER

        manager = SimpleActivationManager(base_dir=str(simple_root))
        rec = manager.create_activation(mode="values", ttl_minutes=180)
        manager.claim_owner(rec.code, TEST_USER)

        record["activation_code"] = rec.code
        (rdir / "record.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        monkeypatch.setattr(simple_chat_api, "_trigger_anchor_refiner", lambda *a, **k: None)

        return {
            "client": TestClient(app),
            "headers": {"Authorization": "Bearer fake-token"},
            "activation_code": rec.code,
            "thread_file": rdir / f"values__{THREAD_ID}.json",
        }

    yield _seed
    app.dependency_overrides.clear()


def _stream_events(client: TestClient, headers: Dict[str, str], payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    with client.stream("POST", "/api/v1/simple-chat/message/stream", json=payload, headers=headers) as resp:
        assert resp.status_code == 200
        for line in resp.iter_lines():
            if not line:
                continue
            text = line.decode("utf-8") if isinstance(line, bytes) else line
            if not text.startswith("data: "):
                continue
            events.append(json.loads(text[6:]))
    return events


def _pending_ready_stream_reply() -> str:
    return (
        "好的，我为你整理了结论。\n"
        '[STATE_JSON]{"state":"pending_ready","draft":{"summary":"你重视成长与意义。",'
        '"keywords":["成长","意义感"]}}[/STATE_JSON]'
    )


# ---------------------------------------------------------------- gate


def test_gate_suppresses_pending_ready_before_11_turns(seeded_env, monkeypatch):
    """第 10 条用户消息（<11）：模型输出 pending_ready 也被拦截，不出卡、状态保持 none。"""
    env = seeded_env(9)  # 已有 9 条 + 本次 1 条 = 10 < 11
    called = {"refine": False}

    async def fake_check(*args, **kwargs):
        called["refine"] = True
        return FAKE_CARD

    monkeypatch.setattr(simple_chat_api, "check_dimension_complete", fake_check)
    monkeypatch.setattr(simple_chat_api, "_get_reasoning_llm_provider", lambda vip_level=1: object())
    monkeypatch.setattr(
        simple_chat_api,
        "_get_dialogue_llm_provider",
        lambda vip_level=1: FakeDialogueLLM(stream_reply=_pending_ready_stream_reply()),
    )

    events = _stream_events(
        env["client"],
        env["headers"],
        {
            "activation_code": env["activation_code"],
            "phase": "values",
            "thread_id": THREAD_ID,
            "message": "确认，就是这些。",
        },
    )
    assert any(e.get("done") is True for e in events)
    assert not any("dimension_conclusion" in e for e in events)
    assert not any(e.get("conclusion_loading") for e in events)
    assert called["refine"] is False

    meta = _read_json(env["thread_file"]).get("metadata", {})
    assert meta.get("conclusion_state") in (None, "none")
    assert not isinstance(meta.get("conclusion_draft"), dict)


def test_gate_allows_card_at_11_turns(seeded_env, monkeypatch):
    """第 11 条用户消息起放开：pending_ready 正常出卡，状态置 pending。"""
    env = seeded_env(10)  # 已有 10 条 + 本次 1 条 = 11 ≥ 11

    async def fake_check(*args, **kwargs):
        return dict(FAKE_CARD)

    monkeypatch.setattr(simple_chat_api, "check_dimension_complete", fake_check)
    monkeypatch.setattr(simple_chat_api, "_get_reasoning_llm_provider", lambda vip_level=1: object())
    monkeypatch.setattr(
        simple_chat_api,
        "_get_dialogue_llm_provider",
        lambda vip_level=1: FakeDialogueLLM(stream_reply=_pending_ready_stream_reply()),
    )

    events = _stream_events(
        env["client"],
        env["headers"],
        {
            "activation_code": env["activation_code"],
            "phase": "values",
            "thread_id": THREAD_ID,
            "message": "确认，就是这些。",
        },
    )
    assert any("dimension_conclusion" in e for e in events)
    assert any(e.get("done") is True for e in events)

    meta = _read_json(env["thread_file"]).get("metadata", {})
    assert meta.get("conclusion_state") == "pending"
    assert isinstance(meta.get("conclusion_draft"), dict)


# ---------------------------------------------------------------- injection


def test_injection_gate_tells_model_not_to_conclude():
    """门控开启时注入文案改为「深入探索期不收口」，关闭时保持原口径。"""
    from app.domain.conclusion_card_payload import build_conclusion_state_injection

    gated = build_conclusion_state_injection("values", "none", gate_active=True)
    assert "深入探索期" in gated
    assert "不要输出 STATE_JSON" in gated

    normal = build_conclusion_state_injection("values", "none")
    assert "pending_ready" in normal
    assert "深入探索期" not in normal

    # gate 仅作用 none 态，rejected 不受影啊
    rejected = build_conclusion_state_injection("values", "rejected", feedback="不准", gate_active=True)
    assert "明确点头确认时" in rejected


# ---------------------------------------------------------------- manual endpoint


def test_conclusion_request_rejected_before_11_turns(seeded_env):
    """手动出卡端点：<11 轮返回 400。"""
    env = seeded_env(5)
    resp = env["client"].post(
        "/api/v1/simple-chat/conclusion/request",
        json={
            "activation_code": env["activation_code"],
            "phase": "values",
            "thread_id": THREAD_ID,
        },
        headers=env["headers"],
    )
    assert resp.status_code == 400
    assert "轮数不足" in str(resp.json().get("detail", ""))


def test_conclusion_request_generates_card_and_idempotent(seeded_env, monkeypatch):
    """手动出卡端点：≥11 轮生成草案卡并置 pending；重复调用幂等返回同一张卡。"""
    env = seeded_env(12)

    async def fake_check(*args, **kwargs):
        return dict(FAKE_CARD)

    monkeypatch.setattr(simple_chat_api, "check_dimension_complete", fake_check)
    monkeypatch.setattr(simple_chat_api, "_get_reasoning_llm_provider", lambda vip_level=1: object())

    payload = {
        "activation_code": env["activation_code"],
        "phase": "values",
        "thread_id": THREAD_ID,
    }
    resp = env["client"].post("/api/v1/simple-chat/conclusion/request", json=payload, headers=env["headers"])
    assert resp.status_code == 200
    card = resp.json()["data"]["dimension_conclusion"]
    assert card["summary"] == FAKE_CARD["summary"]

    meta = _read_json(env["thread_file"]).get("metadata", {})
    assert meta.get("conclusion_state") == "pending"
    assert meta.get("conclusion_draft", {}).get("summary") == FAKE_CARD["summary"]

    # 幂等：state 已是 pending，直接返回现有卡，不再生成
    async def fail_if_called(*args, **kwargs):
        raise AssertionError("pending 状态下不应再次调用 LLM 生成")

    monkeypatch.setattr(simple_chat_api, "check_dimension_complete", fail_if_called)
    resp2 = env["client"].post("/api/v1/simple-chat/conclusion/request", json=payload, headers=env["headers"])
    assert resp2.status_code == 200
    assert resp2.json()["data"]["dimension_conclusion"]["summary"] == FAKE_CARD["summary"]
    assert resp2.json()["data"].get("idempotent") is True


def test_conclusion_request_llm_failure_returns_503(seeded_env, monkeypatch):
    """生成失败不静默：端点抛 503，前端据此展示「生成失败，点击重试」。"""
    env = seeded_env(12)

    async def fake_check(*args, **kwargs):
        raise RuntimeError("llm down")

    monkeypatch.setattr(simple_chat_api, "check_dimension_complete", fake_check)
    monkeypatch.setattr(simple_chat_api, "_get_reasoning_llm_provider", lambda vip_level=1: object())

    resp = env["client"].post(
        "/api/v1/simple-chat/conclusion/request",
        json={
            "activation_code": env["activation_code"],
            "phase": "values",
            "thread_id": THREAD_ID,
        },
        headers=env["headers"],
    )
    assert resp.status_code == 503
    meta = _read_json(env["thread_file"]).get("metadata", {})
    assert meta.get("conclusion_state") in (None, "none")
