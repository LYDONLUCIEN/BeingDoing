"""payment_orders add qr_code column

Revision ID: 012_payment_order_qrcode
Revises: 011_payment_and_membership
Create Date: 2026-07-19

支付模块 P2a：payment_orders 加 qr_code String(512) nullable，
存储渠道预下单（当面付 precreate）返回的 qr 串，供订单详情/继续支付。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "012_payment_order_qrcode"
down_revision: Union[str, None] = "011_payment_and_membership"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("payment_orders", sa.Column("qr_code", sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column("payment_orders", "qr_code")
