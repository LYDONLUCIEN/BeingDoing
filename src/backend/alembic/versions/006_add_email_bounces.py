"""add email_bounces table

Revision ID: 006_email_bounces
Revises: 005_fix_timestamps_tz
Create Date: 2026-07-02

新增邮箱退信黑名单表，用于群发邮件时过滤已知不可达邮箱。
- 来源：BounceScanner 扫描退信邮件自动添加 + admin 手动添加
- 字段：email(PK) / bounce_type(hard|soft) / status(blocked|unblocked) / bounce_count / reason / source(auto|manual)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# alembic 识别标识
revision: str = "006_email_bounces"
down_revision: Union[str, None] = "005_fix_timestamps_tz"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "email_bounces",
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("bounce_type", sa.String(length=10), nullable=False, server_default="hard"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="blocked"),
        sa.Column("bounce_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_bounce_at", sa.DateTime(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="auto"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("email"),
    )
    # status 字段常用于过滤 "blocked"，加索引
    op.create_index("ix_email_bounces_status", "email_bounces", ["status"])


def downgrade() -> None:
    op.drop_index("ix_email_bounces_status", table_name="email_bounces")
    op.drop_table("email_bounces")
