"""payment_orders qr_code String(512) -> Text

Revision ID: 015_payment_qrcode_text
Revises: 014_account_deletion
Create Date: 2026-07-25

支付宝下单从当面付 precreate 切换为电脑网站支付 page.pay：
qr_code 列改存收银台跳转 URL（约 800~1000 字符），String(512) 扩为 Text。
列名保持 qr_code 不变。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "015_payment_qrcode_text"
down_revision: Union[str, None] = "014_account_deletion"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("payment_orders") as batch_op:
        batch_op.alter_column(
            "qr_code",
            existing_type=sa.String(length=512),
            type_=sa.Text(),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("payment_orders") as batch_op:
        batch_op.alter_column(
            "qr_code",
            existing_type=sa.Text(),
            type_=sa.String(length=512),
            existing_nullable=True,
        )
