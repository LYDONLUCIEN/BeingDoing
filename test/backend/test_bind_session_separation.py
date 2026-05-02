"""bind_session 职责拆分测试 — 验证 _resolve_report_context 不再内部调 bind_session"""

import re
from pathlib import Path

import pytest

ROUTES_FILE = (
    Path(__file__).resolve().parents[2]
    / "src" / "backend" / "app" / "api" / "v1"
    / "simple_chat_routes.py"
)


def _get_function_body(content: str, func_name: str) -> str | None:
    """提取函数体（从 def 到下一个同级 def 之前）"""
    pattern = re.compile(rf'^def {re.escape(func_name)}\b', re.MULTILINE)
    m = pattern.search(content)
    if not m:
        return None
    start = m.start()
    # 计算函数定义行的缩进
    line_start = content.rfind("\n", 0, start) + 1
    indent_line = content[line_start:start]
    indent = len(indent_line) - len(indent_line.lstrip())
    # 函数结束：下一个同级或更低缩进的 def/class，或文件末尾
    if indent > 0:
        end_pattern = re.compile(rf'\n(?!\s{{{indent}}})\S', re.MULTILINE)
    else:
        end_pattern = re.compile(r'\n\S', re.MULTILINE)
    end_match = end_pattern.search(content, start + 1)
    end = start + end_match.start() + 1 if end_match else len(content)
    return content[start:end]


def _get_endpoint_blocks(content: str) -> list[tuple[str, str, str, str]]:
    """解析所有 @router 装饰的端点，返回 (method, path, func_name, block)"""
    pattern = re.compile(
        r'@router\.(get|post|put|delete|patch)\(\s*"([^"]+)"',
        re.MULTILINE,
    )
    endpoints = []
    for m in pattern.finditer(content):
        method = m.group(1).upper()
        path = m.group(2)
        start = m.end()
        func_match = re.search(r'async\s+def\s+(\w+)\s*\(', content[start : start + 200])
        if not func_match:
            continue
        func_name = func_match.group(1)
        func_start = start + func_match.start()
        next_decorator = re.search(r'\n@router\.', content[func_start + 1 :])
        if next_decorator:
            block_end = func_start + 1 + next_decorator.start()
        else:
            block_end = len(content)
        block = content[func_start:block_end]
        endpoints.append((method, path, func_name, block))
    return endpoints


class TestResolveReportContextNoBindSession:
    """_resolve_report_context 不应内部调 bind_session"""

    def test_resolve_report_context_no_bind_session(self):
        """_resolve_report_context 函数体中不应有 bind_session 调用"""
        content = ROUTES_FILE.read_text(encoding="utf-8")
        body = _get_function_body(content, "_resolve_report_context")
        assert body is not None, "未找到 _resolve_report_context 函数"
        has_bind = "bind_session(" in body
        assert not has_bind, (
            "_resolve_report_context 不应内部调用 bind_session。"
            "bind_session 应由调用方在需要时显式调用。"
        )

    def test_resolve_report_context_no_readonly_param(self):
        """_resolve_report_context 不应有 readonly 参数（已不调 bind_session，不需要）"""
        content = ROUTES_FILE.read_text(encoding="utf-8")
        assert "readonly" not in content, (
            "_resolve_report_context 不应有 readonly 参数"
        )


class TestGetEndpointsNoBindSessionInCallChain:
    """GET 端点的完整调用链中不应出现 bind_session"""

    def test_history_get_no_bind(self):
        """/simple-chat/history (GET) 不应调 bind_session"""
        content = ROUTES_FILE.read_text(encoding="utf-8")
        endpoints = _get_endpoint_blocks(content)
        for method, path, func_name, block in endpoints:
            if method == "GET" and "history" in path:
                assert "bind_session(" not in block, (
                    f"GET /{path} ({func_name}) 不应调用 bind_session"
                )
                return
        assert False, "未找到 GET /simple-chat/history"

    def test_rumination_get_table_no_bind(self):
        """/simple-chat/rumination-get-table (GET) 不应调 bind_session"""
        content = ROUTES_FILE.read_text(encoding="utf-8")
        endpoints = _get_endpoint_blocks(content)
        for method, path, func_name, block in endpoints:
            if method == "GET" and "rumination-get-table" in path:
                assert "bind_session(" not in block, (
                    f"GET /{path} ({func_name}) 不应调用 bind_session"
                )
                return
        assert False, "未找到 GET /simple-chat/rumination-get-table"


class TestPostEndpointsBindExplicitly:
    """需要绑定的 POST 端点应显式调 bind_session（不再依赖隐式调用）"""

    POST_ENDPOINTS_NEEDING_BIND = [
        "simple-chat/init",
        "simple-chat/message",
        "thread/reopen",
        "thread/complete",
    ]

    @pytest.mark.parametrize("endpoint_path", POST_ENDPOINTS_NEEDING_BIND)
    def test_post_endpoints_bind_explicitly(self, endpoint_path):
        content = ROUTES_FILE.read_text(encoding="utf-8")
        endpoints = _get_endpoint_blocks(content)
        for method, path, func_name, block in endpoints:
            if method == "POST" and endpoint_path in path:
                assert "resolve_report_context(" in block, (
                    f"POST /{path} ({func_name}) 应调用 _resolve_report_context"
                )
                assert "bind_session(" in block, (
                    f"POST /{path} ({func_name}) 应显式调用 bind_session"
                )
                return
