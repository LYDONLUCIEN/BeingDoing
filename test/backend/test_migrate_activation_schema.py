"""
migrate_activation_schema.py 脚本测试：无损补丁、备份、幂等、回收站、漂移守卫。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "migrate_activation_schema.py"
BACKEND = Path(__file__).resolve().parents[2] / "src" / "backend"

LEGACY_RECORD = {
    "code": "LEGACY0001",
    "session_id": "sid-1",
    "mode": "combined",
    "created_at": "2026-01-01T00:00:00+00:00",
    "expires_at": "2026-07-01T00:00:00+00:00",
    "last_activity_at": "2026-01-01T00:00:00+00:00",
}

NEW_RECORD = dict(
    LEGACY_RECORD,
    code="NEWCODE001",
    vip_level=2,
    code_type="trial",
    package_type="quarterly",
    source_order_id="order-1",
    purchaser_user_id="u-1",
    report_authorized=True,
)


def _make_root(tmp_path: Path) -> Path:
    """构造测试项目根：data/simple + data/test/simple 四个目标文件。"""
    root = tmp_path / "proj"
    (root / "data" / "simple").mkdir(parents=True)
    (root / "data" / "test" / "simple").mkdir(parents=True)
    (root / "data" / "simple" / "activations.json").write_text(
        json.dumps({"LEGACY0001": dict(LEGACY_RECORD), "NEWCODE001": dict(NEW_RECORD)}),
        encoding="utf-8",
    )
    (root / "data" / "simple" / "activations_recycle_bin.json").write_text(
        json.dumps(
            {
                "OLDCODE001": {
                    "activation_code": "OLDCODE001",
                    "session_id": "sid-old",
                    "mode": "combined",
                    "original_record": dict(LEGACY_RECORD, code="OLDCODE001"),
                    "deleted_at": "2026-02-01T00:00:00+00:00",
                    "purge_after": "2026-03-01T00:00:00+00:00",
                }
            }
        ),
        encoding="utf-8",
    )
    (root / "data" / "test" / "simple" / "activations.json").write_text(
        json.dumps({"SBXTEST0001": dict(LEGACY_RECORD, code="SBXTEST0001")}),
        encoding="utf-8",
    )
    # 测试根回收站不存在 → 应跳过
    return root


def _run(root: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["ACTIVATION_MIGRATION_ROOT_OVERRIDE"] = str(root)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def test_dry_run_writes_nothing(tmp_path: Path):
    root = _make_root(tmp_path)
    before = (root / "data" / "simple" / "activations.json").read_bytes()
    r = _run(root, "--dry-run")
    assert r.returncode == 0, r.stderr
    assert "将补全" in r.stdout
    assert (root / "data" / "simple" / "activations.json").read_bytes() == before
    assert not list((root / "data").glob("backups/activation_schema_migration_*"))


def test_migration_patches_legacy_and_preserves_existing(tmp_path: Path):
    root = _make_root(tmp_path)
    r = _run(root)
    assert r.returncode == 0, r.stderr

    acts = json.loads((root / "data" / "simple" / "activations.json").read_text(encoding="utf-8"))

    # 存量码：补全 code_type=full、vip_level=1、package_type=None 等
    legacy = acts["LEGACY0001"]
    assert legacy["code_type"] == "full"
    assert legacy["vip_level"] == 1
    assert legacy["package_type"] is None
    assert legacy["report_authorized"] is False
    assert legacy["expires_at"] == LEGACY_RECORD["expires_at"]  # 有效期一字不动

    # 已是新 schema 的码：已有值一律不覆盖
    new = acts["NEWCODE001"]
    assert new["code_type"] == "trial"
    assert new["vip_level"] == 2
    assert new["package_type"] == "quarterly"
    assert new["report_authorized"] is True

    # 沙箱码同样补全
    test_acts = json.loads(
        (root / "data" / "test" / "simple" / "activations.json").read_text(encoding="utf-8")
    )
    assert test_acts["SBXTEST0001"]["code_type"] == "full"

    # 回收站：补丁打在 original_record 内，外层结构不动
    bin_ = json.loads(
        (root / "data" / "simple" / "activations_recycle_bin.json").read_text(encoding="utf-8")
    )
    entry = bin_["OLDCODE001"]
    assert entry["original_record"]["code_type"] == "full"
    assert "code_type" not in entry  # 外层不补
    assert entry["purge_after"] == "2026-03-01T00:00:00+00:00"


def test_backup_created(tmp_path: Path):
    root = _make_root(tmp_path)
    original = (root / "data" / "simple" / "activations.json").read_bytes()
    r = _run(root)
    assert r.returncode == 0, r.stderr
    backups = list((root / "data").glob("backups/activation_schema_migration_*"))
    assert len(backups) == 1
    assert (backups[0] / "simple_activations.json").read_bytes() == original
    assert (backups[0] / "simple_activations_recycle_bin.json").exists()
    assert (backups[0] / "test_activations.json").exists()


def test_idempotent_second_run_patches_zero(tmp_path: Path):
    root = _make_root(tmp_path)
    assert _run(root).returncode == 0
    r2 = _run(root)
    assert r2.returncode == 0, r2.stderr
    assert "已补全 0" in r2.stdout


def test_corrupt_json_aborts_without_writing(tmp_path: Path):
    root = _make_root(tmp_path)
    target = root / "data" / "simple" / "activations.json"
    target.write_text("{损坏的json", encoding="utf-8")
    test_file = root / "data" / "test" / "simple" / "activations.json"
    test_before = test_file.read_bytes()
    r = _run(root)
    assert r.returncode == 1
    assert "未写任何文件" in r.stdout
    assert test_file.read_bytes() == test_before  # 其他文件也没被写


def test_unknown_fields_and_broken_entries_preserved(tmp_path: Path):
    root = _make_root(tmp_path)
    f = root / "data" / "simple" / "activations.json"
    raw = json.loads(f.read_text(encoding="utf-8"))
    raw["WEIRD00001"] = {"foo": "bar", "future_field": 123}  # 缺必需字段的"损坏"条目
    f.write_text(json.dumps(raw), encoding="utf-8")
    r = _run(root)
    assert r.returncode == 0, r.stderr
    acts = json.loads(f.read_text(encoding="utf-8"))
    assert acts["WEIRD00001"]["foo"] == "bar"
    assert acts["WEIRD00001"]["future_field"] == 123
    assert acts["WEIRD00001"]["code_type"] == "full"  # 仍被补全，未丢弃


def test_schema_defaults_match_load_all(tmp_path: Path):
    """漂移守卫：SCHEMA_DEFAULTS 必须与 _load_all() 对缺字段记录的实际补全结果一致。"""
    sys.path.insert(0, str(BACKEND))
    import importlib.util

    spec = importlib.util.spec_from_file_location("migrate_activation_schema", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    from app.utils.simple_activation_manager import SimpleActivationManager

    base = tmp_path / "simple"
    base.mkdir()
    (base / "activations.json").write_text(
        json.dumps({"LEGACY0001": dict(LEGACY_RECORD)}), encoding="utf-8"
    )
    mgr = SimpleActivationManager(base_dir=str(base))
    rec = mgr.get_activation("LEGACY0001")
    assert rec is not None
    for key, expected in mod.SCHEMA_DEFAULTS.items():
        actual = getattr(rec, key, "<缺失>")
        assert actual == expected, (
            f"字段 {key}：脚本默认 {expected!r} ≠ _load_all 补全 {actual!r}，清单已漂移"
        )
