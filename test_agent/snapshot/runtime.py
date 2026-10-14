"""子进程入口：先锁定独立工作区，再加载迁移或测试代码。"""

import json
import os
import runpy
import socket
import sqlite3
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


def install_guard(root, evidence):
    root, evidence = root.resolve(), evidence.resolve()
    marker = root / ".snapshot-workspace.json"
    if (
        Path.cwd().resolve() != root
        or not marker.is_file()
        or json.loads(marker.read_text()).get("root") != str(root)
        or os.environ.get("DATABASE_URL") != f"sqlite+aiosqlite:///{root}/app.db"
        or os.environ.get("APP_ENV") != "test"
    ):
        raise RuntimeError("拒绝在非测试副本中执行")

    def writable(value):
        if isinstance(value, int) or value is None:
            return
        path = Path(os.fsdecode(value)).resolve()
        if path == Path(os.devnull):
            return
        if not any(path.is_relative_to(base) for base in (root, evidence)):
            raise RuntimeError("测试尝试写入工作区之外，已拒绝")

    def audit(event, args):
        if event in {
            "socket.connect",
            "socket.connect_ex",
            "socket.sendto",
            "socket.getaddrinfo",
            "socket.bind",
        }:
            raise RuntimeError("生产副本测试禁止外部网络及监听")
        if event in {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn"}:
            raise RuntimeError("副本测试不允许另起未隔离的外部程序")
        if event == "sqlite3.connect":
            database = os.fsdecode(args[0])
            if database != ":memory:":
                if database.startswith("file:"):
                    database = unquote(urlsplit(database).path)
                writable(database)
        if event == "open":
            _, mode, flags = args
            if (mode and any(c in mode for c in "wax+")) or flags & (
                os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC
            ):
                writable(args[0])
        elif event in {
            "os.remove",
            "os.rmdir",
            "os.mkdir",
            "os.chmod",
            "os.chown",
            "os.truncate",
            "os.utime",
        }:
            writable(args[0])
        elif event in {"os.rename", "os.link", "os.symlink"}:
            writable(args[0])
            writable(args[1])

    sys.addaudithook(audit)

    # 某些 Python 版本的 connect_ex 不发审计事件；额外阻断套接字方法。
    def blocked(*args, **kwargs):
        raise RuntimeError("生产副本测试禁止外部网络")

    socket.socket.connect = socket.socket.connect_ex = socket.socket.sendto = blocked


def database_state(path):
    with sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True) as db:
        if db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise ValueError("数据库完整性检查失败")
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("数据库存在失效的外键关系")
        tables = [
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        revisions = [row[0] for row in db.execute("SELECT version_num FROM alembic_version")]
        if not revisions:
            raise ValueError("旧库没有迁移版本，必须先明确实际结构，不能直接 stamp head")
        counts = {
            table: db.execute('SELECT count(*) FROM "' + table.replace('"', '""') + '"').fetchone()[
                0
            ]
            for table in tables
        }
        return {"revisions": sorted(revisions), "counts": counts}


def main():
    action, evidence_name, *args = sys.argv[1:]
    root, evidence = Path.cwd(), Path(evidence_name)
    install_guard(root, evidence)
    if action == "migrate":
        from alembic import command
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        before = database_state(root / "app.db")
        config = Config(str(root / "src/backend/alembic.ini"))
        config.set_main_option("script_location", str(root / "src/backend/alembic"))
        scripts = ScriptDirectory.from_config(config)
        target = args[0]
        if target == "head":
            heads = scripts.get_heads()
            if len(heads) != 1:
                raise ValueError("存在多条迁移分支，必须先解决")
            target = heads[0]
        if scripts.get_revision(target) is None:
            raise ValueError("迁移目标不存在")
        command.upgrade(config, target)
        after = database_state(root / "app.db")
        if after["revisions"] != [target]:
            raise ValueError("迁移后版本与目标不符")
        (evidence / "migration.json").write_text(
            json.dumps(
                {
                    "before": before["revisions"],
                    "after": after["revisions"],
                    "counts_before": before["counts"],
                    "counts_after": after["counts"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    elif action == "file-migration":
        script, *script_args = args
        path = (root / script).resolve()
        if not path.is_relative_to(root) or path.suffix != ".py":
            raise ValueError("文件迁移必须是固定源码内的 Python 脚本")
        sys.argv = [str(path), *script_args]
        runpy.run_path(str(path), run_name="__main__")
    elif action == "state":
        (evidence / "final-state.json").write_text(json.dumps(database_state(root / "app.db")))
    elif action == "pytest":
        import pytest

        return pytest.main(
            [
                *args,
                "-q",
                "--tb=short",
                "-c",
                str(root / "pytest.ini"),
                f"--rootdir={root}",
                f"--confcutdir={root}",
                f"--basetemp={root / 'tmp/pytest'}",
                "-p",
                "pytest_asyncio.plugin",
                "-p",
                "anyio.pytest_plugin",
                f"--junitxml={evidence / 'results.xml'}",
            ]
        )
    else:
        raise ValueError("未知副本动作")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
