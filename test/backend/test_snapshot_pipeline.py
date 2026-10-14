"""生产副本工具的公开导出、导入及执行接口；所有输入均为合成数据。"""

import json
import sqlite3
from pathlib import Path

import pytest


def backup_fixture(tmp_path):
    backup = tmp_path / "backup"
    (backup / "data/simple").mkdir(parents=True)
    with sqlite3.connect(backup / "database.sqlite") as db:
        db.executescript("""
            CREATE TABLE users(id TEXT PRIMARY KEY, email TEXT UNIQUE, username TEXT,
                password_hash TEXT NOT NULL);
            INSERT INTO users VALUES ('u1', 'person@example.com', '张小明', 'live-password');
            CREATE TABLE alembic_version(version_num TEXT PRIMARY KEY);
            INSERT INTO alembic_version VALUES ('024_coupon_multi_redemption');
            CREATE TABLE refresh_tokens(id TEXT PRIMARY KEY, token_hash TEXT);
            INSERT INTO refresh_tokens VALUES ('r1', 'live-token');
        """)
    (backup / "data/simple/activations.json").write_text(
        json.dumps(
            {
                "REALCODE123": {
                    "code": "REALCODE123",
                    "owner_user_id": "u1",
                    "owner_email": "person@example.com",
                    "status": "active",
                }
            },
            ensure_ascii=False,
        )
    )
    (backup / "data/simple/conversation.json").write_text(
        json.dumps(
            {
                "messages": [{"role": "user", "content": "我叫张小明，电话13800138000，想换工作"}],
                "activation_code": "REALCODE123",
                "api_key": "sk-live-secret",
            },
            ensure_ascii=False,
        )
    )
    (backup / "data/simple/report.pdf").write_bytes(b"private binary")
    (backup / "data/admin_runtime_config.json").write_text('{"key":"live-key"}')
    (backup / "BACKUP_COMPLETE").touch()
    return backup


def test_export_import_preserves_relations_without_credentials_or_overwriting(tmp_path):
    from test_agent.snapshot.archive import export_snapshot, import_snapshot

    backup = backup_fixture(tmp_path)
    archive = tmp_path / "sanitized.tar.gz"
    export_snapshot(backup, archive, secret=b"a" * 32)
    baseline = tmp_path / "baseline"
    manifest = import_snapshot(archive, baseline)
    assert manifest["privacy"] == "pseudonymized-restricted"
    assert manifest["excluded_files"]["binary"] == 1
    with sqlite3.connect(baseline / "database.sqlite") as db:
        user = db.execute("SELECT * FROM users").fetchone()
        assert user[0] == "u1"
        assert user[1].endswith("@example.invalid")
        assert user[2] != "张小明" and user[3] != "live-password"
        assert db.execute("SELECT count(*) FROM refresh_tokens").fetchone()[0] == 0
    activation = json.loads((baseline / "data/simple/activations.json").read_text())
    code = next(iter(activation))
    assert code != "REALCODE123"
    assert activation[code]["code"] == code
    assert activation[code]["owner_user_id"] == "u1"
    assert activation[code]["owner_email"] == user[1]
    chat = (baseline / "data/simple/conversation.json").read_text()
    assert code in chat and "想换工作" in chat
    assert all(value not in chat for value in ("张小明", "13800138000", "sk-live-secret"))
    assert not (baseline / "data/admin_runtime_config.json").exists()
    assert not (baseline / "data/simple/report.pdf").exists()
    with pytest.raises(ValueError, match="存在"):
        import_snapshot(archive, baseline)
    with sqlite3.connect(backup / "database.sqlite") as db:
        assert db.execute("SELECT password_hash FROM users").fetchone()[0] == "live-password"


