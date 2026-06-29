"""
T5 — profile bug 修复回归测试。

背景：save_basic_info_by_user 原用 loop.create_task 后台异步写库 + except: pass 吞异常，
导致 UserProfile 表可能不更新 → admin /admin/users 查不到老用户已填 profile。

修复策略：改 async def，同步 await 写 DB（先 DB 后 JSON），失败 raise。

覆盖用例：
1) 复现 bug：提交 survey → 立即查 UserProfile → 能看到 gender / profile_completed
2) DB 故意失败 → save_basic_info_by_user 抛错（不再静默成功）
3) DB 失败时一致性：JSON 文件不应被写入（避免 DB 无 / JSON 有的不一致）
"""

import json
from unittest.mock import patch

import pytest
from app.core.database.user_db import UserDB
from app.models.database import AsyncSessionLocal
from app.utils.survey_storage import load_basic_info_by_user, save_basic_info_by_user


async def _create_user(email: str = "profile@example.com") -> str:
    """创建测试用户，返回 user_id。"""
    async with AsyncSessionLocal() as db:
        user_db = UserDB(db)
        user = await user_db.create_user(
            email=email, username="profile_tester", password_hash="h"
        )
        return user.id


@pytest.mark.asyncio
async def test_save_basic_info_updates_user_profile_immediately():
    """
    [回归] 修复前：loop.create_task 后台写库 + except: pass，立即查 Profile 查不到。
    修复后：await 同步写库，函数返回时 DB 已提交。
    """
    user_id = await _create_user("regress_t5@example.com")

    survey_data = {
        "nickname": "小明",
        "gender": "male",
        "age": 28,
        "career_status": "在职",
        "industry": "互联网",
        "position": "工程师",
    }

    # 调用修复后的 save_basic_info_by_user
    await save_basic_info_by_user(user_id, survey_data)

    # 立即查 UserProfile（不应再出现「DB 没更新」的情况）
    async with AsyncSessionLocal() as db:
        user_db = UserDB(db)
        profile = await user_db.get_user_profile(user_id)
        assert profile is not None, "UserProfile 应已被创建/更新"
        assert profile.gender == "male"
        assert profile.profile_completed is True  # survey 含有效字段

    # JSON 缓存也应写入
    loaded = load_basic_info_by_user(user_id)
    assert loaded is not None
    assert loaded.get("gender") == "male"


@pytest.mark.asyncio
async def test_save_basic_info_raises_on_db_failure():
    """
    [一致性] DB 故意失败时，save_basic_info_by_user 必须抛错（不再静默成功），
    让上层 API 返回 500 / 提示重试。
    """
    user_id = await _create_user("db_fail@example.com")
    survey_data = {"gender": "female", "career_status": "在职"}

    # mock UserDB.update_user_profile 抛异常
    with patch(
        "app.core.database.user_db.UserDB.update_user_profile",
        side_effect=RuntimeError("simulated DB down"),
    ):
        with pytest.raises(RuntimeError, match="simulated DB down"):
            await save_basic_info_by_user(user_id, survey_data)


@pytest.mark.asyncio
async def test_db_failure_does_not_write_json(tmp_path, monkeypatch):
    """
    [一致性] DB 失败时 JSON 不应被写入，避免「DB 无 / JSON 有」的不一致：
    admin 查不到，但 prompt 注入却用了这份问卷。

    策略：先 DB 后 JSON，DB 抛错时函数提前 return（不会执行到 JSON 写入）。
    """
    user_id = await _create_user("consistency@example.com")
    survey_data = {"gender": "male", "career_status": "在职"}

    # 把 user data 目录指向临时目录，便于断言「文件不存在」
    from app.utils import survey_storage

    fake_path = tmp_path / user_id / "basic_info.json"
    monkeypatch.setattr(
        survey_storage,
        "_get_user_basic_info_path",
        lambda uid: fake_path,
    )

    with patch(
        "app.core.database.user_db.UserDB.update_user_profile",
        side_effect=RuntimeError("DB down"),
    ):
        with pytest.raises(RuntimeError):
            await save_basic_info_by_user(user_id, survey_data)

    # DB 失败 → JSON 不应存在
    assert not fake_path.exists(), "DB 失败时 JSON 不应被写入（保证一致性）"


@pytest.mark.asyncio
async def test_save_empty_survey_still_persists():
    """
    [边界] 空问卷也应正确写入（profile_completed=False），且不抛错。
    """
    user_id = await _create_user("empty_survey@example.com")

    await save_basic_info_by_user(user_id, {})

    async with AsyncSessionLocal() as db:
        user_db = UserDB(db)
        profile = await user_db.get_user_profile(user_id)
        assert profile is not None
        # 空问卷：gender 为 None，profile_completed=False
        assert profile.profile_completed is False
