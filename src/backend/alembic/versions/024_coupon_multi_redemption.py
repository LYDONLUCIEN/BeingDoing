"""coupon multi-redemption + code format groundwork

Revision ID: 024_coupon_multi_redemption
Revises: 023_payment_refund_system
Create Date: 2026-10-06

优惠券多次核销（wiki/开发文档/10-06/优惠券多次核销与码格式区分-设计定稿.md）：
- coupons 加 max_uses / used_count / locked_count / suspended_at
- 存量 backfill：max_uses=1；used 行 used_count=1、locked 行 locked_count=1（对齐守卫口径）
- 新表 coupon_redemptions：每次锁定/核销一行，退款全额按行回退（历史数据不回填）
- payment_orders.delivered_code 扩宽 String(16) → String(64)
  （新激活码格式 OPENLIFE-XXXX-XXXX-XXXX 共 23 字符，16 位存不下）
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "024_coupon_multi_redemption"
down_revision: Union[str, None] = "023_payment_refund_system"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- coupons 加多次核销列 ----
    op.add_column(
        "coupons", sa.Column("max_uses", sa.Integer(), nullable=False, server_default="1")
    )
    op.add_column(
        "coupons", sa.Column("used_count", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "coupons", sa.Column("locked_count", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("coupons", sa.Column("suspended_at", sa.DateTime(), nullable=True))

    # 存量 backfill：used/locked 行的计数器对齐（供名额守卫与 admin 列表展示；不动单槽字段）
    op.execute("UPDATE coupons SET used_count = 1 WHERE status = 'used'")
    op.execute("UPDATE coupons SET locked_count = 1 WHERE status = 'locked'")

    # ---- coupon_redemptions：核销记录表 ----
    op.create_table(
        "coupon_redemptions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("coupon_id", sa.String(length=36), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="locked"),
        sa.Column("locked_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("refunded_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["coupon_id"], ["coupons.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["payment_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_coupon_redemptions_coupon_id", "coupon_redemptions", ["coupon_id"])
    op.create_index("ix_coupon_redemptions_user_id", "coupon_redemptions", ["user_id"])
    op.create_index("ix_coupon_redemptions_status", "coupon_redemptions", ["status"])
    op.create_index("ix_coupon_redemptions_order_id", "coupon_redemptions", ["order_id"], unique=True)

    # ---- delivered_code 扩宽（新激活码 23 字符；加宽方向安全无损）----
    with op.batch_alter_table("payment_orders") as batch_op:
        batch_op.alter_column(
            "delivered_code", existing_type=sa.String(16), type_=sa.String(64), existing_nullable=True
        )


def downgrade() -> None:
    with op.batch_alter_table("payment_orders") as batch_op:
        batch_op.alter_column(
            "delivered_code", existing_type=sa.String(64), type_=sa.String(16), existing_nullable=True
        )
    op.drop_index("ix_coupon_redemptions_order_id", table_name="coupon_redemptions")
    op.drop_index("ix_coupon_redemptions_status", table_name="coupon_redemptions")
    op.drop_index("ix_coupon_redemptions_user_id", table_name="coupon_redemptions")
    op.drop_index("ix_coupon_redemptions_coupon_id", table_name="coupon_redemptions")
    op.drop_table("coupon_redemptions")
    op.drop_column("coupons", "suspended_at")
    op.drop_column("coupons", "locked_count")
    op.drop_column("coupons", "used_count")
    op.drop_column("coupons", "max_uses")