@pytest.mark.parametrize(
    "outcome",
    [
        "pass",
        "migration_error",
        "skip",
        "zero",
        "assertion",
        "timeout",
        "file_pass",
        "file_error",
        "file_row_loss",
    ],
)
def test_pipeline_migrates_old_copy_and_runs_each_suite_from_same_baseline(tmp_path, outcome):
    from test_agent.snapshot.pipeline import run_pipeline

    backup = backup_fixture(tmp_path)
    source = tmp_path / "candidate"
    (source / "test_agent/snapshot").mkdir(parents=True)
    (source / "src/backend/alembic/versions").mkdir(parents=True)
    (source / "src/backend/alembic.ini").write_text(
        "[alembic]\nscript_location = %(here)s/alembic\n"
    )
    (source / "src/backend/alembic/env.py").write_text("""
import os
from sqlalchemy import create_engine
from alembic import context
engine = create_engine(os.environ['DATABASE_URL'].replace('+aiosqlite', ''))
with engine.connect() as connection:
    context.configure(connection=connection)
    with context.begin_transaction(): context.run_migrations()
""")
    versions = source / "src/backend/alembic/versions"
    (versions / "old.py").write_text(
        "revision='024_coupon_multi_redemption'\ndown_revision=None\ndef upgrade(): pass\n"
    )
    (versions / "new.py").write_text("""
revision='next_schema'
down_revision='024_coupon_multi_redemption'
from alembic import op
import sqlalchemy as sa
def upgrade():
    op.add_column('users', sa.Column('new_field', sa.Text(), server_default='migrated'))
""")
    (source / "test/backend").mkdir(parents=True)
    (source / "test/backend/test_imported.py").write_text("""
import os, sqlite3, socket
from pathlib import Path
import pytest
def test_imported_database():
    assert 'PRODUCTION_PASSWORD' not in os.environ
    assert not Path('.env').exists()
    assert not Path('data/dev-only').exists()
    with sqlite3.connect('app.db') as db:
        assert db.execute('SELECT new_field FROM users').fetchone() == ('migrated',)
        assert db.execute('SELECT count(*) FROM users').fetchone()[0] == 1
        db.execute('DELETE FROM users')
    assert Path('data/simple/conversation.json').exists()
    with pytest.raises(RuntimeError): socket.create_connection(('127.0.0.1', 9))
    with pytest.raises(RuntimeError): sqlite3.connect(Path.cwd().parent / 'must-not-create.sqlite')
    with pytest.raises(RuntimeError): (Path.cwd().parent / 'must-not-write.txt').write_text('bad')
""")
    implementation = Path(__file__).resolve().parents[2]
    import shutil

    shutil.copytree(
        implementation / "test_agent/snapshot", source / "test_agent/snapshot", dirs_exist_ok=True
    )
    shutil.copytree(implementation / "test_agent/center", source / "test_agent/center")
    (source / "app.db").write_text("dev-db")
    (source / "data").mkdir()
    (source / "data/dev-only").write_text("keep")
    key = tmp_path / "key"
    key.write_bytes(b"k" * 32)
    config = {
        "state_root": str(tmp_path / "state"),
        "source": {"kind": "local_backup", "backup": str(backup), "key_file": str(key)},
        "migration_target": "next_schema",
        "suites": [
            {"id": "first", "targets": ["test/backend/test_imported.py"]},
            {"id": "second", "targets": ["test/backend/test_imported.py"]},
        ],
    }
    if outcome in {"pass", "file_pass"}:
        (source / "test/backend/test_fresh.py").write_text(
            "from pathlib import Path\ndef test_fresh(): assert not Path('data/simple/conversation.json').exists()\n"
        )
        (source / "test_agent/catalog").mkdir()
        (source / "test_agent/catalog/ordinary.json").write_text(
            json.dumps(
                {
                    "id": "ordinary",
                    "title": "普通回归",
                    "module": "test",
                    "kind": "api",
                    "core": True,
                    "inputs": ["fresh fixtures"],
                    "assertions": ["separate from production baseline"],
                    "targets": ["test/backend/test_fresh.py"],
                    "timeout": 30,
                }
            )
        )
        config["regression_cases"] = ["ordinary"]
    if outcome == "migration_error":
        (versions / "new.py").write_text(
            "revision='next_schema'\ndown_revision='024_coupon_multi_redemption'\ndef upgrade(): raise RuntimeError('migration failed')\n"
        )
    if outcome.startswith("file_"):
        (source / "scripts").mkdir()
        (source / "scripts/migrate_fixture.py").write_text(
            {
                "file_pass": "from pathlib import Path\nPath('data/simple/migrated.txt').write_text('converted')\n",
                "file_error": "raise RuntimeError('file migration failed')\n",
                "file_row_loss": "import sqlite3\nwith sqlite3.connect('app.db') as db: db.execute('DELETE FROM users')\n",
            }[outcome]
        )
        config["file_migrations"] = [{"script": "scripts/migrate_fixture.py", "args": []}]
    if outcome in {"skip", "zero", "assertion", "timeout"}:
        (source / "test/backend/test_imported.py").write_text(
            {
                "skip": "import pytest\n@pytest.mark.skip(reason='not implemented')\ndef test_skipped(): pass\n",
                "zero": "# no tests\n",
                "assertion": "def test_failure(): assert False\n",
                "timeout": "import time\ndef test_slow(): time.sleep(10)\n",
            }[outcome]
        )
        if outcome == "timeout":
            for suite in config["suites"]:
                suite["timeout"] = 0.2
    result = run_pipeline(config, source)
    if outcome not in {"pass", "file_pass"}:
        assert result["status"] != "pass"
        if outcome in {"migration_error", "file_error", "file_row_loss"}:
            assert result["stage"] == "migration" and result["suites"] == []
        else:
            assert all(suite["status"] != "pass" for suite in result["suites"])
        assert (source / "app.db").read_text() == "dev-db"
        return
    if result["status"] != "pass":
        for path in Path(result["run_dir"]).rglob("*.log"):
            print(path.read_text())
    assert result["status"] == "pass", {
        "result": result,
        "logs": [p.read_text() for p in Path(result["run_dir"]).rglob("*.log")],
    }
    assert result["migration"]["before"] == ["024_coupon_multi_redemption"]
    assert result["migration"]["after"] == ["next_schema"]
    assert len(result["suites"]) == 2
    assert not (Path(result["run_dir"]) / "must-not-create.sqlite").exists()
    assert not (Path(result["run_dir"]) / "must-not-write.txt").exists()
    if outcome == "file_pass":
        assert (
            Path(result["run_dir"]) / "upgraded/data/simple/migrated.txt"
        ).read_text() == "converted"
    assert result["regression"]["status"] == "pass"
    assert result["regression"]["cases"][0]["counts"]["tests"] == 1
    assert all(suite["counts"]["tests"] == 1 for suite in result["suites"])
    assert (source / "app.db").read_text() == "dev-db"
    assert (source / "data/dev-only").read_text() == "keep"
    with sqlite3.connect(backup / "database.sqlite") as db:
        assert "new_field" not in [row[1] for row in db.execute("PRAGMA table_info(users)")]


