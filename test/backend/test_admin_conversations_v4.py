"""admin 会话列表/详情覆盖 rumination v4 combo 会话的测试。

口径（2026-10-13）：v4 combo 会话只存 rumination_v4_progress.json、不登记
record.json 的 session_ids；admin 会话列表需补充枚举 combo（否则整组漏行），
详情需支持按 (report_id, rumination, combo_id) 返回对话原文。
"""

from __future__ import annotations

import json
from functools import partial
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.v1.auth import get_current_user
from app.main import app

REPORT_ID = "mock-report-admin-conv-v4"
ACTIVATION_CODE = "ADMV4TEST01"
THREAD_ID = "t_admin_conv_001"

FAKE_DRAFT = {
    "summary": "你重视成长与意义。",
    "keywords": ["成长", "意义感"],
}


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _v4_message(role: str, content: str, ts: str) -> Dict[str, Any]:
    return {"role": role, "content": content, "ts": ts}


@pytest.fixture()
def seeded_env(tmp_path, monkeypatch):
    """tmp simple 根：1 个 values thread + 2 个 v4 combo（带 messages）。

    ReportRegistry() 默认经 get_simple_base_dir() 定位数据根；打桩它可同时覆盖
    列表/详情/_load_report_step_session 里的全部实例化，且保留 normalize_step_id
    等静态方法（不能用 partial(ReportRegistry) 替换类本身）。
    """
    simple_root = tmp_path / "simple"
    rdir = simple_root / "reports" / REPORT_ID
    rdir.mkdir(parents=True, exist_ok=True)

    record = {
        "report_id": REPORT_ID,
        "activation_code": ACTIVATION_CODE,
        "user_id": "admin-conv-user",
        "created_at": "2026-10-13T00:00:00Z",
        "updated_at": "2026-10-13T01:00:00Z",
        "status": "in_progress",
        "final_conclusion": None,
        "steps": {
            step: {
                "step_id": step,
                "selected_session_id": THREAD_ID if step == "values" else None,
                "locked": False,
                "session_ids": [THREAD_ID] if step == "values" else [],
                "updated_at": "2026-10-13T00:30:00Z",
            }
            for step in ["values", "strengths", "interests", "purpose", "rumination"]
        },
    }
    _write_json(rdir / "record.json", record)
    _write_json(
        rdir / f"values__{THREAD_ID}.json",
        {
            "report_id": REPORT_ID,
            "session_id": THREAD_ID,
            "category": f"values__{THREAD_ID}",
            "messages": [
                {
                    "id": "m0",
                    "role": "assistant",
                    "content": "开场",
                    "created_at": "2026-10-13T00:00:00Z",
                }
            ],
            "metadata": {"conclusion_state": "none", "thread_completed": False},
        },
    )
    _write_json(
        rdir / "rumination_v4_progress.json",
        {
            "schema_version": 4,
            "matrix_snapshot": {"passions": ["写作"], "strengths": ["共情"]},
            "combo_sessions": [
                {
                    "combo_id": "combo_1",
                    "passion": "写作",
                    "strengths": ["共情"],
                    "created_at": "2026-10-13T00:10:00Z",
                    "updated_at": "2026-10-13T00:20:00Z",
                    "status": "discussing",
                    "messages": [
                        _v4_message("assistant", "我们聊聊写作×共情。", "2026-10-13T00:10:00Z"),
                        _v4_message("user", "我想做心理科普作者。", "2026-10-13T00:11:00Z"),
                        _v4_message("assistant", "很好，继续展开。", "2026-10-13T00:12:00Z"),
                    ],
                    "summary": None,
                    "summary_last_round": 0,
                    "conclusion_card": None,
                    "balance_analysis": None,
                    "user_skipped": False,
                },
                {
                    "combo_id": "combo_2",
                    "passion": "写作",
                    "strengths": ["共情"],
                    "created_at": "2026-10-13T00:30:00Z",
                    "updated_at": "2026-10-13T00:40:00Z",
                    "status": "discussing",
                    "messages": [
                        _v4_message("assistant", "第二个组合开场。", "2026-10-13T00:30:00Z"),
                    ],
                    "summary": None,
                    "summary_last_round": 0,
                    "conclusion_card": None,
                    "balance_analysis": None,
                    "user_skipped": False,
                },
            ],
            "active_combo_id": "combo_1",
            "final_selection": {
                "selected_combo_ids": [],
                "submitted": False,
                "submitted_at": None,
            },
            "main_section": "combo_session",
            "intro_shown": True,
        },
    )

    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "admin-1",
        "email": "admin@example.com",
    }
    monkeypatch.setattr("app.utils.report_registry.get_simple_base_dir", lambda: simple_root)
    yield {"client": TestClient(app), "simple_root": simple_root}
    app.dependency_overrides.pop(get_current_user, None)


def test_list_includes_v4_combo_rows(seeded_env):
    """列表：values thread 行仍在，且 2 个 v4 combo 行补充出现。"""
    env = seeded_env
    with patch("app.api.v1.admin._is_super_admin", return_value=True):
        resp = env["client"].get(
            "/api/v1/admin/conversations", params={"activation_code": ACTIVATION_CODE}
        )
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    by_session = {(i["step_id"], i["session_id"]): i for i in items}
    assert ("values", THREAD_ID) in by_session
    assert ("rumination", "combo_1") in by_session
    assert ("rumination", "combo_2") in by_session
    assert by_session[("rumination", "combo_1")]["message_count"] == 3
    assert by_session[("rumination", "combo_2")]["message_count"] == 1
    assert by_session[("rumination", "combo_1")]["last_message_at"] == "2026-10-13T00:12:00Z"


def test_list_step_filter_excludes_combos(seeded_env):
    """step_id=values 过滤时不出现 v4 combo 行。"""
    env = seeded_env
    with patch("app.api.v1.admin._is_super_admin", return_value=True):
        resp = env["client"].get(
            "/api/v1/admin/conversations",
            params={"activation_code": ACTIVATION_CODE, "step_id": "values"},
        )
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert all(i["step_id"] == "values" for i in items)
    assert not any(i["session_id"].startswith("combo_") for i in items)


def test_detail_returns_v4_combo_messages(seeded_env):
    """详情：按 (report_id, rumination, combo_id) 返回 messages 原文，ts 归一化为 created_at。"""
    env = seeded_env
    with patch("app.api.v1.admin._is_super_admin", return_value=True):
        resp = env["client"].get(
            "/api/v1/admin/conversations/combo_1",
            params={"report_id": REPORT_ID, "step_id": "rumination"},
        )
    assert resp.status_code == 200
    data = resp.json()["data"]
    conv = data.get("conversation") or {}
    messages = conv.get("messages") or []
    assert len(messages) == 3
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "我想做心理科普作者。"
    assert messages[1].get("created_at") == "2026-10-13T00:11:00Z"
    meta = conv.get("metadata") or {}
    assert meta.get("combo_id") == "combo_1"
    assert meta.get("passion") == "写作"


def test_admin_required_for_list_and_detail(seeded_env):
    """非管理员：列表与详情均 403（拒绝路径）。"""
    env = seeded_env
    with patch("app.api.v1.admin._is_super_admin", return_value=False):
        r1 = env["client"].get("/api/v1/admin/conversations")
        r2 = env["client"].get(
            "/api/v1/admin/conversations/combo_1",
            params={"report_id": REPORT_ID, "step_id": "rumination"},
        )
    assert r1.status_code == 403
    assert r2.status_code == 403
