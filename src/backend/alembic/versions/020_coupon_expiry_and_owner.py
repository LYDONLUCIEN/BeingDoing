"""coupon expiry and owner

Revision ID: 020_coupon_expiry_and_owner
Revises: 019_llm_usage_logs
Create Date: 2026-09-14

折扣券有效期 + 用户绑定体系：
- coupons 加 expires_at（过期时间）/ owner_user_id（归属用户）/ voided_at（软删除）
- 存量券追溯生效：全部补 expires_at = 迁移时刻 + 90 天（与运行时配置初始默认值一致）
"""

from datetime import datetime, timedelta, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "020_coupon_expiry_and_owner"
down_revision: Union[str, None] = "019_llm_usage_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 存量券追溯有效期天数（与 coupon_config.DEFAULT_COUPON_TTL_DAYS 初始默认值一致，
# 迁移不读运行时配置文件，保持确定性）
_LEGACY_TTL_DAYS = 90


def upgrade() -> None:
    op.add_column("coupons", sa.Column("expires_at", sa.DateTime(), nullable=True))
    op.add_column("coupons", sa.Column("owner_user_id", sa.String(36), nullable=True))
    op.add_column("coupons", sa.Column("voided_at", sa.DateTime(), nullable=True))
    op.create_index("ix_coupons_owner_user_id", "coupons", ["owner_user_id"])

    # 存量券追溯生效：迁移时刻 + 默认天数，统一同一天过期
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
        days=_LEGACY_TTL_DAYS
    )
    op.execute(
        sa.text("UPDATE coupons SET expires_at = :exp WHERE expires_at IS NULL").bindparams(
            exp=expires_at
        )
    )


def downgrade() -> None:
    op.drop_index("ix_coupons_owner_user_id", table_name="coupons")
    op.drop_column("coupons", "voided_at")
    op.drop_column("coupons", "owner_user_id")
    op.drop_column("coupons", "expires_at")
