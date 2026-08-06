"""analytics_events 通用事件表

Revision ID: 017_analytics_events
Revises: 016_feedback_sla_assignee
Create Date: 2026-08-05

ADR-0013：统计看板（事件时间口径漏斗）。
- page_view：前端埋点上报（不依赖登录），visitor_id 匿名访客 cookie
- auth_active：服务端内部写（登录成功 + token 刷新成功），供日活统计
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "017_analytics_events"
down_revision: Union[str, None] = "016_feedback_sla_assignee"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analytics_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_type", sa.String(32), nullable=False, index=True),
        sa.Column("user_id", sa.String(36), nullable=True, index=True),
        sa.Column("visitor_id", sa.String(64), nullable=True, index=True),
        sa.Column("path", sa.String(255), nullable=True),
        sa.Column("meta", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), index=True),
    )


def downgrade() -> None:
    op.drop_table("analytics_events")
