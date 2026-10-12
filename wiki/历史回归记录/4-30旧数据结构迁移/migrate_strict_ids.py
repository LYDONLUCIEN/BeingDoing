#!/usr/bin/env python3
"""
将旧数据结构对齐为严格 ID 语义（不再兼容 legacy session_id 线程语义）。

主要变更：
1) 激活码记录补齐 activation_session_id（保留 session_id 以兼容后端 ActivationRecord 存储层）。
2) report record.json 中，剔除误混入 steps.*.session_ids 的 activation_session_id。
   - 若该会话文件有消息：迁移为新的 thread_id（t_migrated_*）并重命名文件。
   - 若无消息：直接移除该 session_id，并清理 selected_session_id。
3) 对话文件中移除 message/session_id（旧线程别名），统一使用 thread_id。
4) 对话文件根节点移除 legacy session_id，仅保留 report_id。

默认 dry-run，不落盘；加 --apply 才会写入。
"""

from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


STEP_IDS = ["values", "strengths", "interests", "purpose", "rumination"]


@dataclass
class Summary:
    roots_scanned: int = 0
    activations_updated: int = 0
    reports_scanned: int = 0
    report_records_updated: int = 0
    migrated_thread_files: int = 0
    removed_activation_sid_refs: int = 0
    conversation_files_updated: int = 0
    conversation_rows_thread_patched: int = 0
    conversation_rows_session_removed: int = 0
    root_session_removed: int = 0
    warnings: List[str] = field(default_factory=list)


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, payload: Dict[str, Any], apply: bool) -> None:
    if not apply:
        return
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _message_count(conversation_file: Path) -> int:
    raw = _read_json(conversation_file)
    msgs = raw.get("messages") if isinstance(raw, dict) else []
    return len(msgs) if isinstance(msgs, list) else 0


def _migrate_activations(root: Path, apply: bool, summary: Summary) -> Dict[str, str]:
    activation_sid_by_code: Dict[str, str] = {}
    activations_file = root / "activations.json"
    if not activations_file.is_file():
        return activation_sid_by_code

    raw = _read_json(activations_file)
    changed = False
    for code, rec in (raw or {}).items():
        if not isinstance(rec, dict):
            continue
        sid = str(rec.get("session_id") or "").strip()
        if not sid:
            continue
        code_u = str(code or "").strip().upper()
        activation_sid_by_code[code_u] = sid
        if not str(rec.get("activation_session_id") or "").strip():
            rec["activation_session_id"] = sid
            changed = True
            summary.activations_updated += 1

    if changed:
        _write_json(activations_file, raw, apply=apply)
    return activation_sid_by_code


def _migrate_conversation_file(path: Path, report_id: str, apply: bool, summary: Summary) -> None:
    raw = _read_json(path)
    if not isinstance(raw, dict):
        return
    changed = False

    # 根节点：只认 report_id
    if not str(raw.get("report_id") or "").strip():
        raw["report_id"] = report_id
        changed = True

    if "session_id" in raw:
        raw.pop("session_id", None)
        summary.root_session_removed += 1
        changed = True

    msgs = raw.get("messages")
    if isinstance(msgs, list):
        for msg in msgs:
            if not isinstance(msg, dict):
                continue
            legacy_sid = str(msg.get("session_id") or "").strip()
            if (not str(msg.get("thread_id") or "").strip()) and legacy_sid:
                msg["thread_id"] = legacy_sid
                summary.conversation_rows_thread_patched += 1
                changed = True
            if "session_id" in msg:
                msg.pop("session_id", None)
                summary.conversation_rows_session_removed += 1
                changed = True

    if changed:
        summary.conversation_files_updated += 1
        _write_json(path, raw, apply=apply)


