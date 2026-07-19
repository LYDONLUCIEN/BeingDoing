"""add feedbacks, feedback_attachments, notifications tables

Revision ID: 010_feedback_and_notifications
Revises: 009_llm_model_configs
Create Date: 2026-07-16

新增反馈与站内信相关三张表：
- feedbacks: 用户提交的反馈（bug / 产品想法）
- feedback_attachments: 反馈截图元信息（OSS 对象 key + 大小/类型）
- notifications: 站内信（用户↔管理员双向通知）

注意：此 notifications 表与现有 notification_tasks/notification_recipients
（邮件群发任务）是不同的东西。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "010_feedback_and_notifications"
down_revision: Union[str, None] = "009_llm_model_configs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- feedbacks ----
    op.create_table(
        "feedbacks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("user_email", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="received",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_feedbacks_user_id_created_at",
        "feedbacks",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_feedbacks_status_updated_at",
        "feedbacks",
        ["status", "updated_at"],
    )

    # ---- feedback_attachments ----
    op.create_table(
        "feedback_attachments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("feedback_id", sa.String(length=36), nullable=True),
        sa.Column("uploader_user_id", sa.String(length=36), nullable=False),
        sa.Column("oss_key", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["feedback_id"], ["feedbacks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["uploader_user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_feedback_attachments_feedback_id",
        "feedback_attachments",
        ["feedback_id"],
    )
    op.create_index(
        "ix_feedback_attachments_uploader_created",
        "feedback_attachments",
        ["uploader_user_id", "created_at"],
    )

    # ---- notifications ----
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("related_feedback_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["related_feedback_id"], ["feedbacks.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notifications_user_id_created_at",
        "notifications",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_notifications_user_id_read_at",
        "notifications",
        ["user_id", "read_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_user_id_read_at", table_name="notifications")
    op.drop_index("ix_notifications_user_id_created_at", table_name="notifications")
    op.drop_table("notifications")

    op.drop_index(
        "ix_feedback_attachments_uploader_created",
        table_name="feedback_attachments",
    )
    op.drop_index(
        "ix_feedback_attachments_feedback_id", table_name="feedback_attachments"
    )
    op.drop_table("feedback_attachments")

    op.drop_index("ix_feedbacks_status_updated_at", table_name="feedbacks")
    op.drop_index("ix_feedbacks_user_id_created_at", table_name="feedbacks")
    op.drop_table("feedbacks")
