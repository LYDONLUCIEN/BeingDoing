"""
simple-chat 回放用例测试（单条 + 批量）。

说明：
- 使用 test/backend/fixtures/simple_chat_reports 下的假数据（符合 report 标准结构）
- 全部通过后端 API 调用（不依赖前端）
- 用 monkeypatch 模拟 LLM 输出，确保回归结果稳定
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from app.api.v1.auth import get_current_user
from app.main import app
import app.api.v1.simple_chat as simple_chat_api
import app.utils.simple_activation_manager as activation_manager_mod
from app.utils.simple_activation_manager import SimpleActivationManager


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_ROOT = PROJECT_ROOT / "test" / "backend" / "fixtures"
REPORT_FIXTURE_DIR = FIXTURES_ROOT / "simple_chat_reports" / "mock_values_pending"
SINGLE_CASE_FILE = FIXTURES_ROOT / "simple_chat_cases" / "single_values_continue.json"
BATCH_CASE_FILE = FIXTURES_ROOT / "simple_chat_cases" / "batch_basic.json"

TEST_USER = {
    "user_id": "pytest-replay-user",
    "email": "pytest-replay@example.com",
}


class FakeDialogueLLM:
    def __init__(self, stream_reply: str = "", chat_reply: str = "测试回复"):
        self.stream_reply = stream_reply
        self.chat_reply = chat_reply
        self._last_stream_usage = None

    async def chat(self, messages, temperature=0.7, response_format=None):
        return SimpleNamespace(content=self.chat_reply, usage={})

    async def chat_stream(self, messages, temperature=0.7):
        if self.stream_reply:
            yield self.stream_reply


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _seed_fixture_report(simple_root: Path, fixture_dir: Path, user: Dict[str, Any]) -> str:
    record_file = fixture_dir / "record.json"
    assert record_file.is_file(), f"fixture 缺少 record.json: {record_file}"
    record = _read_json(record_file)
    report_id = (record.get("report_id") or "").strip()
    assert report_id, "fixture record.json 缺少 report_id"

    reports_root = simple_root / "reports"
    reports_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(fixture_dir, reports_root / report_id, dirs_exist_ok=True)

    manager = SimpleActivationManager(base_dir=str(simple_root))
    rec = manager.create_activation(mode="values", ttl_minutes=180)
    manager.claim_owner(rec.code, user)

    copied_record = reports_root / report_id / "record.json"
    copied = _read_json(copied_record)
    copied["activation_code"] = rec.code
    copied["user_id"] = user["user_id"]
    copied_record.write_text(json.dumps(copied, ensure_ascii=False, indent=2), encoding="utf-8")
    return rec.code


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


def _apply_case_mocks(case: Dict[str, Any], monkeypatch) -> None:
    mock = case.get("mock") if isinstance(case.get("mock"), dict) else {}
    stream_reply = str(mock.get("stream_reply") or "")
    chat_reply = str(mock.get("chat_reply") or "测试回复")
    monkeypatch.setattr(
        simple_chat_api,
        "_get_dialogue_llm_provider",
        lambda vip_level=1: FakeDialogueLLM(stream_reply=stream_reply, chat_reply=chat_reply),
    )
    monkeypatch.setattr(simple_chat_api, "_trigger_anchor_refiner", lambda *args, **kwargs: None)

    if isinstance(mock.get("pending_decision"), dict):
        decision = mock["pending_decision"]

        async def _fake_decide(*args, **kwargs):
            return decision

        monkeypatch.setattr(simple_chat_api, "_decide_pending_action_by_llm", _fake_decide)

    if isinstance(mock.get("dimension_conclusion"), dict):
        conclusion = mock["dimension_conclusion"]

        async def _fake_check(*args, **kwargs):
            return conclusion

        monkeypatch.setattr(simple_chat_api, "check_dimension_complete", _fake_check)
        monkeypatch.setattr(simple_chat_api, "_get_reasoning_llm_provider", lambda vip_level=1: object())


@pytest.fixture()
def replay_env(tmp_path, monkeypatch):
    simple_root = tmp_path / "simple"
    simple_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(activation_manager_mod, "get_simple_base_dir", lambda: simple_root)
    app.dependency_overrides[get_current_user] = lambda: TEST_USER
    client = TestClient(app)
    headers = {"Authorization": "Bearer replay-token"}
    yield {"client": client, "headers": headers, "simple_root": simple_root}
    app.dependency_overrides.clear()


def _run_case(case: Dict[str, Any], env: Dict[str, Any], monkeypatch) -> Dict[str, Any]:
    client = env["client"]
    headers = env["headers"]
    simple_root = env["simple_root"]

    seed_cfg = case.get("seed_fixture") or {}
    report_dir = PROJECT_ROOT / str(seed_cfg.get("report_dir") or "")
    assert report_dir.is_dir(), f"case seed_fixture.report_dir 不存在: {report_dir}"
    activation_code = _seed_fixture_report(simple_root, report_dir, TEST_USER)

    _apply_case_mocks(case, monkeypatch)

    phase = str(case.get("phase") or "values")
    thread_id = str(case.get("thread_id") or "")
    message = str(case.get("message") or "")
    events = _stream_events(
        client,
        headers,
        {
            "activation_code": activation_code,
            "phase": phase,
            "thread_id": thread_id,
            "message": message,
        },
    )
    history = client.get(
        "/api/v1/simple-chat/history",
        params={"activation_code": activation_code, "phase": phase, "thread_id": thread_id},
        headers=headers,
    )
    assert history.status_code == 200
    hist_data = history.json()["data"]

    chunks = "".join(str(e.get("chunk") or "") for e in events)
    return {
        "events": events,
        "chunks": chunks,
        "history": hist_data,
    }


def test_replay_case_single_continue(replay_env, monkeypatch):
    case = _read_json(SINGLE_CASE_FILE)
    ret = _run_case(case, replay_env, monkeypatch)
    assert any((e or {}).get("done") is True for e in ret["events"])
    assert "[STATE_JSON]" not in ret["chunks"]
    assert "[/STATE_JSON]" not in ret["chunks"]


def test_replay_cases_batch_basic(replay_env, monkeypatch):
    payload = _read_json(BATCH_CASE_FILE)
    cases = payload.get("cases") if isinstance(payload, dict) else None
    assert isinstance(cases, list) and len(cases) >= 2

    for case in cases:
        ret = _run_case(case, replay_env, monkeypatch)
        assert any((e or {}).get("done") is True for e in ret["events"])
        chunks = ret["chunks"]
        assert "[STATE_JSON]" not in chunks
        assert "[/STATE_JSON]" not in chunks

        if case.get("name") == "batch_pending_confirmed_emit_card":
            assert any((m or {}).get("role") == "conclusion_card" for m in ret["history"]["messages"])

