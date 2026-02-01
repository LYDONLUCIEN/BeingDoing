"""
数据库初始化脚本
"""
import asyncio
from app.models.database import engine, Base
from app.models import (
    User, UserProfile, WorkHistory, ProjectExperience,
    Session, Progress,
    Question, Answer,
    UserSelection, GuidePreference, ExplorationResult
)


async def init_db():
    """初始化数据库表结构"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("数据库表结构创建完成")


async def drop_db():
    """删除所有表（谨慎使用）"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    print("所有表已删除")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "drop":
        asyncio.run(drop_db())
    else:
        asyncio.run(init_db())