def test_capture_cli_requires_quiescence_and_never_copies_config(tmp_path):
    import subprocess
    import sys

    backup = backup_fixture(tmp_path)
    script = Path(__file__).resolve().parents[2] / "scripts/test_snapshot.py"
    output = tmp_path / "capture"
    command = [
        sys.executable,
        str(script),
        "capture",
        "--database",
        str(backup / "database.sqlite"),
        "--data",
        str(backup / "data"),
        "--output",
        str(output),
    ]
    rejected = subprocess.run(command, capture_output=True, text=True)
    assert rejected.returncode != 0 and not output.exists()
    completed = subprocess.run(command + ["--writers-stopped"], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert (output / "BACKUP_COMPLETE").is_file()
    assert (output / "data/simple/conversation.json").is_file()
    assert not (output / ".env").exists()


@pytest.mark.parametrize(
    "name,kind", [("../escape", "file"), ("data/link", "symlink"), ("data/link", "hardlink")]
)
def test_import_rejects_archive_escape_without_leaving_partial_baseline(tmp_path, name, kind):
    import io
    import tarfile

    from test_agent.snapshot.archive import import_snapshot

    archive = tmp_path / "attack.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        member = tarfile.TarInfo(name)
        member.size = 1 if kind == "file" else 0
        if kind != "file":
            member.type = tarfile.SYMTYPE if kind == "symlink" else tarfile.LNKTYPE
            member.linkname = "../../escape"
        tar.addfile(member, io.BytesIO(b"x") if kind == "file" else None)
    destination = tmp_path / "baseline"
    with pytest.raises(ValueError):
        import_snapshot(archive, destination)
    assert not destination.exists() and not (tmp_path / "escape").exists()


def test_export_rejects_unknown_schema_and_missing_completion_marker(tmp_path):
    from test_agent.snapshot.archive import export_snapshot

    backup = backup_fixture(tmp_path)
    (backup / "BACKUP_COMPLETE").unlink()
    with pytest.raises(ValueError, match="BACKUP_COMPLETE"):
        export_snapshot(backup, tmp_path / "first.tgz", secret=b"k" * 32)
    (backup / "BACKUP_COMPLETE").touch()
    with sqlite3.connect(backup / "database.sqlite") as db:
        db.execute("ALTER TABLE users ADD COLUMN new_private_value TEXT")
    with pytest.raises(ValueError, match="未登记"):
        export_snapshot(backup, tmp_path / "second.tgz", secret=b"k" * 32)
    assert not (tmp_path / "second.tgz").exists()


def test_real_project_migration_and_existing_product_read_interfaces(tmp_path):
    """用合成的 024 数据走真正的 025 迁移和产品读取，不能只验证假迁移脚本。"""
    from sqlalchemy import create_engine
    from test_agent.snapshot.pipeline import run_pipeline

    import app.models  # noqa: F401
    from app.models.database import Base

    backup = tmp_path / "old-backup"
    (backup / "data/simple/reports/r1").mkdir(parents=True)
    engine = create_engine(f"sqlite:///{backup / 'database.sqlite'}")
    Base.metadata.create_all(engine)  # 只构造合成测试夹具，流水线禁止 create_all。
    engine.dispose()
    with sqlite3.connect(backup / "database.sqlite") as db:
        db.execute("ALTER TABLE users DROP COLUMN user_type")
        db.execute("ALTER TABLE users DROP COLUMN admin_note")
        db.execute("CREATE TABLE alembic_version(version_num TEXT PRIMARY KEY)")
        db.execute("INSERT INTO alembic_version VALUES ('024_coupon_multi_redemption')")
        db.execute(
            "INSERT INTO users(id,email,password_hash,is_active,email_verified,membership_plan) VALUES ('u1','test@example.com','live-hash',1,1,'none')"
        )
    activation = {
        "code": "REAL123",
        "session_id": "s1",
        "mode": "combined",
        "created_at": "2026-01-01T00:00:00+00:00",
        "expires_at": None,
        "last_activity_at": "2026-01-01T00:00:00+00:00",
        "owner_user_id": "u1",
        "report_id": "r1",
    }
    (backup / "data/simple/activations.json").write_text(json.dumps({"REAL123": activation}))
    (backup / "data/simple/reports/r1/record.json").write_text(
        json.dumps({"report_id": "r1", "activation_code": "REAL123", "user_id": "u1", "steps": {}})
    )
    (backup / "BACKUP_COMPLETE").touch()
    key = tmp_path / "key"
    key.write_bytes(b"r" * 32)
    import tempfile

    source = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix="snapshot-real-", dir=source.parent) as state:
        result = run_pipeline(
            {
                "state_root": state,
                "source": {"kind": "local_backup", "backup": str(backup), "key_file": str(key)},
                "migration_target": "025_user_type_admin_note",
                "suites": [{"id": "actual-product", "targets": ["test_agent/snapshot/cases.py"]}],
            },
            source,
        )
        if result["status"] != "pass":
            print(result.get("stage"), result.get("error"))
            for path in Path(result["run_dir"]).rglob("*.log"):
                print(path.read_text())
        assert result["status"] == "pass", result
        assert result["suites"][0]["counts"]["tests"] == 3


