"""
折扣券服务

职责：
1. create_coupons: 单个/批量创建（12 位大写字母+数字券码，唯一冲突重试）；
   有效期 ttl_days 默认读运行时配置（coupon_config，默认 90 天），可绑定归属用户
2. list_coupons: 分页列表（used 态联查核销用户邮箱、锁定/核销订单号）；
   status 过滤支持 expired（unused 且已过期的派生态）与 void（软删除）
3. update_coupon_amount / update_coupon_expiry / delete_coupon(软删除) / restore_coupon:
   后台管理；used/locked 一律不可改，void 仅可恢复
4. validate / lock / release / redeem: 下单用券状态机（P2 用）
   unused → locked（下单锁定+认领）→ used（支付成功核销）；关单释放 locked → unused（保留归属）
   过期判定惰性派生：unused 且 expires_at<now 即不可用；locked 免疫（锁定期不过期）
5. draw_from_pool: 券池 FIFO 取券（邮件发券用，发放即绑定收件人），
   池空按 DEFAULT_COUPON_AMOUNT 自动创建
6. list_my_coupons: 用户侧「我的折扣券」（按派生态分组 available/used/expired）
7. return_coupon_on_refund: 退款退券（used → unused，保留归属）

设计要点：
- 金额一律整数分
- lock 用 UPDATE ... WHERE status='unused' 的影响行数判断，并发下只成功一次
- 归属语义：owner_user_id=None 为流通券（下单锁定时认领）；已绑定券仅归属人可用
- expired 不落库，是 unused 的派生态（无定时 job）；void 是落库的软删除态
- 业务约束违反一律抛 ValueError（路由层转 400）
"""

from __future__ import annotations

import logging
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func, or_, select, update

from app.config.settings import settings
from app.models.database import AsyncSessionLocal
from app.models.payment import Coupon, PaymentOrder
from app.models.user import User
from app.services import coupon_config

logger = logging.getLogger(__name__)

