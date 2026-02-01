"""
Alembic环境配置
"""
from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# 导入Base和所有模型
from app.models.database import Base
from app.models import (
    User, UserProfile, WorkHistory, ProjectExperience,
    Session, Progress,
    Question, Answer,
    UserSelection, GuidePreference, ExplorationResult
)

# 导入配置
from app.config.settings import settings
from app.models.database import get_database_url

# this is the Alembic Config object
config = context.config

# 设置数据库URL
config.set_main_option("sqlalchemy.url", get_database_url())

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 设置target_metadata
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
