#!/usr/bin/env python3
"""
迁移脚本：将 purpose 结论卡中 experience_value_rows 的旧格式 {value: "xxx"}
转为新格式 {values: ["xxx"]}。

扫描所有 report 的 purpose thread 文件，找到结论卡消息中的
experience_value_rows，逐条将 value 单值转为 values 数组。

用法（在项目根目录执行）：
  cd src/backend && python scripts/migrate_purpose_value_to_values.py
  cd src/backend && python scripts/migrate_purpose_value_to_values.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.utils.simple_activation_manager import get_simple_base_dir

STEP_FILE_RE = re.compile(r"^purpose__(?P<thread_id>.+)\.json$")
SKIP_DIRS = {".deleted_threads", ".locks"}


def _coerce_values(raw: Any) -> List[str]:
    if isinstance(raw, list):
        return [str(v).strip() for v in raw if str(v).strip()]
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    return []


def _needs_migration(rows: List[Dict[str, Any]]) -> bool:
    """检查 experience_value_rows 是否有旧格式需要迁移。"""
    for row in rows:
        if not isinstance(row, dict):
            continue
        if "value" in row and "values" not in row:
            return True
    return False


def _migrate_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """将旧格式 value 转为 values 数组。"""
    migrated = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        new_row = dict(row)
        if "value" in new_row and "values" not in new_row:
            new_row["values"] = _coerce_values(new_row.pop("value"))
        migrated.append(new_row)
    return migrated


def _extract_and_migrate_conclusion_payloads(data: Dict[str, Any]) -> bool:
    """遍历消息列表，迁移结论卡中的 experience_value_rows。返回是否有变更。"""
    messages = data.get("messages")
    if not isinstance(messages, list):
        return False

    changed = False
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role", "")
        if role not in ("conclusion_card",):
            continue

        # 尝试从 content 或 card_payload 中提取
        for payload_key in ("card_payload", "content"):
            payload_raw = msg.get(payload_key)
            if not isinstance(payload_raw, str):
                continue
            try:
                payload = json.loads(payload_raw)
            except (json.JSONDecodeError, TypeError):
                continue

            rows = payload.get("experience_value_rows")
            if not isinstance(rows, list) or not _needs_migration(rows):
                continue

            payload["experience_value_rows"] = _migrate_rows(rows)
            msg[payload_key] = json.dumps(payload, ensure_ascii=False)
            changed = True

    return changed


def _migrate_thread_file(file_path: Path, dry_run: bool = False) -> bool:
    """处理单个 thread 文件。返回是否有迁移。"""
    try:
        raw = file_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return False

    if not isinstance(data, dict):
        return False

    if not _extract_and_migrate_conclusion_payloads(data):
        return False

    if dry_run:
        print(f"  [预览] 需要迁移: {file_path}")
        return True

    file_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [完成] 已迁移: {file_path}")
    return True


def migrate(dry_run: bool = False) -> int:
    base_dir = get_simple_base_dir()
    reports_dir = base_dir / "reports"
    if not reports_dir.exists():
        print(f"报告目录不存在: {reports_dir}")
        return 0

    total_migrated = 0
    total_scanned = 0

    for report_dir in reports_dir.iterdir():
        if not report_dir.is_dir():
            continue
        if report_dir.name.startswith("."):
            continue

        purpose_files = [f for f in report_dir.iterdir() if f.is_file() and STEP_FILE_RE.match(f.name)]
        if not purpose_files:
            continue

        print(f"\n扫描 report: {report_dir.name} ({len(purpose_files)} 个 purpose 文件)")
        for pf in purpose_files:
            total_scanned += 1
            if _migrate_thread_file(pf, dry_run=dry_run):
                total_migrated += 1

    print(f"\n总计: 扫描 {total_scanned} 个文件, 迁移 {total_migrated} 个")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="将 purpose 结论卡中 experience_value_rows 的 value 单值转为 values 数组"
    )
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不实际修改")
    args = parser.parse_args()

    sys.exit(migrate(dry_run=args.dry_run))