# 券码字符集：大写字母+数字（与 10 位激活码同字符集，长度 12 位区分）
_CODE_ALPHABET = string.ascii_uppercase + string.digits
_CODE_LENGTH = 12
# 唯一冲突重试上限（理论上几乎不会触发）
_MAX_CODE_RETRIES = 10


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite 读回的 naive datetime 按 UTC 解释"""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _is_expired(coupon: Coupon) -> bool:
    """过期判定（惰性派生）：unused 且 expires_at 已过"""
    expires_at = _as_utc(coupon.expires_at)
    return expires_at is not None and expires_at <= _utcnow()


def _not_expired_sql():
    """SQL 层「未过期」谓词（SQLite 存 naive UTC，比较用 naive now）"""
    naive_now = _utcnow().replace(tzinfo=None)
    return or_(Coupon.expires_at.is_(None), Coupon.expires_at > naive_now)


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
        ttl_days: Optional[int] = None,
        owner_user_id: Optional[str] = None,
    ) -> List[Coupon]:
        """批量创建折扣券

        Args:
            amount: 面额（分，>0）
            count: 数量（1-500）
            source: 来源（admin / email_auto）
            created_by: 创建人用户 ID（admin 创建时填）
            ttl_days: 有效期天数（None=读运行时默认配置；1-3650）
            owner_user_id: 归属用户 ID（None=未绑定流通券）

        Returns:
            创建的券列表

        Raises:
            ValueError: 参数非法
        """
        if amount <= 0:
            raise ValueError("券面额必须大于 0")
        if not 1 <= count <= 500:
            raise ValueError("批量创建数量须在 1-500 之间")
        if ttl_days is None:
            ttl_days = coupon_config.get_default_ttl_days()
        if not coupon_config.MIN_TTL_DAYS <= ttl_days <= coupon_config.MAX_TTL_DAYS:
            raise ValueError(
                f"有效期天数须在 {coupon_config.MIN_TTL_DAYS}-{coupon_config.MAX_TTL_DAYS} 之间"
            )

        now = _utcnow()
        expires_at = now + timedelta(days=ttl_days)
        async with AsyncSessionLocal() as db:
            coupons: List[Coupon] = []
            for _ in range(count):
                code = await cls._pick_unique_code(db)
                coupon = Coupon(
                    code=code,
                    amount=amount,
                    status="unused",
                    expires_at=expires_at,
                    owner_user_id=owner_user_id,
                    source=source,
                    created_by=created_by,
                    created_at=now,
                )
                db.add(coupon)
                coupons.append(coupon)
            await db.commit()
            for c in coupons:
                await db.refresh(c)
            logger.info(
                "created %d coupons (amount=%d, source=%s, ttl_days=%d)",
                len(coupons),
                amount,
                source,
                ttl_days,
            )
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
        供后台展示。status=expired 为派生态过滤（unused 且已过期）。

        Args:
            status: 状态过滤（unused/locked/used/expired/void）
            page / page_size: 分页
            source: 来源过滤（admin/email_auto）

        Returns:
            (items, total)
        """
        async with AsyncSessionLocal() as db:
            base = select(Coupon)
            count_base = select(func.count()).select_from(Coupon)
            naive_now = _utcnow().replace(tzinfo=None)
            if status == "expired":
                cond = and_(
                    Coupon.status == "unused",
                    Coupon.expires_at.is_not(None),
                    Coupon.expires_at <= naive_now,
                )
                base = base.where(cond)
                count_base = count_base.where(cond)
            elif status == "unused":
                # unused 过滤排除已过期行（expired 是派生态）
                cond = and_(Coupon.status == "unused", _not_expired_sql())
                base = base.where(cond)
                count_base = count_base.where(cond)
            elif status:
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
    def _derive_status(cls, coupon: Coupon) -> str:
        """派生状态：unused 且已过期 → expired（不落库），其余原样"""
        if coupon.status == "unused" and _is_expired(coupon):
            return "expired"
        return coupon.status

    @classmethod
    async def _serialize(cls, db, coupon: Coupon) -> Dict[str, Any]:
        """ORM → API dict（联查邮箱与订单号；status 为派生态）"""
        used_by_email: Optional[str] = None
        if coupon.used_by_user_id:
            used_by_email = (
                await db.execute(select(User.email).where(User.id == coupon.used_by_user_id))
            ).scalar_one_or_none()

        owner_email: Optional[str] = None
        if coupon.owner_user_id:
            owner_email = (
                await db.execute(select(User.email).where(User.id == coupon.owner_user_id))
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
            "status": cls._derive_status(coupon),
            "source": coupon.source,
            "created_by": coupon.created_by,
            "created_at": coupon.created_at.isoformat() if coupon.created_at else None,
            "expires_at": coupon.expires_at.isoformat() if coupon.expires_at else None,
            "owner_email": owner_email,
            "voided_at": coupon.voided_at.isoformat() if coupon.voided_at else None,
            "used_at": coupon.used_at.isoformat() if coupon.used_at else None,
            "used_by_email": used_by_email,
            "used_order_no": used_order_no,
            "locked_order_no": locked_order_no,
        }

    # ─── 后台管理（used/locked 一律不可改；void 仅可恢复）─────────

    @classmethod
    async def update_coupon_amount(cls, coupon_id: str, amount: int) -> Coupon:
        """调整券面额（仅 unused，含派生 expired）

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
    async def update_coupon_expiry(cls, coupon_id: str, expires_at: datetime) -> Coupon:
        """调整券过期时间（仅 unused，含派生 expired——改期即复活）

        Raises:
            ValueError: 券不存在 / 非 unused / 时间非法
        """
        expires_at = _as_utc(expires_at)
        if expires_at is None:
            raise ValueError("过期时间不能为空")
        async with AsyncSessionLocal() as db:
            coupon = await cls._get_or_raise(db, coupon_id)
            if coupon.status != "unused":
                raise ValueError(f"仅未使用的券可调整有效期（当前状态：{coupon.status}）")
            coupon.expires_at = expires_at
            await db.commit()
            await db.refresh(coupon)
            logger.info("coupon %s 有效期调整为 %s", coupon.code, expires_at.isoformat())
            return coupon

    @classmethod
    async def delete_coupon(cls, coupon_id: str) -> None:
        """作废券（仅 unused，含派生 expired；软删除置 void，可恢复）

        Raises:
            ValueError: 券不存在 / 非 unused
        """
        async with AsyncSessionLocal() as db:
            coupon = await cls._get_or_raise(db, coupon_id)
            if coupon.status != "unused":
                raise ValueError(f"仅未使用的券可作废（当前状态：{coupon.status}）")
            coupon.status = "void"
            coupon.voided_at = _utcnow()
            await db.commit()
            logger.info("coupon %s 已作废（软删除）", coupon.code)

    @classmethod
    async def restore_coupon(cls, coupon_id: str) -> Coupon:
        """恢复已作废券：void → unused（若已过有效期，恢复后即派生 expired，可再改期）

        Raises:
            ValueError: 券不存在 / 非 void
        """
        async with AsyncSessionLocal() as db:
            coupon = await cls._get_or_raise(db, coupon_id)
            if coupon.status != "void":
                raise ValueError(f"仅已作废的券可恢复（当前状态：{coupon.status}）")
            coupon.status = "unused"
            coupon.voided_at = None
            await db.commit()
            await db.refresh(coupon)
            logger.info("coupon %s 已恢复", coupon.code)
            return coupon

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
    async def validate_coupon(cls, code: str, user_id: Optional[str] = None) -> Coupon:
        """校验券码可用：存在、unused、未过期、归属匹配

        Args:
            code: 券码
            user_id: 当前用户 ID（归属校验用；None 跳过归属校验，兼容内部调用）

        Raises:
            ValueError: 券不存在 / 不可用 / 已过期 / 不属于当前账号
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
            if _is_expired(coupon):
                raise ValueError("券已过期")
            if (
                user_id
                and coupon.owner_user_id
                and coupon.owner_user_id != user_id
            ):
                raise ValueError("该券不属于当前账号")
            return coupon

    @classmethod
    async def lock_coupon(cls, code: str, order_id: str, user_id: Optional[str] = None) -> Coupon:
        """下单锁定：unused → locked，写 locked_order_id；未绑定券同时认领归属

        并发安全：UPDATE ... WHERE status='unused' 且未过期且归属匹配，
        按影响行数判断，并发竞争下只有一单能锁定成功。
        认领与锁定在同一 UPDATE 中原子完成（校验不认领，防扫号抢券）。

        Raises:
            ValueError: 券不存在 / 已被锁定或使用 / 已过期 / 不属于当前账号
        """
        normalized = (code or "").strip().upper()
        naive_now = _utcnow().replace(tzinfo=None)
        conditions = [Coupon.code == normalized, Coupon.status == "unused", _not_expired_sql()]
        if user_id:
            conditions.append(
                or_(Coupon.owner_user_id.is_(None), Coupon.owner_user_id == user_id)
            )
        values: Dict[str, Any] = {"status": "locked", "locked_order_id": order_id}
        if user_id:
            values["owner_user_id"] = user_id  # 认领（已归属本人时幂等）
        async with AsyncSessionLocal() as db:
            result = await db.execute(update(Coupon).where(and_(*conditions)).values(**values))
            if result.rowcount == 0:
                await db.rollback()
                # 区分不存在 vs 状态不对，给出准确错误
                coupon = (
                    await db.execute(select(Coupon).where(Coupon.code == normalized))
                ).scalar_one_or_none()
                if not coupon:
                    raise ValueError("券码不存在")
                if coupon.status != "unused":
                    raise ValueError("券码已被使用或锁定中")
                if _is_expired(coupon):
                    raise ValueError("券已过期")
                raise ValueError("该券不属于当前账号")
            await db.commit()
            return (await db.execute(select(Coupon).where(Coupon.code == normalized))).scalar_one()

    @classmethod
    async def release_coupon(cls, coupon_id: str) -> Coupon:
        """关单释放：locked → unused，清空 locked_order_id（保留归属，认领不撤销）

        不判过期：释放后若已过有效期，自然派生为 expired。

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

        不判过期：锁定免疫，锁定期内过期的券仍可正常核销。

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
                    used_at=_utcnow(),
                )
            )
            if result.rowcount == 0:
                await db.rollback()
                coupon = await cls._get_or_raise(db, coupon_id)
                raise ValueError(f"券不在锁定状态，无法核销（当前状态：{coupon.status}）")
            await db.commit()
            return (await db.execute(select(Coupon).where(Coupon.id == coupon_id))).scalar_one()

    @classmethod
    async def return_coupon_on_refund(cls, coupon_id: str) -> Coupon:
        """退款退券：used → unused，清核销字段，保留归属（退还给使用者）

        不判过期：若已过有效期，退回后自然派生为 expired。

        Raises:
            ValueError: 券不存在或非 used
        """
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                update(Coupon)
                .where(Coupon.id == coupon_id, Coupon.status == "used")
                .values(
                    status="unused",
                    used_by_user_id=None,
                    used_order_id=None,
                    used_at=None,
                )
            )
            if result.rowcount == 0:
                await db.rollback()
                coupon = await cls._get_or_raise(db, coupon_id)
                raise ValueError(f"券不在已核销状态，无法退回（当前状态：{coupon.status}）")
            await db.commit()
            logger.info("coupon %s 已随退款退回", coupon_id)
            return (await db.execute(select(Coupon).where(Coupon.id == coupon_id))).scalar_one()

    # ─── 用户侧「我的折扣券」─────────────────────────────────────

    @classmethod
    async def list_my_coupons(cls, user_id: str) -> Dict[str, List[Dict[str, Any]]]:
        """当前用户的券列表（不含 void），按派生态分组

        Returns:
            {"available": [...], "used": [...], "expired": [...]}
            单券字段：code/amount/expires_at/used_at/used_order_no/source
        """
        groups: Dict[str, List[Dict[str, Any]]] = {"available": [], "used": [], "expired": []}
        async with AsyncSessionLocal() as db:
            rows = (
                (
                    await db.execute(
                        select(Coupon)
                        .where(Coupon.owner_user_id == user_id, Coupon.status != "void")
                        .order_by(Coupon.created_at.desc())
                    )
                )
                .scalars()
                .all()
            )
            for c in rows:
                used_order_no: Optional[str] = None
                if c.used_order_id:
                    used_order_no = (
                        await db.execute(
                            select(PaymentOrder.order_no).where(
                                PaymentOrder.id == c.used_order_id
                            )
                        )
                    ).scalar_one_or_none()
                item = {
                    "code": c.code,
                    "amount": c.amount,
                    "expires_at": c.expires_at.isoformat() if c.expires_at else None,
                    "used_at": c.used_at.isoformat() if c.used_at else None,
                    "used_order_no": used_order_no,
                    "source": c.source,
                }
                derived = cls._derive_status(c)
                if derived == "unused":
                    groups["available"].append(item)
                elif derived == "expired":
                    groups["expired"].append(item)
                elif c.status == "used":
                    groups["used"].append(item)
                # locked（有 pending 订单挂着）不展示在各组，避免用户重复用券疑惑
            return groups

    # ─── 券池取券（邮件发券用）──────────────────────────────────

    @classmethod
    async def draw_from_pool(
        cls, exclude_ids: Optional[set] = None, owner_user_id: Optional[str] = None
    ) -> Coupon:
        """券池 FIFO 取券：取创建最早的未绑定且未过期 unused；池空按
        DEFAULT_COUPON_AMOUNT 自动创建。发放即绑定：取到/创建的券写 owner_user_id。

        注意：取券不改状态（券仍 unused，直到下单锁定）。同一批群发内
        通过 exclude_ids 排除已分出的券，保证每个收件人拿到不同券码。

        Args:
            exclude_ids: 本次批次内已分出的券 ID 集合（可选）
            owner_user_id: 收件人用户 ID（发放即绑定；可选，None 不绑定）

        Returns:
            取到（或新创建）的券
        """
        async with AsyncSessionLocal() as db:
            q = (
                select(Coupon)
                .where(
                    Coupon.status == "unused",
                    Coupon.owner_user_id.is_(None),
                    _not_expired_sql(),
                )
                .order_by(Coupon.created_at.asc(), Coupon.id.asc())
                .limit(1)
            )
            if exclude_ids:
                q = q.where(Coupon.id.not_in(list(exclude_ids)))
            coupon = (await db.execute(q)).scalar_one_or_none()
            if coupon:
                if owner_user_id:
                    coupon.owner_user_id = owner_user_id
                    await db.commit()
                    await db.refresh(coupon)
                return coupon

        # 池空：按默认面额自动创建（source="email_auto"，有效期走默认配置）
        created = await cls.create_coupons(
            amount=settings.DEFAULT_COUPON_AMOUNT,
            count=1,
            source="email_auto",
            created_by=None,
            owner_user_id=owner_user_id,
        )
        logger.info(
            "coupon pool empty, auto-created %s (amount=%d)",
            created[0].code,
            settings.DEFAULT_COUPON_AMOUNT,
        )
        return created[0]
