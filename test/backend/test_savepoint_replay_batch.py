"""
存档点批量回放：消费 batch_savepoints_general.json，与 replay_simple_chat 用例格式一致。
"""

from __future__ import annotations

import json
import os
import warnings
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient
from _pytest.warning_types import PytestCacheWarning

# 先于 app.main 导入执行，避免测试输出被非关键 warning 淹没。
warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"app\.main")
warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"app\.config\.settings")
warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"passlib\..*")
warnings.filterwarnings("ignore", message=r".*on_event is deprecated.*", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=PytestCacheWarning)

_app = None
_get_current_user = None
simple_chat_api = None
activation_manager_mod = None

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BATCH_FILE = (
    PROJECT_ROOT / "test" / "backend" / "fixtures" / "simple_chat_cases" / "batch_savepoints_general.json"
)

# 与 test_simple_chat_replay_cases 一致，避免写入 data/user 下未授权路径
TEST_USER = {"user_id": "pytest-replay-user", "email": "pytest-replay@example.com"}

# 补充按字符串过滤，覆盖部分第三方 warning 文本。
pytestmark = [pytest.mark.filterwarnings("ignore:.*datetime.datetime.utcnow.*:DeprecationWarning")]


class FakeDialogueLLM:
    def __init__(self, stream_reply: str = "", chat_reply: str = "测试回复"):
        self.stream_reply = stream_reply
        self.chat_reply = chat_reply

    async def chat(self, messages, temperature=0.7, response_format=None):
        return SimpleNamespace(content=self.chat_reply, usage={})

    async def chat_stream(self, messages, temperature=0.7):
        if self.stream_reply:
            yield self.stream_reply


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _env_true(name: str) -> bool:
    v = (os.environ.get(name) or "").strip().lower()
    return v in {"1", "true", "yes", "on"}


def _load_cases_from_batch() -> List[Dict[str, Any]]:
    cases_file_env = (os.environ.get("SAVEPOINT_CASES_FILE") or "").strip()
    batch_file = Path(cases_file_env).resolve() if cases_file_env else DEFAULT_BATCH_FILE
    payload = _read_json(batch_file)
    cases = payload.get("cases") if isinstance(payload, dict) else None
    assert isinstance(cases, list), f"invalid cases file: {batch_file}"
    out = [c for c in cases if isinstance(c, dict) and str(c.get("name") or "").strip()]
    assert out, f"no runnable cases in {batch_file}"

    llm_mode = (os.environ.get("SAVEPOINT_LLM_MODE") or "mock").strip().lower()
    if llm_mode not in {"mock", "real", "all"}:
        raise AssertionError(f"invalid SAVEPOINT_LLM_MODE={llm_mode!r}, expected mock|real|all")
    if llm_mode == "mock":
        out = [c for c in out if not bool(c.get("use_real_llm"))]
    elif llm_mode == "real":
        out = [c for c in out if bool(c.get("use_real_llm"))]
    # all: keep both
    assert out, f"no runnable cases after SAVEPOINT_LLM_MODE={llm_mode!r}"

    selected = (os.environ.get("SAVEPOINT_CASES") or "").strip()
    if not selected:
        return out
    names = {x.strip() for x in selected.split(",") if x.strip()}
    filtered = [c for c in out if str(c.get("name")) in names]
    assert filtered, f"SAVEPOINT_CASES did not match any case names: {sorted(names)}"
    return filtered


def _seed_fixture_report(simple_root: Path, fixture_dir: Path, user: Dict[str, Any]) -> str:
    import shutil

    record_file = fixture_dir / "record.json"
    record = _read_json(record_file)
    report_id = (record.get("report_id") or "").strip()
    assert report_id, "fixture record.json 缺少 report_id"
    reports_root = simple_root / "reports"
    reports_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(fixture_dir, reports_root / report_id, dirs_exist_ok=True)

    from app.utils.simple_activation_manager import SimpleActivationManager

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
        assert resp.status_code == 200, resp.text
        for line in resp.iter_lines():
            if not line:
                continue
            text = line.decode("utf-8") if isinstance(line, bytes) else line
            if not text.startswith("data: "):
                continue
            events.append(json.loads(text[6:]))
    return events


