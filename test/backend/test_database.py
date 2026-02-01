"""
数据库连接和模型测试
"""
import pytest
import asyncio
from sqlalchemy import text
from app.models.database import engine, get_database_url, AsyncSessionLocal
from app.models import Base, User, Session


@pytest.fixture(scope="function")
async def db_session():
    """创建测试数据库会话"""
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()


@pytest.mark.asyncio
async def test_database_connection():
    """测试数据库连接"""
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT 1"))
        assert result.scalar() == 1


@pytest.mark.asyncio
async def test_database_url():
    """测试数据库URL获取"""
    url = get_database_url()
    assert url is not None
    assert "sqlite" in url or "postgresql" in url


@pytest.mark.asyncio
async def test_create_tables():
    """测试创建数据表"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # 验证表已创建
    async with engine.begin() as conn:
        result = await conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ))
        tables = [row[0] for row in result]
        assert "users" in tables
        assert "sessions" in tables


@pytest.mark.asyncio
async def test_user_model_crud(db_session):
    """测试用户模型CRUD"""
    # 创建用户
    user = User(
        email="test@example.com",
        username="testuser",
        password_hash="hashed_password"
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    
    assert user.id is not None
    assert user.email == "test@example.com"
    
    # 读取用户
    from sqlalchemy import select
    result = await db_session.execute(select(User).where(User.email == "test@example.com"))
    found_user = result.scalar_one()
    assert found_user.username == "testuser"
    
    # 更新用户
    found_user.username = "updated_user"
    await db_session.commit()
    
    # 删除用户
    await db_session.delete(found_user)
    await db_session.commit()


@pytest.mark.asyncio
async def test_session_model_crud(db_session):
    """测试会话模型CRUD"""
    # 创建会话
    session = Session(
        device_id="test_device",
        current_step="values_exploration",
        status="active"
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    
    assert session.id is not None
    assert session.status == "active"
    
    # 更新会话
    session.status = "paused"
    await db_session.commit()
    
    # 删除会话
    await db_session.delete(session)
    await db_session.commit()
