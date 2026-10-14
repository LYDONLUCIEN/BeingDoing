"""CLI：配置初始化、只读预检、停写快照、脱敏导出和完整验收流水线。"""

import argparse
import importlib.util
import json
import os
import secrets
import shutil
import sys
import tempfile
from pathlib import Path

from test_agent.snapshot.archive import (
    capture_snapshot,
    export_snapshot,
    fresh_directory,
    write_json,
)


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="生成私密配置目录，不覆盖已有文件")
    init.add_argument("--directory", type=Path, required=True)
    init.add_argument("--state-root", type=Path, required=True)
    keygen = commands.add_parser("keygen", help="在生产侧创建持久脱敏密钥")
    keygen.add_argument("--output", type=Path, required=True)
    for name in ("run", "doctor"):
        command = commands.add_parser(name)
        command.add_argument("--config", type=Path, required=True)
    capture = commands.add_parser("capture", help="仅在操作者已停止全部写入后创建一致备份")
    capture.add_argument("--database", type=Path, required=True)
    capture.add_argument("--data", type=Path, required=True)
    capture.add_argument("--output", type=Path, required=True)
    capture.add_argument("--writers-stopped", action="store_true")
    export = commands.add_parser("export", help="源端脱敏；output=- 时仅向 stdout 写传输包")
    export.add_argument("--backup", type=Path, required=True)
    export.add_argument("--key-file", type=Path, required=True)
    export.add_argument("--policy", type=Path)
    export.add_argument("--output", required=True)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    previous_umask = os.umask(0o077)
    try:
        if args.command == "init":
            folder = fresh_directory(args.directory)
            config = {
                "state_root": str(args.state_root.absolute()),
                "source": {
                    "kind": "ssh_export",
                    "host": "beingdoing-export",
                    "python": "/usr/bin/python3",
                    "script": "/opt/beingdoing-snapshot/scripts/test_snapshot.py",
                    "backup": "/var/backups/beingdoing/prod/REPLACE_BACKUP_ID",
                    "key_file": "/etc/beingdoing-snapshot/redaction.key",
                    "policy_file": "/etc/beingdoing-snapshot/policy.json",
                    "timeout": 900,
                },
                "migration_target": "head",
                "migration_timeout": 300,
                "allow_row_count_changes": [],
                "file_migrations": [],
                "suites": [
                    {
                        "id": "historical-compatibility",
                        "targets": ["test_agent/snapshot/cases.py"],
                        "timeout": 300,
                    }
                ],
                "regression_cases": ["@core"],
            }
            write_json(folder / "pipeline.json", config)
            write_json(folder / "policy.json", {"redact_literals": [], "extra_schema": {}})
            print(f"配置已生成：{folder / 'pipeline.json'}；请按手册替换主机及路径")
        elif args.command == "keygen":
            args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with args.output.open("xb") as output:
                os.chmod(args.output, 0o600)
                output.write(secrets.token_bytes(32))
            print("脱敏密钥已创建；不要上传到代码仓库或 dev")
        elif args.command == "capture":
            print(
                capture_snapshot(
                    args.database, args.data, args.output, writers_stopped=args.writers_stopped
                )
            )
        elif args.command == "export":
            secret = args.key_file.read_bytes()
            policy = json.loads(args.policy.read_text()) if args.policy else None
            if args.output == "-":
                with tempfile.TemporaryDirectory(prefix="beingdoing-export-") as folder:
                    archive = Path(folder) / "sanitized.tar.gz"
                    export_snapshot(args.backup, archive, secret=secret, policy=policy)
                    with archive.open("rb") as source:
                        shutil.copyfileobj(source, sys.stdout.buffer)
            else:
                export_snapshot(args.backup, Path(args.output), secret=secret, policy=policy)
                print("脱敏包已生成（自由文本仍按受限资料处理）")
        elif args.command in {"run", "doctor"}:
            from test_agent.snapshot.pipeline import run_pipeline, validate_config

            config = json.loads(args.config.read_text())
            source = Path(__file__).resolve().parents[2]
            validate_config(config, source)
            if args.command == "doctor":
                missing = [
                    name
                    for name in (
                        "alembic",
                        "sqlalchemy",
                        "pytest",
                        "pytest_asyncio",
                        "anyio",
                        "aiosqlite",
                    )
                    if importlib.util.find_spec(name) is None
                ]
                if missing:
                    raise ValueError("缺少依赖：" + ", ".join(missing))
                print("本地配置结构与执行依赖检查通过；未连接服务器、未验证远端路径或运行产品")
            else:
                result = run_pipeline(config, source)
                print(
                    json.dumps(
                        {key: result.get(key) for key in ("status", "run_dir", "stage", "error")},
                        ensure_ascii=False,
                    )
                )
                return 0 if result["status"] == "pass" else 1
        return 0
    except (Exception, KeyboardInterrupt) as error:
        # 不打印数据库行、输入文本或密钥；详细业务失败只进入私密运行目录。
        print(f"操作失败：{type(error).__name__}: {error}", file=sys.stderr)
        return 1
    finally:
        os.umask(previous_umask)


if __name__ == "__main__":
    raise SystemExit(main())
