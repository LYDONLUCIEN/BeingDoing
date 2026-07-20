"""
折扣券服务

职责：
1. create_coupons: 单个/批量创建（12 位大写字母+数字券码，唯一冲突重试）
2. list_coupons: 分页列表（used 态联查核销用户邮箱、锁定/核销订单号）
3. update_coupon_amount / delete_coupon: 仅 unused 可改/可删
4. validate / lock / release / redeem: 下单用券状态机（P2 用）
   unused → locked（下单锁定）→ used（支付成功核销）；关单释放 locked → unused
5. draw_from_pool: 券池 FIFO 取券（邮件发券用），池空按 DEFAULT_COUPON_AMOUNT 自动创建

设计要点：
- 金额一律整数分
- lock 用 UPDATE ... WHERE status='unused' 的影响行数判断，并发下只成功一次
- 业务约束违反一律抛 ValueError（路由层转 400）
"""

from __future__ import annotations

import logging
import secrets
import string
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select, update

from app.config.settings import settings
from app.models.database import AsyncSessionLocal
from app.models.payment import Coupon, PaymentOrder
from app.models.user import User

logger = logging.getLogger(__name__)

# 券码字符集：大写字母+数字（与 10 位激活码同字符集，长度 12 位区分）
_CODE_ALPHABET = string.ascii_uppercase + string.digits
_CODE_LENGTH = 12
# 唯一冲突重试上限（理论上几乎不会触发）
_MAX_CODE_RETRIES = 10


