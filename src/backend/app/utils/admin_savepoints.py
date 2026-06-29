"""
Admin Savepoint 管理（仅调试工作区）。

约束：
- 仅允许在 data/test/simple 下操作（SBX/ADM）。
- create 不修改当前 fork 数据：仅复制并裁剪到 savepoints 目录。
- load 会将检查点内容投影回当前调试 report，用于继续真实链路测试。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.utils.report_registry import STEP_IDS, ReportRegistry
from app.utils.simple_activation_manager import (
    ActivationRecord,
    SimpleActivationManager,
    get_effective_simple_root,
    get_simple_test_base_dir,
    is_debug_workspace_record,
)

INDEX_REL_PATH = Path("savepoints") / "index.json"
MIRROR_REL_PATH = Path("test_agent") / "savepoints_registry.json"
REPLAY_LOG_REL_PATH = Path("savepoints") / "replay_logs.jsonl"
GENERATED_INDEX_REL_PATH = Path("test_agent") / "scenarios" / "generated" / "generated_index.json"
JOB_HISTORY_REL_PATH = Path("savepoints") / "batch_job_history.jsonl"
BATCH_JOB_STATE_REL_PATH = Path("savepoints") / "batch_jobs_state.json"
AI_ROLES = {"assistant", "table_widget", "conclusion_card"}
_BATCH_JOB_LOCK = threading.Lock()
_BATCH_JOBS: Dict[str, Dict[str, Any]] = {}
_RUNNING_SAVEPOINTS: set[str] = set()
_BATCH_STATE_LOADED = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _savepoints_root() -> Path:
    root = get_simple_test_base_dir() / "savepoints"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _index_path() -> Path:
    p = get_simple_test_base_dir() / INDEX_REL_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _mirror_path() -> Path:
    p = _project_root() / MIRROR_REL_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _replay_log_path() -> Path:
    p = get_simple_test_base_dir() / REPLAY_LOG_REL_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _generated_index_path() -> Path:
    p = _project_root() / GENERATED_INDEX_REL_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _job_history_path() -> Path:
    p = get_simple_test_base_dir() / JOB_HISTORY_REL_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _batch_job_state_path() -> Path:
    p = get_simple_test_base_dir() / BATCH_JOB_STATE_REL_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_batch_job_state_file() -> Dict[str, Any]:
    p = _batch_job_state_path()
    if not p.is_file():
        return {"version": 1, "jobs": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "jobs": {}}
    if not isinstance(data, dict):
        return {"version": 1, "jobs": {}}
    jobs = data.get("jobs")
    if not isinstance(jobs, dict):
        data["jobs"] = {}
    data.setdefault("version", 1)
    return data


def _save_batch_job_state_file(state_obj: Dict[str, Any]) -> None:
    p = _batch_job_state_path()
    p.write_text(json.dumps(state_obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_index() -> Dict[str, Any]:
    p = _index_path()
    if not p.is_file():
        return {"version": 1, "items": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "items": []}
    if not isinstance(data, dict):
        return {"version": 1, "items": []}
    items = data.get("items")
    if not isinstance(items, list):
        data["items"] = []
    data.setdefault("version", 1)
    return data


def _load_generated_index() -> Dict[str, Any]:
    p = _generated_index_path()
    if not p.is_file():
        return {"version": 1, "items": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "items": []}
    if not isinstance(data, dict):
        return {"version": 1, "items": []}
    items = data.get("items")
    if not isinstance(items, list):
        data["items"] = []
    data.setdefault("version", 1)
    return data


def _save_generated_index(index_obj: Dict[str, Any]) -> None:
    p = _generated_index_path()
    p.write_text(json.dumps(index_obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _save_index(index_obj: Dict[str, Any]) -> None:
    index_path = _index_path()
    index_path.write_text(json.dumps(index_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    # 评审镜像固定同步
    _mirror_path().write_text(json.dumps(index_obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _ensure_unique_display_name(display_name: str, items: List[Dict[str, Any]]) -> None:
    normalized = (display_name or "").strip()
    for item in items:
        if (item.get("display_name") or "").strip() == normalized:
            raise FileExistsError(
                json.dumps(
                    {
                        "display_name": normalized,
                        "savepoint_id": item.get("savepoint_id"),
                        "created_at": item.get("created_at"),
                    },
                    ensure_ascii=False,
                )
            )


def _find_report_for_activation(
    registry: ReportRegistry, code: str, rec: ActivationRecord
) -> Optional[Dict[str, Any]]:
    owner_key = (rec.owner_user_id or rec.owner_email or "").strip()
    report = registry.get_by_activation_user(code, owner_key) if owner_key else None
    if report:
        return report
    for item in registry.list_reports():
        if (item.get("activation_code") or "").strip().upper() == code:
            return item
    return None


def _extract_keywords(content: str) -> List[str]:
    raw = (content or "").strip()
    if not raw:
        return []
    parts = re.split(r"[，。！？；、\s,.;!?]+", raw)
    out: List[str] = []
    for p in parts:
        t = p.strip()
        if len(t) < 2:
            continue
        if t in out:
            continue
        out.append(t[:16])
        if len(out) >= 5:
            break
    return out


def _write_meta(path: Path, meta: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_name(raw: str) -> str:
    s = (raw or "").strip().lower()
    s = re.sub(r"[^a-z0-9_\-\u4e00-\u9fff]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or f"sp_{uuid.uuid4().hex[:8]}"


def _load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8") or "null")
    except (OSError, json.JSONDecodeError):
        return default


def _append_replay_log(entry: Dict[str, Any]) -> None:
    p = _replay_log_path()
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _append_job_history(entry: Dict[str, Any]) -> None:
    p = _job_history_path()
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _persist_batch_jobs_locked() -> None:
    state = {"version": 1, "jobs": _BATCH_JOBS}
    _save_batch_job_state_file(state)


def _ensure_batch_jobs_loaded() -> None:
    global _BATCH_STATE_LOADED
    if _BATCH_STATE_LOADED:
        return
    with _BATCH_JOB_LOCK:
        if _BATCH_STATE_LOADED:
            return
        state = _load_batch_job_state_file()
        raw_jobs = state.get("jobs")
        loaded_jobs = raw_jobs if isinstance(raw_jobs, dict) else {}
        now = _now_iso()
        for jid, job in loaded_jobs.items():
            if not isinstance(job, dict):
                continue
            status = str(job.get("status") or "")
            if status == "running":
                # 服务重启后无法恢复线程，显式标记为 interrupted，供追踪
                job["status"] = "interrupted"
                job["finished_at"] = now
                job["interrupted_reason"] = "service_restarted"
                _append_job_history(
                    {
                        "job_id": jid,
                        "status": "interrupted",
                        "created_at": job.get("created_at"),
                        "started_at": job.get("started_at"),
                        "finished_at": now,
                        "engine": job.get("engine"),
                        "max_retries": job.get("max_retries"),
                        "only_failed": job.get("only_failed"),
                        "total": job.get("total"),
                        "processed": job.get("processed"),
                        "passed": job.get("passed"),
                        "failed": job.get("failed"),
                        "interrupted_reason": "service_restarted",
                    }
                )
            _BATCH_JOBS[str(jid)] = job
        _persist_batch_jobs_locked()
        _BATCH_STATE_LOADED = True


def list_replay_logs(limit: int = 200) -> List[Dict[str, Any]]:
    p = _replay_log_path()
    if not p.is_file():
        return []
    out: List[Dict[str, Any]] = []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
        if len(out) >= max(1, int(limit)):
            break
    return out


def list_generated_scenarios(limit: int = 200) -> List[Dict[str, Any]]:
    idx_obj = _load_generated_index()
    items = [x for x in idx_obj.get("items", []) if isinstance(x, dict)]
    cleaned: List[Dict[str, Any]] = []
    for raw in items:
        item = dict(raw)
        scenario_path = Path(str(item.get("scenario_file") or ""))
        if scenario_path.is_file():
            cleaned.append(item)
    cleaned.sort(key=lambda x: x.get("exported_at") or "", reverse=True)
    return cleaned[: max(1, int(limit))]


def list_batch_job_history(limit: int = 50) -> List[Dict[str, Any]]:
    _ensure_batch_jobs_loaded()
    p = _job_history_path()
    if not p.is_file():
        return []
    out: List[Dict[str, Any]] = []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
        if len(out) >= max(1, int(limit)):
            break
    return out


def cleanup_batch_job_history(
    *, keep_latest: int = 200, older_than_days: Optional[int] = None
) -> Dict[str, Any]:
    _ensure_batch_jobs_loaded()
    if keep_latest < 1 or keep_latest > 5000:
        raise ValueError("keep_latest 必须在 1~5000")
    if older_than_days is not None and (older_than_days < 1 or older_than_days > 3650):
        raise ValueError("older_than_days 必须在 1~3650")

    p = _job_history_path()
    if not p.is_file():
        return {"removed": 0, "remaining": 0}

    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {"removed": 0, "remaining": 0}

    entries: List[Dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            entries.append(obj)

    # 时间倒序
    entries.sort(
        key=lambda x: x.get("finished_at") or x.get("created_at") or "",
        reverse=True,
    )

    now_ts = time.time()
    filtered: List[Dict[str, Any]] = []
    for idx, e in enumerate(entries):
        if idx >= keep_latest:
            continue
        if older_than_days is not None:
            t_raw = str(e.get("finished_at") or e.get("created_at") or "")
            try:
                dt = datetime.fromisoformat(t_raw.replace("Z", "+00:00"))
                if now_ts - dt.timestamp() > older_than_days * 86400:
                    continue
            except Exception:
                pass
        filtered.append(e)

    # 重新按时间正序落盘，便于 append
    filtered.sort(key=lambda x: x.get("finished_at") or x.get("created_at") or "")
    p.write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in filtered) + ("\n" if filtered else ""),
        encoding="utf-8",
    )
    removed = max(0, len(entries) - len(filtered))
    return {"removed": removed, "remaining": len(filtered)}


def list_batch_jobs(limit: int = 50) -> List[Dict[str, Any]]:
    _ensure_batch_jobs_loaded()
    with _BATCH_JOB_LOCK:
        jobs = [dict(v) for v in _BATCH_JOBS.values() if isinstance(v, dict)]
    jobs.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return jobs[: max(1, int(limit))]


def run_generated_scenario(
    *,
    savepoint_id: str,
    engine: str = "auto",
    dry_run: bool = False,
    timeout_sec: int = 600,
    max_retries: int = 0,
) -> Dict[str, Any]:
    spid = (savepoint_id or "").strip()
    if not spid:
        raise ValueError("savepoint_id 不能为空")
    eng = (engine or "auto").strip().lower()
    if eng not in {"auto", "replay", "playwright"}:
        raise ValueError("engine 必须是 auto/replay/playwright")
    if timeout_sec < 5 or timeout_sec > 3600:
        raise ValueError("timeout_sec 必须在 5~3600 秒")
    if max_retries < 0 or max_retries > 3:
        raise ValueError("max_retries 必须在 0~3")

    with _BATCH_JOB_LOCK:
        if spid in _RUNNING_SAVEPOINTS:
            raise ValueError("该 savepoint 正在执行中，请稍后重试")
        _RUNNING_SAVEPOINTS.add(spid)

    try:
        idx_obj = _load_generated_index()
        items = [x for x in idx_obj.get("items", []) if isinstance(x, dict)]
        hit = next((x for x in items if (x.get("savepoint_id") or "") == spid), None)
        if hit is None:
            raise ValueError("generated 场景不存在，请先 Export")

        scenario_raw = str(hit.get("scenario_file") or "").strip()
        if not scenario_raw:
            raise ValueError("generated 场景缺少 scenario_file")
        scenario_path = Path(scenario_raw)
        if not scenario_path.is_absolute():
            scenario_path = _project_root() / scenario_path
        if not scenario_path.is_file():
            raise ValueError(f"scenario 文件不存在: {scenario_path}")

        cmd = [
            sys.executable,
            str(_project_root() / "test_agent" / "l2" / "run_scenario.py"),
            "--scenario",
            str(scenario_path),
            "--engine",
            eng,
        ]
        if dry_run:
            cmd.append("--dry-run")
        cmd_pretty = " ".join(f'"{x}"' if " " in x else x for x in cmd)

        log_dir = _project_root() / "test_agent" / "reports" / "job_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"{spid}_{ts}_{uuid.uuid4().hex[:6]}.log"

        status = "failed"
        run_code = "runner_error"
        last_exit_code = 1
        final_stdout = ""
        final_stderr = ""
        report_file = ""
        attempts = 0
        max_attempts = 1 + max_retries
        with log_file.open("w", encoding="utf-8") as logf:
            logf.write(f"command={cmd_pretty}\n")
            for attempt in range(1, max_attempts + 1):
                attempts = attempt
                logf.write(f"\n===== attempt {attempt}/{max_attempts} =====\n")
                try:
                    proc = subprocess.run(
                        cmd,
                        cwd=str(_project_root()),
                        capture_output=True,
                        text=True,
                        timeout=timeout_sec,
                    )
                    final_stdout = proc.stdout or ""
                    final_stderr = proc.stderr or ""
                    last_exit_code = proc.returncode
                    logf.write("[stdout]\n")
                    logf.write(final_stdout)
                    logf.write("\n[stderr]\n")
                    logf.write(final_stderr)
                    if proc.returncode == 0:
                        status = "passed"
                        run_code = "ok"
                        break
                    status = "failed"
                    run_code = "runner_error"
                except subprocess.TimeoutExpired as e:
                    final_stdout = (e.stdout or "") if isinstance(e.stdout, str) else ""
                    final_stderr = (e.stderr or "") if isinstance(e.stderr, str) else ""
                    last_exit_code = 124
                    status = "failed"
                    run_code = "timeout"
                    logf.write("[timeout]\n")
                    logf.write(f"{type(e).__name__}: {e}\n")
                    if final_stdout:
                        logf.write("[stdout-partial]\n")
                        logf.write(final_stdout)
                    if final_stderr:
                        logf.write("\n[stderr-partial]\n")
                        logf.write(final_stderr)
                if attempt < max_attempts:
                    logf.write("\n[retry] next attempt\n")

        report_match = re.search(r"\[L2\] report=(.+)", final_stdout)
        report_file = report_match.group(1).strip() if report_match else ""
        now = _now_iso()
        summary = (
            f"engine={eng}, status={status}, code={run_code}, exit={last_exit_code}, "
            f"attempts={attempts}, report={report_file or '-'}, dry_run={str(bool(dry_run)).lower()}"
        )

        hit["last_run_at"] = now
        hit["last_run_status"] = status
        hit["last_run_code"] = run_code
        hit["last_run_engine"] = eng
        hit["last_run_exit_code"] = last_exit_code
        hit["last_run_report_file"] = report_file or None
        hit["last_run_summary"] = summary[:500]
        hit["last_run_attempts"] = attempts
        hit["last_run_log_file"] = str(log_file)
        hit["last_run_stdout_tail"] = final_stdout[-3000:] if final_stdout else ""
        hit["last_run_stderr_tail"] = final_stderr[-3000:] if final_stderr else ""
        idx_obj["items"] = sorted(items, key=lambda x: x.get("exported_at") or "", reverse=True)
        _save_generated_index(idx_obj)

        if not dry_run:
            try:
                replay_status = "passed" if status == "passed" else "failed"
                record_savepoint_replay_result(
                    savepoint_id=spid,
                    status=replay_status,
                    summary=summary,
                    command=cmd_pretty,
                )
            except Exception:
                pass

        return {
            "savepoint_id": spid,
            "engine": eng,
            "dry_run": bool(dry_run),
            "command": cmd_pretty,
            "exit_code": last_exit_code,
            "status": status,
            "run_code": run_code,
            "summary": summary,
            "attempts": attempts,
            "report_file": report_file or None,
            "log_file": str(log_file),
            "stdout_tail": final_stdout[-3000:],
            "stderr_tail": final_stderr[-3000:],
            "last_run_at": now,
        }
    finally:
        with _BATCH_JOB_LOCK:
            _RUNNING_SAVEPOINTS.discard(spid)


def run_generated_scenarios_batch(
    *,
    savepoint_ids: Optional[List[str]] = None,
    only_failed: bool = False,
    engine: str = "auto",
    timeout_sec: int = 600,
    max_retries: int = 1,
) -> Dict[str, Any]:
    idx_obj = _load_generated_index()
    items = [x for x in idx_obj.get("items", []) if isinstance(x, dict)]
    selected_ids = [str(x or "").strip() for x in (savepoint_ids or []) if str(x or "").strip()]
    target_ids: List[str]
    if selected_ids:
        target_ids = selected_ids
    else:
        pool = items
        if only_failed:
            pool = [x for x in pool if (x.get("last_run_status") or "") == "failed"]
        target_ids = [
            str(x.get("savepoint_id") or "").strip()
            for x in pool
            if str(x.get("savepoint_id") or "").strip()
        ]

    if not target_ids:
        return {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "items": [],
            "message": "无可执行场景",
        }

    out: List[Dict[str, Any]] = []
    for spid in target_ids:
        try:
            ret = run_generated_scenario(
                savepoint_id=spid,
                engine=engine,
                dry_run=False,
                timeout_sec=timeout_sec,
                max_retries=max_retries,
            )
        except Exception as e:
            ret = {
                "savepoint_id": spid,
                "engine": engine,
                "dry_run": False,
                "command": "",
                "exit_code": 1,
                "status": "failed",
                "summary": f"batch-run exception: {type(e).__name__}: {e}",
                "report_file": None,
                "stdout_tail": "",
                "stderr_tail": "",
                "last_run_at": _now_iso(),
            }
        out.append(ret)

    passed = sum(1 for x in out if str(x.get("status") or "") == "passed")
    failed = len(out) - passed
    return {
        "total": len(out),
        "passed": passed,
        "failed": failed,
        "items": out,
    }


def _resolve_generated_target_ids(
    *, savepoint_ids: Optional[List[str]], only_failed: bool
) -> List[str]:
    idx_obj = _load_generated_index()
    items = [x for x in idx_obj.get("items", []) if isinstance(x, dict)]
    selected_ids = [str(x or "").strip() for x in (savepoint_ids or []) if str(x or "").strip()]
    if selected_ids:
        return selected_ids
    pool = items
    if only_failed:
        pool = [x for x in pool if (x.get("last_run_status") or "") == "failed"]
    return [
        str(x.get("savepoint_id") or "").strip()
        for x in pool
        if str(x.get("savepoint_id") or "").strip()
    ]


def start_generated_scenarios_batch_job(
    *,
    savepoint_ids: Optional[List[str]] = None,
    only_failed: bool = False,
    engine: str = "auto",
    timeout_sec: int = 600,
    max_retries: int = 1,
) -> Dict[str, Any]:
    _ensure_batch_jobs_loaded()
    eng = (engine or "auto").strip().lower()
    if eng not in {"auto", "replay", "playwright"}:
        raise ValueError("engine 必须是 auto/replay/playwright")
    if timeout_sec < 5 or timeout_sec > 3600:
        raise ValueError("timeout_sec 必须在 5~3600 秒")
    if max_retries < 0 or max_retries > 3:
        raise ValueError("max_retries 必须在 0~3")

    target_ids = _resolve_generated_target_ids(savepoint_ids=savepoint_ids, only_failed=only_failed)
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    now = _now_iso()
    job = {
        "job_id": job_id,
        "status": "running",
        "created_at": now,
        "started_at": now,
        "finished_at": None,
        "engine": eng,
        "timeout_sec": timeout_sec,
        "max_retries": max_retries,
        "only_failed": bool(only_failed),
        "total": len(target_ids),
        "processed": 0,
        "passed": 0,
        "failed": 0,
        "cancel_requested": False,
        "items": [],
        "target_ids": target_ids,
    }
    with _BATCH_JOB_LOCK:
        running = next(
            (x for x in _BATCH_JOBS.values() if (x.get("status") or "") == "running"), None
        )
        if running:
            raise ValueError(f"已有批量任务运行中: {running.get('job_id')}")
        _BATCH_JOBS[job_id] = job
        _persist_batch_jobs_locked()

    def _runner() -> None:
        final_status = "completed"
        for spid in target_ids:
            with _BATCH_JOB_LOCK:
                cur = _BATCH_JOBS.get(job_id)
                if not cur:
                    return
                if bool(cur.get("cancel_requested")):
                    final_status = "cancelled"
                    break
            try:
                ret = run_generated_scenario(
                    savepoint_id=spid,
                    engine=eng,
                    dry_run=False,
                    timeout_sec=timeout_sec,
                    max_retries=max_retries,
                )
            except Exception as e:
                ret = {
                    "savepoint_id": spid,
                    "status": "failed",
                    "exit_code": 1,
                    "run_code": "batch_exception",
                    "summary": f"batch-async exception: {type(e).__name__}: {e}",
                    "report_file": None,
                }
            with _BATCH_JOB_LOCK:
                cur = _BATCH_JOBS.get(job_id)
                if not cur:
                    return
                cur_items = cur.get("items") or []
                cur_items.append(ret)
                cur["items"] = cur_items
                cur["processed"] = int(cur.get("processed") or 0) + 1
                if str(ret.get("status") or "") == "passed":
                    cur["passed"] = int(cur.get("passed") or 0) + 1
                else:
                    cur["failed"] = int(cur.get("failed") or 0) + 1
                _BATCH_JOBS[job_id] = cur
                _persist_batch_jobs_locked()
        with _BATCH_JOB_LOCK:
            cur = _BATCH_JOBS.get(job_id)
            if not cur:
                return
            cur["status"] = final_status
            cur["finished_at"] = _now_iso()
            _BATCH_JOBS[job_id] = cur
            _persist_batch_jobs_locked()
            _append_job_history(
                {
                    "job_id": cur.get("job_id"),
                    "status": cur.get("status"),
                    "created_at": cur.get("created_at"),
                    "started_at": cur.get("started_at"),
                    "finished_at": cur.get("finished_at"),
                    "engine": cur.get("engine"),
                    "max_retries": cur.get("max_retries"),
                    "only_failed": cur.get("only_failed"),
                    "total": cur.get("total"),
                    "processed": cur.get("processed"),
                    "passed": cur.get("passed"),
                    "failed": cur.get("failed"),
                }
            )

    t = threading.Thread(target=_runner, daemon=True, name=f"savepoint-batch-{job_id}")
    t.start()

    return {
        "job_id": job_id,
        "status": "running",
        "total": len(target_ids),
        "processed": 0,
        "passed": 0,
        "failed": 0,
        "max_retries": max_retries,
    }


def get_generated_scenarios_batch_job(*, job_id: str) -> Dict[str, Any]:
    _ensure_batch_jobs_loaded()
    jid = (job_id or "").strip()
    if not jid:
        raise ValueError("job_id 不能为空")
    with _BATCH_JOB_LOCK:
        job = _BATCH_JOBS.get(jid)
        if not job:
            raise ValueError("任务不存在")
        # 避免无限增长：已完成且超过 24h 自动清理旧任务
        now_ts = time.time()
        stale: List[str] = []
        for k, v in _BATCH_JOBS.items():
            if (v.get("status") or "") != "completed":
                continue
            finished = str(v.get("finished_at") or "")
            try:
                dt = datetime.fromisoformat(finished.replace("Z", "+00:00"))
            except Exception:
                continue
            if now_ts - dt.timestamp() > 24 * 3600:
                stale.append(k)
        for k in stale:
            _BATCH_JOBS.pop(k, None)
        if stale:
            _persist_batch_jobs_locked()
        return dict(job)


def cancel_generated_scenarios_batch_job(*, job_id: str) -> Dict[str, Any]:
    _ensure_batch_jobs_loaded()
    jid = (job_id or "").strip()
    if not jid:
        raise ValueError("job_id 不能为空")
    with _BATCH_JOB_LOCK:
        job = _BATCH_JOBS.get(jid)
        if not job:
            raise ValueError("任务不存在")
        if (job.get("status") or "") != "running":
            return {"job_id": jid, "cancel_requested": False, "status": job.get("status")}
        job["cancel_requested"] = True
        _BATCH_JOBS[jid] = job
        _persist_batch_jobs_locked()
        return {"job_id": jid, "cancel_requested": True, "status": job.get("status")}


def _build_replay_command(*, seed_report_dir: str, phase: str, thread_id: str, message: str) -> str:
    replay_msg = (message or "请继续").replace("\n", " ").replace('"', '\\"')
    replay_phase = (phase or "values").strip()
    replay_thread = (thread_id or "").strip()
    return (
        "python src/backend/scripts/replay_simple_chat.py "
        f'--seed-report-dir "{seed_report_dir}" '
        f"--phase {replay_phase} "
        f'--thread-id "{replay_thread}" '
        f'--message "{replay_msg}"'
    )


def _build_playwright_command(*, scenario_file: str) -> str:
    return (
        "python test_agent/l2/run_scenario.py "
        f'--scenario "{scenario_file}" '
        "--engine playwright"
    )


def _trim_report_snapshot(
    report_dir: Path,
    *,
    phase: str,
    thread_id: str,
    cut_idx: int,
) -> None:
    now = _now_iso()
    target_thread_file = report_dir / f"{phase}__{thread_id}.json"
    if not target_thread_file.is_file():
        raise ValueError(f"检查点目标线程文件不存在: {target_thread_file.name}")

    # 1) 截断目标线程
    conv = json.loads(target_thread_file.read_text(encoding="utf-8") or "{}")
    msgs = conv.get("messages") or []
    conv["messages"] = msgs[:cut_idx]
    meta = conv.setdefault("metadata", {})
    meta["updated_at"] = now
    meta["total_messages"] = len(conv["messages"])
    target_thread_file.write_text(json.dumps(conv, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2) 清理后续 phase 全量状态
    record_file = report_dir / "record.json"
    record = json.loads(record_file.read_text(encoding="utf-8") or "{}")
    steps = record.get("steps") or {}
    phase_idx = STEP_IDS.index(phase)
    for sid in STEP_IDS[phase_idx + 1 :]:
        # 删除后续 phase 的会话文件
        for f in report_dir.glob(f"{sid}__*.json"):
            f.unlink(missing_ok=True)
        step = steps.get(sid) or {}
        step["session_ids"] = []
        step["selected_session_id"] = None
        step["locked"] = False
        step["updated_at"] = now
        step.pop("anchor_summary", None)
        step.pop("anchor_updated_at", None)
        steps[sid] = step

    record["steps"] = steps
    record["updated_at"] = now
    # 后续被清理，统一重置可疑终态标记
    record["final_conclusion"] = None
    record_file.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    # 3) 若不是 rumination 起点，移除 rumination_progress，避免残留
    if phase != "rumination":
        prog = report_dir / "rumination_progress.json"
        if prog.is_file():
            prog.unlink(missing_ok=True)


def create_savepoint(
    *,
    activation_code: str,
    phase: str,
    thread_id: str,
    target_message_index: int,
    display_name: str,
    created_by: Dict[str, Any],
    expected_hint: Optional[str] = None,
    expected_keywords: Optional[List[str]] = None,
) -> Dict[str, Any]:
    code = (activation_code or "").strip().upper()
    if not code:
        raise ValueError("activation_code 不能为空")
    phase_n = ReportRegistry.normalize_step_id(phase)
    if phase_n not in STEP_IDS:
        raise ValueError("phase 无效")
    tid = (thread_id or "").strip()
    if not tid:
        raise ValueError("thread_id 不能为空")
    name = (display_name or "").strip()
    if not name:
        raise ValueError("display_name 不能为空")
    if target_message_index < 0:
        raise ValueError("target_message_index 必须 >= 0")

    mgr = SimpleActivationManager(base_dir=str(get_simple_test_base_dir()))
    rec = mgr.get_activation(code)
    if rec is None:
        raise ValueError("调试激活码不存在")
    if not is_debug_workspace_record(rec):
        raise ValueError("仅支持调试工作区激活码创建 savepoint")

    root = get_effective_simple_root(rec)
    registry = ReportRegistry(base_dir=str(root))
    report = _find_report_for_activation(registry, code, rec)
    if not report:
        raise ValueError("未找到对应报告")
    report_id = (report.get("report_id") or "").strip()
    if not report_id:
        raise ValueError("报告缺少 report_id")

    src_report_dir = root / "reports" / report_id
    src_thread_file = src_report_dir / f"{phase_n}__{tid}.json"
    if not src_thread_file.is_file():
        raise ValueError("目标线程不存在")

    conv = json.loads(src_thread_file.read_text(encoding="utf-8") or "{}")
    messages = conv.get("messages") or []
    if target_message_index >= len(messages):
        raise ValueError("target_message_index 超出范围")
    target_msg = messages[target_message_index] or {}
    if target_msg.get("role") not in AI_ROLES:
        raise ValueError("目标消息必须是 AI 输出")

    cut_idx = target_message_index
    if cut_idx > 0 and (messages[cut_idx - 1] or {}).get("role") == "user":
        cut_idx = cut_idx - 1

    idx_obj = _load_index()
    items = [x for x in idx_obj.get("items", []) if isinstance(x, dict)]
    _ensure_unique_display_name(name, items)

    savepoint_id = f"sp_{uuid.uuid4().hex[:12]}"
    savepoint_dir = _savepoints_root() / savepoint_id
    report_snapshot_dir = savepoint_dir / "report"
    shutil.copytree(src_report_dir, report_snapshot_dir)
    _trim_report_snapshot(report_snapshot_dir, phase=phase_n, thread_id=tid, cut_idx=cut_idx)

    content = str(target_msg.get("content") or "")
    auto_keywords = _extract_keywords(content)
    final_keywords = [
        str(x).strip() for x in (expected_keywords or auto_keywords) if str(x).strip()
    ]
    final_hint = (expected_hint or content[:120]).strip()

    created_at = _now_iso()
    meta = {
        "savepoint_id": savepoint_id,
        "display_name": name,
        "created_at": created_at,
        "created_by": {
            "user_id": (created_by or {}).get("user_id"),
            "email": (created_by or {}).get("email"),
        },
        "source_activation_code": code,
        "source_report_id": report_id,
        "phase": phase_n,
        "thread_id": tid,
        "target_message_index": target_message_index,
        "rewind_cut_index": cut_idx,
        "rewind_mode": "global_rewind",
        "expected_hint": final_hint,
        "expected_keywords": final_keywords,
        "report_snapshot_path": str(report_snapshot_dir),
    }
    _write_meta(savepoint_dir / "meta.json", meta)

    items.append(
        {
            "savepoint_id": savepoint_id,
            "display_name": name,
            "created_at": created_at,
            "created_by_user_id": (created_by or {}).get("user_id"),
            "source_activation_code": code,
            "source_report_id": report_id,
            "phase": phase_n,
            "thread_id": tid,
            "rewind_mode": "global_rewind",
            "fixture_path": str(report_snapshot_dir),
            "meta_path": str(savepoint_dir / "meta.json"),
            "last_replay_status": None,
            "last_replay_at": None,
            "last_replay_summary": None,
        }
    )
    idx_obj["items"] = sorted(items, key=lambda x: x.get("created_at") or "", reverse=True)
    _save_index(idx_obj)
    return meta


def list_savepoints() -> List[Dict[str, Any]]:
    idx_obj = _load_index()
    items = []
    for raw in idx_obj.get("items", []):
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        meta_path = Path(str(item.get("meta_path") or ""))
        meta = _load_json(meta_path, {}) if meta_path.is_file() else {}
        if isinstance(meta, dict):
            expected_hint = str(meta.get("expected_hint") or "").strip()
            if expected_hint:
                item["expected_hint"] = expected_hint
            item["replay_command"] = _build_replay_command(
                seed_report_dir=str(item.get("fixture_path") or ""),
                phase=str(item.get("phase") or "values"),
                thread_id=str(item.get("thread_id") or ""),
                message=expected_hint or "请继续",
            )
        items.append(item)
    items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return items


def record_savepoint_replay_result(
    *,
    savepoint_id: str,
    status: str,
    summary: str,
    command: Optional[str] = None,
) -> Dict[str, Any]:
    spid = (savepoint_id or "").strip()
    st = (status or "").strip().lower()
    if not spid:
        raise ValueError("savepoint_id 不能为空")
    if st not in {"passed", "failed"}:
        raise ValueError("status 必须是 passed 或 failed")

    idx_obj = _load_index()
    items = [x for x in idx_obj.get("items", []) if isinstance(x, dict)]
    hit = next((x for x in items if (x.get("savepoint_id") or "") == spid), None)
    if hit is None:
        raise ValueError("savepoint 不存在")
    hit["last_replay_status"] = st
    hit["last_replay_at"] = _now_iso()
    hit["last_replay_summary"] = (summary or "").strip()[:500]
    if command:
        hit["last_replay_command"] = command
    idx_obj["items"] = items
    _save_index(idx_obj)
    _append_replay_log(
        {
            "at": hit.get("last_replay_at"),
            "savepoint_id": spid,
            "display_name": hit.get("display_name"),
            "status": st,
            "summary": hit.get("last_replay_summary"),
            "command": command or "",
            "source_activation_code": hit.get("source_activation_code"),
            "phase": hit.get("phase"),
            "thread_id": hit.get("thread_id"),
        }
    )
    return {
        "savepoint_id": spid,
        "last_replay_status": hit.get("last_replay_status"),
        "last_replay_at": hit.get("last_replay_at"),
        "last_replay_summary": hit.get("last_replay_summary"),
    }


def delete_savepoint(*, savepoint_id: str) -> Dict[str, Any]:
    spid = (savepoint_id or "").strip()
    if not spid:
        raise ValueError("savepoint_id 不能为空")
    idx_obj = _load_index()
    items = [x for x in idx_obj.get("items", []) if isinstance(x, dict)]
    hit = next((x for x in items if (x.get("savepoint_id") or "") == spid), None)
    if hit is None:
        raise ValueError("savepoint 不存在")

    meta_path = Path(str(hit.get("meta_path") or ""))
    sp_dir = meta_path.parent if meta_path.name == "meta.json" else (_savepoints_root() / spid)
    if sp_dir.is_dir():
        shutil.rmtree(sp_dir, ignore_errors=True)

    idx_obj["items"] = [x for x in items if (x.get("savepoint_id") or "") != spid]
    _save_index(idx_obj)
    return {"deleted": True, "savepoint_id": spid}


def export_savepoint_assets(*, savepoint_id: str) -> Dict[str, Any]:
    spid = (savepoint_id or "").strip()
    if not spid:
        raise ValueError("savepoint_id 不能为空")

    idx_obj = _load_index()
    items = [x for x in idx_obj.get("items", []) if isinstance(x, dict)]
    hit = next((x for x in items if (x.get("savepoint_id") or "") == spid), None)
    if hit is None:
        raise ValueError("savepoint 不存在")

    meta_path = Path(str(hit.get("meta_path") or ""))
    if not meta_path.is_file():
        raise ValueError("savepoint meta 不存在")
    meta = _load_json(meta_path, {})
    if not isinstance(meta, dict):
        raise ValueError("savepoint meta 无效")

    snapshot_dir = Path(str(meta.get("report_snapshot_path") or ""))
    if not snapshot_dir.is_dir():
        raise ValueError("savepoint snapshot 不存在")

    output_name = _safe_name(f"{hit.get('display_name')}_{spid}")
    fixture_root = _project_root() / "test" / "backend" / "fixtures" / "simple_chat_reports"
    fixture_root.mkdir(parents=True, exist_ok=True)
    target_fixture_dir = fixture_root / output_name
    if target_fixture_dir.exists():
        raise ValueError("导出失败：目标 fixture 已存在，请先重命名 savepoint 再导出")
    shutil.copytree(snapshot_dir, target_fixture_dir)

    # 导出 case 到 batch_savepoints_general.json
    cases_file = (
        _project_root()
        / "test"
        / "backend"
        / "fixtures"
        / "simple_chat_cases"
        / "batch_savepoints_general.json"
    )
    cases_obj = _load_json(
        cases_file, {"schema_version": 1, "description": "savepoints", "cases": []}
    )
    if not isinstance(cases_obj, dict):
        cases_obj = {"schema_version": 1, "description": "savepoints", "cases": []}
    cases = cases_obj.get("cases")
    if not isinstance(cases, list):
        cases = []
    case_name = f"savepoint_{spid}"
    if any(str((x or {}).get("name") or "") == case_name for x in cases if isinstance(x, dict)):
        raise ValueError("导出失败：case 已存在，请删除旧 case 或换 savepoint")
    cases.append(
        {
            "name": case_name,
            "start_state_code": "",
            "end_state_code": "",
            "seed_fixture": {
                "report_dir": f"test/backend/fixtures/simple_chat_reports/{output_name}",
                "ttl_minutes": 180,
            },
            "phase": str(meta.get("phase") or "values"),
            "thread_id": str(meta.get("thread_id") or ""),
            "message": str(meta.get("expected_hint") or "请继续"),
        }
    )
    cases_obj["cases"] = cases
    cases_file.parent.mkdir(parents=True, exist_ok=True)
    cases_file.write_text(json.dumps(cases_obj, ensure_ascii=False, indent=2), encoding="utf-8")

    # 导出 scenario 到 test_agent/scenarios/generated（默认 Playwright）
    scenario_dir = _project_root() / "test_agent" / "scenarios" / "generated"
    scenario_dir.mkdir(parents=True, exist_ok=True)
    scenario_file = scenario_dir / f"{spid}.yaml"
    expected_hint = str(meta.get("expected_hint") or "请继续")
    expected_hint_escaped = expected_hint.replace('"', '\\"')
    expected_keywords = json.dumps(meta.get("expected_keywords") or [], ensure_ascii=False)
    scenario_yaml = (
        f"schema_version: 1\n"
        f"id: {spid}\n"
        f"title: {hit.get('display_name')}\n"
        f"primary_level: L2\n"
        f"support_levels: [L3]\n"
        f"engine: playwright\n"
        f"data:\n"
        f"  base_url: http://127.0.0.1:3000\n"
        f"  backend_url: http://127.0.0.1:8000\n"
        f"  activation_code: \"{hit.get('source_activation_code')}\"\n"
        f'  savepoint_id: "{spid}"\n'
        f"  phase: {meta.get('phase')}\n"
        f"  thread_id: {meta.get('thread_id')}\n"
        f"steps:\n"
        f"  - action: goto\n"
        f"    url: /explore/chat/{meta.get('phase')}\n"
        f"  - action: wait_ms\n"
        f"    ms: 1200\n"
        f"  - action: chat_send\n"
        f'    text: "{expected_hint_escaped}"\n'
        f"  - action: wait_for_ai\n"
        f"    delta: 1\n"
        f"  - action: screenshot\n"
        f"    name: after_chat_send.png\n"
        f"assertions:\n"
        f'  expected_hint: "{expected_hint_escaped}"\n'
        f"  expected_keywords: {expected_keywords}\n"
        f'  no_leak_tags: ["[STATE_JSON]", "[ROW_STATE_JSON]"]\n'
        f"  metadata_checks:\n"
        f"    phase: {meta.get('phase')}\n"
        f"    thread_id: {meta.get('thread_id')}\n"
    )
    scenario_file.write_text(scenario_yaml, encoding="utf-8")

    try:
        fixture_rel = str(target_fixture_dir.relative_to(_project_root()))
    except ValueError:
        fixture_rel = str(target_fixture_dir)
    replay_cmd = _build_replay_command(
        seed_report_dir=fixture_rel,
        phase=str(meta.get("phase") or "values"),
        thread_id=str(meta.get("thread_id") or ""),
        message=expected_hint,
    )
    replay_cmd = f'{replay_cmd} --savepoint-id "{spid}"'
    try:
        scenario_rel = str(scenario_file.relative_to(_project_root()))
    except ValueError:
        scenario_rel = str(scenario_file)
    playwright_cmd = _build_playwright_command(scenario_file=scenario_rel)

    exported_at = _now_iso()
    generated_idx = _load_generated_index()
    generated_items = [x for x in generated_idx.get("items", []) if isinstance(x, dict)]
    generated_items = [x for x in generated_items if (x.get("savepoint_id") or "") != spid]
    generated_items.append(
        {
            "savepoint_id": spid,
            "display_name": str(hit.get("display_name") or ""),
            "exported_at": exported_at,
            "phase": str(meta.get("phase") or ""),
            "thread_id": str(meta.get("thread_id") or ""),
            "source_activation_code": str(hit.get("source_activation_code") or ""),
            "scenario_file": str(scenario_file),
            "playwright_scenario_file": str(scenario_file),
            "playwright_command": playwright_cmd,
            "replay_command": replay_cmd,
            "fixture_report_dir": fixture_rel,
        }
    )
    generated_idx["items"] = sorted(
        generated_items, key=lambda x: x.get("exported_at") or "", reverse=True
    )
    _save_generated_index(generated_idx)

    return {
        "savepoint_id": spid,
        "exported_at": exported_at,
        "fixture_dir": str(target_fixture_dir),
        "fixture_report_dir": fixture_rel,
        "cases_file": str(cases_file),
        "scenario_file": str(scenario_file),
        "playwright_scenario_file": str(scenario_file),
        "playwright_command": playwright_cmd,
        "replay_command": replay_cmd,
    }


def load_savepoint(*, activation_code: str, savepoint_id: str) -> Dict[str, Any]:
    code = (activation_code or "").strip().upper()
    spid = (savepoint_id or "").strip()
    if not code or not spid:
        raise ValueError("activation_code/savepoint_id 不能为空")

    mgr = SimpleActivationManager(base_dir=str(get_simple_test_base_dir()))
    rec = mgr.get_activation(code)
    if rec is None:
        raise ValueError("调试激活码不存在")
    if not is_debug_workspace_record(rec):
        raise ValueError("仅支持调试工作区激活码 load savepoint")

    idx_obj = _load_index()
    items = [x for x in idx_obj.get("items", []) if isinstance(x, dict)]
    hit = next((x for x in items if (x.get("savepoint_id") or "") == spid), None)
    if hit is None:
        raise ValueError("savepoint 不存在")
    if (hit.get("source_activation_code") or "").strip().upper() != code:
        raise ValueError("savepoint 仅允许加载回原调试激活码")

    meta_path = Path(str(hit.get("meta_path") or ""))
    if not meta_path.is_file():
        raise ValueError("savepoint 元数据缺失")
    meta = json.loads(meta_path.read_text(encoding="utf-8") or "{}")
    snapshot_dir = Path(str(meta.get("report_snapshot_path") or ""))
    if not snapshot_dir.is_dir():
        raise ValueError("savepoint 快照目录缺失")

    root = get_effective_simple_root(rec)
    report_id = str(meta.get("source_report_id") or "").strip()
    if not report_id:
        raise ValueError("savepoint 缺少 source_report_id")
    target_report_dir = root / "reports" / report_id
    if target_report_dir.exists():
        shutil.rmtree(target_report_dir, ignore_errors=True)
    shutil.copytree(snapshot_dir, target_report_dir)

    # 保持激活码 report 索引一致
    rec.report_id = report_id
    rec.report_index_updated_at = _now_iso()
    mgr.put_activation(rec)

    return {
        "loaded": True,
        "savepoint_id": spid,
        "activation_code": code,
        "phase": meta.get("phase"),
        "thread_id": meta.get("thread_id"),
        "report_id": report_id,
    }