def test_usage_counters_and_business_keys_survive_redaction(tmp_path):
    from test_agent.snapshot.archive import export_snapshot, import_snapshot

    backup = backup_fixture(tmp_path)
    path = backup / "data/simple/conversation.json"
    path.write_text(
        json.dumps(
            {
                "nickname": "active",
                "status": "active",
                "prompt_tokens": 321,
                "content": "active说想换工作",
                "api_key": "secret",
            }
        )
    )
    export_snapshot(backup, tmp_path / "out.tgz", secret=b"s" * 32)
    import_snapshot(tmp_path / "out.tgz", tmp_path / "baseline")
    value = json.loads((tmp_path / "baseline/data/simple/conversation.json").read_text())
    assert value["status"] == "active"
    assert value["prompt_tokens"] == 321
    assert value["nickname"] != "active"
    assert value["api_key"] != "secret"


def test_import_detects_tampering_and_export_rejects_symlink(tmp_path):
    import tarfile

    from test_agent.snapshot.archive import export_snapshot, import_snapshot

    backup = backup_fixture(tmp_path)
    archive = tmp_path / "out.tgz"
    export_snapshot(backup, archive, secret=b"z" * 32)
    first = tmp_path / "first"
    import_snapshot(archive, first)
    (first / "data/simple/conversation.json").write_text('{"tampered":true}')
    attack = tmp_path / "tampered.tgz"
    with tarfile.open(attack, "w:gz") as tar:
        for path in first.rglob("*"):
            if path.is_file():
                tar.add(path, arcname=str(path.relative_to(first)))
    with pytest.raises(ValueError, match="校验"):
        import_snapshot(attack, tmp_path / "bad")
    (backup / "data/simple/linked.json").symlink_to(backup / "data/admin_runtime_config.json")
    with pytest.raises(ValueError, match="链接"):
        export_snapshot(backup, tmp_path / "linked.tgz", secret=b"z" * 32)


