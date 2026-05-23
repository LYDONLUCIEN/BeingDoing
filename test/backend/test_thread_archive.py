"""thread_archive 软归档与 context_resolver 空 session_ids 行为"""

import json
from pathlib import Path

import pytest

from app.utils.report_registry import ReportRegistry
from app.utils.thread_archive import archive_step_session_file


class TestArchiveStepSessionFile:
    def test_moves_session_and_lock_to_deleted_threads(self, tmp_path):
        report_dir = tmp_path / "rep-1"
        report_dir.mkdir()
        session_file = report_dir / "values__t_abc123.json"
        session_file.write_text('{"messages": []}', encoding="utf-8")
        lock_file = report_dir / "values__t_abc123.json.lock"
        lock_file.write_text("", encoding="utf-8")

        archive_dir = archive_step_session_file(
            session_file,
            phase_step="values",
            thread_id="t_abc123",
            report_id="rep-1",
            operator_user_id="user-1",
        )

        assert archive_dir is not None
        assert not session_file.exists()
        assert not lock_file.exists()
        assert (archive_dir / "values__t_abc123.json").is_file()
        assert (archive_dir / "values__t_abc123.json.lock").is_file()
        manifest = json.loads((archive_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["thread_id"] == "t_abc123"
        assert manifest["phase_step"] == "values"
        assert manifest["operator_user_id"] == "user-1"


class TestDeleteThreadRemovesFromSessionIds:
    def test_remove_session_then_file_archived(self, tmp_path):
        registry = ReportRegistry(base_dir=str(tmp_path))
        report = registry.ensure_report("CODE1", "user-1", session_id="act-sid-1")
        report_id = report["report_id"]
        registry.bind_session(report_id, "values", "t_one")
        registry.bind_session(report_id, "values", "t_two")

        f = registry.get_step_session_file(report_id, "values", "t_one")
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text('{"messages": [{"role":"user","content":"hi"}]}', encoding="utf-8")

        archive_step_session_file(
            f,
            phase_step="values",
            thread_id="t_one",
            report_id=report_id,
        )
        updated = registry.remove_session(report_id, "values", "t_one")
        remaining = ((updated.get("steps") or {}).get("values") or {}).get("session_ids") or []

        assert "t_one" not in remaining
        assert "t_two" in remaining
        assert not f.is_file()
        deleted_root = f.parent / ".deleted_threads" / "values"
        assert deleted_root.is_dir()
        assert any(p.name.startswith("t_one_") for p in deleted_root.iterdir())


class TestContextResolverNoActSidFallback:
    def test_resolve_default_returns_empty_when_no_candidates(self):
        content = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "backend"
            / "app"
            / "api"
            / "v1"
            / "simple_chat"
            / "context_resolver.py"
        ).read_text(encoding="utf-8")
        import re

        body_match = re.search(
            r"def resolve_default_logical_thread_id\((.*?)^def ",
            content,
            re.DOTALL | re.MULTILINE,
        )
        assert body_match, "未找到 resolve_default_logical_thread_id"
        body = body_match.group(1)
        assert not re.search(r"return\s+act_sid\b", body), (
            "context_resolver 不应在 candidates 为空时返回 act_sid"
        )
        assert re.search(r"if not candidates.*?return\s+\"\"", body, re.DOTALL), (
            "context_resolver 在 candidates 为空时应 return \"\""
        )
