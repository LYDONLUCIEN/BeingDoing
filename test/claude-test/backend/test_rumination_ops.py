"""S-03 / S-09: rumination_ops 测试 — 关键词来源优先级 + 快照一致性"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch

import pytest

from app.utils import rumination_ops as ro


# ── S-03: _is_sentence_fragment 句子过滤 ────────────────────────────

class TestSentenceFragment:
    def test_filters_sentences_with_end_punctuation(self):
        assert ro._is_sentence_fragment("写作、沟通。") is True
        assert ro._is_sentence_fragment("我觉得可以") is True  # 句末句号

    def test_filters_sentences_starting_with_subject(self):
        assert ro._is_sentence_fragment("我认为这个方向不错") is True
        assert ro._is_sentence_fragment("我觉得应该选择") is True
        # "你说的" 不在 _SENTENCE_STARTER_RE 中，但它以句末标点结尾才算句子
        assert ro._is_sentence_fragment("你说的有道理。") is True

    def test_filters_sentences_starting_with_connectors(self):
        assert ro._is_sentence_fragment("但是我觉得不行") is True
        assert ro._is_sentence_fragment("所以选了第一个") is True
        assert ro._is_sentence_fragment("也就是说") is True
        assert ro._is_sentence_fragment("总的来说") is True
        assert ro._is_sentence_fragment("从某种角度") is True

    def test_keeps_keywords(self):
        assert ro._is_sentence_fragment("教育") is False
        assert ro._is_sentence_fragment("写作") is False
        assert ro._is_sentence_fragment("公益") is False
        assert ro._is_sentence_fragment("帮助他人") is False

    def test_empty_and_whitespace(self):
        assert ro._is_sentence_fragment("") is True
        assert ro._is_sentence_fragment("   ") is True
        # None 通过 str(None) = "None" 进入，实际函数签名接受 text: str
        # 不直接传 None，因为类型注解是 str

    def test_strict_mode_rejects_long_text(self):
        """strict 模式下超过 20 字的片段应被过滤。"""
        long_text = "我" * 21  # 21 字，超过 max_len=20
        found = ro._extract_keywords(long_text, limit=10, strict=True)
        assert found == []


# ── S-03: _normalize_alpha_marker 括号清洗 ─────────────────────────

class TestNormalizeAlphaMarker:
    def test_repairs_missing_close_paren(self):
        assert ro._normalize_alpha_marker("(a 文案") == "(a) 文案"

    def test_removes_leading_close_paren_half(self):
        assert ro._normalize_alpha_marker(")文案") == "文案"

    def test_removes_leading_close_paren_full(self):
        assert ro._normalize_alpha_marker("）文案") == "文案"

    def test_removes_unpaired_open_paren_half(self):
        assert ro._normalize_alpha_marker("(文案") == "文案"

    def test_removes_unpaired_open_paren_full(self):
        assert ro._normalize_alpha_marker("（文案") == "文案"

    def test_keeps_balanced_parens(self):
        assert ro._normalize_alpha_marker("(a) 正常文案") == "(a) 正常文案"
        assert ro._normalize_alpha_marker("（正常）文案") == "（正常）文案"

    def test_empty_input(self):
        assert ro._normalize_alpha_marker("") == ""
        assert ro._normalize_alpha_marker(None) == ""


# ── S-03: _resolve_dimension 来源优先级 ─────────────────────────────

class TestResolveDimension:
    def _make_resolve_args(self):
        """构建 _resolve_dimension 的标准参数。"""
        store: Dict[str, Dict] = {}
        record: Dict[str, Any] = {}
        report_dir = Path("/tmp/nonexistent_report")
        return store, record, report_dir

    @patch.object(ro, "_keywords_from_stored_dimension_conclusion")
    @patch.object(ro, "_keywords_from_report_anchor")
    @patch.object(ro, "_read_prior_context")
    def test_priority1_confirmed_card_first(
        self, mock_prior, mock_anchor, mock_confirmed
    ):
        """confirmed_card 有数据时优先返回。"""
        mock_confirmed.return_value = ["诚信", "成长"]
        mock_anchor.return_value = ["自由", "责任"]
        mock_prior.return_value = "1. 诚信\n2. 成长"

        store, record, report_dir = self._make_resolve_args()
        kws, source = ro._resolve_dimension("values", store, record, report_dir, 12)

        assert source == ro._SOURCE_CONFIRMED
        assert kws == ["诚信", "成长"]
        mock_anchor.assert_not_called()  # 第二优先级不应被调用

    @patch.object(ro, "_keywords_from_stored_dimension_conclusion")
    @patch.object(ro, "_keywords_from_report_anchor")
    @patch.object(ro, "_read_prior_context")
    def test_priority2_anchor_when_no_confirmed(
        self, mock_prior, mock_anchor, mock_confirmed
    ):
        """confirmed_card 为空时回退到 report_anchor。"""
        mock_confirmed.return_value = []
        mock_anchor.return_value = ["自由", "责任"]
        mock_prior.return_value = "1. 诚信\n2. 成长"

        store, record, report_dir = self._make_resolve_args()
        kws, source = ro._resolve_dimension("values", store, record, report_dir, 12)

        assert source == ro._SOURCE_ANCHOR
        assert kws == ["自由", "责任"]

    @patch.object(ro, "_keywords_from_stored_dimension_conclusion")
    @patch.object(ro, "_keywords_from_report_anchor")
    @patch.object(ro, "_read_prior_context")
    @patch.object(ro, "_extract_keywords", return_value=["诚信", "成长"])
    def test_priority3_prior_text_fallback(
        self, mock_extract, mock_prior_text, mock_anchor, mock_confirmed
    ):
        """前两者为空时回退到 prior_text（strict 模式）。"""
        mock_confirmed.return_value = []
        mock_anchor.return_value = []
        mock_prior_text.return_value = "1. 诚信\n2. 成长"

        store, record, report_dir = self._make_resolve_args()
        kws, source = ro._resolve_dimension("values", store, record, report_dir, 12)

        assert source == ro._SOURCE_TEXT

    @patch.object(ro, "_keywords_from_stored_dimension_conclusion")
    @patch.object(ro, "_keywords_from_report_anchor")
    @patch.object(ro, "_read_prior_context")
    def test_none_when_all_empty(
        self, mock_prior, mock_anchor, mock_confirmed
    ):
        """所有来源为空时返回 (_SOURCE_NONE)。"""
        mock_confirmed.return_value = []
        mock_anchor.return_value = []
        mock_prior.return_value = ""

        store, record, report_dir = self._make_resolve_args()
        kws, source = ro._resolve_dimension("values", store, record, report_dir, 12)

        assert source == ro._SOURCE_NONE
        assert kws == []


# ── S-09: resolve_values_for_step4 快照一致性 ───────────────────────

class TestResolveValuesForStep4:
    @patch.object(ro, "load_dimension_conclusions")
    @patch.object(ro, "_resolve_dimension")
    def test_snapshot_used_first(self, mock_resolve, mock_load):
        """有快照时优先使用快照，不调用实时解析。"""
        mock_load.return_value = {}
        snapshots = {
            "4": {
                "_values_snapshot": {
                    "keywords": ["诚信", "成长", "自由"],
                    "source": "confirmed_card",
                }
            }
        }
        kws, source = ro.resolve_values_for_step4(
            reports_root="/tmp",
            report_id="test",
            record_obj=None,
            snapshots=snapshots,
        )
        assert kws == ["诚信", "成长", "自由"]
        assert source == "confirmed_card"

    @patch.object(ro, "extract_dimension_lists_for_rumination_table")
    @patch.object(ro, "load_dimension_conclusions")
    def test_live_resolve_fallback(self, mock_load, mock_extract):
        """无快照时实时解析。"""
        mock_load.return_value = {}
        mock_extract.return_value = (
            ["诚信", "成长"],
            ["写作"],
            ["教育"],
            ["帮助他人"],
            {"values": "confirmed_card", "strengths": "none", "interests": "none", "purpose": "none"},
        )

        kws, source = ro.resolve_values_for_step4(
            reports_root="/tmp",
            report_id="test",
            record_obj=None,
            snapshots={},
        )
        assert kws == ["诚信", "成长"]
        assert source == "confirmed_card"


class TestValuesSnapshot:
    def test_build_and_load_roundtrip(self):
        """快照写入→读取一致性。"""
        from app.utils.rumination_ops import (
            build_values_snapshot,
            load_values_snapshot_from_snapshots,
            save_values_snapshot_to_snapshots,
        )

        kws = ["诚信", "成长", "自由"]
        src = "confirmed_card"

        snapshots = save_values_snapshot_to_snapshots({}, kws, src, step=4)
        result = load_values_snapshot_from_snapshots(snapshots, step=4)

        assert result is not None
        loaded_kws, loaded_src = result
        assert loaded_kws == kws
        assert loaded_src == src

    def test_load_from_empty_snapshots(self):
        """空 snapshots 应返回 None。"""
        from app.utils.rumination_ops import load_values_snapshot_from_snapshots

        assert load_values_snapshot_from_snapshots({}) is None
        assert load_values_snapshot_from_snapshots({"4": {}}) is None
        assert load_values_snapshot_from_snapshots(None) is None

    def test_load_with_empty_keywords(self):
        """快照中 keywords 为空列表应返回 None。"""
        from app.utils.rumination_ops import load_values_snapshot_from_snapshots

        snapshots = {"4": {"_values_snapshot": {"keywords": [], "source": "none"}}}
        assert load_values_snapshot_from_snapshots(snapshots) is None
