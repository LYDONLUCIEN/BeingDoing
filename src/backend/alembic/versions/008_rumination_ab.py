"""add rumination_ab_assignments table

Revision ID: 008_rumination_ab
Revises: 007_site_notices
Create Date: 2026-07-09

新增 Rumination v3/v4 分组分配表，用于：
- 首次进入 rumination 时记录该 report 走 v3 还是 v4
- 保证同一 report 后续访问版本稳定
- 配合 AB 随机（按比例）与配置强制两种模式

字段：id(uuid) / report_id(唯一) / user_id / version / source /
      ratio_at_assignment / created_at / updated_at
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "008_rumination_ab"
down_revision: Union[str, None] = "007_site_notices"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rumination_ab_assignments",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("report_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("version", sa.String(length=4), nullable=False),
        sa.Column("source", sa.String(length=8), nullable=False),
        sa.Column("ratio_at_assignment", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("report_id", name="uq_rumination_ab_report_id"),
    )
    op.create_index("ix_rumination_ab_report_id", "rumination_ab_assignments", ["report_id"])
    op.create_index("ix_rumination_ab_user_id", "rumination_ab_assignments", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_rumination_ab_user_id", table_name="rumination_ab_assignments")
    op.drop_index("ix_rumination_ab_report_id", table_name="rumination_ab_assignments")
    op.drop_table("rumination_ab_assignments")
