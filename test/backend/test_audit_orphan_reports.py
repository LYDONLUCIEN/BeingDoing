"""
audit_orphan_reports.py 脚本测试:scan 分类、archive、clean、双确认机制。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# 脚本路径
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "audit_orphan_reports.py"
BACKEND = Path(__file__).resolve().parents[2] / "src" / "backend"


def _make_base(tmp_path: Path) -> Path:
    """创建测试数据根目录,含 activations.json 和 reports/。"""
    base = tmp_path / "simple"
    (base / "reports").mkdir(parents=True)
    (base / "activations.json").write_text("{}", encoding="utf-8")
    return base


def _add_activation(base: Path, code: str, *, owner_user_id=None, status="active", deleted_at=None) -> None:
    """向 activations.json 注入一条激活码记录。"""
    f = base / "activations.json"
    data = json.loads(f.read_text(encoding="utf-8") or "{}")
    data[code.upper()] = {
        "code": code.upper(),
        "owner_user_id": owner_user_id,
        "owner_email": None,
        "status": status,
        "deleted_at": deleted_at,
    }
    f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _add_report(base: Path, report_id: str, code: str, user_id: str, created_at: str = "2026-01-01T00:00:00Z") -> None:
    d = base / "reports" / report_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "record.json").write_text(json.dumps({
        "report_id": report_id,
        "activation_code": code,
        "user_id": user_id,
        "created_at": created_at,
        "updated_at": created_at,
        "status": "in_progress",
        "final_conclusion": None,
        "steps": {},
    }, ensure_ascii=False), encoding="utf-8")


def _run_script(args: list, base_dir: Path) -> subprocess.CompletedProcess:
    """执行脚本,--base-dir 指向临时目录。"""
    cmd = [sys.executable, str(SCRIPT), "--base-dir", str(base_dir)] + args
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30)


# ──────────────────────────────────────────────────────────────────
# scan 分类
# ──────────────────────────────────────────────────────────────────


def test_scan_identifies_activation_missing(tmp_path: Path) -> None:
    base = _make_base(tmp_path)
    # report 的 code 不在 activations.json
    _add_report(base, "r1", "GHOST123", "user-1")
    result = _run_script(["scan", "--json"], base)
    assert result.returncode == 1  # 发现可疑
    data = json.loads(result.stdout)
    assert len(data["categories"]["activation_missing"]) == 1
    assert data["categories"]["activation_missing"][0]["report_id"] == "r1"


def test_scan_identifies_activation_deleted(tmp_path: Path) -> None:
    base = _make_base(tmp_path)
    _add_activation(base, "DEL123", status="deleted", deleted_at="2026-01-01T00:00:00Z")
    _add_report(base, "r2", "DEL123", "user-1")
    result = _run_script(["scan", "--json"], base)
    data = json.loads(result.stdout)
    assert len(data["categories"]["activation_deleted"]) == 1


def test_scan_identifies_orphan_prefix(tmp_path: Path) -> None:
    base = _make_base(tmp_path)
    _add_report(base, "r3", "ORPHAN__ABC-123", "unknown:orphan:abc")
    result = _run_script(["scan", "--json"], base)
    data = json.loads(result.stdout)
    assert len(data["categories"]["orphan_prefix"]) == 1


def test_scan_identifies_cross_user(tmp_path: Path) -> None:
    base = _make_base(tmp_path)
    _add_activation(base, "CROSS1", owner_user_id="real-owner")
    _add_report(base, "r4", "CROSS1", "admin-user")  # user_id 不匹配
    result = _run_script(["scan", "--json"], base)
    data = json.loads(result.stdout)
    assert len(data["categories"]["cross_user"]) == 1
    assert data["categories"]["cross_user"][0]["record_user_id"] == "admin-user"
    assert data["categories"]["cross_user"][0]["owner_user_id"] == "real-owner"


def test_scan_identifies_duplicates(tmp_path: Path) -> None:
    base = _make_base(tmp_path)
    _add_activation(base, "DUP123", owner_user_id="user-1")
    _add_report(base, "canon", "DUP123", "user-1", created_at="2026-01-01T00:00:00Z")
    _add_report(base, "extra", "DUP123", "user-1", created_at="2026-02-01T00:00:00Z")
    result = _run_script(["scan", "--json"], base)
    data = json.loads(result.stdout)
    dups = data["categories"]["duplicate"]
    assert len(dups) == 1
    assert dups[0]["canonical_report_id"] == "canon"
    assert len(dups[0]["extras"]) == 1
    assert dups[0]["extras"][0]["report_id"] == "extra"


def test_scan_clean_returns_0_when_no_orphans(tmp_path: Path) -> None:
    base = _make_base(tmp_path)
    _add_activation(base, "OK123", owner_user_id="user-1")
    _add_report(base, "r-ok", "OK123", "user-1")
    result = _run_script(["scan"], base)
    assert result.returncode == 0


# ──────────────────────────────────────────────────────────────────
# archive / clean
# ──────────────────────────────────────────────────────────────────


def test_archive_moves_to_archive_dir(tmp_path: Path) -> None:
    base = _make_base(tmp_path)
    _add_report(base, "ghost", "GHOST", "u1")  # activation_missing
    result = _run_script(["archive", "--confirm-count", "1"], base)
    assert result.returncode == 0
    # 原目录消失
    assert not (base / "reports" / "ghost").exists()
    # 归档目录存在
    archive_dirs = list((base / "reports_archive").iterdir())
    assert len(archive_dirs) == 1
    assert (archive_dirs[0] / "ghost").is_dir()
    assert (archive_dirs[0] / "_manifest.json").is_file()


def test_archive_dry_run_no_change(tmp_path: Path) -> None:
    base = _make_base(tmp_path)
    _add_report(base, "ghost", "GHOST", "u1")
    result = _run_script(["archive", "--dry-run", "--confirm-count", "1"], base)
    assert result.returncode == 0
    # 原目录仍在
    assert (base / "reports" / "ghost").is_dir()
    # 无归档
    assert not (base / "reports_archive").exists()


def test_archive_wrong_confirm_count_rejected(tmp_path: Path) -> None:
    base = _make_base(tmp_path)
    _add_report(base, "ghost", "GHOST", "u1")
    result = _run_script(["archive", "--confirm-count", "99"], base)
    assert result.returncode == 2  # 确认失败
    assert "不匹配" in result.stderr


def test_archive_excludes_cross_user_by_default(tmp_path: Path) -> None:
    base = _make_base(tmp_path)
    _add_activation(base, "CROSS1", owner_user_id="real")
    _add_report(base, "r-cross", "CROSS1", "admin")
    # 待处理数量应为 0(cross_user 默认排除)
    result = _run_script(["archive", "--confirm-count", "0"], base)
    assert result.returncode == 0
    assert "没有需要处理" in result.stdout


def test_archive_includes_cross_user_with_flag(tmp_path: Path) -> None:
    base = _make_base(tmp_path)
    _add_activation(base, "CROSS1", owner_user_id="real")
    _add_report(base, "r-cross", "CROSS1", "admin")
    result = _run_script(["archive", "--include-cross-user", "--confirm-count", "1"], base)
    assert result.returncode == 0
    assert not (base / "reports" / "r-cross").exists()


def test_clean_requires_destructive_flag(tmp_path: Path) -> None:
    base = _make_base(tmp_path)
    _add_report(base, "ghost", "GHOST", "u1")
    result = _run_script(["clean", "--confirm-count", "1"], base)
    assert result.returncode == 2
    assert "destructive" in result.stderr
    # 原目录仍在
    assert (base / "reports" / "ghost").is_dir()


def test_clean_with_destructive_flag_removes(tmp_path: Path) -> None:
    base = _make_base(tmp_path)
    _add_report(base, "ghost", "GHOST", "u1")
    result = _run_script(
        ["clean", "--confirm-count", "1", "--i-know-this-is-destructive"], base
    )
    assert result.returncode == 0
    assert not (base / "reports" / "ghost").exists()
    # clean 不创建归档目录
    assert not (base / "reports_archive").exists()


def test_clean_duplicate_extras_keeps_canonical(tmp_path: Path) -> None:
    base = _make_base(tmp_path)
    _add_activation(base, "DUP", owner_user_id="u1")
    _add_report(base, "canon", "DUP", "u1", created_at="2026-01-01T00:00:00Z")
    _add_report(base, "extra", "DUP", "u1", created_at="2026-02-01T00:00:00Z")
    result = _run_script(
        ["clean", "--confirm-count", "1", "--i-know-this-is-destructive"], base
    )
    assert result.returncode == 0
    assert (base / "reports" / "canon").is_dir()
    assert not (base / "reports" / "extra").exists()