def _apply_case_mocks(case: Dict[str, Any], monkeypatch) -> str:
    mock = case.get("mock") if isinstance(case.get("mock"), dict) else {}
    force_real_llm = _env_true("SAVEPOINT_REAL_LLM")
    use_real_llm = bool(case.get("use_real_llm")) or force_real_llm
    if use_real_llm:
        # 真实 LLM 模式下，不覆盖 provider；可选关闭后台精炼避免噪音。
        if not bool(case.get("enable_anchor_refiner")):
            monkeypatch.setattr(simple_chat_api, "_trigger_anchor_refiner", lambda *args, **kwargs: None)
        return "real"

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
    return "mock"


@pytest.fixture()
def savepoint_env(tmp_path, monkeypatch):
    global _app, _get_current_user, activation_manager_mod, simple_chat_api
    if _app is None:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            from app.api.v1.auth import get_current_user as _gcu
            from app.main import app as _main_app
            import app.api.v1.simple_chat_routes as _routes
            import app.utils.simple_activation_manager as _activation_mod
        _get_current_user = _gcu
        _app = _main_app
        simple_chat_api = _routes
        activation_manager_mod = _activation_mod

    simple_root = tmp_path / "simple"
    simple_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(activation_manager_mod, "get_simple_base_dir", lambda: simple_root)
    _app.dependency_overrides[_get_current_user] = lambda: TEST_USER
    client = TestClient(_app)
    headers = {"Authorization": "Bearer savepoint-token"}
    yield {"client": client, "headers": headers, "simple_root": simple_root}
    _app.dependency_overrides.clear()


def _run_case(case: Dict[str, Any], env: Dict[str, Any], monkeypatch) -> Dict[str, Any]:
    client = env["client"]
    headers = env["headers"]
    simple_root = env["simple_root"]
    seed_cfg = case.get("seed_fixture") or {}
    report_dir = PROJECT_ROOT / str(seed_cfg.get("report_dir") or "")
    assert report_dir.is_dir(), f"case seed_fixture.report_dir 不存在: {report_dir}"
    activation_code = _seed_fixture_report(simple_root, report_dir, TEST_USER)
    phase = str(case.get("phase") or "values")
    thread_id = str(case.get("thread_id") or "")
    steps = case.get("steps")
    runnable_steps: List[Dict[str, Any]] = []
    if isinstance(steps, list) and steps:
        for s in steps:
            if not isinstance(s, dict):
                continue
            msg = str(s.get("message") or "").strip()
            if not msg:
                continue
            runnable_steps.append(s)
    else:
        runnable_steps.append(
            {
                "message": str(case.get("message") or ""),
                "mock": case.get("mock") if isinstance(case.get("mock"), dict) else {},
            }
        )
    assert runnable_steps, f"case has no runnable step: {case.get('name')}"

    all_events: List[Dict[str, Any]] = []
    all_chunks: List[str] = []
    step_results: List[Dict[str, Any]] = []
    llm_mode = "mock"
    for step in runnable_steps:
        local_phase = str(step.get("phase") or phase)
        local_thread = str(step.get("thread_id") or thread_id)
        local_msg = str(step.get("message") or "")
        local_case = dict(case)
        if isinstance(step.get("mock"), dict):
            local_case["mock"] = step["mock"]
        llm_mode = _apply_case_mocks(local_case, monkeypatch)
        events = _stream_events(
            client,
            headers,
            {
                "activation_code": activation_code,
                "phase": local_phase,
                "thread_id": local_thread,
                "message": local_msg,
            },
        )
        all_events.extend(events)
        local_chunks = "".join(str(e.get("chunk") or "") for e in events)
        all_chunks.append(local_chunks)
        local_hist = client.get(
            "/api/v1/simple-chat/history",
            params={"activation_code": activation_code, "phase": local_phase, "thread_id": local_thread},
            headers=headers,
        )
        assert local_hist.status_code == 200
        step_results.append(
            {
                "phase": local_phase,
                "thread_id": local_thread,
                "chunks": local_chunks,
                "history": local_hist.json()["data"],
                "events_count": len(events),
            }
        )
        phase = local_phase
        thread_id = local_thread

    history = client.get(
        "/api/v1/simple-chat/history",
        params={"activation_code": activation_code, "phase": phase, "thread_id": thread_id},
        headers=headers,
    )
    assert history.status_code == 200
    hist_data = history.json()["data"]
    chunks = "".join(all_chunks)
    return {
        "events": all_events,
        "chunks": chunks,
        "history": hist_data,
        "case_name": case.get("name"),
        "steps_executed": len(runnable_steps),
        "step_results": step_results,
        "llm_mode": llm_mode,
    }


