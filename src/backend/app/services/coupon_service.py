"""
折扣券服务

职责：
1. create_coupons: 单个/批量创建（新码 Q-+8 位防混淆字符，唯一冲突重试）；
   有效期 ttl_days 默认读运行时配置（coupon_config，默认 90 天），可绑定归属用户；
   max_uses 支持多次核销券（促销码模式，2026-10-06）：n=1 单次（原语义），
   n>1 流通券（禁绑归属）总额度 n 次、每用户每券限 1 次
2. list_coupons: 分页列表（used 态联查核销用户邮箱、锁定/核销订单号）；
   status 过滤支持 expired（unused 且已过期的派生态）、suspended（停用）、
   void（软删除）与 n>1 用满（used_count>=max_uses 的派生 used）
3. update_coupon_amount / update_coupon_expiry / delete_coupon(软删除) / restore_coupon /
   suspend_coupon / resume_coupon: 后台管理；used/locked 一律不可改；
   n>1 部分核销后仍可调面额/有效期（停用→调整→启用的运营闭环），但不可作废
4. validate / lock / release / redeem: 下单用券状态机
   n=1：unused → locked（下单锁定+认领）→ used（支付成功核销）；关单释放 locked → unused（保留归属）
   n>1：券级 status 恒 unused；锁定=占名额（locked_count 原子自增 + coupon_redemptions 行），
        核销=行 locked→used + 计数迁移；每用户每券限 1 次（NOT EXISTS 守卫）
   过期判定惰性派生：unused 且 expires_at<now 即不可用；locked 免疫（锁定期不过期）
5. draw_from_pool: 券池 FIFO 取券（邮件发券用，发放即绑定收件人；仅取 n=1 券），
   池空按 DEFAULT_COUPON_AMOUNT 自动创建
6. list_my_coupons: 用户侧「我的折扣券」（按派生态分组 available/used/expired；
   used 组含本人名下券与共享券核销记录）
7. return_coupon_on_refund: 退款退券（按订单核销行回退：used_count-1；
   n=1 同步回退单槽字段，保留归属）

设计要点：
- 金额一律整数分
- 并发守卫一律「UPDATE ... WHERE 前置条件」的影响行数判断：
  n=1 锁定守卫 status='unused'；n>1 锁定守卫 used_count+locked_count<max_uses
  + 停用/过期/每用户一次（NOT EXISTS 子查询），并发下恰好 n 个锁成功
- 归属语义：owner_user_id=None 为流通券（下单锁定时认领）；已绑定券仅归属人可用；
  n>1 共享券恒为流通券（创建即校验，券池跳过）
- expired/suspended 不落库，是 unused 的派生态（无定时 job）；void 是落库的软删除态
- n=1 双写：新发生的锁定/核销同时写 coupon_redemptions 行与单槽字段（历史数据不回填）
- 业务约束违反一律抛 ValueError（路由层转 400）
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, exists, func, or_, select, update

from app.config.settings import settings
from app.models.database import AsyncSessionLocal
from app.models.payment import Coupon, CouponRedemption, PaymentOrder
from app.models.user import User
from app.services import coupon_config
from app.utils.code_format import (
    COUPON_CONTEXT,
    generate_coupon_code,
    normalize_user_code,
)

logger = logging.getLogger(__name__)

# 多次券额度上限（D7：面额×n=总补贴负债，封顶可控）
MAX_MAX_USES = 10000
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


def _is_exhausted(coupon: Coupon) -> bool:
    """名额耗尽判定：n>1 且 used_count >= max_uses（n=1 恒 False，其用满态落库为 used）"""
    return coupon.max_uses > 1 and coupon.used_count >= coupon.max_uses


def _has_quota_sql():
    """SQL 层「尚有名额」谓词（n>1：used_count<max_uses；n=1 状态机自守卫恒真）"""
    return Coupon.used_count < Coupon.max_uses


def _exhausted_sql():
    """SQL 层「名额耗尽」谓词（与 _is_exhausted 同口径的 SQL 版）"""
    return Coupon.used_count >= Coupon.max_uses


class CouponService:
    """折扣券服务"""

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
        max_uses: int = 1,
    ) -> List[Coupon]:
        """批量创建折扣券

        Args:
            amount: 面额（分，>0）
            count: 数量（1-500）
            source: 来源（admin / email_auto）
            created_by: 创建人用户 ID（admin 创建时填）
            ttl_days: 有效期天数（None=读运行时默认配置；1-3650）
            owner_user_id: 归属用户 ID（None=未绑定流通券；max_uses>1 时必须 None）
            max_uses: 总核销次数上限（1-10000；n=1 为单次券原语义）

        Returns:
            创建的券列表

        Raises:
            ValueError: 参数非法
        """
        if amount <= 0:
            raise ValueError("券面额必须大于 0")
        if not 1 <= count <= 500:
            raise ValueError("批量创建数量须在 1-500 之间")
        if not 1 <= max_uses <= MAX_MAX_USES:
            raise ValueError(f"总核销次数须在 1-{MAX_MAX_USES} 之间")
        if max_uses > 1 and owner_user_id is not None:
            raise ValueError("多次核销券为共享流通券，不可绑定归属用户")
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
                    max_uses=max_uses,
                    used_count=0,
                    locked_count=0,
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
                "created %d coupons (amount=%d, source=%s, ttl_days=%d, max_uses=%d)",
                len(coupons),
                amount,
                source,
                ttl_days,
                max_uses,
            )
            return coupons

    @classmethod
    async def _pick_unique_code(cls, db) -> str:
        """生成不冲突的券码（唯一冲突重试；新格式 Q-+8 位，与存量裸码空间永不相交）"""
        for _ in range(_MAX_CODE_RETRIES):
            code = generate_coupon_code()
            exists_row = (
                await db.execute(select(Coupon.id).where(Coupon.code == code))
            ).scalar_one_or_none()
            if not exists_row:
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
        供后台展示。status 过滤与派生态对齐（见 _derive_status 的 SQL 版条件）。

        Args:
            status: 状态过滤（unused/locked/used/expired/suspended/void）
            page / page_size: 分页
            source: 来源过滤（admin/email_auto）

        Returns:
            (items, total)
        """
        async with AsyncSessionLocal() as db:
            base = select(Coupon)
            count_base = select(func.count()).select_from(Coupon)
            cond = cls._status_filter_sql(status)
            if cond is not None:
                base = base.where(cond)
                count_base = count_base.where(cond)
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
    def _status_filter_sql(cls, status: Optional[str]):
        """status 过滤条件（与 _derive_status 口径一致；None=不过滤）

        - used：落库 used（n=1）∪ 名额耗尽（n>1 且 used_count>=max_uses）
        - unused：落库 unused 且未停用、有名额、未过期（排除派生 expired/suspended/used）
        - expired：落库 unused、有名额、已过期（名额随过期整体作废）
        - suspended：落库 unused、有名额、未过期、已停用
        """
        if not status:
            return None
        if status == "used":
            return or_(
                Coupon.status == "used",
                and_(Coupon.status == "unused", _exhausted_sql()),
            )
        if status == "unused":
            return and_(
                Coupon.status == "unused",
                Coupon.suspended_at.is_(None),
                _has_quota_sql(),
                _not_expired_sql(),
            )
        if status == "expired":
            return and_(
                Coupon.status == "unused",
                _has_quota_sql(),
                Coupon.expires_at.is_not(None),
                Coupon.expires_at <= _utcnow().replace(tzinfo=None),
            )
        if status == "suspended":
            return and_(
                Coupon.status == "unused",
                Coupon.suspended_at.is_not(None),
                _has_quota_sql(),
                _not_expired_sql(),
            )
        return Coupon.status == status  # locked / void

    @classmethod
    def _derive_status(cls, coupon: Coupon) -> str:
        """派生状态（不落库）：

        - void/locked/used（n=1 落库态）原样
        - n>1 名额耗尽 → used（优先于 expired/suspended，终态）
        - unused 且已过期 → expired（优先于 suspended，时间硬边界）
        - unused 且已停用 → suspended
        """
        if coupon.status in ("void", "locked", "used"):
            return coupon.status
        if _is_exhausted(coupon):
            return "used"
        if _is_expired(coupon):
            return "expired"
        if coupon.suspended_at is not None:
            return "suspended"
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
            "max_uses": coupon.max_uses,
            "used_count": coupon.used_count,
            "locked_count": coupon.locked_count,
            "status": cls._derive_status(coupon),
            "source": coupon.source,
            "created_by": coupon.created_by,
            "created_at": coupon.created_at.isoformat() if coupon.created_at else None,
            "expires_at": coupon.expires_at.isoformat() if coupon.expires_at else None,
            "owner_email": owner_email,
            "voided_at": coupon.voided_at.isoformat() if coupon.voided_at else None,
            "suspended_at": coupon.suspended_at.isoformat() if coupon.suspended_at else None,
            "used_at": coupon.used_at.isoformat() if coupon.used_at else None,
            "used_by_email": used_by_email,
            "used_order_no": used_order_no,
            "locked_order_no": locked_order_no,
        }

    # ─── 后台管理（used/locked 一律不可改；void 仅可恢复）─────────

    @classmethod
    async def update_coupon_amount(cls, coupon_id: str, amount: int) -> Coupon:
        """调整券面额（仅 unused，含派生 expired/suspended；n>1 部分核销后仍可调——
        停用→调整→启用的运营闭环，仅影响后续核销）

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
        """作废券（仅 unused 且从未使用/锁定；软删除置 void，可恢复）。
        n>1 部分核销的券不可作废——用 suspend_coupon 停用剩余名额。

        Raises:
            ValueError: 券不存在 / 非 unused / 已有核销或锁定记录
        """
        async with AsyncSessionLocal() as db:
            coupon = await cls._get_or_raise(db, coupon_id)
            if coupon.status != "unused":
                raise ValueError(f"仅未使用的券可作废（当前状态：{coupon.status}）")
            if coupon.used_count > 0 or coupon.locked_count > 0:
                raise ValueError("已有核销或锁定记录的券不可作废，请改用「停用」冻结剩余名额")
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
    async def suspend_coupon(cls, coupon_id: str) -> Coupon:
        """停用券（停机开关，D6）：仅 unused（含派生 expired/suspended）可停；
        已核销名额保持有效，剩余名额立即冻结（锁定被拒），可 resume 恢复。

        Raises:
            ValueError: 券不存在 / 非 unused（locked/used/void 无停用意义）
        """
        async with AsyncSessionLocal() as db:
            coupon = await cls._get_or_raise(db, coupon_id)
            if coupon.status != "unused":
                raise ValueError(f"仅未使用完的券可停用（当前状态：{coupon.status}）")
            if coupon.suspended_at is not None:
                raise ValueError("券已处于停用状态")
            coupon.suspended_at = _utcnow()
            await db.commit()
            await db.refresh(coupon)
            logger.info("coupon %s 已停用（剩余名额冻结）", coupon.code)
            return coupon

    @classmethod
    async def resume_coupon(cls, coupon_id: str) -> Coupon:
        """启用券：清除停用标记，剩余名额恢复可用（若已过期则自然派生 expired）

        Raises:
            ValueError: 券不存在 / 未处于停用状态
        """
        async with AsyncSessionLocal() as db:
            coupon = await cls._get_or_raise(db, coupon_id)
            if coupon.suspended_at is None:
                raise ValueError(f"券未处于停用状态（当前状态：{cls._derive_status(coupon)}）")
            coupon.suspended_at = None
            await db.commit()
            await db.refresh(coupon)
            logger.info("coupon %s 已启用", coupon.code)
            return coupon

    @classmethod
    async def _get_or_raise(cls, db, coupon_id: str) -> Coupon:
        coupon = (
            await db.execute(select(Coupon).where(Coupon.id == coupon_id))
        ).scalar_one_or_none()
        if not coupon:
            raise ValueError("券不存在")
        return coupon

    # ─── 下单用券状态机 ─────────────────────────────────────────

    @classmethod
    def _normalize(cls, code: str) -> str:
        """用户输入券码归一化（全角横杠/折行空白/裸 8 位补 Q- 前缀）"""
        return normalize_user_code(code or "", COUPON_CONTEXT)

    @classmethod
    async def validate_coupon(cls, code: str, user_id: Optional[str] = None) -> Coupon:
        """校验券码可用：存在、unused、未过期、未停用、有名额、归属匹配、每用户限一次

        Args:
            code: 券码（自动归一化）
            user_id: 当前用户 ID（归属与每用户一次校验用；None 跳过，兼容内部调用）

        Raises:
            ValueError: 券不存在 / 不可用 / 已过期 / 已停用 / 已被抢完 /
                每账号限用一次 / 不属于当前账号
        """
        normalized = cls._normalize(code)
        if not normalized:
            raise ValueError("券码不能为空")
        async with AsyncSessionLocal() as db:
            coupon = (
                await db.execute(select(Coupon).where(Coupon.code == normalized))
            ).scalar_one_or_none()
            if not coupon:
                raise ValueError("券码不存在")
            await cls._assert_usable(db, coupon, user_id=user_id)
            return coupon

    @classmethod
    async def _assert_usable(cls, db, coupon: Coupon, user_id: Optional[str]) -> None:
        """共用可用性校验（validate 与 lock 失败归因）；并发窗口内以 lock 的 UPDATE 守卫为准"""
        if coupon.status != "unused":
            raise ValueError("券码已被使用或锁定中")
        if _is_exhausted(coupon):
            raise ValueError("该券已被抢完")
        if coupon.used_count + coupon.locked_count >= coupon.max_uses:
            # n>1 名额被锁定占满（含释放回补窗口；n=1 locked 已被首个分支拦截）
            raise ValueError("该券已被抢完")
        if coupon.suspended_at is not None:
            raise ValueError("该券已停止使用")
        if _is_expired(coupon):
            raise ValueError("券已过期")
        if user_id and coupon.owner_user_id and coupon.owner_user_id != user_id:
            raise ValueError("该券不属于当前账号")
        if user_id and coupon.max_uses > 1:
            used = (
                await db.execute(
                    select(CouponRedemption.id).where(
                        CouponRedemption.coupon_id == coupon.id,
                        CouponRedemption.user_id == user_id,
                        CouponRedemption.status.in_(("locked", "used")),
                    )
                )
            ).scalar_one_or_none()
            if used:
                raise ValueError("该券每个账号限用一次")

    @classmethod
    async def lock_coupon(cls, code: str, order_id: str, user_id: Optional[str] = None) -> Coupon:
        """下单锁定（n=1：unused→locked+认领；n>1：占名额 locked_count+1），
        同时写 coupon_redemptions 行（status=locked）。

        并发安全：UPDATE ... WHERE 前置条件的影响行数判断。
        - n=1 守卫：status='unused' 且未过期且归属匹配（原逻辑原样保留）
        - n>1 守卫：status='unused' 且未停用且有名额且未过期且该用户无
          locked/used 核销行（NOT EXISTS 子查询，每用户每券限 1 次）
        并发竞争下 n=1 只有一单、n>1 恰好 n 单能锁定成功。

        Raises:
            ValueError: 券不存在 / 已被锁定或使用 / 已过期 / 已停用 / 已被抢完 /
                每账号限用一次 / 不属于当前账号
        """
        normalized = cls._normalize(code)
        if not normalized:
            raise ValueError("券码不能为空")
        naive_now = _utcnow().replace(tzinfo=None)
        async with AsyncSessionLocal() as db:
            coupon = (
                await db.execute(select(Coupon).where(Coupon.code == normalized))
            ).scalar_one_or_none()
            if not coupon:
                raise ValueError("券码不存在")

            # rollback 会使 ORM 实例过期（属性访问触发同步懒加载），先捕获主键
            coupon_id = coupon.id

            if coupon.max_uses == 1:
                # ── n=1 原子锁（原语义 + locked_count 同步自增）──
                conditions = [
                    Coupon.id == coupon.id,
                    Coupon.status == "unused",
                    _not_expired_sql(),
                ]
                if user_id:
                    conditions.append(
                        or_(Coupon.owner_user_id.is_(None), Coupon.owner_user_id == user_id)
                    )
                values: Dict[str, Any] = {
                    "status": "locked",
                    "locked_order_id": order_id,
                    "locked_count": Coupon.locked_count + 1,
                }
                if user_id:
                    values["owner_user_id"] = user_id  # 认领（已归属本人时幂等）
                result = await db.execute(update(Coupon).where(and_(*conditions)).values(**values))
                if result.rowcount == 0:
                    await db.rollback()
                    fresh = await cls._get_or_raise(db, coupon_id)
                    await cls._assert_usable(db, fresh, user_id=user_id)
                    raise ValueError("券码已被使用或锁定中")  # 兜底（守卫窗口内状态变化）
            else:
                # ── n>1 名额守卫锁（NOT EXISTS 防同人重复占额）──
                conditions = [
                    Coupon.id == coupon.id,
                    Coupon.status == "unused",
                    Coupon.suspended_at.is_(None),
                    Coupon.used_count + Coupon.locked_count < Coupon.max_uses,
                    _not_expired_sql(),
                ]
                if user_id:
                    conditions.append(
                        ~exists(
                            select(CouponRedemption.id).where(
                                CouponRedemption.coupon_id == Coupon.id,
                                CouponRedemption.user_id == user_id,
                                CouponRedemption.status.in_(("locked", "used")),
                            )
                        )
                    )
                result = await db.execute(
                    update(Coupon)
                    .where(and_(*conditions))
                    .values(locked_count=Coupon.locked_count + 1)
                )
                if result.rowcount == 0:
                    await db.rollback()
                    fresh = await cls._get_or_raise(db, coupon_id)
                    await cls._assert_usable(db, fresh, user_id=user_id)
                    raise ValueError("券码不可用")  # 兜底

            # 核销行（n=1/n>1 统一记行；历史存量锁定券无行，此处新建仍正确）
            db.add(
                CouponRedemption(
                    coupon_id=coupon_id,
                    order_id=order_id,
                    user_id=user_id or "",
                    status="locked",
                    locked_at=_utcnow(),
                )
            )
            await db.commit()
            return (await db.execute(select(Coupon).where(Coupon.id == coupon_id))).scalar_one()

    @classmethod
    async def release_coupon(cls, coupon_id: str, order_id: Optional[str] = None) -> Coupon:
        """关单释放：核销行 locked→released + locked_count-1；
        n=1 同时 locked→unused、清 locked_order_id（保留归属，认领不撤销）。

        不判过期：释放后若已过有效期，自然派生为 expired。

        Args:
            coupon_id: 券 ID
            order_id: 订单 ID（优先按行释放；缺省按 coupon_id 找 locked 行，
                      兼容历史无行数据的 n=1 存量券）

        Raises:
            ValueError: 券不存在或无锁定中的核销
        """
        async with AsyncSessionLocal() as db:
            await cls._get_or_raise(db, coupon_id)

            # 1) 核销行 locked → released
            row_cond = [
                CouponRedemption.coupon_id == coupon_id,
                CouponRedemption.status == "locked",
            ]
            if order_id:
                row_cond.append(CouponRedemption.order_id == order_id)
            row_result = await db.execute(
                update(CouponRedemption).where(and_(*row_cond)).values(status="released")
            )

            # 2) n=1 券级状态回退（存量无行券靠这一步；n>1 券级状态本就是 unused）
            legacy_result = await db.execute(
                update(Coupon)
                .where(Coupon.id == coupon_id, Coupon.status == "locked")
                .values(status="unused", locked_order_id=None)
            )

            if row_result.rowcount == 0 and legacy_result.rowcount == 0:
                await db.rollback()
                coupon = await cls._get_or_raise(db, coupon_id)
                raise ValueError(f"券不在锁定状态（当前状态：{cls._derive_status(coupon)}）")

            # 3) 名额回补
            if row_result.rowcount > 0 or legacy_result.rowcount > 0:
                await db.execute(
                    update(Coupon)
                    .where(Coupon.id == coupon_id, Coupon.locked_count > 0)
                    .values(locked_count=Coupon.locked_count - 1)
                )
            await db.commit()
            return (await db.execute(select(Coupon).where(Coupon.id == coupon_id))).scalar_one()

    @classmethod
    async def redeem_coupon(cls, coupon_id: str, user_id: str, order_id: str) -> Coupon:
        """支付成功核销：核销行 locked→used；计数迁移 locked_count-1、used_count+1；
        n=1 同步写单槽字段（status=used/used_by/used_order/used_at，双写兼容旧查询）。

        不判过期：锁定免疫，锁定期内过期的券仍可正常核销。

        Raises:
            ValueError: 券不存在或非锁定中的核销
        """
        async with AsyncSessionLocal() as db:
            await cls._get_or_raise(db, coupon_id)

            # 1) 核销行 locked → used
            row_result = await db.execute(
                update(CouponRedemption)
                .where(
                    CouponRedemption.coupon_id == coupon_id,
                    CouponRedemption.order_id == order_id,
                    CouponRedemption.status == "locked",
                )
                .values(status="used", used_at=_utcnow())
            )

            # 2) n=1 券级状态推进（存量无行券靠这一步；失败即整体失败）
            legacy_result = await db.execute(
                update(Coupon)
                .where(Coupon.id == coupon_id, Coupon.status == "locked")
                .values(
                    status="used",
                    used_by_user_id=user_id,
                    used_order_id=order_id,
                    used_at=_utcnow(),
                )
            )

            if row_result.rowcount == 0 and legacy_result.rowcount == 0:
                await db.rollback()
                coupon = await cls._get_or_raise(db, coupon_id)
                raise ValueError(
                    f"券不在锁定状态，无法核销（当前状态：{cls._derive_status(coupon)}）"
                )

            # 3) 计数迁移：locked → used（幂等保护：locked_count>0 才减）
            await db.execute(
                update(Coupon)
                .where(Coupon.id == coupon_id, Coupon.locked_count > 0)
                .values(
                    locked_count=Coupon.locked_count - 1,
                    used_count=Coupon.used_count + 1,
                )
            )
            await db.commit()
            return (await db.execute(select(Coupon).where(Coupon.id == coupon_id))).scalar_one()

    @classmethod
    async def return_coupon_on_refund(
        cls, coupon_id: str, order_id: Optional[str] = None
    ) -> Coupon:
        """退款退券（按订单核销行回退）：核销行 used→refunded、used_count-1、名额恢复；
        n=1 同步回退单槽字段（used→unused，保留归属，退还给使用者）。

        不判过期：若已过有效期，退回后自然派生为 expired。

        Args:
            coupon_id: 券 ID
            order_id: 退款订单 ID（n>1 必传以定位核销行；n=1 缺省走单槽回退兼容旧调用）

        Raises:
            ValueError: 券不存在或无该订单的已核销记录
        """
        async with AsyncSessionLocal() as db:
            await cls._get_or_raise(db, coupon_id)

            # 1) 核销行 used → refunded
            row_cond = [CouponRedemption.coupon_id == coupon_id, CouponRedemption.status == "used"]
            if order_id:
                row_cond.append(CouponRedemption.order_id == order_id)
            row_result = await db.execute(
                update(CouponRedemption)
                .where(and_(*row_cond))
                .values(refunded_at=_utcnow(), status="refunded")
            )

            # 2) n=1 券级状态回退（存量无行券靠这一步）
            legacy_result = await db.execute(
                update(Coupon)
                .where(Coupon.id == coupon_id, Coupon.status == "used")
                .values(
                    status="unused",
                    used_by_user_id=None,
                    used_order_id=None,
                    used_at=None,
                )
            )

            if row_result.rowcount == 0 and legacy_result.rowcount == 0:
                await db.rollback()
                coupon = await cls._get_or_raise(db, coupon_id)
                raise ValueError(
                    f"券不在已核销状态，无法退回（当前状态：{cls._derive_status(coupon)}）"
                )

            # 3) 名额恢复
            await db.execute(
                update(Coupon)
                .where(Coupon.id == coupon_id, Coupon.used_count > 0)
                .values(used_count=Coupon.used_count - 1)
            )
            await db.commit()
            logger.info("coupon %s 已随退款退回（order=%s）", coupon_id, order_id)
            return (await db.execute(select(Coupon).where(Coupon.id == coupon_id))).scalar_one()

    # ─── 用户侧「我的折扣券」─────────────────────────────────────

    @classmethod
    async def list_my_coupons(cls, user_id: str) -> Dict[str, List[Dict[str, Any]]]:
        """当前用户的券列表（不含 void），按派生态分组

        Returns:
            {"available": [...], "used": [...], "expired": [...]}
            单券字段：code/amount/expires_at/used_at/used_order_no/source；
            used 组 = 名下已核销券（n=1）∪ 共享券核销记录（n>1，不归属仅记录）
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
                            select(PaymentOrder.order_no).where(PaymentOrder.id == c.used_order_id)
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
                if derived in ("unused", "suspended"):
                    groups["available"].append(item)
                elif derived == "expired":
                    groups["expired"].append(item)
                elif c.status == "used":
                    groups["used"].append(item)
                # locked（有 pending 订单挂着）不展示在各组，避免用户重复用券疑惑

            # 共享券（n>1）核销记录 → used 组（按行取，券本身不归属）
            shared_rows = (
                await db.execute(
                    select(CouponRedemption, Coupon)
                    .join(Coupon, CouponRedemption.coupon_id == Coupon.id)
                    .where(
                        CouponRedemption.user_id == user_id,
                        CouponRedemption.status == "used",
                        Coupon.max_uses > 1,
                    )
                    .order_by(CouponRedemption.used_at.desc())
                )
            ).all()
            for redemption, coupon in shared_rows:
                used_order_no = (
                    await db.execute(
                        select(PaymentOrder.order_no).where(PaymentOrder.id == redemption.order_id)
                    )
                ).scalar_one_or_none()
                groups["used"].append(
                    {
                        "code": coupon.code,
                        "amount": coupon.amount,
                        "expires_at": coupon.expires_at.isoformat() if coupon.expires_at else None,
                        "used_at": redemption.used_at.isoformat() if redemption.used_at else None,
                        "used_order_no": used_order_no,
                        "source": coupon.source,
                    }
                )
            return groups

    # ─── 券池取券（邮件发券用）──────────────────────────────────

    @classmethod
    async def draw_from_pool(
        cls, exclude_ids: Optional[set] = None, owner_user_id: Optional[str] = None
    ) -> Coupon:
        """券池 FIFO 取券：取创建最早的未绑定、未过期、未停用且 n=1 的 unused 券；
        池空按 DEFAULT_COUPON_AMOUNT 自动创建。发放即绑定：取到/创建的券写 owner_user_id。
        （共享券 max_uses>1 不进券池——券池语义是「每人一张不同的券」，与共享矛盾。）

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
                    Coupon.max_uses == 1,
                    Coupon.suspended_at.is_(None),
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
