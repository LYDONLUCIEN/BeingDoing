"""ReportRegistry：canonical 选用、跨激活 session 冲突、ensure_report 并发。"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from app.utils.report_registry import ReportRegistry


def _write_record(root: Path, report_id: str, payload: dict) -> None:
    d = root / "reports" / report_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "record.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.fixture
def reg(tmp_path: Path) -> ReportRegistry:
    base = tmp_path / "simple"
    base.mkdir(parents=True, exist_ok=True)
    return ReportRegistry(base_dir=str(base))


def test_get_by_activation_user_prefers_oldest_created_when_duplicates(reg: ReportRegistry) -> None:
    root = reg.simple_base_dir
    code, uid = "ABC123", "user-1"
    older = {
        "report_id": "older-id",
        "activation_code": code,
        "user_id": uid,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-05T00:00:00Z",
        "status": "in_progress",
        "final_conclusion": None,
        "steps": {},
    }
    newer = {
        "report_id": "newer-id",
        "activation_code": code,
        "user_id": uid,
        "created_at": "2026-02-01T00:00:00Z",
        "updated_at": "2026-03-01T00:00:00Z",
        "status": "in_progress",
        "final_conclusion": None,
        "steps": {},
    }
    _write_record(root, "newer-id", newer)
    _write_record(root, "older-id", older)

    got = reg.get_by_activation_user(code, uid)
    assert got is not None
    assert got["report_id"] == "older-id"


def test_get_by_activation_user_same_created_prefers_more_sessions(reg: ReportRegistry) -> None:
    root = reg.simple_base_dir
    code, uid = "XYZ99", "user-2"
    ts = "2026-01-10T12:00:00Z"
    sparse = {
        "report_id": "sparse-id",
        "activation_code": code,
        "user_id": uid,
        "created_at": ts,
        "updated_at": ts,
        "status": "in_progress",
        "final_conclusion": None,
        "steps": {
            "values": {"step_id": "values", "session_ids": ["a"], "locked": False},
        },
    }
    rich = {
        "report_id": "rich-id",
        "activation_code": code,
        "user_id": uid,
        "created_at": ts,
        "updated_at": ts,
        "status": "in_progress",
        "final_conclusion": None,
        "steps": {
            "values": {"step_id": "values", "session_ids": ["a", "b"], "locked": False},
            "strengths": {"step_id": "strengths", "session_ids": ["c"], "locked": False},
        },
    }
    _write_record(root, "sparse-id", sparse)
    _write_record(root, "rich-id", rich)

    got = reg.get_by_activation_user(code, uid)
    assert got is not None
    assert got["report_id"] == "rich-id"


def test_bind_session_rejects_same_session_on_different_activation(reg: ReportRegistry) -> None:
    root = reg.simple_base_dir
    shared = "shared-thread-xyz"
    r1 = {
        "report_id": "r1",
        "activation_code": "CODE1",
        "user_id": "u1",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "status": "in_progress",
        "final_conclusion": None,
        "steps": {"values": {"step_id": "values", "session_ids": [shared], "locked": False}},
    }
    r2 = {
        "report_id": "r2",
        "activation_code": "CODE2",
        "user_id": "u2",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "status": "in_progress",
        "final_conclusion": None,
        "steps": {"values": {"step_id": "values", "session_ids": [], "locked": False}},
    }
    _write_record(root, "r1", r1)
    _write_record(root, "r2", r2)

    with pytest.raises(ValueError, match="已绑定到其他探索报告"):
        reg.bind_session("r2", "values", shared)


def test_bind_session_admin_mock_allowed_on_second_report(reg: ReportRegistry) -> None:
    root = reg.simple_base_dir
    r1 = {
        "report_id": "r1",
        "activation_code": "CODE1",
        "user_id": "u1",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "status": "in_progress",
        "final_conclusion": None,
        "steps": {"values": {"step_id": "values", "session_ids": ["admin_mock"], "locked": False}},
    }
    r2 = {
        "report_id": "r2",
        "activation_code": "CODE2",
        "user_id": "u2",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "status": "in_progress",
        "final_conclusion": None,
        "steps": {"values": {"step_id": "values", "session_ids": [], "locked": False}},
    }
    _write_record(root, "r1", r1)
    _write_record(root, "r2", r2)
    out = reg.bind_session("r2", "values", "admin_mock")
    assert out is not None
    assert "admin_mock" in out["steps"]["values"]["session_ids"]


def test_ensure_report_prunes_duplicate_and_keeps_canonical(reg: ReportRegistry) -> None:
    root = reg.simple_base_dir
    code, uid = "DUP01", "user-dup"
    a = {
        "report_id": "keep-me",
        "activation_code": code,
        "user_id": uid,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-02T00:00:00Z",
        "status": "in_progress",
        "final_conclusion": None,
        "steps": {},
    }
    b = {
        "report_id": "drop-me",
        "activation_code": code,
        "user_id": uid,
        "created_at": "2026-02-01T00:00:00Z",
        "updated_at": "2026-02-03T00:00:00Z",
        "status": "in_progress",
        "final_conclusion": None,
        "steps": {},
    }
    _write_record(root, "drop-me", b)
    _write_record(root, "keep-me", a)

    rec = reg.ensure_report(code, uid, session_id=None)
    assert rec["report_id"] == "keep-me"
    assert (root / "reports" / "keep-me" / "record.json").is_file()
    assert not (root / "reports" / "drop-me").exists()


def test_ensure_report_concurrent_only_one_report_dir(reg: ReportRegistry) -> None:
    code, uid = "CONC", "user-c"
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            reg.ensure_report(code, uid, session_id=None)
        except BaseException as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    matches = reg._matches_activation_user(code, uid)
    assert len(matches) == 1
    rid = {m.get("report_id") for m in matches}
    assert len(rid) == 1


def test_simple_thread_id_unique() -> None:
    from app.utils.simple_thread_id import allocate_simple_chat_thread_id

    ids = {allocate_simple_chat_thread_id() for _ in range(100)}
    assert len(ids) == 100
    assert all(x.startswith("t_") and len(x) > 8 for x in ids)


def test_end_user_cannot_soft_delete(tmp_path: Path) -> None:
    from app.utils.simple_activation_manager import SimpleActivationManager

    m = SimpleActivationManager(base_dir=str(tmp_path / "simple"))
    with pytest.raises(PermissionError):
        m.soft_delete_to_recycle_bin(["ANY"], caller_role="end_user")
    with pytest.raises(PermissionError):
        m.permanent_delete_from_recycle_bin(["ANY"], caller_role="end_user")