class CouponService:
    """折扣券服务"""

    # ─── 券码生成 ───────────────────────────────────────────────

    @staticmethod
    def _generate_code() -> str:
        """生成 12 位大写字母+数字券码"""
        return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))

    # ─── 创建 ───────────────────────────────────────────────────

    @classmethod
    async def create_coupons(
        cls,
        amount: int,
        count: int = 1,
        source: str = "admin",
        created_by: Optional[str] = None,
    ) -> List[Coupon]:
        """批量创建折扣券

        Args:
            amount: 面额（分，>0）
            count: 数量（1-500）
            source: 来源（admin / email_auto）
            created_by: 创建人用户 ID（admin 创建时填）

        Returns:
            创建的券列表

        Raises:
            ValueError: 参数非法
        """
        if amount <= 0:
            raise ValueError("券面额必须大于 0")
        if not 1 <= count <= 500:
            raise ValueError("批量创建数量须在 1-500 之间")

        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            coupons: List[Coupon] = []
            for _ in range(count):
                code = await cls._pick_unique_code(db)
                coupon = Coupon(
                    code=code,
                    amount=amount,
                    status="unused",
                    source=source,
                    created_by=created_by,
                    created_at=now,
                )
                db.add(coupon)
                coupons.append(coupon)
            await db.commit()
            for c in coupons:
                await db.refresh(c)
            logger.info("created %d coupons (amount=%d, source=%s)", len(coupons), amount, source)
            return coupons

    @classmethod
    async def _pick_unique_code(cls, db) -> str:
        """生成不冲突的券码（唯一冲突重试）"""
        for _ in range(_MAX_CODE_RETRIES):
            code = cls._generate_code()
            exists = (
                await db.execute(select(Coupon.id).where(Coupon.code == code))
            ).scalar_one_or_none()
            if not exists:
                return code
        raise ValueError("券码生成冲突次数过多，请重试")

    # ─── 列表 ───────────────────────────────────────────────────

    @classmethod
    async def list_coupons(
        cls,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        source: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """分页查询券列表

        used/locked 态联查：used_by 用户邮箱、used_order/locked_order 的 order_no，
        供后台展示。

        Args:
            status: 状态过滤（unused/locked/used）
            page / page_size: 分页
            source: 来源过滤（admin/email_auto）

        Returns:
            (items, total)
        """
        async with AsyncSessionLocal() as db:
            base = select(Coupon)
            count_base = select(func.count()).select_from(Coupon)
            if status:
                base = base.where(Coupon.status == status)
                count_base = count_base.where(Coupon.status == status)
            if source:
                base = base.where(Coupon.source == source)
                count_base = count_base.where(Coupon.source == source)

            total = (await db.execute(count_base)).scalar() or 0
            offset = (page - 1) * page_size
            rows = (
                (
                    await db.execute(
                        base.order_by(Coupon.created_at.desc()).offset(offset).limit(page_size)
                    )
                )
                .scalars()
                .all()
            )

            items = [await cls._serialize(db, c) for c in rows]
            return items, total

    @classmethod
    async def _serialize(cls, db, coupon: Coupon) -> Dict[str, Any]:
        """ORM → API dict（联查邮箱与订单号）"""
        used_by_email: Optional[str] = None
        if coupon.used_by_user_id:
            used_by_email = (
                await db.execute(select(User.email).where(User.id == coupon.used_by_user_id))
            ).scalar_one_or_none()

        used_order_no: Optional[str] = None
        if coupon.used_order_id:
            used_order_no = (
                await db.execute(
                    select(PaymentOrder.order_no).where(PaymentOrder.id == coupon.used_order_id)
                )
            ).scalar_one_or_none()

        locked_order_no: Optional[str] = None
        if coupon.locked_order_id:
            locked_order_no = (
                await db.execute(
                    select(PaymentOrder.order_no).where(PaymentOrder.id == coupon.locked_order_id)
                )
            ).scalar_one_or_none()

        return {
            "id": coupon.id,
            "code": coupon.code,
            "amount": coupon.amount,
            "status": coupon.status,
            "source": coupon.source,
            "created_by": coupon.created_by,
            "created_at": coupon.created_at.isoformat() if coupon.created_at else None,
            "used_at": coupon.used_at.isoformat() if coupon.used_at else None,
            "used_by_email": used_by_email,
            "used_order_no": used_order_no,
            "locked_order_no": locked_order_no,
        }

    # ─── 后台管理（仅 unused 可改/可删）─────────────────────────

    @classmethod
    async def update_coupon_amount(cls, coupon_id: str, amount: int) -> Coupon:
        """调整券面额（仅 unused）

        Raises:
            ValueError: 券不存在 / 非 unused / 面额非法
        """
        if amount <= 0:
            raise ValueError("券面额必须大于 0")
        async with AsyncSessionLocal() as db:
            coupon = await cls._get_or_raise(db, coupon_id)
            if coupon.status != "unused":
                raise ValueError(f"仅未使用的券可调整面额（当前状态：{coupon.status}）")
            coupon.amount = amount
            await db.commit()
            await db.refresh(coupon)
            return coupon

    @classmethod
    async def delete_coupon(cls, coupon_id: str) -> None:
        """作废券（仅 unused，物理删除）

        Raises:
            ValueError: 券不存在 / 非 unused
        """
        async with AsyncSessionLocal() as db:
            coupon = await cls._get_or_raise(db, coupon_id)
            if coupon.status != "unused":
                raise ValueError(f"仅未使用的券可作废（当前状态：{coupon.status}）")
            await db.delete(coupon)
            await db.commit()

    @classmethod
    async def _get_or_raise(cls, db, coupon_id: str) -> Coupon:
        coupon = (
            await db.execute(select(Coupon).where(Coupon.id == coupon_id))
        ).scalar_one_or_none()
        if not coupon:
            raise ValueError("券不存在")
        return coupon

    # ─── 下单用券状态机（P2 用）─────────────────────────────────

    @classmethod
    async def validate_coupon(cls, code: str) -> Coupon:
        """校验券码可用：存在且 unused

        Raises:
            ValueError: 券不存在或不可用
        """
        normalized = (code or "").strip().upper()
        if not normalized:
            raise ValueError("券码不能为空")
        async with AsyncSessionLocal() as db:
            coupon = (
                await db.execute(select(Coupon).where(Coupon.code == normalized))
            ).scalar_one_or_none()
            if not coupon:
                raise ValueError("券码不存在")
            if coupon.status != "unused":
                raise ValueError("券码已被使用或锁定中")
            return coupon

    @classmethod
    async def lock_coupon(cls, code: str, order_id: str) -> Coupon:
        """下单锁定：unused → locked，写 locked_order_id

        并发安全：UPDATE ... WHERE status='unused'，按影响行数判断，
        并发竞争下只有一单能锁定成功。

        Raises:
            ValueError: 券不存在或已被锁定/使用
        """
        normalized = (code or "").strip().upper()
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                update(Coupon)
                .where(Coupon.code == normalized, Coupon.status == "unused")
                .values(status="locked", locked_order_id=order_id)
            )
            if result.rowcount == 0:
                await db.rollback()
                # 区分不存在 vs 状态不对，给出准确错误
                coupon = (
                    await db.execute(select(Coupon).where(Coupon.code == normalized))
                ).scalar_one_or_none()
                if not coupon:
                    raise ValueError("券码不存在")
                raise ValueError("券码已被使用或锁定中")
            await db.commit()
            return (await db.execute(select(Coupon).where(Coupon.code == normalized))).scalar_one()

    @classmethod
    async def release_coupon(cls, coupon_id: str) -> Coupon:
        """关单释放：locked → unused，清空 locked_order_id

        Raises:
            ValueError: 券不存在或非 locked
        """
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                update(Coupon)
                .where(Coupon.id == coupon_id, Coupon.status == "locked")
                .values(status="unused", locked_order_id=None)
            )
            if result.rowcount == 0:
                await db.rollback()
                coupon = await cls._get_or_raise(db, coupon_id)
                raise ValueError(f"券不在锁定状态（当前状态：{coupon.status}）")
            await db.commit()
            return (await db.execute(select(Coupon).where(Coupon.id == coupon_id))).scalar_one()

    @classmethod
    async def redeem_coupon(cls, coupon_id: str, user_id: str, order_id: str) -> Coupon:
        """支付成功核销：locked → used，写核销信息

        Raises:
            ValueError: 券不存在或非 locked
        """
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                update(Coupon)
                .where(Coupon.id == coupon_id, Coupon.status == "locked")
                .values(
                    status="used",
                    used_by_user_id=user_id,
                    used_order_id=order_id,
                    used_at=datetime.now(timezone.utc),
                )
            )
            if result.rowcount == 0:
                await db.rollback()
                coupon = await cls._get_or_raise(db, coupon_id)
                raise ValueError(f"券不在锁定状态，无法核销（当前状态：{coupon.status}）")
            await db.commit()
            return (await db.execute(select(Coupon).where(Coupon.id == coupon_id))).scalar_one()

    # ─── 券池取券（邮件发券用）──────────────────────────────────

    @classmethod
    async def draw_from_pool(cls, exclude_ids: Optional[set] = None) -> Coupon:
        """券池 FIFO 取券：取创建最早的 unused；池空按 DEFAULT_COUPON_AMOUNT 自动创建

        注意：取券不改状态（券仍 unused，直到下单锁定）。同一批群发内
        通过 exclude_ids 排除已分出的券，保证每个收件人拿到不同券码。

        Args:
            exclude_ids: 本次批次内已分出的券 ID 集合（可选）

        Returns:
            取到（或新创建）的券
        """
        async with AsyncSessionLocal() as db:
            q = (
                select(Coupon)
                .where(Coupon.status == "unused")
                .order_by(Coupon.created_at.asc(), Coupon.id.asc())
                .limit(1)
            )
            if exclude_ids:
                q = q.where(Coupon.id.not_in(list(exclude_ids)))
            coupon = (await db.execute(q)).scalar_one_or_none()
            if coupon:
                return coupon

        # 池空：按默认面额自动创建（source="email_auto"）
        created = await cls.create_coupons(
            amount=settings.DEFAULT_COUPON_AMOUNT,
            count=1,
            source="email_auto",
            created_by=None,
        )
        logger.info(
            "coupon pool empty, auto-created %s (amount=%d)",
            created[0].code,
            settings.DEFAULT_COUPON_AMOUNT,
        )
        return created[0]
