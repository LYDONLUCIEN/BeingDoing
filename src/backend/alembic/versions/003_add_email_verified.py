"""Add email_verified column to users table

Revision ID: 003_add_email_verified
Revises: 002_enhance_likes
Create Date: 2026-06-09

Existing users are set to true (already verified).
Only new registrations will default to false.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "003_add_email_verified"
down_revision: Union[str, None] = "002_enhance_likes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default="true"),
    )


def downgrade() -> None:
    op.drop_column("users", "email_verified")
