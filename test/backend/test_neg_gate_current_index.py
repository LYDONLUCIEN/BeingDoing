"""neg_gate current_index 逐条注入与推进。"""

import importlib.util
from pathlib import Path

from app.utils.rumination_neg_gate import (
    advance_neg_index,
    build_injection_zh,
    build_neg_progress_header,
    collect_step2_mismatches,
    refresh_neg_state_injection,
    user_wants_neg_advance,
)


def _load_stream_utils():
    path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "backend"
        / "app"
        / "api"
        / "v1"
        / "simple_chat"
        / "stream_utils.py"
    )
    spec = importlib.util.spec_from_file_location("stream_utils_isolated", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _mismatch_items(n: int = 2):
    rows = []
    for i in range(n):
        rows.append(
            {
                "id": str(i + 1),
                "热爱": f"热{i+1}",
                "优势": f"优{i+1}",
                "匹配性": "不匹配",
            }
        )
    return collect_step2_mismatches(rows)


class TestNegGateCurrentIndexInjection:
    def test_injection_only_current_item_when_index_set(self):
        items = _mismatch_items(3)
        full = build_injection_zh(2, "mismatch", items, False)
        single = build_injection_zh(2, "mismatch", items, False, current_index=1)
        assert "热1" not in single or "第 2 / 3 条" in single
        assert "第 2 / 3 条" in single
        assert "禁止讨论列表外条目" in single
        assert "NEG_ITEM_DONE" in single
        assert "待讨论条目" in full or "当前仅讨论" not in full

    def test_progress_header_shows_position(self):
        items = _mismatch_items(2)
        neg = refresh_neg_state_injection(
            {
                "status": "exploring",
                "step": 2,
                "kind": "mismatch",
                "items": items,
                "current_index": 0,
                "llm_failed": False,
            }
        )
        header = build_neg_progress_header(neg)
        assert "第 1 / 2 条" in header
        assert "热1" in header or "热爱" in header


class TestNegGateAdvance:
    def test_advance_moves_index_by_one(self):
        items = _mismatch_items(2)
        neg = refresh_neg_state_injection(
            {
                "status": "exploring",
                "step": 2,
                "kind": "mismatch",
                "items": items,
                "current_index": 0,
                "llm_failed": False,
            }
        )
        new_neg, msg = advance_neg_index(neg)
        assert int(new_neg.get("current_index") or 0) == 1
        assert msg and "第 2" in msg

    def test_advance_past_last_shows_end_hint(self):
        items = _mismatch_items(1)
        neg = refresh_neg_state_injection(
            {
                "status": "exploring",
                "step": 2,
                "kind": "mismatch",
                "items": items,
                "current_index": 0,
                "llm_failed": False,
            }
        )
        new_neg, msg = advance_neg_index(neg)
        assert int(new_neg.get("current_index") or 0) >= 1
        assert "结束讨论" in (msg or "")


class TestNegItemDoneMarker:
    def test_split_strips_marker(self):
        split_visible_reply_and_neg_item_done = _load_stream_utils().split_visible_reply_and_neg_item_done
        raw = "聊得不错。\n[NEG_ITEM_DONE]\n[/NEG_ITEM_DONE]"
        visible, done = split_visible_reply_and_neg_item_done(raw)
        assert done is True
        assert "NEG_ITEM_DONE" not in visible
        assert "聊得不错" in visible


class TestUserAdvanceIntent:
    def test_user_phrases_detected(self):
        assert user_wants_neg_advance("这条聊完了，下一条吧")
        assert user_wants_neg_advance("我们看下一条")
        assert not user_wants_neg_advance("我觉得不匹配是因为…")
