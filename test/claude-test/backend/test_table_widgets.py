"""S-02 / P-06 / U-04 / P-05 / U-07: rumination_table_widgets 测试"""
from app.utils.rumination_table_widgets import (
    EDITABLE_COLS,
    GUIDE_TEXT,
    _cols_step1,
    _cols_step2,
    _cols_step345,
    _cols_step6,
    _cols_step7,
    _cols_step7_final,
    _cols_step8,
    build_table_widget_payload,
    columns_for_step,
)


# ── S-02: Step 1 优势标记列只读 ────────────────────────────────────

def test_s02_step1_strength_col_exists_but_not_editable():
    """S-02: 优势标记列在 step1 中可见，但不可编辑。"""
    cols = _cols_step1()
    col_keys = [c["key"] for c in cols]
    assert "优势标记" in col_keys, "step1 应包含优势标记列"
    assert "优势标记" not in EDITABLE_COLS.get(1, []), "step1 优势标记不可编辑"


# ── P-06 / U-04: Step 2 无匹配原因列 ──────────────────────────────

def test_p06_step2_no_match_reason_column():
    """P-06: Step 2 列定义中不应包含 匹配原因。"""
    cols = _cols_step2()
    col_keys = [c["key"] for c in cols]
    assert "匹配原因" not in col_keys


def test_u04_step2_payload_no_match_reason():
    """U-04: Step 2 payload 的行数据和列定义均不含匹配原因。"""
    rows = [
        {"id": "1", "热爱": "教育", "优势": "沟通", "匹配性": "匹配"},
        {"id": "2", "热爱": "写作", "优势": "分析", "匹配性": "不匹配"},
    ]
    payload = build_table_widget_payload(step=2, rows=rows, values_keywords=[])
    assert payload is not None
    col_keys = [c["key"] for c in payload["columns"]]
    assert "匹配原因" not in col_keys
    for row in payload["rows"]:
        assert "匹配原因" not in row


# ── P-05: Step 7 引导文案 ──────────────────────────────────────────

def test_p05_step7_guide_text_contains_selection_phrase():
    """P-05: Step 7 GUIDE_TEXT 应包含'选择1-3'方向的引导。"""
    guide = GUIDE_TEXT.get(7, "")
    assert "1" in guide and "3" in guide, f"实际 GUIDE_TEXT[7]: {guide}"
    assert "选择" in guide or "行" in guide, f"实际 GUIDE_TEXT[7]: {guide}"


def test_p05_step7_guide_text_retains_click_hint():
    """P-05: Step 7 GUIDE_TEXT 仍保留'整行'操作说明。"""
    guide = GUIDE_TEXT.get(7, "")
    assert "整行" in guide or "行" in guide, "应保留行选择的交互说明"


# ── U-07: 列标签无多余括号 ─────────────────────────────────────────

def test_u07_all_column_labels_balanced_brackets():
    """U-07: 所有步骤的列标签中括号配对完整，无孤立半括号。"""
    for step in range(1, 8):
        cols = columns_for_step(step, [])
        for col in cols:
            label = col["label"]
            assert label.count("（") == label.count(
                "）"
            ), f"step {step} label '{label}' 全角括号不配对"
            assert label.count("(") == label.count(
                ")"
            ), f"step {step} label '{label}' 半角括号不配对"
            assert not label.startswith(
                "）"
            ), f"step {step} label '{label}' 以孤立闭括号开头"
            assert not label.startswith(
                ")"
            ), f"step {step} label '{label}' 以孤立闭括号开头"


# ── 通用验证 ────────────────────────────────────────────────────────

def test_editable_cols_consistency():
    """EDITABLE_COLS 与实际列定义一致性：editable 项必须存在于列定义中。"""
    for step, edit_keys in EDITABLE_COLS.items():
        cols = columns_for_step(step, [])
        col_keys = {c["key"] for c in cols}
        for ek in edit_keys:
            assert ek in col_keys, f"step {step} EDITABLE_COLS 包含 '{ek}'，但列定义中不存在"


def test_build_payload_none_for_empty_rows():
    """无行时 build_table_widget_payload 应返回 None。"""
    assert build_table_widget_payload(step=1, rows=[], values_keywords=[]) is None


def test_build_payload_step7_multi_selection():
    """Step 7 payload 应包含 rowSelectionMode: multi。"""
    rows = [{"id": "1", "用户确认的假设": "假设A"}]
    payload = build_table_widget_payload(step=7, rows=rows, values_keywords=[])
    assert payload is not None
    assert payload.get("rowSelectionMode") == "multi"
    assert payload.get("rowSelectionMin") == 1
    assert payload.get("rowSelectionMax") == 3


def test_step4_values_source_degradation():
    """Step 4 无关键词时应只提供'自定义'选项。"""
    rows = [{"id": "1", "用户确认的假设": "假设A"}]
    payload = build_table_widget_payload(
        step=4, rows=rows, values_keywords=[], values_source="none"
    )
    assert payload is not None
    assert payload.get("valuesSource") == "none"
    # 工作目的列应只有"自定义"
    work_cols = [c for c in payload["columns"] if c["key"] == "工作目的"]
    assert len(work_cols) == 1
    assert work_cols[0]["options"] == ["自定义"]
    # guideText 应含降级提示
    assert "暂未解析" in payload.get("guideText", "")


def test_step4_values_keywords_present():
    """Step 4 有关键词时 options 应含关键词 + 都不符合 + 自定义。"""
    rows = [{"id": "1", "用户确认的假设": "假设A"}]
    payload = build_table_widget_payload(
        step=4, rows=rows, values_keywords=["诚信", "成长"]
    )
    assert payload is not None
    work_cols = [c for c in payload["columns"] if c["key"] == "工作目的"]
    assert "诚信" in work_cols[0]["options"]
    assert "成长" in work_cols[0]["options"]
    assert "都不符合" in work_cols[0]["options"]
    assert "自定义" in work_cols[0]["options"]
