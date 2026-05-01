"""E2E 测试 runner — playwright 占位"""
import os


def run(items):
    """E2E playwright 占位。playwright 未配置时返回 skipped。"""
    result = {
        "test_type": "e2e",
        "total": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 1,
        "errors": 0,
        "duration": 0.0,
        "details": [],
        "raw_output": "SKIPPED: E2E 测试框架（playwright）尚未配置。如需启用：\n  1. npm install -D @playwright/test\n  2. npx playwright install chromium\n  3. 在 claude-test/e2e/ 中编写 .spec.ts 文件\n  注意：E2E 测试需要前后端服务运行中（./start.sh start-dev）。",
    }
    return result
