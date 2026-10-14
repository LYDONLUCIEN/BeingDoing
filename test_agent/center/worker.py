"""独立串行 worker；仅执行固定源码中的登记入口，不在 Web 应用中执行测试。"""

import argparse
import fcntl
import hashlib
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from app.services.test_center import TestCenter, encode


def heartbeat(center):
    temporary = center.root / "heartbeat.tmp"
    temporary.write_text(
        encode(
            {
                "pid": os.getpid(),
                "time": time.time(),
                "ai_key_ready": bool(os.environ.get("TEST_CENTER_AI_API_KEY")),
            }
        )
    )
    temporary.replace(center.root / "heartbeat.json")


def environment(work):
    # 白名单而不是删掉几个已知密钥：测试进程不继承服务端生产凭据。
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(work),
        "TMPDIR": str(work / "tmp"),
        "APP_ENV": "test",
        "DEBUG": "False",
        "AUDIO_MODE": "False",
        "SECRET_KEY": "test-center-isolated-key-not-for-production-000000",
        "DATABASE_URL": f"sqlite+aiosqlite:///{work}/app.db",
        "NEXT_TELEMETRY_DISABLED": "1",
        "PYTHONPATH": os.pathsep.join([str(work), str(work / "src/backend")]),
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "TOKENIZERS_PARALLELISM": "false",
    }


def pytest_result(path, returncode):
    try:
        root = ET.parse(path).getroot()
        suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
        counts = {
            key: sum(int(s.get(key, 0)) for s in suites)
            for key in ("tests", "failures", "errors", "skipped")
        }
        if counts["errors"] or returncode not in {0, 1, 5}:
            status = "error"
        elif counts["failures"] or returncode == 1:
            status = "fail"
        elif counts["tests"] == 0 or counts["skipped"] or returncode == 5:
            status = "incomplete"
        else:
            status = "pass"
        return status, counts
    except (OSError, ValueError, ET.ParseError):
        return "error", {}


