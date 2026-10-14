"""每次业务回放从新源码/数据库/进程开始；不连接 dev 正在服务用户的后端。"""

import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

from app.services.test_center import encode, source_files


def prepare_workspace(source, work, run_id):
    from test_agent.center.worker import environment

    work = work.resolve()
    for path in source_files(source):
        target = work / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
    (work / "tmp").mkdir()
    (work / ".test-center-workspace.json").write_text(
        encode({"root": str(work.resolve()), "run_id": run_id})
    )
    env = environment(work)
    if os.environ.get("TEST_CENTER_AI_API_KEY"):
        env["TEST_CENTER_AI_API_KEY"] = os.environ["TEST_CENTER_AI_API_KEY"]
    return env


async def execute_workflow(center, run, case, checkpoint=None):
    from test_agent.center.ai_runner import aggregate

    definition = case["definition"]
    folder = center.root / "runs" / run["id"] / "artifacts" / case["id"]
    folder.mkdir(parents=True, exist_ok=True)
    result = {"status": "running", "attempts": [], "executor": "existing-api-workflow-v1"}
    started = time.monotonic()
    try:
        for repeat in range(definition["repeats"]):
            if center.cancelled(run["id"]):
                raise InterruptedError("批次已取消")
            output = folder / f"workflow-{repeat + 1}.json"
            with tempfile.TemporaryDirectory(prefix="beingdoing-workflow-") as directory:
                work = Path(directory)
                env = prepare_workspace(center.source, work, run["id"])
                with (folder / f"workflow-{repeat + 1}.log").open("w") as log:
                    process = await asyncio.create_subprocess_exec(
                        sys.executable,
                        "-m",
                        "test_agent.center.workflow_runtime",
                        str(center.root),
                        run["id"],
                        case["id"],
                        str(repeat),
                        str(output),
                        cwd=work,
                        env=env,
                        stdout=log,
                        stderr=asyncio.subprocess.STDOUT,
                    )
                    try:
                        while process.returncode is None:
                            if time.monotonic() - started > definition["timeout"]:
                                raise TimeoutError("业务回放超时")
                            if output.exists() and checkpoint:
                                current = json.loads(output.read_text())
                                checkpoint(
                                    {
                                        **result,
                                        "attempts": result["attempts"]
                                        + current.get("attempts", []),
                                    }
                                )
                            try:
                                await asyncio.wait_for(process.wait(), 0.25)
                            except asyncio.TimeoutError:
                                pass
                    finally:
                        if process.returncode is None:
                            process.terminate()
                            try:
                                await asyncio.wait_for(process.wait(), 3)
                            except asyncio.TimeoutError:
                                process.kill()
                                await process.wait()
                if not output.exists() or process.returncode != 0:
                    raise RuntimeError("业务回放子进程未正常结束，请检查本次日志")
                current = json.loads(output.read_text())
                result["attempts"].extend(current.get("attempts", []))
                if current["status"] in {"error", "incomplete", "cancelled"}:
                    result.update(status=current["status"], error=current.get("error"))
                    break
        if result["status"] == "running":
            result["status"] = aggregate({a["status"] for a in result["attempts"]})
    except Exception as error:
        result.update(
            status="cancelled" if isinstance(error, InterruptedError) else "error", error=str(error)
        )
    result["counts"] = {
        "tests": len(result["attempts"]),
        "passed": sum(a["status"] == "pass" for a in result["attempts"]),
        "failures": sum(a["status"] == "fail" for a in result["attempts"]),
        "errors": sum(a["status"] == "error" for a in result["attempts"]),
        "needs_review": sum(a["status"] == "needs_review" for a in result["attempts"]),
        "planned": len(definition["steps"]) * definition["repeats"],
    }
    if checkpoint:
        checkpoint(result)
    return result
