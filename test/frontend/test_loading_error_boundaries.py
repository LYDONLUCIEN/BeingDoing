"""加载状态和错误边界测试 — 验证关键路由的 loading.tsx 和 error.tsx 存在且结构正确"""

import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2] / "src" / "frontend" / "app"

# 需要有 loading.tsx 的路由
ROUTES_NEEDING_LOADING = [
    # (相对路径描述, 文件路径)
    ("explore 路由", "app/(main)/explore/loading.tsx"),
    ("chat/[phase] 路由", "app/(main)/explore/chat/[phase]/loading.tsx"),
    ("landing 路由", "app/(main)/loading.tsx"),
]

# 需要有 error.tsx 的路由
ROUTES_NEEDING_ERROR = [
    ("explore 路由", "app/(main)/explore/error.tsx"),
    ("chat/[phase] 路由", "app/(main)/explore/chat/[phase]/error.tsx"),
    ("landing 路由", "app/(main)/error.tsx"),
]


def _resolve(rel_path: str) -> Path:
    # rel_path like "app/(main)/explore/loading.tsx"
    # APP_DIR = .../src/frontend/app
    return APP_DIR.parent / rel_path


def test_loading_files_exist():
    """关键路由应有 loading.tsx"""
    for label, rel_path in ROUTES_NEEDING_LOADING:
        path = _resolve(rel_path)
        assert path.exists(), f"[{label}] 缺少 {rel_path}"


def test_error_files_exist():
    """关键路由应有 error.tsx"""
    for label, rel_path in ROUTES_NEEDING_ERROR:
        path = _resolve(rel_path)
        assert path.exists(), f"[{label}] 缺少 {rel_path}"


def test_loading_files_export_default():
    """loading.tsx 应有 default export（Next.js 要求）"""
    for label, rel_path in ROUTES_NEEDING_LOADING:
        path = _resolve(rel_path)
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        has_default = bool(re.search(r'export\s+default\s+function', content))
        assert has_default, f"[{label}] {rel_path} 缺少 default export"


def test_error_files_export_default():
    """error.tsx 应有 default export 且接受 props"""
    for label, rel_path in ROUTES_NEEDING_ERROR:
        path = _resolve(rel_path)
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        has_default = bool(re.search(r'export\s+default\s+function', content))
        assert has_default, f"[{label}] {rel_path} 缺少 default export"


def test_loading_files_contain_loading_indicator():
    """loading.tsx 应包含加载指示（文字或图标类名）"""
    for label, rel_path in ROUTES_NEEDING_LOADING:
        path = _resolve(rel_path)
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8").lower()
        has_indicator = any(kw in content for kw in [
            "loading", "spinner", "animate", "pulse", "skeleton", "loader", "lucide",
        ])
        assert has_indicator, f"[{label}] {rel_path} 没有可感知的加载指示元素"


def test_error_files_contain_retry_or_message():
    """error.tsx 应包含错误提示信息和可操作按钮"""
    for label, rel_path in ROUTES_NEEDING_ERROR:
        path = _resolve(rel_path)
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8").lower()
        has_message = any(kw in content for kw in ["error", "错误", "出错了", "出了点问题"])
        has_action = any(kw in content for kw in ["retry", "重试", "button", "按钮", "onclick"])
        assert has_message, f"[{label}] {rel_path} 缺少错误提示信息"
        assert has_action, f"[{label}] {rel_path} 缺少可操作按钮（如重试）"
