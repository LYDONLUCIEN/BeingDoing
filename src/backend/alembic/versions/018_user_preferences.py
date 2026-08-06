"""users add preferences

Revision ID: 018_user_preferences
Revises: 017_analytics_events
Create Date: 2026-08-05

用户偏好（ADR-0014 升级弹窗「不再提醒」等）：
- users 加列 preferences（JSON 字符串，NULL = 无偏好）
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "018_user_preferences"
down_revision: Union[str, None] = "017_analytics_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("preferences", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "preferences")
