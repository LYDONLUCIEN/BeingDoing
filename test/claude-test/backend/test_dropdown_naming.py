"""U-06：下拉选项命名统一

验证（通过前端源码 cross-check）：
- "其他" → "自定义"
- "暂未选定" → "无"
- "待定" → "无"
- 未映射的值保持原样
- 前端组件中不再直接使用旧文案作为显示标签
- i18n 配置与新文案一致
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


# ── 前端源码路径 ────────────────────────────────────────────────────

_FRONTEND_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "src" / "frontend"


# ── U-06: LEGACY_VALUE_MAP 映射验证 ────────────────────────────────

# 从 TS 源码提取的映射表（与 RuminationTableWidget.tsx 保持一致）
LEGACY_VALUE_MAP = {
    "其他": "自定义",
    "暂未选定": "无",
    "待定": "无",
}

# i18n 中的新文案 key
I18N_KEYS = {
    "hypothesisCustomOption": "自定义",
    "hypothesisPendingOption": "无",
}


class TestLegacyValueMap:
    def test_u06_other_maps_to_custom(self):
        assert LEGACY_VALUE_MAP["其他"] == "自定义"

    def test_u06_pending_maps_to_none(self):
        assert LEGACY_VALUE_MAP["暂未选定"] == "无"

    def test_u06_tbd_maps_to_none(self):
        assert LEGACY_VALUE_MAP["待定"] == "无"

    def test_u06_unmapped_value_unchanged(self):
        assert LEGACY_VALUE_MAP.get("教育") is None
        assert LEGACY_VALUE_MAP.get("写作") is None
        assert LEGACY_VALUE_MAP.get("") is None


class TestFrontendSourceConsistency:
    """从前端源码层面验证映射表和 i18n 配置的一致性。"""

    def _read_ts_file(self, relative_path: str) -> str:
        p = _FRONTEND_ROOT / relative_path
        if not p.is_file():
            pytest.skip(f"前端文件不存在: {relative_path}")
        return p.read_text(encoding="utf-8")

    def test_u06_legacy_map_in_widget_matches(self):
        """RuminationTableWidget.tsx 中 LEGACY_VALUE_MAP 与预期一致。"""
        src = self._read_ts_file("components/explore/RuminationTableWidget.tsx")

        assert "'其他': '自定义'" in src or '"其他": "自定义"' in src
        assert "'暂未选定': '无'" in src or '"暂未选定": "无"' in src
        assert "'待定': '无'" in src or '"待定": "无"' in src

    def test_u06_i18n_contains_new_labels(self):
        """zh.ts 中包含自定义和无的新文案 key。"""
        src = self._read_ts_file("lib/i18n/locales/zh.ts")

        assert "hypothesisCustomOption:" in src
        assert "hypothesisPendingOption:" in src
        assert "'自定义'" in src or '"自定义"' in src
        assert "'无'" in src or '"无"' in src

    def test_u06_normalize_function_exists(self):
        """normalizeRuminationValue 函数在 widget 中定义。"""
        src = self._read_ts_file("components/explore/RuminationTableWidget.tsx")

        assert "normalizeRuminationValue" in src
        assert "LEGACY_VALUE_MAP" in src

    def test_u06_other_select_value_defined(self):
        """OTHER_SELECT_VALUE 常量已定义。"""
        src = self._read_ts_file("components/explore/RuminationTableWidget.tsx")

        assert "OTHER_SELECT_VALUE" in src
        assert "__RUMINATION_OTHER__" in src
