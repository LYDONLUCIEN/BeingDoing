"""退款 revoke_codes 迁移测试（2026-10-18）

在临时目录复制真实 Alembic 脚本，并用最小 env.py 验证 025→026→025。
不导入应用 Settings，不触碰共享工作区数据库。
"""

import os
from pathlib import Path
import shutil
import sqlite3
import subprocess


ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_SOURCE = ROOT / "src/backend" / "alembic"


def _prepare_scripts(tmp_path: Path) -> Path:
    """复制真实迁移脚本，替换为无应用依赖的测试 env.py"""
    backend = tmp_path / "backend"
    shutil.copytree(ALEMBIC_SOURCE, backend / "alembic")
    (backend / "alembic.ini").write_text(
        "[alembic]\nscript_location = %(here)s/alembic\n",
        encoding="utf-8",
    )
    (backend / "alembic" / "env.py").write_text(
        """
import os
from sqlalchemy import create_engine
from alembic import context

engine = create_engine(os.environ['DATABASE_URL'].replace('+aiosqlite', ''))
with engine.connect() as connection:
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return backend


def _run_alembic(backend: Path, db_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("alembic")
    assert executable, "测试环境缺少 alembic CLI"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    return subprocess.run(
        [executable, "-c", "alembic.ini", *args],
        cwd=backend,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_refund_revoke_codes_migration_026(tmp_path):
    """025 → 026 添加可空 revoke_codes；回滚后移除"""
    backend = _prepare_scripts(tmp_path)
    db_path = tmp_path / "refund-migration.db"
    with sqlite3.connect(db_path) as db:
        db.execute("CREATE TABLE payment_refunds (id TEXT PRIMARY KEY)")
        db.execute("CREATE TABLE alembic_version (version_num TEXT PRIMARY KEY)")
        db.execute(
            "INSERT INTO alembic_version VALUES ('025_user_type_admin_note')"
        )

    upgrade = _run_alembic(backend, db_path, "upgrade", "026_refund_revoke_codes")
    assert upgrade.returncode == 0, upgrade.stderr + upgrade.stdout
    with sqlite3.connect(db_path) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(payment_refunds)")}
        version = db.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    assert "revoke_codes" in columns
    assert version == "026_refund_revoke_codes"

    downgrade = _run_alembic(backend, db_path, "downgrade", "-1")
    assert downgrade.returncode == 0, downgrade.stderr + downgrade.stdout
    with sqlite3.connect(db_path) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(payment_refunds)")}
        version = db.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    assert "revoke_codes" not in columns
    assert version == "025_user_type_admin_note"