def stop_process(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
    except ProcessLookupError:
        pass
    except PermissionError:
        # macOS 沙箱可能对已消失的进程组返回 EPERM；活进程仍必须报错。
        if process.poll() is None:
            raise


def execute(center, run, case, python):
    folder = center.root / "runs" / run["id"]
    snapshot = folder / "source"
    work = folder / "work"
    artifacts = folder / "artifacts" / case["id"]
    artifacts.mkdir(parents=True, exist_ok=True)
    started = time.time()
    process = None
    try:
        expected = json.loads((folder / "source-hashes.json").read_text())
        for relative, checksum in expected.items():
            if hashlib.sha256((snapshot / relative).read_bytes()).hexdigest() != checksum:
                raise ValueError("固定源码快照被修改，拒绝运行")
        shutil.copytree(snapshot, work)
        (work / "tmp").mkdir()
        env = environment(work)
        definition = case["definition"]
        if definition["kind"] == "ai":
            if os.environ.get("TEST_CENTER_AI_API_KEY"):
                env["TEST_CENTER_AI_API_KEY"] = os.environ["TEST_CENTER_AI_API_KEY"]
            command = [
                python,
                "-m",
                "test_agent.center.ai_runner",
                str(center.root),
                run["id"],
                case["id"],
                str(artifacts / "results.json"),
            ]
        elif definition["kind"] == "api":
            command = [
                python,
                "-m",
                "pytest",
                *definition["targets"],
                "-q",
                "--tb=short",
                "-p",
                "pytest_asyncio.plugin",
                "-p",
                "anyio.pytest_plugin",
                "-p",
                "test_agent.center.network_guard",
                f"--junitxml={artifacts / 'results.xml'}",
            ]
        else:
            # 共享安装好的只读依赖；源码、Next 编译缓存、浏览器状态每例独立。
            for relative in ("src/frontend", "test_agent/l2"):
                modules = center.source / relative / "node_modules"
                if not modules.is_dir():
                    raise ValueError(f"缺少浏览器依赖，请先安装 {relative}")
                (work / relative / "node_modules").symlink_to(modules, target_is_directory=True)
            # 浏览器可执行文件是安装产物，不是账号数据。通过显式路径传递。
            cache = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
            if not cache:
                cache = str(
                    Path.home()
                    / (
                        "Library/Caches/ms-playwright"
                        if sys.platform == "darwin"
                        else ".cache/ms-playwright"
                    )
                )
            env["PLAYWRIGHT_BROWSERS_PATH"] = cache
            command = [
                "node",
                str(work / "test_agent/l2/center_runner.mjs"),
                definition["targets"][0],
                str(artifacts),
            ]
            if definition["targets"] == ["scenario"]:
                scenario = work / "scenario.json"
                scenario.write_text(encode(definition))
                command.append(str(scenario))
        with (artifacts / "execution.log").open("w") as log:
            supervised = [
                python,
                str(work / "test_agent/center/supervise.py"),
                str(os.getpid()),
                *command,
            ]
            process = subprocess.Popen(
                supervised,
                cwd=work,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            while process.poll() is None:
                heartbeat(center)
                if center.cancelled(run["id"]) and definition["kind"] != "ai":
                    case["status"] = "cancelled"
                    break
                if time.time() - started > definition.get("timeout", 180) + (
                    100 if definition["kind"] == "ai" else 0
                ):
                    case.update(status="error", error="执行超时")
                    break
                time.sleep(0.2)
            if case["status"] != "running":
                stop_process(process)
                process = None
            elif definition["kind"] == "ai":
                report = json.loads((artifacts / "results.json").read_text())
                case.update(report)
                if process.returncode != 0 or case["status"] not in {
                    "pass",
                    "fail",
                    "needs_review",
                    "incomplete",
                    "cancelled",
                    "error",
                }:
                    case.update(status="error", error="AI 执行器未正常结束")
            elif definition["kind"] == "api":
                case["status"], case["counts"] = pytest_result(
                    artifacts / "results.xml", process.returncode
                )
                if case["status"] != "pass" and (artifacts / "results.xml").exists():
                    failures = []
                    for test in ET.parse(artifacts / "results.xml").iter("testcase"):
                        for evidence in test:
                            if evidence.tag in {"failure", "error", "skipped"}:
                                failures.append(
                                    f"{test.get('name')}: {evidence.get('message', evidence.tag)}"
                                )
                    case["error"] = "\n".join(failures)[:6000]
            else:
                report = json.loads((artifacts / "results.json").read_text())
                case["counts"] = report.get("counts", {})
                case["status"] = (
                    "pass"
                    if process.returncode == 0
                    and report.get("passed") is True
                    and case["counts"].get("assertions", 0) > 0
                    else "fail"
                )
                case["error"] = report.get("error")
    except Exception as error:
        case.update(status="error", error=str(error))
    finally:
        if process is not None:
            # 即使父进程已退出，也清理同组的浏览器和 Next 子进程。
            stop_process(process)
        shutil.rmtree(work, ignore_errors=True)
        case["duration_ms"] = int((time.time() - started) * 1000)
        case["artifacts"] = sorted(p.name for p in artifacts.iterdir() if p.is_file())


def run_once(center, python=sys.executable):
    with (center.root / "worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("已有 worker 正在运行")
        heartbeat(center)
        # 拿到独占锁后仍为 running 的批次是前任进程中断的证据，不伪装成功或重跑覆盖。
        with center.db() as db:
            for row in db.execute("SELECT payload FROM runs WHERE status='running'").fetchall():
                old = json.loads(row[0])
                old.update(status="error", error="worker 中断，请新建重跑批次")
                for case in old["cases"]:
                    if case["status"] in {"queued", "running"}:
                        case["status"] = "error"
                db.execute(
                    "UPDATE runs SET status='error', payload=? WHERE id=?",
                    (encode(old), old["id"]),
                )
                shutil.rmtree(center.root / "runs" / old["id"] / "work", ignore_errors=True)
            row = db.execute(
                "SELECT payload FROM runs WHERE status='queued' ORDER BY created LIMIT 1"
            ).fetchone()
        if not row:
            return False
        run = json.loads(row[0])
        run["status"] = "running"
        run["runtime"] = {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "executor": "test-center-v2",
            "external_io": "explicit-ai-only" if run.get("ai") else "controlled",
        }
        center.save_run(run)
        for case in run["cases"]:
            if center.cancelled(run["id"]):
                case["status"] = "cancelled"
            else:
                case["status"] = "running"
                center.save_run(run)
                execute(center, run, case, python)
            center.save_run(run)
        statuses = {c["status"] for c in run["cases"]}
        run["status"] = next(
            (
                s
                for s in ("cancelled", "error", "fail", "incomplete", "needs_review")
                if s in statuses
            ),
            "pass",
        )
        run["finished"] = time.time()
        center.save_run(run)
        # 固定清单与摘要长期保留，临时执行源码完成后丢弃。
        shutil.rmtree(center.root / "runs" / run["id"] / "source", ignore_errors=True)
        return True


def main():
    parser = argparse.ArgumentParser(description="dev 专用测试 worker")
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if os.environ.get("APP_ENV", "").lower() not in {"development", "dev", "test"}:
        parser.error("必须明确 APP_ENV=development/dev/test；生产禁止启动")
    center = TestCenter(args.source, args.control)
    while True:
        run_once(center)
        if args.once:
            break
        time.sleep(2)


if __name__ == "__main__":
    main()
