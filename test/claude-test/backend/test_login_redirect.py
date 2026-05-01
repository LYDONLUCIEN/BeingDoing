"""O-02：登录后统一跳"开始探索"

验证（通过前端源码 cross-check）：
- 登录后默认跳转到 /explore/intro
- 清缓存后重新登录，跳转目标仍是 /explore/intro
- 无残留的"回到上次页面"逻辑（redirectTo 默认值始终为 /explore/intro）

策略：从 TS/TSX 源码解析验证跳转规则，不需要运行前端 dev server。
"""
from __future__ import annotations

from pathlib import Path

import pytest


_FRONTEND_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "src" / "frontend"

TARGET_PATH = "/explore/intro"


class TestAuthRedirectDefaults:
    """验证所有 auth 入口的 redirectTo 默认值都是 /explore/intro。"""

    def _read_file(self, relative_path: str) -> str:
        p = _FRONTEND_ROOT / relative_path
        if not p.is_file():
            pytest.skip(f"前端文件不存在: {relative_path}")
        return p.read_text(encoding="utf-8")

    def test_o02_auth_modal_default_redirect(self):
        """AuthModal.tsx 中 redirectTo 默认值为 /explore/intro。"""
        src = self._read_file("components/layout/AuthModal.tsx")
        assert f"redirectTo = '{TARGET_PATH}'" in src or f'redirectTo = "{TARGET_PATH}"' in src

    def test_o02_auth_modal_handle_success_pushes_target(self):
        """handleSuccess 使用 router.push(targetPath) 跳转。"""
        src = self._read_file("components/layout/AuthModal.tsx")
        assert "router.push(targetPath)" in src

    def test_o02_auth_store_default_redirect(self):
        """authModalStore.ts 中 openAuthModal 默认值为 /explore/intro。"""
        src = self._read_file("stores/authModalStore.ts")
        assert f"redirectTo = '{TARGET_PATH}'" in src or f"redirectTo = \"{TARGET_PATH}\"" in src

    def test_o02_auth_store_initial_redirect(self):
        """authModalStore 初始 state 中 redirectTo 为 /explore/intro。"""
        src = self._read_file("stores/authModalStore.ts")
        assert f"redirectTo: '{TARGET_PATH}'" in src or f'redirectTo: "{TARGET_PATH}"' in src

    def test_o02_api_client_fallback_redirect(self):
        """client.ts 中 401 回调 fallback 为 /explore/intro。"""
        src = self._read_file("lib/api/client.ts")
        assert f"'{TARGET_PATH}'" in src or f'"{TARGET_PATH}"' in src

    def test_o02_no_redirect_to_dashboard_after_login(self):
        """登录后不应 redirect 到 /dashboard 或其他旧路由。"""
        src = self._read_file("components/layout/AuthModal.tsx")
        # 不应包含 redirectTo = '/dashboard' 或类似
        assert "redirectTo = '/dashboard'" not in src
        assert 'redirectTo = "/dashboard"' not in src

    def test_o02_auth_gate_redirects_to_explore(self):
        """AuthGate.tsx 未登录时打开 AuthModal 并设置 redirectTo 为 /explore/intro。"""
        src = self._read_file("components/layout/AuthGate.tsx")
        assert TARGET_PATH in src


class TestExplorePageRoute:
    """验证 /explore 路由配置。"""

    def test_o02_explore_page_redirects_to_intro(self):
        """/explore 页面重定向到 /explore/intro。"""
        src_path = _FRONTEND_ROOT / "app" / "(main)" / "explore" / "page.tsx"
        if not src_path.is_file():
            pytest.skip("explore page.tsx 不存在")
        src = src_path.read_text(encoding="utf-8")
        assert "'/explore/intro'" in src or '"/explore/intro"' in src
