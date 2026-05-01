"""前端测试 runner — vitest 占位"""
import subprocess
import sys
import os
import time

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_SCRIPT_DIR, "..", "..", ".."))


def run(items):
    """前端 vitest 占位。vitest 未安装时返回 skipped。"""
    result = {
        "test_type": "frontend",
        "total": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 1,
        "errors": 0,
        "duration": 0.0,
        "details": [],
        "raw_output": "SKIPPED: 前端测试框架（vitest）尚未安装。如需启用：\n  cd src/frontend && npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom\n  然后在 claude-test/frontend/ 中编写 .test.tsx 文件。",
    }
    return result
