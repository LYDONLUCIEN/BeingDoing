"""add llm_model_configs and user_llm_model_configs tables

Revision ID: 009_llm_model_configs
Revises: 008_rumination_ab
Create Date: 2026-07-16

新增管理员可配置的 LLM 模型表：
- llm_model_configs: 一个端点一条（provider/model/base_url/api_key_enc/...）
- user_llm_model_configs: 用户 → 配置 绑定（每 user 至多一行）

迁移会从当前 .env 读出 LLM_PROVIDER/LLM_MODEL/LLM_BASE_URL/(OPENAI|DEEPSEEK)_API_KEY，
seed 一条默认记录（api_key 加密），让 admin 后台开箱即用。
"""
from typing import Sequence, Union
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision: str = "009_llm_model_configs"
down_revision: Union[str, None] = "008_rumination_ab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SEED_ID = "envseed0000000000000000000000"  # 32-char 占位


def upgrade() -> None:
    op.create_table(
        "llm_model_configs",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("base_url", sa.String(length=255), nullable=True),
        sa.Column("api_key_enc", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "user_llm_model_configs",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("config_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["config_id"], ["llm_model_configs.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("user_id", name="uq_user_llm_config_user"),
        sa.PrimaryKeyConstraint("id"),
    )

    # ---- seed 一条默认记录，来自当前 .env ----
    bind = op.get_bind()
    exists = bind.execute(
        sa.text("SELECT 1 FROM llm_model_configs WHERE id = :id"), {"id": SEED_ID}
    ).fetchone()
    if exists:
        return

    try:
        from app.config.settings import settings
        from app.utils import llm_config_crypto
    except Exception:
        return  # 极端情况下跳过 seed，不动表结构

    provider = (settings.LLM_PROVIDER or "openai").lower()
    model = settings.LLM_MODEL or "gpt-4"
    base_url = settings.LLM_BASE_URL
    if provider == "deepseek":
        api_key = settings.DEEPSEEK_API_KEY
        base_url = base_url or "https://api.deepseek.com"
    elif provider == "kimi":
        api_key = getattr(settings, "KIMI_API_KEY", None)
        base_url = base_url or getattr(settings, "KIMI_BASE_URL", None)
    elif provider == "qwen":
        api_key = getattr(settings, "QWEN_API_KEY", None)
        base_url = base_url or getattr(settings, "QWEN_BASE_URL", None)
    else:
        api_key = settings.OPENAI_API_KEY

    now = datetime.now(timezone.utc)
    api_key_enc = llm_config_crypto.encrypt(api_key) if api_key else None

    bind.execute(
        sa.text(
            """
            INSERT INTO llm_model_configs
              (id, name, provider, model, base_url, api_key_enc,
               is_default, enabled, notes, created_at, updated_at)
            VALUES
              (:id, :name, :provider, :model, :base_url, :api_key_enc,
               :is_default, :enabled, :notes, :created_at, :updated_at)
            """
        ),
        {
            "id": SEED_ID,
            "name": ".env 默认（迁移自动 seed）",
            "provider": provider,
            "model": model,
            "base_url": base_url,
            "api_key_enc": api_key_enc,
            "is_default": True,
            "enabled": True,
            "notes": "由 alembic 009 从 .env 自动生成；可在后台修改或停用。",
            "created_at": now,
            "updated_at": now,
        },
    )


def downgrade() -> None:
    op.drop_table("user_llm_model_configs")
    op.drop_table("llm_model_configs")
