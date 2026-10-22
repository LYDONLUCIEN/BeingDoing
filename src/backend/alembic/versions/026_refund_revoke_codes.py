"""payment_refunds add revoke_codes

Revision ID: 026_refund_revoke_codes
Revises: 025_user_type_admin_note
Create Date: 2026-10-18

退款批准后激活码作废可配置（2026-10-18 admin 退款改造）：
- payment_refunds.revoke_codes：NULL/True=批准后作废交付码（默认，历史兼容）；
  False=admin 审批时选择保留码。失败重试沿用审批时保存的选择。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "026_refund_revoke_codes"
down_revision: Union[str, None] = "025_user_type_admin_note"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "payment_refunds",
        sa.Column("revoke_codes", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("payment_refunds", "revoke_codes")
