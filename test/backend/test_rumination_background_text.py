"""rumination_background_text 纯函数单测"""
from app.utils.rumination_background_text import compose_hypothesis_user_background


def test_compose_hypothesis_user_background_empty():
    assert compose_hypothesis_user_background(values_hint="", prior_rumination_text="") == ""


def test_compose_hypothesis_user_background_parts():
    s = compose_hypothesis_user_background(
        values_hint="  成长、诚信 ",
        prior_rumination_text="【使命】帮助他人",
    )
    assert "价值观关键词参考" in s
    assert "成长" in s
    assert "前序探索摘要" in s
    assert "帮助他人" in s