def _migrate_report_record(
    report_dir: Path,
    activation_sid_by_code: Dict[str, str],
    apply: bool,
    summary: Summary,
) -> None:
    record_file = report_dir / "record.json"
    if not record_file.is_file():
        return
    summary.reports_scanned += 1
    record = _read_json(record_file)
    if not isinstance(record, dict):
        summary.warnings.append(f"record.json 非法，跳过: {record_file}")
        return

    report_id = str(record.get("report_id") or report_dir.name).strip()
    activation_code = str(record.get("activation_code") or "").strip().upper()
    activation_sid = activation_sid_by_code.get(activation_code, "")
    steps = record.get("steps") if isinstance(record.get("steps"), dict) else {}

    record_changed = False

    # 迁移所有会话文件（包含 note / step 会话）
    for conv in report_dir.glob("*.json"):
        if conv.name == "record.json":
            continue
        _migrate_conversation_file(conv, report_id=report_id, apply=apply, summary=summary)

    for step in STEP_IDS:
        step_payload = steps.get(step)
        if not isinstance(step_payload, dict):
            continue

        session_ids = step_payload.get("session_ids")
        if not isinstance(session_ids, list):
            session_ids = []

        normalized: List[str] = []
        seen = set()
        for sid in session_ids:
            sid_s = str(sid or "").strip()
            if not sid_s or sid_s in seen:
                continue
            seen.add(sid_s)
            normalized.append(sid_s)

        selected = str(step_payload.get("selected_session_id") or "").strip()

        # 关键处理：activation sid 不再允许出现在 steps.*.session_ids
        if activation_sid and activation_sid in normalized:
            legacy_file = report_dir / f"{step}__{activation_sid}.json"
            msg_cnt = _message_count(legacy_file) if legacy_file.is_file() else 0

            if msg_cnt > 0:
                new_tid = f"t_migrated_{uuid.uuid4().hex[:24]}"
                new_file = report_dir / f"{step}__{new_tid}.json"
                while new_file.exists():
                    new_tid = f"t_migrated_{uuid.uuid4().hex[:24]}"
                    new_file = report_dir / f"{step}__{new_tid}.json"

                normalized = [new_tid if x == activation_sid else x for x in normalized]
                if selected == activation_sid:
                    selected = new_tid

                if apply and legacy_file.is_file():
                    legacy_file.rename(new_file)
                summary.migrated_thread_files += 1
                record_changed = True
            else:
                normalized = [x for x in normalized if x != activation_sid]
                if selected == activation_sid:
                    selected = normalized[0] if normalized else ""
                # 空文件或缺文件场景直接移除引用
                if apply and legacy_file.is_file():
                    try:
                        legacy_file.unlink()
                    except OSError:
                        pass
                summary.removed_activation_sid_refs += 1
                record_changed = True

        # selected 必须属于 session_ids
        if selected and selected not in normalized:
            selected = normalized[0] if normalized else ""
            record_changed = True

        selected_out = selected if selected else None
        if step_payload.get("session_ids") != normalized:
            step_payload["session_ids"] = normalized
            record_changed = True
        if step_payload.get("selected_session_id") != selected_out:
            step_payload["selected_session_id"] = selected_out
            record_changed = True

    if record_changed:
        summary.report_records_updated += 1
        _write_json(record_file, record, apply=apply)


def migrate_root(root: Path, apply: bool, summary: Summary) -> None:
    if not root.exists():
        summary.warnings.append(f"数据根不存在，跳过: {root}")
        return

    summary.roots_scanned += 1
    activation_sid_by_code = _migrate_activations(root, apply=apply, summary=summary)
    reports_root = root / "reports"
    if not reports_root.is_dir():
        return

    for report_dir in reports_root.iterdir():
        if not report_dir.is_dir():
            continue
        _migrate_report_record(
            report_dir,
            activation_sid_by_code=activation_sid_by_code,
            apply=apply,
            summary=summary,
        )


def main() -> None:
    script_path = Path(__file__).resolve()
    project_root = script_path.parents[3]
    default_root = project_root / "data" / "simple"
    default_test_root = project_root / "data" / "test" / "simple"

    parser = argparse.ArgumentParser(description="旧 session_id 混用迁移脚本（strict id）")
    parser.add_argument("--apply", action="store_true", help="执行写入（默认 dry-run）")
    parser.add_argument("--root", action="append", default=[], help="指定数据根目录（可多次）")
    parser.add_argument(
        "--include-test-root",
        action="store_true",
        help="同时迁移 data/test/simple",
    )
    args = parser.parse_args()

    roots: List[Path] = []
    if args.root:
        roots.extend(Path(r).expanduser().resolve() for r in args.root)
    else:
        roots.append(default_root.resolve())
    if args.include_test_root:
        roots.append(default_test_root.resolve())

    summary = Summary()
    for root in roots:
        migrate_root(root, apply=args.apply, summary=summary)

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] migration finished")
    print(f"- roots_scanned: {summary.roots_scanned}")
    print(f"- activations_updated: {summary.activations_updated}")
    print(f"- reports_scanned: {summary.reports_scanned}")
    print(f"- report_records_updated: {summary.report_records_updated}")
    print(f"- migrated_thread_files: {summary.migrated_thread_files}")
    print(f"- removed_activation_sid_refs: {summary.removed_activation_sid_refs}")
    print(f"- conversation_files_updated: {summary.conversation_files_updated}")
    print(f"- conversation_rows_thread_patched: {summary.conversation_rows_thread_patched}")
    print(f"- conversation_rows_session_removed: {summary.conversation_rows_session_removed}")
    print(f"- root_session_removed: {summary.root_session_removed}")
    if summary.warnings:
        print("- warnings:")
        for w in summary.warnings:
            print(f"  - {w}")


if __name__ == "__main__":
    main()
