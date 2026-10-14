"""拉取、导入、迁移、按套件重置和执行。永远不写生产或现有 dev 数据。"""

import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

from test_agent.snapshot.archive import (
    MAX_BYTES,
    export_snapshot,
    fresh_directory,
    import_snapshot,
    sha,
    verify_snapshot,
    write_json,
)


def isolated_environment(work):
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "TMPDIR": str(work / "tmp"),
        "APP_ENV": "test",
        "DEBUG": "False",
        "AUDIO_MODE": "False",
        "PYTHONDONTWRITEBYTECODE": "1",
        "SECRET_KEY": "snapshot-copy-independent-test-key-0000000000000000",
        "DATABASE_URL": f"sqlite+aiosqlite:///{work}/app.db",
        "PYTHONPATH": os.pathsep.join([str(work), str(work / "src/backend")]),
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "TOKENIZERS_PARALLELISM": "false",
        "BD_SNAPSHOT_WORKSPACE": str(work),
    }


def run_child(command, *, cwd, env, log, timeout, stdout=None):
    with log.open("wb") as stream:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=stdout or stream,
            stderr=stream,
            start_new_session=True,
        )
        try:
            deadline = time.monotonic() + timeout
            while process.poll() is None:
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(command, timeout)
                if os.fstat(stream.fileno()).st_size > 64 * 1024**2:
                    raise RuntimeError("日志超过 64 MiB，停止执行")
                if stdout and os.fstat(stdout.fileno()).st_size > MAX_BYTES:
                    raise RuntimeError("传输包超过大小限制")
                try:
                    return process.wait(timeout=0.2)
                except subprocess.TimeoutExpired:
                    pass
            return process.returncode
        finally:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except PermissionError:
                if process.poll() is None:
                    raise
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()


def validate_config(config, source):
    allowed = {
        "state_root",
        "source",
        "migration_target",
        "migration_timeout",
        "allow_row_count_changes",
        "file_migrations",
        "suites",
        "regression_cases",
    }
    if set(config) - allowed:
        raise ValueError("配置含未知字段，请对照使用手册")
    root = Path(config["state_root"])
    if (
        not root.is_absolute()
        or root.resolve().is_relative_to(source.resolve())
        or source.resolve().is_relative_to(root.resolve())
    ):
        raise ValueError("state_root 必须是仓库之外的独立绝对目录")
    if root.is_symlink():
        raise ValueError("state_root 不能是符号链接")
    origin = config["source"]
    required = {
        "local_backup": {"backup", "key_file"},
        "archive": {"path"},
        "ssh_export": {"host", "python", "script", "backup", "key_file"},
    }
    kind = origin.get("kind")
    if kind not in required or any(
        not isinstance(origin.get(key), str) or not origin[key] for key in required[kind]
    ):
        raise ValueError("source 类型未知或缺少必需的路径/账号配置")
    path_keys = required[kind] - {"host"}
    if any(not Path(origin[key]).is_absolute() for key in path_keys):
        raise ValueError("source 路径必须为绝对路径，不能依赖当前目录或 shell 展开")
    if kind == "ssh_export" and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]*", origin["host"]):
        raise ValueError("SSH host 格式无效")
    if origin.get("kind") == "local_backup":
        backup = Path(origin["backup"]).resolve()
        if root.resolve().is_relative_to(backup) or backup.is_relative_to(root.resolve()):
            raise ValueError("state_root 与源备份必须互相独立")
    suites = config.get("suites", [])
    if not suites:
        raise ValueError("至少配置一个真实测试套件")
    ids = set()
    for suite in suites:
        name = suite["id"]
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", name) or name in ids:
            raise ValueError("套件 id 非法或重复")
        ids.add(name)
        if not suite.get("targets"):
            raise ValueError("套件不能没有测试入口")
        for target in suite["targets"]:
            if not re.fullmatch(
                r"(?:test/backend/test_[\w]+|test_agent/snapshot/(?:cases|test_[\w]+))\.py(?:::[\w\[\]-]+)*",
                target,
            ):
                raise ValueError("只能执行固定源码内的测试文件或节点")
            if not (source / target.split("::")[0]).is_file():
                raise ValueError("配置中的测试文件不存在")
    return root