def test_ssh_fetch_uses_checked_host_and_quoted_arguments(tmp_path, monkeypatch):
    import os

    from test_agent.snapshot.archive import export_snapshot, import_snapshot
    from test_agent.snapshot.pipeline import fetch

    backup = backup_fixture(tmp_path)
    archive = tmp_path / "prepared.tgz"
    export_snapshot(backup, archive, secret=b"z" * 32)
    binary = tmp_path / "bin"
    binary.mkdir()
    # 只替换系统 SSH 边界；实际执行子进程、传输和导入均真实运行。
    fake = binary / "ssh"
    fake.write_text(
        '#!/bin/sh\ncase "$*" in *StrictHostKeyChecking=yes*) ;; *) exit 3;; esac\ncat "$SNAPSHOT_TEST_ARCHIVE"\n'
    )
    fake.chmod(0o700)
    monkeypatch.setenv("PATH", str(binary) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("SNAPSHOT_TEST_ARCHIVE", str(archive))
    config = {
        "kind": "ssh_export",
        "host": "export-reader",
        "python": "/usr/bin/python3",
        "script": "/read only/export.py",
        "backup": "/backups/frozen",
        "key_file": "/private/key",
    }
    received = tmp_path / "received.tgz"
    fetch(config, received, tmp_path)
    assert import_snapshot(received, tmp_path / "baseline")["format"] == 1
    config["host"] = "-oProxyCommand=bad"
    with pytest.raises(ValueError, match="host"):
        fetch(config, tmp_path / "invalid.tgz", tmp_path)


def test_redacted_codes_keep_legacy_and_current_input_formats(tmp_path):
    from test_agent.snapshot.archive import export_snapshot, import_snapshot

    from app.utils.code_format import normalize_user_code

    backup = backup_fixture(tmp_path)
    values = ["OPENLIFE-9F2K-8M4P-7X2D", "Q-K3M7X9A2", "ABCD234567", "ABCD23456789"]
    (backup / "data/simple/formats.json").write_text(
        json.dumps([{"code": value} for value in values])
    )
    export_snapshot(backup, tmp_path / "codes.tgz", secret=b"c" * 32)
    import_snapshot(tmp_path / "codes.tgz", tmp_path / "baseline")
    codes = [
        item["code"]
        for item in json.loads((tmp_path / "baseline/data/simple/formats.json").read_text())
    ]
    assert codes[0].startswith("OPENLIFE-") and len(codes[0]) == 23
    assert codes[1].startswith("Q-") and len(codes[1]) == 10
    assert len(codes[2]) == 10 and "-" not in codes[2]
    assert len(codes[3]) == 12 and "-" not in codes[3]
    for old, new, context in zip(values, codes, ["activation", "coupon", "activation", "coupon"]):
        assert new != old
        assert normalize_user_code(new, context) == new
