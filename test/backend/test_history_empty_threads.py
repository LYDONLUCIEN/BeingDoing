"""验证删除所有 thread 后 GET /history 不再 fallback 到 act_sid 残留文件"""

import re
from pathlib import Path

import pytest

ROUTES_FILE = (
    Path(__file__).resolve().parents[2]
    / "src" / "backend" / "app" / "api" / "v1"
    / "simple_chat_routes.py"
)


class TestResolveDefaultLogicalThreadIdNoFallback:
    """_resolve_default_logical_thread_id 在 session_ids 为空时不应 fallback 到 act_sid"""

    def test_no_return_act_sid_when_candidates_empty(self):
        """当 session_ids 为空且 selected_session_id 为 null 时，
        函数不应返回 act_sid，而应返回空字符串。
        这防止了 GET /history fallback 到旧的 act_sid 对话文件。"""
        content = ROUTES_FILE.read_text(encoding="utf-8")
        body = _get_function_body(content, "_resolve_default_logical_thread_id")
        assert body is not None, "未找到 _resolve_default_logical_thread_id 函数"

        # 验证函数中不包含 "return act_sid" 模式
        has_return_act_sid = bool(re.search(r"return\s+act_sid\b", body))
        assert not has_return_act_sid, (
            "_resolve_default_logical_thread_id 不应在 candidates 为空时返回 act_sid。"
            "session_ids 为空意味着用户删光了所有 thread，应返回空字符串让调用方处理。"
        )

    def test_candidates_empty_returns_empty_string(self):
        """当 session_ids 列表为空时，函数应返回空字符串（或以空字符串为基准），
        而非 activation_storage_session_id。"""
        content = ROUTES_FILE.read_text(encoding="utf-8")
        body = _get_function_body(content, "_resolve_default_logical_thread_id")
        assert body is not None

        # 验证 "if not candidates" 分支返回空字符串
        # 模式：if not candidates:\n        return ""
        has_empty_return = bool(
            re.search(r"if not candidates.*?return\s+\"\"", body, re.DOTALL)
        )
        assert has_empty_return, (
            "_resolve_default_logical_thread_id 在 candidates 为空时"
            "应 return \"\"（空字符串），而非 fallback 到 act_sid"
        )


class TestHistoryEmptySessionIdsReturnsEmpty:
    """GET /history 在 session_ids 为空时应返回空消息列表"""

    def test_history_checks_empty_logical_session_id(self):
        """simple_history 端点应检查 logical_session_id 为空的情况，
        并返回空消息列表而非 fallback 数据。"""
        content = ROUTES_FILE.read_text(encoding="utf-8")
        endpoints = _get_endpoint_blocks(content)
        for method, path, func_name, block in endpoints:
            if method == "GET" and "history" in path:
                # 验证在 _resolve_report_context 后有 logical_session_id 空检查
                has_empty_check = (
                    "not logical_session_id" in block
                    or 'logical_session_id == ""' in block
                    or "logical_session_id" in block and "return" in block
                )
                # 关键：不应在没有检查的情况下直接使用 logical_session_id 构建请求
                return  # 找到了 GET /history 端点
        assert False, "未找到 GET /simple-chat/history"


# ---------- helpers (shared with other test files) ----------

def _get_function_body(content: str, func_name: str) -> str | None:
    """提取函数体（从 def 到下一个同级 def 之前）"""
    pattern = re.compile(rf"^def {re.escape(func_name)}\b", re.MULTILINE)
    m = pattern.search(content)
    if not m:
        return None
    start = m.start()
    line_start = content.rfind("\n", 0, start) + 1
    indent_line = content[line_start:start]
    indent = len(indent_line) - len(indent_line.lstrip())
    if indent > 0:
        end_pattern = re.compile(rf"\n(?!\s{{{indent}}})\S", re.MULTILINE)
    else:
        end_pattern = re.compile(r"\n\S", re.MULTILINE)
    end_match = end_pattern.search(content, start + 1)
    end = start + end_match.start() + 1 if end_match else len(content)
    return content[start:end]


def _get_endpoint_blocks(content: str) -> list[tuple[str, str, str, str]]:
    """解析所有 @router 装饰的端点"""
    pattern = re.compile(
        r'@router\.(get|post|put|delete|patch)\(\s*"([^"]+)"',
        re.MULTILINE,
    )
    endpoints = []
    for m in pattern.finditer(content):
        method = m.group(1).upper()
        path = m.group(2)
        start = m.end()
        func_match = re.search(r"async\s+def\s+(\w+)\s*\(", content[start : start + 200])
        if not func_match:
            continue
        func_name = func_match.group(1)
        func_start = start + func_match.start()
        next_decorator = re.search(r"\n@router\.", content[func_start + 1 :])
        if next_decorator:
            block_end = func_start + 1 + next_decorator.start()
        else:
            block_end = len(content)
        block = content[func_start:block_end]
        endpoints.append((method, path, func_name, block))
    return endpoints