def fetch(config, archive, evidence):
    kind = config["kind"]
    if kind == "local_backup":
        policy = (
            json.loads(Path(config["policy_file"]).read_text())
            if config.get("policy_file")
            else None
        )
        export_snapshot(
            Path(config["backup"]),
            archive,
            secret=Path(config["key_file"]).read_bytes(),
            policy=policy,
        )
    elif kind == "archive":
        with Path(config["path"]).open("rb") as source, archive.open("xb") as dest:
            shutil.copyfileobj(source, dest)
    elif kind == "ssh_export":
        host = config["host"]
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]*", host):
            raise ValueError("SSH host 必须是已配置的主机别名或 user@host")
        arguments = [
            config["python"],
            config["script"],
            "export",
            "--backup",
            config["backup"],
            "--key-file",
            config["key_file"],
            "--output",
            "-",
        ]
        if config.get("policy_file"):
            arguments += ["--policy", config["policy_file"]]
        command = [
            "ssh",
            "-T",
            "-oBatchMode=yes",
            "-oStrictHostKeyChecking=yes",
            "-oConnectTimeout=15",
            host,
            shlex.join(arguments),
        ]
        with archive.open("xb") as output:
            code = run_child(
                command,
                cwd=evidence,
                env=None,
                log=evidence / "transfer.log",
                timeout=config.get("timeout", 900),
                stdout=output,
            )
        if code != 0:
            raise RuntimeError("SSH 脱敏传输失败，见 transfer.log")
    else:
        raise ValueError("source.kind 必须是 local_backup / archive / ssh_export")
    os.chmod(archive, 0o600)


def workspace(source, baseline, target):
    shutil.copytree(source, target)
    shutil.copy2(baseline / "database.sqlite", target / "app.db")
    if (baseline / "data").exists():
        shutil.copytree(baseline / "data", target / "data")
    (target / "tmp").mkdir()
    if not (target / "pytest.ini").exists():
        (target / "pytest.ini").write_text("[pytest]\nasyncio_mode = auto\n")
    write_json(target / ".snapshot-workspace.json", {"root": str(target.resolve())})
    return isolated_environment(target.resolve())


def run_regression(config, frozen, source, run):
    """复用测试中心固定 API/UI 用例；结果明确标注这些使用既有夹具。"""
    from test_agent.center.worker import run_once

    from app.services.test_center import TestCenter

    for relative in ("src/frontend", "test_agent/l2"):
        modules = source / relative / "node_modules"
        if modules.is_dir():
            (frozen / relative).mkdir(parents=True, exist_ok=True)
            (frozen / relative / "node_modules").symlink_to(modules, target_is_directory=True)
    center = TestCenter(frozen, run / "regression")
    available = {
        item["id"]: item
        for item in center.catalog()["cases"]
        if item["available"] and not item["archived"]
    }
    selected = config["regression_cases"]
    if selected == ["@core"]:
        selected = [key for key, item in available.items() if item["core"]]
    if not selected or any(key not in available for key in selected):
        raise ValueError("普通回归用例不存在、不可用或为空")
    if any(available[key]["definition"]["kind"] == "ai" for key in selected):
        raise ValueError("本流水线禁止外部 AI；真实 AI 仍需使用现有测试中心的已审阅上下文和预算")
    job = center.enqueue(selected, mode="diagnostic")
    if not run_once(center, python=sys.executable):
        raise RuntimeError("回归执行器未领取任务")
    result = center.get_run(job["id"])
    return {
        "status": result["status"],
        "run_id": job["id"],
        "data_source": "existing-test-fixtures",
        "cases": [
            {key: case.get(key) for key in ("id", "status", "counts", "error")}
            for case in result["cases"]
        ],
    }


