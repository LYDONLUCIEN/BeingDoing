"""Add analytics tables

Revision ID: 001_analytics
Revises: 
Create Date: 2025-02-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = '001_analytics'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'analytics_chat_turns',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('session_id', sa.String(128), nullable=False, index=True),
        sa.Column('dimension', sa.String(50), nullable=True),
        sa.Column('user_input_chars', sa.Integer(), default=0),
        sa.Column('llm_input_tokens', sa.Integer(), default=0),
        sa.Column('llm_output_tokens', sa.Integer(), default=0),
        sa.Column('log_index', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        'analytics_reports',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('session_id', sa.String(128), nullable=False, index=True),
        sa.Column('activation_code', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        'analytics_likes',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('session_id', sa.String(128), nullable=False, index=True),
        sa.Column('log_index', sa.Integer(), nullable=False),
        sa.Column('content_preview', sa.Text(), nullable=True),
        sa.Column('dimension', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('analytics_likes')
    op.drop_table('analytics_reports')
    op.drop_table('analytics_chat_turns')