def _assert_case_expectations(case: Dict[str, Any], ret: Dict[str, Any]) -> None:
    assert any((e or {}).get("done") is True for e in ret["events"])
    if not bool(case.get("allow_state_json_leak")):
        assert "[STATE_JSON]" not in ret["chunks"]
        assert "[/STATE_JSON]" not in ret["chunks"]
    assertions = case.get("assertions") if isinstance(case.get("assertions"), dict) else {}
    if not assertions:
        return
    msgs = ret["history"].get("messages") or []
    roles = [str((m or {}).get("role") or "") for m in msgs if isinstance(m, dict)]
    for role in assertions.get("history_roles_contains") or []:
        assert role in roles, f"missing role in history: {role}"
    for role in assertions.get("history_roles_not_contains") or []:
        assert role not in roles, f"unexpected role in history: {role}"
    meta = ret["history"].get("metadata") or {}
    for k, v in (assertions.get("history_metadata_equals") or {}).items():
        assert meta.get(k) == v, f"metadata mismatch: {k} expected={v!r} actual={meta.get(k)!r}"
    for token in assertions.get("chunks_contains") or []:
        assert token in ret["chunks"], f"missing token in chunks: {token}"
    for token in assertions.get("chunks_not_contains") or []:
        assert token not in ret["chunks"], f"unexpected token in chunks: {token}"
    if "steps_executed" in assertions:
        assert ret["steps_executed"] == int(assertions["steps_executed"])
    for step_asrt in assertions.get("step_assertions") or []:
        if not isinstance(step_asrt, dict):
            continue
        idx = int(step_asrt.get("index", -1))
        assert 0 <= idx < len(ret["step_results"]), f"invalid step_assertion index: {idx}"
        sret = ret["step_results"][idx]
        smeta = (sret.get("history") or {}).get("metadata") or {}
        for k, v in (step_asrt.get("history_metadata_equals") or {}).items():
            assert smeta.get(k) == v, (
                f"step[{idx}] metadata mismatch: {k} expected={v!r} actual={smeta.get(k)!r}"
            )
        for token in step_asrt.get("chunks_contains") or []:
            assert token in str(sret.get("chunks") or ""), f"step[{idx}] missing token: {token}"
        for token in step_asrt.get("chunks_not_contains") or []:
            assert token not in str(sret.get("chunks") or ""), f"step[{idx}] unexpected token: {token}"


ALL_CASES = _load_cases_from_batch()


@pytest.mark.parametrize("case", ALL_CASES, ids=[str(c["name"]) for c in ALL_CASES])
def test_savepoint_batch_cases(savepoint_env, monkeypatch, case: Dict[str, Any]):
    ret = _run_case(case, savepoint_env, monkeypatch)
    _assert_case_expectations(case, ret)
