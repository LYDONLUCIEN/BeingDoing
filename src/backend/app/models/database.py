"""
数据库配置和连接
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.config.settings import settings
from app.config.architecture import get_arch_config

# 创建基础模型类
Base = declarative_base()

# 获取数据库URL
def get_database_url() -> str:
    """根据架构模式获取数据库URL"""
    config = get_arch_config()
    db_type = config.get("database", "sqlite")
    
    if db_type == "sqlite":
        return settings.DATABASE_URL or "sqlite+aiosqlite:///./app.db"
    elif db_type == "postgresql":
        return settings.DATABASE_URL or "postgresql+asyncpg://user:pass@localhost/db"
    else:
        return settings.DATABASE_URL

# 创建数据库引擎
database_url = get_database_url()
engine = create_async_engine(
    database_url,
    echo=settings.DEBUG,  # 开发环境显示SQL
    future=True
)

# 创建会话工厂
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# 依赖注入：获取数据库会话（用于FastAPI）
async def get_db():
    """获取数据库会话（生成器函数）"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
