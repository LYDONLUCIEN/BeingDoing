"""rumination_ops 表格变换单测"""
from app.utils import rumination_ops as ro


def test_filter_strength_drops_uncertain():
    t = [
        {"id": "1", "优势标记": "有充实感"},
        {"id": "2", "优势标记": "不确定"},
    ]
    out = ro.filter_strength(t)
    assert len(out) == 1 and out[0]["id"] == "1"


def test_structure_hypothesis_round1_drops_non_match():
    t = [
        {"id": "1", "匹配性": "匹配", "匹配原因": "ok", "热爱": "a", "优势": "b"},
        {"id": "2", "匹配性": "不匹配", "匹配原因": "no", "热爱": "c", "优势": "d"},
    ]
    out = ro.structure_hypothesis_round1_table(t)
    assert len(out) == 1
    assert "匹配原因" not in out[0]
    assert "假设1" in out[0]


def test_value_filter_drops_pending_and_empty_hypothesis():
    t = [
        {"id": "1", "用户确认的假设": "写书", "假设1": "x"},
        {"id": "2", "用户确认的假设": ""},
        {"id": "3", "用户确认的假设": "待定"},
    ]
    out = ro.value_filter(t, ["诚信"])
    assert len(out) == 1
    assert out[0]["id"] == "1"
    assert "工作目的" in out[0]
    assert "假设1" not in out[0]


def test_passion_reality_similar_chain():
    t = [
        {"id": "1", "用户确认的假设": "A", "工作目的": "成长"},
        {"id": "2", "用户确认的假设": "B", "工作目的": "都不符合"},
    ]
    p = ro.passion_filter(t)
    assert len(p) == 1
    assert p[0].get("激情标记") == ""
    r = ro.reality_filter(
        [
            {"id": "1", "用户确认的假设": "A", "激情标记": "忍不住想做"},
            {"id": "2", "用户确认的假设": "C", "激情标记": "应该做"},
        ]
    )
    assert len(r) == 1
    s = ro.similar_filter(
        [
            {"id": "1", "用户确认的假设": "A", "现实标记": "现在"},
            {"id": "2", "用户确认的假设": "B", "现实标记": "未来"},
        ]
    )
    assert len(s) == 1
    assert set(s[0].keys()) == {"id", "用户确认的假设"}


def test_merge_row_by_id():
    t = [{"id": "1", "x": 1}, {"id": "2", "x": 2}]
    out = ro.merge_row_by_id(t, "2", {"x": 3})
    assert out[1]["x"] == 3


def test_extract_from_prior_context_four_sections():
    text = """
【信念 阶段结果】
1. 真诚
2. 责任

【禀赋 阶段结果】
写作、沟通

【热忱 阶段结果】
教育、公益

【使命 阶段结果】
帮助他人
"""
    v, s, i, p = ro.extract_from_prior_context(text)
    assert "真诚" in v or len(v) >= 1
    assert len(s) >= 1
    assert len(i) >= 1
    assert len(p) >= 1
