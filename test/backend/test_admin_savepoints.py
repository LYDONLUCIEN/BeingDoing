import json
import subprocess
import time
from pathlib import Path

from app.utils import admin_savepoints
from app.utils.report_registry import ReportRegistry
from app.utils.simple_activation_manager import ActivationRecord, SimpleActivationManager


def _seed_debug_activation(tmp_root: Path) -> ActivationRecord:
    code = "SBXTEST0001"
    rec = ActivationRecord(
        code=code,
        session_id="sess_admin_1",
        activation_session_id="sess_admin_1",
        mode="combined",
        created_at="2026-01-01T00:00:00Z",
        expires_at="2027-01-01T00:00:00Z",
        last_activity_at="2026-01-01T00:00:00Z",
        status="active",
        owner_user_id="admin-1",
        owner_email="admin@example.com",
        claimed_at="2026-01-01T00:00:00Z",
        is_sandbox=True,
        workspace_kind="fork",
        workspace_root="sandboxes/fork_1",
    )
    mgr = SimpleActivationManager(base_dir=str(tmp_root))
    mgr.put_activation(rec)
    return rec


def _seed_report_with_messages(rec: ActivationRecord, thread_id: str):
    root = Path(admin_savepoints.get_effective_simple_root(rec))
    registry = ReportRegistry(base_dir=str(root))
    report = registry.ensure_report(rec.code, rec.owner_user_id or "admin-1")
    report_id = report["report_id"]

    # values 主线程消息（目标是 assistant@idx=3）
    values_file = registry.get_step_session_file(report_id, "values", thread_id)
    values_file.parent.mkdir(parents=True, exist_ok=True)
    values_file.write_text(
        json.dumps(
            {
                "report_id": report_id,
                "category": f"values__{thread_id}",
                "messages": [
                    {"id": "m0", "role": "user", "content": "u0"},
                    {"id": "m1", "role": "assistant", "content": "a1"},
                    {"id": "m2", "role": "user", "content": "u2"},
                    {"id": "m3", "role": "assistant", "content": "a3_target"},
                    {"id": "m4", "role": "user", "content": "u4_future"},
                ],
                "metadata": {"total_messages": 5},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    registry.bind_session(report_id, "values", thread_id)
    registry.select_session(report_id, "values", thread_id)

    # 后续 phase 数据（用于验证 global_rewind 清理）
    t2 = "t_strengths_1"
    strengths_file = registry.get_step_session_file(report_id, "strengths", t2)
    strengths_file.write_text(
        json.dumps(
            {
                "report_id": report_id,
                "category": f"strengths__{t2}",
                "messages": [{"id": "s0", "role": "assistant", "content": "future"}],
                "metadata": {"total_messages": 1},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    registry.bind_session(report_id, "strengths", t2)
    registry.select_session(report_id, "strengths", t2)
    registry.lock_step(report_id, "strengths")
    return report_id, values_file


def test_create_and_load_savepoint_global_rewind(monkeypatch, tmp_path):
    test_root = tmp_path / "data_test_simple"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(admin_savepoints, "get_simple_test_base_dir", lambda: test_root)
    monkeypatch.setattr(admin_savepoints, "_project_root", lambda: project_root)

    rec = _seed_debug_activation(test_root)
    report_id, values_file = _seed_report_with_messages(rec, "t_values_1")

    before_source = json.loads(values_file.read_text(encoding="utf-8"))
    assert len(before_source["messages"]) == 5

    meta = admin_savepoints.create_savepoint(
        activation_code=rec.code,
        phase="values",
        thread_id="t_values_1",
        target_message_index=3,
        display_name="值观-step4-引导语检查点",
        created_by={"user_id": "admin-1", "email": "admin@example.com"},
    )
    assert meta["rewind_mode"] == "global_rewind"
    assert meta["savepoint_id"].startswith("sp_")

    # create 不应修改源 fork 数据
    after_source = json.loads(values_file.read_text(encoding="utf-8"))
    assert len(after_source["messages"]) == 5

    sp_dir = test_root / "savepoints" / meta["savepoint_id"]
    snap_values = json.loads((sp_dir / "report" / "values__t_values_1.json").read_text(encoding="utf-8"))
    # 目标 assistant 前一条 user 一并回退 => 保留 m0,m1
    assert [m["id"] for m in snap_values["messages"]] == ["m0", "m1"]
    # 后续 phase 文件被清理
    assert not (sp_dir / "report" / "strengths__t_strengths_1.json").exists()

    # 破坏源 report 后再 load，验证可恢复
    values_file.write_text(
        json.dumps({"messages": [{"id": "dirty", "role": "assistant", "content": "x"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    loaded = admin_savepoints.load_savepoint(activation_code=rec.code, savepoint_id=meta["savepoint_id"])
    assert loaded["loaded"] is True
    assert loaded["phase"] == "values"
    assert loaded["thread_id"] == "t_values_1"
    assert loaded["report_id"] == report_id

    restored = json.loads(values_file.read_text(encoding="utf-8"))
    assert [m["id"] for m in restored["messages"]] == ["m0", "m1"]


def test_savepoint_display_name_conflict(monkeypatch, tmp_path):
    test_root = tmp_path / "data_test_simple"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(admin_savepoints, "get_simple_test_base_dir", lambda: test_root)
    monkeypatch.setattr(admin_savepoints, "_project_root", lambda: project_root)

    rec = _seed_debug_activation(test_root)
    _seed_report_with_messages(rec, "t_values_1")

    admin_savepoints.create_savepoint(
        activation_code=rec.code,
        phase="values",
        thread_id="t_values_1",
        target_message_index=3,
        display_name="重复名检查点",
        created_by={"user_id": "admin-1", "email": "admin@example.com"},
    )

    try:
        admin_savepoints.create_savepoint(
            activation_code=rec.code,
            phase="values",
            thread_id="t_values_1",
            target_message_index=3,
            display_name="重复名检查点",
            created_by={"user_id": "admin-1", "email": "admin@example.com"},
        )
        assert False, "expected FileExistsError"
    except FileExistsError as e:
        payload = json.loads(str(e))
        assert payload["display_name"] == "重复名检查点"
        assert payload["savepoint_id"].startswith("sp_")
        assert "created_at" in payload


def test_export_and_delete_savepoint(monkeypatch, tmp_path):
    test_root = tmp_path / "data_test_simple"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(admin_savepoints, "get_simple_test_base_dir", lambda: test_root)
    monkeypatch.setattr(admin_savepoints, "_project_root", lambda: project_root)

    rec = _seed_debug_activation(test_root)
    _seed_report_with_messages(rec, "t_values_1")

    meta = admin_savepoints.create_savepoint(
        activation_code=rec.code,
        phase="values",
        thread_id="t_values_1",
        target_message_index=3,
        display_name="导出删除检查点",
        created_by={"user_id": "admin-1", "email": "admin@example.com"},
    )

    ret = admin_savepoints.export_savepoint_assets(savepoint_id=meta["savepoint_id"])
    assert Path(ret["fixture_dir"]).is_dir()
    assert Path(ret["cases_file"]).is_file()
    assert Path(ret["scenario_file"]).is_file()
    assert "playwright_command" in ret
    assert "--engine playwright" in str(ret.get("playwright_command") or "")
    assert "replay_command" in ret
    cases = json.loads(Path(ret["cases_file"]).read_text(encoding="utf-8"))
    assert any((x or {}).get("name") == f"savepoint_{meta['savepoint_id']}" for x in cases.get("cases", []))
    scenario_text = Path(ret["scenario_file"]).read_text(encoding="utf-8")
    assert "engine: playwright" in scenario_text
    assert f'savepoint_id: "{meta["savepoint_id"]}"' in scenario_text
    generated_index = project_root / "test_agent" / "scenarios" / "generated" / "generated_index.json"
    assert generated_index.is_file()
    generated_obj = json.loads(generated_index.read_text(encoding="utf-8"))
    generated_items = generated_obj.get("items") or []
    assert any((x or {}).get("savepoint_id") == meta["savepoint_id"] for x in generated_items)
    listed = admin_savepoints.list_generated_scenarios(limit=50)
    assert any((x or {}).get("savepoint_id") == meta["savepoint_id"] for x in listed)

    deleted = admin_savepoints.delete_savepoint(savepoint_id=meta["savepoint_id"])
    assert deleted["deleted"] is True
    assert not (test_root / "savepoints" / meta["savepoint_id"]).exists()


def test_run_generated_scenario_records_status(monkeypatch, tmp_path):
    test_root = tmp_path / "data_test_simple"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(admin_savepoints, "get_simple_test_base_dir", lambda: test_root)
    monkeypatch.setattr(admin_savepoints, "_project_root", lambda: project_root)

    rec = _seed_debug_activation(test_root)
    _seed_report_with_messages(rec, "t_values_1")
    meta = admin_savepoints.create_savepoint(
        activation_code=rec.code,
        phase="values",
        thread_id="t_values_1",
        target_message_index=3,
        display_name="执行场景检查点",
        created_by={"user_id": "admin-1", "email": "admin@example.com"},
    )
    ret_export = admin_savepoints.export_savepoint_assets(savepoint_id=meta["savepoint_id"])
    scenario_file = ret_export["scenario_file"]

    fake_stdout = f"[L2] scenario={meta['savepoint_id']}\n[L2] report={project_root}/test_agent/reports/x.json\n"

    def _fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=fake_stdout, stderr="")

    monkeypatch.setattr(admin_savepoints.subprocess, "run", _fake_run)
    ret = admin_savepoints.run_generated_scenario(savepoint_id=meta["savepoint_id"], engine="auto")
    assert ret["status"] == "passed"
    assert ret["exit_code"] == 0
    assert ret["report_file"]

    generated = admin_savepoints.list_generated_scenarios(limit=20)
    hit = next((x for x in generated if x.get("savepoint_id") == meta["savepoint_id"]), None)
    assert hit is not None
    assert hit.get("scenario_file") == scenario_file
    assert hit.get("last_run_status") == "passed"
    assert "report=" in str(hit.get("last_run_stdout_tail") or "")


def test_run_generated_scenarios_batch_only_failed(monkeypatch, tmp_path):
    test_root = tmp_path / "data_test_simple"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(admin_savepoints, "get_simple_test_base_dir", lambda: test_root)
    monkeypatch.setattr(admin_savepoints, "_project_root", lambda: project_root)
    admin_savepoints._BATCH_JOBS.clear()
    admin_savepoints._RUNNING_SAVEPOINTS.clear()

    generated_dir = project_root / "test_agent" / "scenarios" / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)
    for sid in ("sp_a", "sp_b"):
        (generated_dir / f"{sid}.yaml").write_text("schema_version: 1\nid: x\n", encoding="utf-8")
    idx_file = generated_dir / "generated_index.json"
    idx_file.write_text(
        json.dumps(
            {
                "version": 1,
                "items": [
                    {
                        "savepoint_id": "sp_a",
                        "scenario_file": str(generated_dir / "sp_a.yaml"),
                        "exported_at": "2026-01-01T00:00:00Z",
                        "last_run_status": "failed",
                    },
                    {
                        "savepoint_id": "sp_b",
                        "scenario_file": str(generated_dir / "sp_b.yaml"),
                        "exported_at": "2026-01-01T00:00:01Z",
                        "last_run_status": "passed",
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    called = []

    def _fake_run_generated_scenario(
        *, savepoint_id, engine="auto", dry_run=False, timeout_sec=600, max_retries=0
    ):
        called.append(savepoint_id)
        return {
            "savepoint_id": savepoint_id,
            "status": "passed",
            "exit_code": 0,
            "summary": f"{savepoint_id}-ok",
        }

    monkeypatch.setattr(admin_savepoints, "run_generated_scenario", _fake_run_generated_scenario)
    ret = admin_savepoints.run_generated_scenarios_batch(only_failed=True, engine="auto")
    assert ret["total"] == 1
    assert ret["failed"] == 0
    assert ret["passed"] == 1
    assert called == ["sp_a"]


def test_start_generated_scenarios_batch_job(monkeypatch, tmp_path):
    test_root = tmp_path / "data_test_simple"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(admin_savepoints, "get_simple_test_base_dir", lambda: test_root)
    monkeypatch.setattr(admin_savepoints, "_project_root", lambda: project_root)
    admin_savepoints._BATCH_JOBS.clear()
    admin_savepoints._RUNNING_SAVEPOINTS.clear()

    generated_dir = project_root / "test_agent" / "scenarios" / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)
    (generated_dir / "sp_async.yaml").write_text("schema_version: 1\nid: x\n", encoding="utf-8")
    (generated_dir / "generated_index.json").write_text(
        json.dumps(
            {
                "version": 1,
                "items": [
                    {
                        "savepoint_id": "sp_async",
                        "scenario_file": str(generated_dir / "sp_async.yaml"),
                        "exported_at": "2026-01-01T00:00:00Z",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    def _fake_run_generated_scenario(
        *, savepoint_id, engine="auto", dry_run=False, timeout_sec=600, max_retries=0
    ):
        return {
            "savepoint_id": savepoint_id,
            "status": "passed",
            "exit_code": 0,
            "summary": "ok",
        }

    monkeypatch.setattr(admin_savepoints, "run_generated_scenario", _fake_run_generated_scenario)

    started = admin_savepoints.start_generated_scenarios_batch_job(only_failed=False, engine="auto")
    assert started["job_id"].startswith("job_")
    job_id = started["job_id"]

    final = None
    for _ in range(20):
        final = admin_savepoints.get_generated_scenarios_batch_job(job_id=job_id)
        if final.get("status") == "completed":
            break
        time.sleep(0.05)

    assert final is not None
    assert final.get("status") == "completed"
    assert final.get("total") == 1
    assert final.get("passed") == 1


def test_cancel_generated_scenarios_batch_job_and_history(monkeypatch, tmp_path):
    test_root = tmp_path / "data_test_simple"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(admin_savepoints, "get_simple_test_base_dir", lambda: test_root)
    monkeypatch.setattr(admin_savepoints, "_project_root", lambda: project_root)
    admin_savepoints._BATCH_JOBS.clear()
    admin_savepoints._RUNNING_SAVEPOINTS.clear()

    generated_dir = project_root / "test_agent" / "scenarios" / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)
    for sid in ("sp_c1", "sp_c2"):
        (generated_dir / f"{sid}.yaml").write_text("schema_version: 1\nid: x\n", encoding="utf-8")
    (generated_dir / "generated_index.json").write_text(
        json.dumps(
            {
                "version": 1,
                "items": [
                    {
                        "savepoint_id": "sp_c1",
                        "scenario_file": str(generated_dir / "sp_c1.yaml"),
                        "exported_at": "2026-01-01T00:00:00Z",
                    },
                    {
                        "savepoint_id": "sp_c2",
                        "scenario_file": str(generated_dir / "sp_c2.yaml"),
                        "exported_at": "2026-01-01T00:00:01Z",
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    def _fake_run_generated_scenario(
        *, savepoint_id, engine="auto", dry_run=False, timeout_sec=600, max_retries=0
    ):
        time.sleep(0.08)
        return {
            "savepoint_id": savepoint_id,
            "status": "passed",
            "exit_code": 0,
            "summary": "ok",
        }

    monkeypatch.setattr(admin_savepoints, "run_generated_scenario", _fake_run_generated_scenario)
    started = admin_savepoints.start_generated_scenarios_batch_job(only_failed=False, engine="auto")
    job_id = started["job_id"]
    admin_savepoints.cancel_generated_scenarios_batch_job(job_id=job_id)

    final = None
    for _ in range(30):
        final = admin_savepoints.get_generated_scenarios_batch_job(job_id=job_id)
        if final.get("status") in {"completed", "cancelled"}:
            break
        time.sleep(0.05)
    assert final is not None
    assert final.get("status") in {"completed", "cancelled"}
    hist = admin_savepoints.list_batch_job_history(limit=20)
    assert any((x or {}).get("job_id") == job_id for x in hist)


def test_start_generated_batch_conflict(monkeypatch, tmp_path):
    test_root = tmp_path / "data_test_simple"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(admin_savepoints, "get_simple_test_base_dir", lambda: test_root)
    monkeypatch.setattr(admin_savepoints, "_project_root", lambda: project_root)
    admin_savepoints._BATCH_JOBS.clear()
    admin_savepoints._RUNNING_SAVEPOINTS.clear()

    generated_dir = project_root / "test_agent" / "scenarios" / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)
    (generated_dir / "sp_k1.yaml").write_text("schema_version: 1\nid: x\n", encoding="utf-8")
    (generated_dir / "generated_index.json").write_text(
        json.dumps(
            {
                "version": 1,
                "items": [
                    {
                        "savepoint_id": "sp_k1",
                        "scenario_file": str(generated_dir / "sp_k1.yaml"),
                        "exported_at": "2026-01-01T00:00:00Z",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    def _fake_run_generated_scenario(
        *, savepoint_id, engine="auto", dry_run=False, timeout_sec=600, max_retries=0
    ):
        time.sleep(0.2)
        return {
            "savepoint_id": savepoint_id,
            "status": "passed",
            "exit_code": 0,
            "summary": "ok",
        }

    monkeypatch.setattr(admin_savepoints, "run_generated_scenario", _fake_run_generated_scenario)
    first = admin_savepoints.start_generated_scenarios_batch_job(only_failed=False, engine="auto")
    try:
        admin_savepoints.start_generated_scenarios_batch_job(only_failed=False, engine="auto")
        assert False, "expected ValueError for running job conflict"
    except ValueError as e:
        assert "已有批量任务运行中" in str(e)
    for _ in range(30):
        final = admin_savepoints.get_generated_scenarios_batch_job(job_id=first["job_id"])
        if final.get("status") == "completed":
            break
        time.sleep(0.05)


def test_run_generated_scenario_savepoint_mutex(monkeypatch, tmp_path):
    test_root = tmp_path / "data_test_simple"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(admin_savepoints, "get_simple_test_base_dir", lambda: test_root)
    monkeypatch.setattr(admin_savepoints, "_project_root", lambda: project_root)
    admin_savepoints._BATCH_JOBS.clear()
    admin_savepoints._RUNNING_SAVEPOINTS.clear()
    admin_savepoints._RUNNING_SAVEPOINTS.add("sp_lock")
    try:
        admin_savepoints.run_generated_scenario(savepoint_id="sp_lock")
        assert False, "expected lock conflict"
    except ValueError as e:
        assert "正在执行中" in str(e)
    finally:
        admin_savepoints._RUNNING_SAVEPOINTS.discard("sp_lock")


def test_batch_job_state_recovery_marks_running_interrupted(monkeypatch, tmp_path):
    test_root = tmp_path / "data_test_simple"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(admin_savepoints, "get_simple_test_base_dir", lambda: test_root)
    monkeypatch.setattr(admin_savepoints, "_project_root", lambda: project_root)
    admin_savepoints._BATCH_JOBS.clear()
    admin_savepoints._RUNNING_SAVEPOINTS.clear()
    admin_savepoints._BATCH_STATE_LOADED = False

    state_file = test_root / "savepoints" / "batch_jobs_state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps(
            {
                "version": 1,
                "jobs": {
                    "job_r1": {
                        "job_id": "job_r1",
                        "status": "running",
                        "created_at": "2026-01-01T00:00:00Z",
                        "started_at": "2026-01-01T00:00:00Z",
                        "finished_at": None,
                        "engine": "auto",
                        "total": 2,
                        "processed": 1,
                        "passed": 1,
                        "failed": 0,
                    }
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    jobs = admin_savepoints.list_batch_jobs(limit=10)
    hit = next((x for x in jobs if x.get("job_id") == "job_r1"), None)
    assert hit is not None
    assert hit.get("status") == "interrupted"
    hist = admin_savepoints.list_batch_job_history(limit=20)
    assert any((x or {}).get("job_id") == "job_r1" and (x or {}).get("status") == "interrupted" for x in hist)


def test_cleanup_batch_job_history(monkeypatch, tmp_path):
    test_root = tmp_path / "data_test_simple"
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(admin_savepoints, "get_simple_test_base_dir", lambda: test_root)
    monkeypatch.setattr(admin_savepoints, "_project_root", lambda: project_root)
    admin_savepoints._BATCH_JOBS.clear()
    admin_savepoints._RUNNING_SAVEPOINTS.clear()
    admin_savepoints._BATCH_STATE_LOADED = False

    hist_file = test_root / "savepoints" / "batch_job_history.jsonl"
    hist_file.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        {"job_id": "j1", "status": "completed", "created_at": "2026-01-01T00:00:00Z"},
        {"job_id": "j2", "status": "completed", "created_at": "2026-01-01T00:00:01Z"},
        {"job_id": "j3", "status": "completed", "created_at": "2026-01-01T00:00:02Z"},
    ]
    hist_file.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n", encoding="utf-8")
    ret = admin_savepoints.cleanup_batch_job_history(keep_latest=2)
    assert ret["removed"] == 1
    assert ret["remaining"] == 2
    got = admin_savepoints.list_batch_job_history(limit=10)
    assert len(got) == 2