def run_pipeline(config, source):
    from test_agent.center.worker import pytest_result

    from app.services.test_center import source_files

    source = Path(source).resolve()
    root = validate_config(config, source)
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    if shutil.disk_usage(root).free < 512 * 1024**2:
        raise ValueError("剩余空间不足 512 MiB，拒绝开始")
    run = fresh_directory(
        root / "runs" / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:12])
    )
    result = {
        "status": "running",
        "run_dir": str(run),
        "suites": [],
        "scope": "snapshot-migration-and-selected-suites",
        "deployment": "not-performed",
    }
    stage = "prepare"
    try:
        frozen = fresh_directory(run / "source")
        hashes = {}
        for path in source_files(source):
            relative = path.relative_to(source)
            data = path.read_bytes()
            destination = frozen / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            hashes[str(relative)] = hashlib.sha256(data).hexdigest()
        write_json(run / "source-hashes.json", hashes)
        result["source_digest"] = hashlib.sha256(
            json.dumps(hashes, sort_keys=True).encode()
        ).hexdigest()
        git_result = subprocess.run(
            ["git", "-C", str(source), "rev-parse", "HEAD"], capture_output=True, text=True
        )
        result["git_commit"] = git_result.stdout.strip() if git_result.returncode == 0 else None
        result["python_version"] = sys.version.split()[0]
        stage = "fetch"
        archive = run / "snapshot.tar.gz"
        fetch(config["source"], archive, run)
        result["archive_sha256"] = sha(archive)
        stage = "import"
        baseline = run / "baseline"
        result["snapshot"] = import_snapshot(archive, baseline)
        stage = "migration"
        work = run / "migration-work"
        env = workspace(frozen, baseline, work)
        migration = fresh_directory(run / "migration")
        command = [
            sys.executable,
            "-m",
            "test_agent.snapshot.runtime",
            "migrate",
            str(migration),
            config.get("migration_target", "head"),
        ]
        code = run_child(
            command,
            cwd=work,
            env=env,
            log=migration / "execution.log",
            timeout=config.get("migration_timeout", 300),
        )
        if code != 0 or not (migration / "migration.json").is_file():
            raise RuntimeError("旧库迁移失败；后续测试未执行")
        result["migration"] = json.loads((migration / "migration.json").read_text())
        before, after = result["migration"]["counts_before"], result["migration"]["counts_after"]
        allowed = set(config.get("allow_row_count_changes", []))
        changed = [
            table
            for table, count in before.items()
            if table != "alembic_version" and table not in allowed and after.get(table) != count
        ]
        if changed:
            raise RuntimeError("迁移改变了未批准的表行数：" + ", ".join(changed))
        for index, entry in enumerate(config.get("file_migrations", [])):
            path = entry["script"]
            if (
                not re.fullmatch(r"(?:scripts|src/backend/scripts)/[\w]+\.py", path)
                or not (work / path).is_file()
            ):
                raise ValueError("文件迁移脚本必须存在于固定源码目录")
            command = [
                sys.executable,
                "-m",
                "test_agent.snapshot.runtime",
                "file-migration",
                str(migration),
                path,
                *entry.get("args", []),
            ]
            if (
                run_child(
                    command,
                    cwd=work,
                    env=env,
                    log=migration / f"files-{index}.log",
                    timeout=config.get("migration_timeout", 300),
                )
                != 0
            ):
                raise RuntimeError("文件迁移失败；后续测试未执行")
        if config.get("file_migrations"):
            command = [sys.executable, "-m", "test_agent.snapshot.runtime", "state", str(migration)]
            if (
                run_child(
                    command,
                    cwd=work,
                    env=env,
                    log=migration / "final-state.log",
                    timeout=config.get("migration_timeout", 300),
                )
                != 0
            ):
                raise RuntimeError("文件迁移后的数据库检查失败")
            final_state = json.loads((migration / "final-state.json").read_text())
            if final_state["revisions"] != result["migration"]["after"]:
                raise RuntimeError("文件迁移意外改变数据库版本")
            if any(
                final_state["counts"].get(table) != count
                for table, count in before.items()
                if table not in allowed and table != "alembic_version"
            ):
                raise RuntimeError("文件迁移改变了未批准的数据库行数")
            result["migration"]["counts_after"] = final_state["counts"]
        upgraded = fresh_directory(run / "upgraded")
        shutil.copy2(work / "app.db", upgraded / "database.sqlite")
        if (work / "data").exists():
            shutil.copytree(work / "data", upgraded / "data")
        shutil.rmtree(work)
        stage = "tests"
        for suite in config["suites"]:
            evidence = fresh_directory(run / "suites" / suite["id"])
            work = run / ("work-" + suite["id"])
            env = workspace(frozen, upgraded, work)
            command = [
                sys.executable,
                "-m",
                "test_agent.snapshot.runtime",
                "pytest",
                str(evidence),
                *suite["targets"],
            ]
            try:
                code = run_child(
                    command,
                    cwd=work,
                    env=env,
                    log=evidence / "execution.log",
                    timeout=suite.get("timeout", 300),
                )
                status, counts = pytest_result(evidence / "results.xml", code)
                item = {"id": suite["id"], "status": status, "counts": counts}
            except subprocess.TimeoutExpired:
                item = {"id": suite["id"], "status": "error", "error": "执行超时"}
            finally:
                shutil.rmtree(work)
            result["suites"].append(item)
            write_json(run / "result.json", result)
        verify_snapshot(baseline)
        result["status"] = (
            "pass" if all(s["status"] == "pass" for s in result["suites"]) else "fail"
        )
        if config.get("regression_cases"):
            stage = "regression"
            result["regression"] = run_regression(config, frozen, source, run)
            if result["regression"]["status"] != "pass":
                result["status"] = "fail"
    except (Exception, KeyboardInterrupt) as error:
        result.update(status="error", stage=stage, error=str(error))
    finally:
        write_json(run / "result.json", result)
    return result
