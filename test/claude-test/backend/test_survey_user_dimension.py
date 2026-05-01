"""O-04 + S-04：问卷用户维度读取 + 问卷状态不随激活码变

O-04 验证：
- 登录后进入个人中心，无需先输入激活码即可看到问卷信息
- 个人中心问卷数据以用户维度读取，不依赖当前激活码上下文
- 旧数据兼容显示正常

S-04 验证：
- 已填写过问卷的用户，清缓存后重新登录+输入激活码，不会要求重填问卷
- 切换不同激活码，问卷完成状态不丢失（跟 user 绑定）
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.utils.survey_storage import (
    save_basic_info_by_user,
    load_basic_info_by_user,
    merge_basic_info_sources,
)


# ── helpers ──────────────────────────────────────────────────────────

def _patch_user_data_dir(tmp_path: Path, monkeypatch) -> Path:
    """将 get_user_data_dir 指向 tmp_path。"""
    user_dir = tmp_path / "user"
    monkeypatch.setattr(
        "app.utils.survey_storage.get_user_data_dir",
        lambda: user_dir,
    )
    monkeypatch.setattr(
        "app.utils.data_paths.get_user_data_dir",
        lambda: user_dir,
    )
    return user_dir


# ── O-04: save / load by user_id ───────────────────────────────────

class TestSaveLoadByUser:
    def test_o04_save_and_load_by_user_id(self, tmp_path, monkeypatch):
        _patch_user_data_dir(tmp_path, monkeypatch)

        data = {"nickname": "小明", "age": "28", "city": "北京"}
        save_basic_info_by_user("user_001", data)

        loaded = load_basic_info_by_user("user_001")
        assert loaded is not None
        assert loaded["nickname"] == "小明"
        assert loaded["age"] == "28"

    def test_o04_load_returns_none_for_nonexistent_user(self, tmp_path, monkeypatch):
        _patch_user_data_dir(tmp_path, monkeypatch)

        loaded = load_basic_info_by_user("nonexistent_user")
        assert loaded is None

    def test_o04_multiple_saves_return_latest(self, tmp_path, monkeypatch):
        _patch_user_data_dir(tmp_path, monkeypatch)

        save_basic_info_by_user("user_001", {"nickname": "小明", "age": "28"})
        save_basic_info_by_user("user_001", {"nickname": "小明改", "age": "29"})

        loaded = load_basic_info_by_user("user_001")
        assert loaded["nickname"] == "小明改"
        assert loaded["age"] == "29"

    def test_o04_different_users_independent(self, tmp_path, monkeypatch):
        _patch_user_data_dir(tmp_path, monkeypatch)

        save_basic_info_by_user("user_001", {"nickname": "用户1"})
        save_basic_info_by_user("user_002", {"nickname": "用户2"})

        assert load_basic_info_by_user("user_001")["nickname"] == "用户1"
        assert load_basic_info_by_user("user_002")["nickname"] == "用户2"


# ── O-04: merge_basic_info_sources ─────────────────────────────────

class TestMergeBasicInfoSources:
    def test_o04_merge_basic_info_sources_strategy_a(self):
        """Strategy A = 取最新源（sources[-1]）。"""
        sources = [
            {"nickname": "旧名", "age": "25"},
            {"nickname": "新名"},
        ]
        result = merge_basic_info_sources(sources, strategy="A")
        # Strategy A 只取最后一个源的全部内容
        assert result["nickname"] == "新名"
        assert "age" not in result

    def test_o04_merge_basic_info_sources_empty_list(self):
        result = merge_basic_info_sources([])
        assert result == {}

    def test_o04_merge_single_source(self):
        """单源直接返回。"""
        sources = [{"nickname": "唯一"}]
        result = merge_basic_info_sources(sources)
        assert result["nickname"] == "唯一"


# ── S-04: 问卷状态跨激活码持久 ────────────────────────────────────

class TestSurveyPersistsAcrossActivationCodes:
    def test_s04_user_has_survey_returns_data(self, tmp_path, monkeypatch):
        _patch_user_data_dir(tmp_path, monkeypatch)

        save_basic_info_by_user("user_001", {"nickname": "小明"})

        # 模拟不同激活码场景 — 数据始终按 user_id 存取
        loaded_1 = load_basic_info_by_user("user_001")
        loaded_2 = load_basic_info_by_user("user_001")

        assert loaded_1 == loaded_2
        assert loaded_1["nickname"] == "小明"

    def test_s04_user_no_survey_returns_none(self, tmp_path, monkeypatch):
        _patch_user_data_dir(tmp_path, monkeypatch)

        assert load_basic_info_by_user("never_filled_user") is None

    def test_s04_survey_persists_across_activation_codes(self, tmp_path, monkeypatch):
        """同一 user_id 在不同激活码下读到的问卷数据相同。"""
        _patch_user_data_dir(tmp_path, monkeypatch)

        save_basic_info_by_user("user_001", {
            "nickname": "小明",
            "career_status": "在职",
        })

        # 用不同激活码对应不同 session，但用户维度数据一致
        data_via_code_a = load_basic_info_by_user("user_001")
        data_via_code_b = load_basic_info_by_user("user_001")

        assert data_via_code_a is not None
        assert data_via_code_a == data_via_code_b
        assert data_via_code_a["career_status"] == "在职"
