"""Enhance analytics_likes: add user_id, message_id, snapshot, thread_id, phase, activation_code
SQLite-compatible version using batch_alter_table.

Revision ID: 002_enhance_likes
Revises: 001_analytics
Create Date: 2026-04-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = '002_enhance_likes'
down_revision: Union[str, None] = '001_analytics'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 第一步：先用 batch_alter_table 新增列和索引（不混 alter_column 避免循环依赖）
    with op.batch_alter_table('analytics_likes') as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.String(36), nullable=True))
        batch_op.add_column(sa.Column('thread_id', sa.String(128), nullable=True))
        batch_op.add_column(sa.Column('message_id', sa.String(128), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('role', sa.String(20), nullable=True))
        batch_op.add_column(sa.Column('content_snapshot', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('phase', sa.String(50), nullable=True))
        batch_op.add_column(sa.Column('activation_code', sa.String(64), nullable=True))

        batch_op.create_index('ix_analytics_likes_user_id', ['user_id'])
        batch_op.create_index('ix_analytics_likes_thread_id', ['thread_id'])
        batch_op.create_index('ix_analytics_likes_message_id', ['message_id'])
        batch_op.create_index('ix_analytics_likes_activation_code', ['activation_code'])

    # 第二步：单独用 batch_alter_table 修改 log_index 的 nullable
    with op.batch_alter_table('analytics_likes') as batch_op:
        batch_op.alter_column('log_index', existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    # 第一步：单独处理 alter_column
    with op.batch_alter_table('analytics_likes') as batch_op:
        batch_op.alter_column('log_index', existing_type=sa.Integer(), nullable=False)

    # 第二步：删列和索引
    with op.batch_alter_table('analytics_likes') as batch_op:
        batch_op.drop_index('ix_analytics_likes_activation_code')
        batch_op.drop_index('ix_analytics_likes_message_id')
        batch_op.drop_index('ix_analytics_likes_thread_id')
        batch_op.drop_index('ix_analytics_likes_user_id')

        batch_op.drop_column('activation_code')
        batch_op.drop_column('phase')
        batch_op.drop_column('content_snapshot')
        batch_op.drop_column('role')
        batch_op.drop_column('message_id')
        batch_op.drop_column('thread_id')
        batch_op.drop_column('user_id')
