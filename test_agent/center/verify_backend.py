"""开发者回归入口：独立源码、数据库、文件根和网络边界。"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from test_agent.center.worker import environment, pytest_result

from app.services.test_center import SOURCE_DIRS, digest, source_files


def verify(source: Path, output: Path, targets: list[str]) -> dict:
    source, output = source.resolve(), output.resolve()
    if output == source or any(output.is_relative_to(source / p) for p in (*SOURCE_DIRS, "data")):
        raise ValueError("验证证据不能放入业务数据或被复制的源码目录")
    if not targets or any(
        target != "test/backend"
        and not re.fullmatch(r"test/backend/(?:[\w-]+/)*test_[\w]+\.py(?:::[\w\[\]-]+)*", target)
        for target in targets
    ):
        raise ValueError("验证目标只能是后端测试目录或固定 pytest 节点")
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("证据目录已有内容，请指定新目录，保留旧验证记录")
    with tempfile.TemporaryDirectory(prefix="beingdoing-backend-") as directory:
        work = Path(directory)
        hashes = {}
        for file in source_files(source):
            relative = file.relative_to(source)
            data = file.read_bytes()
            destination = work / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            hashes[str(relative)] = hashlib.sha256(data).hexdigest()
        (work / "tmp").mkdir()
        command = [
            sys.executable,
            "-m",
            "pytest",
            *targets,
            "-q",
            "-p",
            "pytest_asyncio.plugin",
            "-p",
            "anyio.pytest_plugin",
            "-p",
            "test_agent.center.network_guard",
            f"--junitxml={output / 'results.xml'}",
        ]
        with (output / "execution.log").open("w") as log:
            process = subprocess.run(
                command, cwd=work, env=environment(work), stdout=log, stderr=subprocess.STDOUT
            )
        status, counts = pytest_result(output / "results.xml", process.returncode)
        result = {
            "status": status,
            "counts": counts,
            "source_digest": digest(hashes),
            "targets": targets,
        }
        (output / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="新的验证证据目录")
    parser.add_argument("targets", nargs="*", default=["test/backend"])
    args = parser.parse_args()
    result = verify(Path(__file__).resolve().parents[2], args.output, args.targets)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
