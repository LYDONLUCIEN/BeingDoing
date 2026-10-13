"""thread/complete 结论卡前置校验测试。

口径（2026-10-13）：用户点「确认没有问题」时该线程必须已有结论卡
（confirmed final 或 pending draft），否则返回 400，且不得执行
bind/select_session、不得置 thread_completed——防止前端串会话时
把无结论的空线程固化成 phase 级选择，污染 dimension_conclusions /
anchor / rumination 输入。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

import app.api.v1.simple_chat_routes as simple_chat_api
import app.utils.simple_activation_manager as activation_manager_mod
from app.api.v1.auth import get_current_user
from app.main import app
from app.utils.simple_activation_manager import SimpleActivationManager

TEST_USER = {
    "user_id": "pytest-complete-guard-user",
    "email": "pytest-complete-guard@example.com",
}
REPORT_ID = "mock-report-complete-guard-001"
THREAD_ID = "t_complete_guard_001"

FAKE_DRAFT = {
    "summary": "你重视成长、创新、意义感。",
    "keywords": ["成长", "创新", "意义感"],
}


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture()
def seeded_env(tmp_path, monkeypatch):
    """fresh values 线程（conclusion_state=none）种子；返回临时目录上下文。"""

    def _seed() -> Dict[str, Any]:
        simple_root = tmp_path / "simple"
        reports_root = simple_root / "reports"
        rdir = reports_root / REPORT_ID
        rdir.mkdir(parents=True, exist_ok=True)

        record = {
            "report_id": REPORT_ID,
            "activation_code": "MOCKPLACEHOLDER",
            "user_id": TEST_USER["user_id"],
            "created_at": "2026-10-13T00:00:00Z",
            "updated_at": "2026-10-13T00:00:00Z",
            "status": "in_progress",
            "final_conclusion": None,
            "steps": {
                step: {
                    "step_id": step,
                    "selected_session_id": None,
                    "locked": False,
                    "session_ids": [],
                    "updated_at": "2026-10-13T00:00:00Z",
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
            "messages": [
                {
                    "id": "m0",
                    "role": "assistant",
                    "content": "开场：我们来聊聊你的价值观。",
                    "thread_id": THREAD_ID,
                    "step_id": "values",
                    "agent_id": "coach",
                    "event": "assistant_reply",
                    "created_at": "2026-10-13T00:00:00Z",
                },
                {
                    "id": "u1",
                    "role": "user",
                    "content": "我在意成长与意义。",
                    "thread_id": THREAD_ID,
                    "step_id": "values",
                    "agent_id": None,
                    "event": "user_message",
                    "created_at": "2026-10-13T00:01:00Z",
                },
            ],
            "metadata": {
                "created_at": "2026-10-13T00:00:00Z",
                "updated_at": "2026-10-13T00:00:00Z",
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
            "record_file": rdir / "record.json",
        }

    yield _seed
    app.dependency_overrides.clear()


def _complete(env: Dict[str, Any]):
    return env["client"].post(
        "/api/v1/simple-chat/thread/complete",
        json={"activation_code": env["activation_code"], "phase": "values", "thread_id": THREAD_ID},
        headers=env["headers"],
    )


def test_complete_without_conclusion_returns_400(seeded_env):
    """无结论卡（state=none）的线程调 complete：400，不落任何完成状态。"""
    env = seeded_env()
    resp = _complete(env)
    assert resp.status_code == 400

    meta = _read_json(env["thread_file"]).get("metadata", {})
    assert meta.get("thread_completed") is not True
    # 不得追加 conclusion_card 消息
    thread = _read_json(env["thread_file"])
    assert not any((m or {}).get("role") == "conclusion_card" for m in thread.get("messages", []))
    # 不得把该线程写为 phase 级 selected（防 phase 级数据被无线索线程污染）
    record = _read_json(env["record_file"])
    assert record["steps"]["values"].get("selected_session_id") is None


def test_complete_with_pending_draft_returns_200(seeded_env):
    """有 pending 草案的线程调 complete：正常 200 并置 completed（既有行为回归）。"""
    env = seeded_env()
    thread = _read_json(env["thread_file"])
    thread["metadata"]["conclusion_state"] = "pending"
    thread["metadata"]["conclusion_draft"] = dict(FAKE_DRAFT)
    env["thread_file"].write_text(
        json.dumps(thread, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    resp = _complete(env)
    assert resp.status_code == 200

    meta = _read_json(env["thread_file"]).get("metadata", {})
    assert meta.get("thread_completed") is True
    record = _read_json(env["record_file"])
    assert record["steps"]["values"].get("selected_session_id") == THREAD_ID
