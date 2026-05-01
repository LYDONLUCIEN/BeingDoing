#!/usr/bin/env python3
"""
存档点 / 测试数据批量生成工具。

两种模式：
1) template — 从内置或已有 fixture 模板克隆，可选 ID 重映射，写入 test/backend/fixtures/simple_chat_reports/<name>/。
2) snapshot — 从运行中的 data/simple（或任意 --simple-root）拷贝指定 report_id 目录，可选重映射 UUID，生成 manifest。

用法示例：
  # 列出内置模板
  python src/backend/scripts/generate_simple_chat_savepoints.py template --list

  # 从模板克隆到新目录（dry-run）
  python src/backend/scripts/generate_simple_chat_savepoints.py template \\
    --template mock_values_pending --output-name my_values_fork --dry-run

  # 应用：写入 fixtures 并生成 manifest
  python src/backend/scripts/generate_simple_chat_savepoints.py template \\
    --template mock_values_pending --output-name my_values_fork --apply

  # 从真实数据快照（默认重映射 report_id 与对话 thread_id）
  python src/backend/scripts/generate_simple_chat_savepoints.py snapshot \\
    --simple-root data/simple --report-id <uuid> --output-name prod_snap_001 --apply

说明：
- 激活码仍由 replay / pytest seed 时创建并写回 record.activation_code；模板里保留 MOCKPLACEHOLDER。
- ID 重映射规则：report_id、各 phase__thread 文件名中的 thread、JSON 内 report_id / category / messages[].thread_id。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PHASE_THREAD_FILE = re.compile(r"^([a-z]+)__(.+)\.json$", re.I)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2].parent


def _fixtures_reports_root() -> Path:
    return _project_root() / "test" / "backend" / "fixtures" / "simple_chat_reports"


def _builtin_templates() -> Dict[str, Path]:
    root = _fixtures_reports_root()
    return {
        "mock_values_pending": root / "mock_values_pending",
        "mock_strengths_dialogue": root / "mock_strengths_dialogue",
        "mock_rumination_opening": root / "mock_rumination_opening",
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _replace_thread_in_obj(obj: Any, old_tid: str, new_tid: str) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in ("thread_id", "selected_session_id") and isinstance(v, str) and v == old_tid:
                out[k] = new_tid
            elif k == "session_ids" and isinstance(v, list):
                out[k] = [new_tid if x == old_tid else x for x in v]
            elif k == "category" and isinstance(v, str) and old_tid in v:
                out[k] = v.replace(old_tid, new_tid, 1)
            else:
                out[k] = _replace_thread_in_obj(v, old_tid, new_tid)
        return out
    if isinstance(obj, list):
        return [_replace_thread_in_obj(x, old_tid, new_tid) for x in obj]
    if isinstance(obj, str) and obj == old_tid:
        return new_tid
    return obj


def _collect_thread_ids_from_steps(record: Dict[str, Any]) -> List[Tuple[str, str]]:
    """(phase, thread_id) 来自 steps.*.session_ids / selected."""
    out: List[Tuple[str, str]] = []
    steps = record.get("steps") or {}
    if not isinstance(steps, dict):
        return out
    for phase, ent in steps.items():
        if not isinstance(ent, dict):
            continue
        for tid in ent.get("session_ids") or []:
            if isinstance(tid, str) and tid.strip():
                out.append((phase, tid.strip()))
        sel = ent.get("selected_session_id")
        if isinstance(sel, str) and sel.strip():
            out.append((phase, sel.strip()))
    # 去重保序
    seen = set()
    uniq: List[Tuple[str, str]] = []
    for p, t in out:
        key = (p, t)
        if key in seen:
            continue
        seen.add(key)
        uniq.append((p, t))
    return uniq


def _load_cases(cases_path: Path) -> Dict[str, Any]:
    if not cases_path.exists():
        return {"schema_version": 1, "description": "auto-generated savepoint cases", "cases": []}
    raw = json.loads(cases_path.read_text(encoding="utf-8") or "{}")
    if isinstance(raw, dict) and isinstance(raw.get("cases"), list):
        return raw
    if isinstance(raw, list):
        return {"schema_version": 1, "description": "auto-generated savepoint cases", "cases": raw}
    raise ValueError(f"invalid cases json: {cases_path}")


def _save_cases(cases_path: Path, payload: Dict[str, Any]) -> None:
    cases_path.parent.mkdir(parents=True, exist_ok=True)
    cases_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _remap_dir_in_place(dst_dir: Path) -> Dict[str, Any]:
    """在已存在的 report 目录上重映射 report_id 与各 phase thread_id，并写 savepoint_manifest。"""
    record_path = dst_dir / "record.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    old_report_id = str(record.get("report_id") or "").strip()
    if not old_report_id:
        raise ValueError("record.json 缺少 report_id")
    new_report_id = str(uuid.uuid4())
    record["report_id"] = new_report_id
    record["activation_code"] = "MOCKPLACEHOLDER"
    record["updated_at"] = _now_iso()

    old_threads = _collect_thread_ids_from_steps(record)
    thread_map: Dict[str, str] = {}
    for _phase, tid in old_threads:
        if tid not in thread_map:
            thread_map[tid] = f"t_{uuid.uuid4().hex[:12]}"

    rec_data = record
    for old_tid, new_tid in thread_map.items():
        rec_data = _replace_thread_in_obj(rec_data, old_tid, new_tid)
    record_path.write_text(json.dumps(rec_data, ensure_ascii=False, indent=2), encoding="utf-8")

    for p in list(dst_dir.iterdir()):
        if not p.is_file():
            continue
        m = PHASE_THREAD_FILE.match(p.name)
        if not m:
            continue
        phase, old_tid = m.group(1), m.group(2)
        new_tid = thread_map.get(old_tid, old_tid)
        new_name = f"{phase}__{new_tid}.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        data["report_id"] = new_report_id
        if isinstance(data.get("category"), str):
            data["category"] = f"{phase}__{new_tid}"
        if old_tid in thread_map:
            data = _replace_thread_in_obj(data, old_tid, new_tid)
        if "session_id" in data and str(data["session_id"]) == old_report_id:
            data["session_id"] = new_report_id
        dst_file = dst_dir / new_name
        dst_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        if new_name != p.name:
            p.unlink(missing_ok=True)

    prog = dst_dir / "rumination_progress.json"
    if prog.is_file():
        pr = json.loads(prog.read_text(encoding="utf-8") or "{}")
        blob = json.dumps(pr, ensure_ascii=False)
        blob = blob.replace(old_report_id, new_report_id)
        pr = json.loads(blob)
        for old_tid, new_tid in thread_map.items():
            pr = _replace_thread_in_obj(pr, old_tid, new_tid)
        prog.write_text(json.dumps(pr, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "old_report_id": old_report_id,
        "new_report_id": new_report_id,
        "thread_map": thread_map,
        "dst": str(dst_dir),
    }


def _remap_fixture_tree(src_dir: Path, dst_dir: Path) -> Dict[str, Any]:
    """将 src 复制到 dst 并重映射 ID。"""
    if dst_dir.exists():
        raise FileExistsError(f"目标已存在: {dst_dir}")
    shutil.copytree(src_dir, dst_dir)
    return _remap_dir_in_place(dst_dir)


def _build_case_from_fixture(
    *,
    output_name: str,
    phase: str,
    thread_id: str,
    message: str,
    mock_stream: str,
    start_state_code: str,
    end_state_code: str,
    case_name: str,
) -> Dict[str, Any]:
    return {
        "name": case_name,
        "start_state_code": start_state_code or "",
        "end_state_code": end_state_code or "",
        "seed_fixture": {
            "report_dir": f"test/backend/fixtures/simple_chat_reports/{output_name}",
            "ttl_minutes": 180,
        },
        "phase": phase,
        "thread_id": thread_id,
        "message": message or "（在此填写触发下一步的用户输入）",
        "mock": {"stream_reply": mock_stream} if mock_stream else {},
    }


def cmd_template(args: argparse.Namespace) -> None:
    templates = _builtin_templates()
    if args.list:
        for k, p in templates.items():
            print(f"  {k}\t{p}")
        return
    name = (args.template or "").strip()
    if name not in templates:
        raise SystemExit(f"未知模板: {name!r}；使用 --list")
    src = templates[name]
    if not src.is_dir():
        raise SystemExit(f"模板目录不存在: {src}")
    out_name = (args.output_name or "").strip() or f"gen_{name}_{uuid.uuid4().hex[:8]}"
    dst = _fixtures_reports_root() / out_name
    manifest: Dict[str, Any] = {
        "mode": "template",
        "source_template": name,
        "output_name": out_name,
        "created_at": _now_iso(),
    }
    if args.dry_run:
        print(f"[dry-run] 将复制 {src} -> {dst} 并重映射 ID")
        manifest["dry_run"] = True
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return
    info = _remap_fixture_tree(src, dst)
    manifest.update(info)
    man_path = dst / "savepoint_manifest.json"
    man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def cmd_snapshot(args: argparse.Namespace) -> None:
    root = (
        Path(args.simple_root).expanduser().resolve()
        if args.simple_root
        else _project_root() / "data" / "simple"
    )
    reports = root / "reports"
    rid = (args.report_id or "").strip()
    if not rid:
        raise SystemExit("--report-id 必填")
    src = reports / rid
    if not src.is_dir():
        raise SystemExit(f"report 目录不存在: {src}")
    out_name = (args.output_name or "").strip() or f"snap_{rid[:8]}_{uuid.uuid4().hex[:6]}"
    dst = _fixtures_reports_root() / out_name
    if args.dry_run:
        print(f"[dry-run] 将复制 {src} -> {dst} remap_ids={args.remap_ids}")
        return
    if dst.exists():
        raise FileExistsError(f"目标已存在: {dst}")
    shutil.copytree(src, dst)
    if args.remap_ids:
        info = _remap_dir_in_place(dst)
        manifest: Dict[str, Any] = {
            "mode": "snapshot",
            "source_report_id": rid,
            "simple_root": str(root),
            "created_at": _now_iso(),
            "remap_ids": True,
            **info,
        }
    else:
        rec_path = dst / "record.json"
        if rec_path.is_file():
            rec = json.loads(rec_path.read_text(encoding="utf-8") or "{}")
            rec["activation_code"] = "MOCKPLACEHOLDER"
            rec_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest = {
            "mode": "snapshot",
            "source_report_id": rid,
            "simple_root": str(root),
            "dst": str(dst),
            "remap_ids": False,
            "created_at": _now_iso(),
        }
    manifest_path = dst / "savepoint_manifest.json"
    if args.create_case:
        record = json.loads((dst / "record.json").read_text(encoding="utf-8") or "{}")
        phase = (args.phase or "values").strip()
        thread_id = (args.thread_id or "").strip()
        if not thread_id:
            step_ent = ((record.get("steps") or {}).get(phase)) or {}
            if isinstance(step_ent, dict):
                thread_id = (step_ent.get("selected_session_id") or "").strip()
        if not thread_id:
            for step in (record.get("steps") or {}).values():
                if isinstance(step, dict):
                    thread_id = (step.get("selected_session_id") or "").strip()
                    if thread_id:
                        break
        auto_name = (args.case_name or "").strip() or f"savepoint_{out_name}"
        case_obj = _build_case_from_fixture(
            output_name=out_name,
            phase=phase,
            thread_id=thread_id,
            message=str(args.message or ""),
            mock_stream=str(args.mock_stream or ""),
            start_state_code=str(args.start_state_code or ""),
            end_state_code=str(args.end_state_code or ""),
            case_name=auto_name,
        )
        cases_path = (
            Path(args.cases_file).expanduser().resolve()
            if args.cases_file
            else _project_root() / "test" / "backend" / "fixtures" / "simple_chat_cases" / "batch_savepoints_general.json"
        )
        payload = _load_cases(cases_path)
        cases = [x for x in payload.get("cases", []) if isinstance(x, dict)]
        if args.replace_case:
            cases = [x for x in cases if str(x.get("name") or "") != auto_name]
        elif any(str(x.get("name") or "") == auto_name for x in cases):
            raise ValueError(f"case name already exists: {auto_name} (use --replace-case)")
        cases.append(case_obj)
        payload["cases"] = cases
        _save_cases(cases_path, payload)
        manifest["created_case"] = {"cases_file": str(cases_path), "name": auto_name}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def cmd_emit_case(args: argparse.Namespace) -> None:
    """根据刚生成的 fixture 目录写一条最小 replay case JSON 到 stdout。"""
    out_name = (args.output_name or "").strip()
    if not out_name:
        raise SystemExit("--output-name 必填")
    fixture_dir = _fixtures_reports_root() / out_name
    record = json.loads((fixture_dir / "record.json").read_text(encoding="utf-8"))
    phase = (args.phase or "values").strip()
    tid = (args.thread_id or "").strip()
    if not tid:
        step_ent = ((record.get("steps") or {}).get(phase)) or {}
        if isinstance(step_ent, dict):
            tid = (step_ent.get("selected_session_id") or "").strip()
    if not tid:
        for step in (record.get("steps") or {}).values():
            if not isinstance(step, dict):
                continue
            tid = (step.get("selected_session_id") or "").strip()
            if tid:
                break
    case = _build_case_from_fixture(
        output_name=out_name,
        phase=phase,
        thread_id=tid,
        message=str(args.message or ""),
        mock_stream=str(args.mock_stream or ""),
        start_state_code=str(args.start_state_code or ""),
        end_state_code=str(args.end_state_code or ""),
        case_name=f"savepoint_{out_name}",
    )
    print(json.dumps(case, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate simple-chat savepoint fixtures.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_t = sub.add_parser("template", help="Clone builtin template with ID remap")
    p_t.add_argument("--list", action="store_true", help="List templates")
    p_t.add_argument("--template", default="", help="Template key")
    p_t.add_argument("--output-name", default="", help="Output directory name under fixtures/simple_chat_reports")
    p_t.add_argument("--dry-run", action="store_true")
    p_t.add_argument("--apply", action="store_true", help="Perform write (default dry without --apply)")
    p_t.set_defaults(func=cmd_template)

    p_s = sub.add_parser("snapshot", help="Copy live report dir into fixtures")
    p_s.add_argument("--simple-root", default="", help="Simple data root (default: <project>/data/simple)")
    p_s.add_argument("--report-id", required=True)
    p_s.add_argument("--output-name", default="")
    p_s.add_argument("--remap-ids", action="store_true", default=True)
    p_s.add_argument("--no-remap-ids", action="store_false", dest="remap_ids")
    p_s.add_argument("--dry-run", action="store_true")
    p_s.add_argument("--apply", action="store_true")
    p_s.add_argument("--create-case", action="store_true", help="Append one generated case after snapshot")
    p_s.add_argument("--cases-file", default="", help="Target cases json path; default batch_savepoints_general.json")
    p_s.add_argument("--replace-case", action="store_true", help="Replace same-name case when create-case")
    p_s.add_argument("--case-name", default="", help="Override auto case name")
    p_s.add_argument("--phase", default="values", help="Case phase when create-case")
    p_s.add_argument("--thread-id", default="", dest="thread_id", help="Case thread id when create-case")
    p_s.add_argument("--message", default="", help="Case message when create-case")
    p_s.add_argument("--mock-stream", default="", dest="mock_stream", help="Case mock.stream_reply")
    p_s.add_argument("--start-state-code", default="", dest="start_state_code")
    p_s.add_argument("--end-state-code", default="", dest="end_state_code")
    p_s.set_defaults(func=cmd_snapshot)

    p_e = sub.add_parser("emit-case", help="Print a JSON case snippet for a generated fixture")
    p_e.add_argument("--output-name", required=True)
    p_e.add_argument("--phase", default="values")
    p_e.add_argument("--thread-id", default="", dest="thread_id", help="优先于 record 推断")
    p_e.add_argument("--message", default="")
    p_e.add_argument("--mock-stream", default="")
    p_e.add_argument("--start-state-code", default="")
    p_e.add_argument("--end-state-code", default="")
    p_e.set_defaults(func=cmd_emit_case)

    args = parser.parse_args()
    if args.cmd in ("template", "snapshot"):
        skip_warn = args.cmd == "template" and getattr(args, "list", False)
        if not skip_warn and not args.dry_run and not getattr(args, "apply", False):
            print("未指定 --apply，按 dry-run 处理（不写入）。加 --apply 确认写入。")
            args.dry_run = True
    args.func(args)


if __name__ == "__main__":
    main()
