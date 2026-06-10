"""沉淀点选表格行发问：user 消息包装逻辑。"""
import json

import pytest

from app.utils.rumination_row_context import (
    build_rumination_row_chat_user_message,
    clean_row_for_row_chat_prompt,
)


SAMPLE_TABLE = [
    {"id": "r1", "热爱": "写作", "优势": "表达", "匹配性": "匹配", "__pick": True},
    {"id": "r2", "热爱": "设计", "优势": "审美", "匹配性": "不匹配"},
]


def test_clean_row_strips_meta_keys():
    row = clean_row_for_row_chat_prompt(SAMPLE_TABLE[0])
    assert "__pick" not in row
    assert row["热爱"] == "写作"


def test_build_row_chat_wraps_step2():
    text = build_rumination_row_chat_user_message(
        filter_step=2,
        row_index=1,
        user_query="为什么是不匹配？",
        filter_table=SAMPLE_TABLE,
    )
    assert text is not None
    assert "分析热爱与优势的匹配性" in text
    assert "第【2】行" in text
    assert "设计" in text
    assert "为什么是不匹配？" in text
    assert "table_data" not in text.lower()


def test_build_row_chat_step3_adds_cursor_note():
    text = build_rumination_row_chat_user_message(
        filter_step=3,
        row_index=0,
        user_query="这行怎么假设？",
        filter_table=SAMPLE_TABLE,
    )
    assert text is not None
    assert "当前解锁行" in text
    assert "以用户选中行为准" in text


def test_build_row_chat_invalid_index_returns_none():
    assert (
        build_rumination_row_chat_user_message(
            filter_step=2,
            row_index=99,
            user_query="x",
            filter_table=SAMPLE_TABLE,
        )
        is None
    )


def test_build_row_chat_empty_query_returns_none():
    assert (
        build_rumination_row_chat_user_message(
            filter_step=2,
            row_index=0,
            user_query="  ",
            filter_table=SAMPLE_TABLE,
        )
        is None
    )


def test_row_json_is_valid_json_in_output():
    text = build_rumination_row_chat_user_message(
        filter_step=4,
        row_index=0,
        user_query="选哪个价值观？",
        filter_table=[{"id": "r1", "用户确认的假设": "独立咨询", "工作目的": ""}],
    )
    assert text is not None
    # 模板中 row_json 应为可解析 JSON
    start = text.index("{")
    end = text.index("}", start) + 1
    parsed = json.loads(text[start:end])
    assert parsed.get("用户确认的假设") == "独立咨询"
