"""add site_notices table

Revision ID: 007_site_notices
Revises: 006_email_bounces
Create Date: 2026-07-04

新增站内公告表，用于：
- 维护计划 banner（升级前 24~48 小时挂顶部窄条）
- 未来扩展：modal / popup / announcement 等形态

字段：id(uuid) / type / title / content_md / severity /
      start_at / end_at / dismissible / is_active / channels_json(Text 存 JSON 字符串) /
      created_at / updated_at
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "007_site_notices"
down_revision: Union[str, None] = "006_email_bounces"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "site_notices",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False, server_default="banner"),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("content_md", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(length=10), nullable=False, server_default="info"),
        sa.Column("start_at", sa.DateTime(), nullable=True),
        sa.Column("end_at", sa.DateTime(), nullable=True),
        sa.Column("dismissible", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("channels_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    # 公开查询常用：is_active + 时间窗口；type 过滤
    op.create_index("ix_site_notices_active", "site_notices", ["is_active"])
    op.create_index("ix_site_notices_type", "site_notices", ["type"])


def downgrade() -> None:
    op.drop_index("ix_site_notices_type", table_name="site_notices")
    op.drop_index("ix_site_notices_active", table_name="site_notices")
    op.drop_table("site_notices")
