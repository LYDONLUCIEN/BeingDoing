"""Enhance analytics_likes: add user_id, message_id, snapshot, thread_id, phase, activation_code

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
    # 新增列：user_id, thread_id, message_id, role, content_snapshot, phase, activation_code
    op.add_column('analytics_likes', sa.Column('user_id', sa.String(36), nullable=True))
    op.add_column('analytics_likes', sa.Column('thread_id', sa.String(128), nullable=True))
    op.add_column('analytics_likes', sa.Column('message_id', sa.String(128), nullable=False, server_default=''))
    op.add_column('analytics_likes', sa.Column('role', sa.String(20), nullable=True))
    op.add_column('analytics_likes', sa.Column('content_snapshot', sa.Text(), nullable=True))
    op.add_column('analytics_likes', sa.Column('phase', sa.String(50), nullable=True))
    op.add_column('analytics_likes', sa.Column('activation_code', sa.String(64), nullable=True))

    # 创建索引
    op.create_index('ix_analytics_likes_user_id', 'analytics_likes', ['user_id'])
    op.create_index('ix_analytics_likes_thread_id', 'analytics_likes', ['thread_id'])
    op.create_index('ix_analytics_likes_message_id', 'analytics_likes', ['message_id'])
    op.create_index('ix_analytics_likes_activation_code', 'analytics_likes', ['activation_code'])

    # log_index 原来是 NOT NULL，新需求允许为空（兼容旧数据）
    op.alter_column('analytics_likes', 'log_index', existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.drop_index('ix_analytics_likes_activation_code', table_name='analytics_likes')
    op.drop_index('ix_analytics_likes_message_id', table_name='analytics_likes')
    op.drop_index('ix_analytics_likes_thread_id', table_name='analytics_likes')
    op.drop_index('ix_analytics_likes_user_id', table_name='analytics_likes')

    op.drop_column('analytics_likes', 'activation_code')
    op.drop_column('analytics_likes', 'phase')
    op.drop_column('analytics_likes', 'content_snapshot')
    op.drop_column('analytics_likes', 'role')
    op.drop_column('analytics_likes', 'message_id')
    op.drop_column('analytics_likes', 'thread_id')
    op.drop_column('analytics_likes', 'user_id')

    op.alter_column('analytics_likes', 'log_index', existing_type=sa.Integer(), nullable=False)
