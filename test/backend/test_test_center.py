"""测试中心的公开服务接口：登记、修订固定、批次结果与隔离。"""

import json
import sys
from pathlib import Path

import pytest

from app.services.test_center import TestCenter


def source(tmp_path):
    root = tmp_path / "repo"
    (root / "test_agent/catalog").mkdir(parents=True)
    (root / "test/backend").mkdir(parents=True)
    (root / "test/backend/test_sample.py").write_text("def test_ok():\n    assert True\n")
    definition = {
        "id": "sample",
        "title": "示例",
        "module": "基础",
        "kind": "api",
        "core": True,
        "inputs": ["执行允许路径"],
        "assertions": ["状态正确"],
        "targets": ["test/backend/test_sample.py"],
        "timeout": 30,
    }
    (root / "test_agent/catalog/sample.json").write_text(json.dumps(definition))
    return root


def test_catalog_is_idempotent_and_run_freezes_revision(tmp_path):
    root = source(tmp_path)
    center = TestCenter(root, tmp_path / "control")
    first = center.catalog()["cases"][0]
    assert center.catalog()["cases"][0]["revision"] == first["revision"]
    job = center.enqueue(["sample"])
    path = root / "test_agent/catalog/sample.json"
    definition = json.loads(path.read_text())
    definition["assertions"] = ["新的断言"]
    path.write_text(json.dumps(definition))
    assert center.catalog()["cases"][0]["revision"] != first["revision"]
    center.set_case("sample", core=False, archived=True)
    assert center.get_run(job["id"])["cases"][0]["revision"] == first["revision"]
    assert center.get_run(job["id"])["cases"][0]["definition"]["assertions"] == ["状态正确"]
    with pytest.raises(ValueError):
        center.enqueue(["sample"])


def test_worker_uses_frozen_source_and_discards_business_copies(tmp_path):
    from test_agent.center.worker import run_once

    root = source(tmp_path)
    # 把执行器放进受控源码，业务数据/环境凭据不应复制过去。
    import shutil

    implementation = Path(__file__).resolve().parents[2] / "test_agent/center"
    shutil.copytree(implementation, root / "test_agent/center")
    (root / ".env").write_text("MUST_NOT_BE_COPIED=secret")
    (root / "data").mkdir()
    (root / "data/original").write_text("keep")
    (root / "test/backend/test_sample.py").write_text("""from pathlib import Path
import os

def test_isolation():
    assert not Path('.env').exists()
    assert not Path('data/original').exists()
    assert not os.environ.get('PAYMENT_SECRET')
    Path('data').mkdir(exist_ok=True)
    assert not Path('data/written').exists()
    Path('data/written').write_text('temporary')
""")
    center = TestCenter(root, tmp_path / "control")
    first = center.enqueue(["sample"])
    second = center.enqueue(["sample"])
    # 排队后修改源码不影响固定批次。
    (root / "test/backend/test_sample.py").write_text("def test_fail():\n    assert False\n")
    for job in (first, second):
        assert run_once(center, python=sys.executable)
        result = center.get_run(job["id"])
        assert result["status"] == "pass"
        assert result["cases"][0]["counts"]["tests"] == 1
        assert not (center.root / "runs" / job["id"] / "work").exists()
    assert (root / "data/original").read_text() == "keep"


def test_cancel_and_zero_executed_tests_never_pass(tmp_path):
    import shutil

    from test_agent.center.worker import run_once

    root = source(tmp_path)
    shutil.copytree(
        Path(__file__).resolve().parents[2] / "test_agent/center", root / "test_agent/center"
    )
    center = TestCenter(root, tmp_path / "control")
    canceled = center.enqueue(["sample"])
    center.cancel(canceled["id"])
    run_once(center, python=sys.executable)
    assert center.get_run(canceled["id"])["status"] == "cancelled"
    (root / "test/backend/test_sample.py").write_text(
        "import pytest\n@pytest.mark.skip(reason='尚未实现')\ndef test_todo(): pass\n"
    )
    skipped = center.enqueue(["sample"])
    run_once(center, python=sys.executable)
    assert center.get_run(skipped["id"])["status"] == "incomplete"
    assert center.get_run(canceled["id"])["status"] == "cancelled"


def test_release_cannot_be_passed_with_partial_selection_or_dirty_source(tmp_path):
    import subprocess

    root = source(tmp_path)

    def git(*args):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)

    git("init")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "测试")
    git("add", ".")
    git("commit", "-m", "测试基线")
    git("tag", "v1.0.0")
    center = TestCenter(root, tmp_path / "control")
    accepted = center.enqueue(["sample"], mode="release")
    assert accepted["build"]["tag"] == "v1.0.0"
    assert accepted["required"] == ["sample"]
    (root / "test/backend/test_sample.py").write_text("def test_updated(): assert True\n")
    with pytest.raises(ValueError, match="干净 tag"):
        center.enqueue(["sample"], mode="release")
    git("add", ".")
    git("commit", "-m", "开发中")
    catalog = center.catalog()
    assert catalog["build"]["label"] == "v1.0.0 · 开发中"
    assert center.get_run(accepted["id"])["build"]["tag"] == "v1.0.0"


def test_worker_timeout_and_active_cancellation(tmp_path):
    import shutil
    import threading
    import time

    from test_agent.center.worker import run_once

    root = source(tmp_path)
    shutil.copytree(
        Path(__file__).resolve().parents[2] / "test_agent/center", root / "test_agent/center"
    )
    (root / "test/backend/test_sample.py").write_text(
        "import time\ndef test_wait(): time.sleep(30)\n"
    )
    path = root / "test_agent/catalog/sample.json"
    value = json.loads(path.read_text())
    value["timeout"] = 1
    path.write_text(json.dumps(value))
    center = TestCenter(root, tmp_path / "control")
    timeout = center.enqueue(["sample"])
    run_once(center)
    assert center.get_run(timeout["id"])["status"] == "error"
    assert center.get_run(timeout["id"])["cases"][0]["error"] == "执行超时"
    value["timeout"] = 30
    path.write_text(json.dumps(value))
    canceled = center.enqueue(["sample"])
    thread = threading.Thread(target=run_once, args=(center,))
    thread.start()
    for _ in range(100):
        if center.get_run(canceled["id"])["cases"][0]["status"] == "running":
            break
        time.sleep(0.02)
    center.cancel(canceled["id"])
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert center.get_run(canceled["id"])["status"] == "cancelled"
    assert not (center.root / "runs" / canceled["id"] / "work").exists()
