"""abuse detection

Revision ID: 022_abuse_detection
Revises: 021_user_avatar
Create Date: 2026-09-30

用户滥用检测与限流系统：
- 新建 abuse_events（用户行为事件流水：message / thread_delete，供硬阈值窗口聚合）
- 新建 abuse_states（用户处置状态机：warned → frozen，admin 裁决恢复即删行）
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "022_abuse_detection"
down_revision: Union[str, None] = "021_user_avatar"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "abuse_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("phase", sa.String(30), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_abuse_events_user_id", "abuse_events", ["user_id"])
    op.create_index("ix_abuse_events_created_at", "abuse_events", ["created_at"])

    op.create_table(
        "abuse_states",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("warned_at", sa.DateTime(), nullable=True),
        sa.Column("warned_rule", sa.String(50), nullable=True),
        sa.Column("frozen_at", sa.DateTime(), nullable=True),
        sa.Column("frozen_rule", sa.String(50), nullable=True),
        sa.Column("frozen_activation_code", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_abuse_states_user_id", "abuse_states", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_table("abuse_states")
    op.drop_table("abuse_events")
