"""Add notification tables for batch email sending

Revision ID: 004_notification
Revises: 003_add_email_verified
Create Date: 2026-06-29

新增两张表：
- notification_tasks: 群发任务主表（含进度统计、状态）
- notification_recipients: 收件人明细（每封邮件一条记录，含发送结果）
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers
revision: str = "004_notification"
down_revision: Union[str, None] = "003_add_email_verified"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notification_tasks",
        sa.Column("task_id", sa.String(36), primary_key=True),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("filter_json", sa.Text(), nullable=True),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "notification_recipients",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "task_id",
            sa.String(36),
            sa.ForeignKey("notification_tasks.task_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error_msg", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_notification_recipients_task_id",
        "notification_recipients",
        ["task_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_notification_recipients_task_id", table_name="notification_recipients")
    op.drop_table("notification_recipients")
    op.drop_table("notification_tasks")
