"""llm usage logs

Revision ID: 019_llm_usage_logs
Revises: 018_user_preferences
Create Date: 2026-08-16

LLM 调用级 token 用量与预估成本表（Admin token 统计）：
- 新建 llm_usage_logs（调用粒度，含 cache hit/miss、cost_yuan、is_peak、scene）
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "019_llm_usage_logs"
down_revision: Union[str, None] = "018_user_preferences"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_usage_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("session_id", sa.String(128), nullable=True),
        sa.Column("activation_code", sa.String(64), nullable=True),
        sa.Column("scene", sa.String(50), nullable=False),
        sa.Column("provider", sa.String(32), nullable=True),
        sa.Column("model", sa.String(64), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("cache_hit_tokens", sa.Integer(), nullable=True),
        sa.Column("cache_miss_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_yuan", sa.Float(), nullable=True),
        sa.Column("is_peak", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_llm_usage_logs_user_id", "llm_usage_logs", ["user_id"])
    op.create_index("ix_llm_usage_logs_session_id", "llm_usage_logs", ["session_id"])
    op.create_index("ix_llm_usage_logs_activation_code", "llm_usage_logs", ["activation_code"])
    op.create_index("ix_llm_usage_logs_scene", "llm_usage_logs", ["scene"])
    op.create_index("ix_llm_usage_logs_model", "llm_usage_logs", ["model"])
    op.create_index("ix_llm_usage_logs_created_at", "llm_usage_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("llm_usage_logs")
