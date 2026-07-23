"""users add deleted_at / deletion_purge_after

Revision ID: 014_account_deletion
Revises: 013_packages_consultation_team
Create Date: 2026-07-20

账户注销/恢复/到期清除：
- users 加列 deleted_at（注销时间，NULL = 未注销）
- users 加列 deletion_purge_after（到期物理清除时间）
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "014_account_deletion"
down_revision: Union[str, None] = "013_packages_consultation_team"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("deletion_purge_after", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "deletion_purge_after")
    op.drop_column("users", "deleted_at")
