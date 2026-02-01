"""
数据库操作测试
"""
import pytest
from app.models.database import AsyncSessionLocal
from app.core.database.user_db import UserDB
from app.core.database.history_db import HistoryDB
from app.core.database.knowledge_db import KnowledgeDB


@pytest.mark.asyncio
async def test_user_db_create():
    """测试用户创建"""
    async with AsyncSessionLocal() as session:
        user_db = UserDB(session)
        user = await user_db.create_user(
            email="test@example.com",
            username="testuser",
            password_hash="hashed_password"
        )
        assert user.id is not None
        assert user.email == "test@example.com"


@pytest.mark.asyncio
async def test_user_db_get_by_email():
    """测试根据邮箱获取用户"""
    async with AsyncSessionLocal() as session:
        user_db = UserDB(session)
        # 先创建用户
        user = await user_db.create_user(
            email="test@example.com",
            password_hash="hashed"
        )
        # 再获取
        found_user = await user_db.get_user_by_email("test@example.com")
        assert found_user is not None
        assert found_user.id == user.id


@pytest.mark.asyncio
async def test_user_profile_create():
    """测试用户信息创建"""
    async with AsyncSessionLocal() as session:
        user_db = UserDB(session)
        user = await user_db.create_user(email="test@example.com", password_hash="hash")
        profile = await user_db.create_user_profile(user.id, gender="male", age=25)
        assert profile.user_id == user.id
        assert profile.gender == "male"
        assert profile.age == 25


@pytest.mark.asyncio
async def test_session_db_create():
    """测试会话创建"""
    async with AsyncSessionLocal() as session:
        history_db = HistoryDB(session)
        sess = await history_db.create_session(
            device_id="test_device",
            current_step="values_exploration"
        )
        assert sess.id is not None
        assert sess.status == "active"


@pytest.mark.asyncio
async def test_progress_db():
    """测试进度操作"""
    async with AsyncSessionLocal() as session:
        history_db = HistoryDB(session)
        sess = await history_db.create_session(device_id="test")
        
        # 创建进度
        progress = await history_db.create_progress(
            sess.id,
            step="values_exploration",
            total_count=30
        )
        assert progress.completed_count == 0
        assert progress.total_count == 30
        
        # 更新进度
        updated = await history_db.update_progress(
            sess.id,
            "values_exploration",
            completed_count=5
        )
        assert updated.completed_count == 5


@pytest.mark.asyncio
async def test_answer_db():
    """测试回答操作"""
    async with AsyncSessionLocal() as session:
        history_db = HistoryDB(session)
        sess = await history_db.create_session(device_id="test")
        
        # 创建回答
        answer = await history_db.create_answer(
            sess.id,
            category="values",
            content="我的回答"
        )
        assert answer.content == "我的回答"
        
        # 获取回答列表
        answers = await history_db.get_session_answers(sess.id)
        assert len(answers) == 1


@pytest.mark.asyncio
async def test_question_db():
    """测试问题操作"""
    async with AsyncSessionLocal() as session:
        knowledge_db = KnowledgeDB(session)
        
        # 创建问题
        question = await knowledge_db.create_question(
            category="values",
            question_number=1,
            content="测试问题"
        )
        assert question.id is not None
        
        # 获取问题列表
        questions = await knowledge_db.get_questions_by_category("values")
        assert len(questions) == 1
