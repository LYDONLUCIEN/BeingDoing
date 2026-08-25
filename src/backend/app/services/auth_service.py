"""
用户认证服务
"""

import hashlib
import logging
import random
import smtplib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select

from app.config.settings import settings
from app.core.database import UserDB
from app.models.database import AsyncSessionLocal, engine
from app.models.refresh_token import RefreshToken
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)


async def _record_auth_active(user_id: str) -> None:
    """日活跃埋点（ADR-0013）：登录/刷新成功时写 auth_active 事件。失败不影响主流程。"""
    try:
        from app.services.analytics_service import AnalyticsService

        await AnalyticsService.record_event("auth_active", user_id=user_id)
    except Exception:
        logger.exception("auth_active 埋点失败: user_id=%s", user_id)


def _friendly_email_send_error(exc: Exception, scene: str) -> ValueError:
    """把 SMTP 发送异常翻译成用户可读的 ValueError（接口统一转为 400）。

    550（收件人不存在/被服务器拒收）单独提示并引导联系管理员；
    其余 SMTP/网络故障提示稍后重试。真实异常只记日志，不暴露给用户。
    """
    refused = isinstance(exc, smtplib.SMTPRecipientsRefused) or (
        isinstance(exc, smtplib.SMTPResponseException) and exc.smtp_code == 550
    )
    if refused:
        logger.warning("%s邮件被邮箱服务器拒收(550): %s", scene, exc)
        return ValueError(
            f"{scene}邮件被邮箱服务器拒收（该邮箱可能不存在或已失效），"
            "无法通过邮箱完成操作，请联系管理员协助处理"
        )
    logger.exception("%s邮件发送失败: %s", scene, exc)
    return ValueError(f"{scene}邮件发送失败，请稍后重试；若多次失败请联系管理员协助")

# 密码加密上下文
# 说明：
# - 当前环境里的 bcrypt 库与 passlib 有兼容性问题（找不到 __about__），并触发 72 字节限制错误
# - 为了简单稳定，本地开发环境改用 pbkdf2_sha256（业界常用方案之一，无额外依赖）
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# JWT 配置（有效期从 .env 的 ACCESS_TOKEN_EXPIRE_MINUTES 读取，默认 60 分钟 = 1 小时内免登录）
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES
REFRESH_TOKEN_EXPIRE_DAYS = settings.REFRESH_TOKEN_EXPIRE_DAYS
REFRESH_TOKEN_ROTATE = settings.REFRESH_TOKEN_ROTATE
REFRESH_TOKEN_ROTATE_GRACE_SECONDS = settings.REFRESH_TOKEN_ROTATE_GRACE_SECONDS
REFRESH_TOKEN_SECRET_KEY = settings.REFRESH_TOKEN_SECRET_KEY or SECRET_KEY

# 简单的内存级找回密码验证码存储（开发环境用，进程重启后会失效）
# key: email/phone, value: {"code": str, "expires_at": datetime, "sent_at": datetime}
_password_reset_email_codes: Dict[str, Dict[str, any]] = {}
_password_reset_phone_codes: Dict[str, Dict[str, any]] = {}
# 账号恢复验证码（已注销账户恢复用，进程内内存存储，重启失效）
# key: email, value: {"code": str, "expires_at": datetime, "sent_at": datetime}
_account_recovery_codes: Dict[str, Dict[str, Any]] = {}
_email_verify_cooldowns: Dict[str, datetime] = {}
_refresh_schema_ready: bool = False

# ── 登录防爆破（进程内内存，对齐上方验证码冷却模式，重启失效）────────────
# 口径：按登录标识（email 小写 / phone）计数，不存在的账号同样计入（防枚举旁路）；
# 1 小时滑动窗口内累计失败达上限 → 锁 15 分钟（固定时长，期间重试不续期）；
# 锁定期间一律拒绝（即使密码正确）；成功登录清零。
LOGIN_FAIL_WINDOW_SECONDS = 3600
LOGIN_FAIL_MAX_ATTEMPTS = 5
LOGIN_LOCK_SECONDS = 15 * 60
LOGIN_FAIL_MESSAGE = "邮箱/手机号或密码错误"
# key: 规范化登录标识，value: {"fails": [datetime, ...], "locked_until": datetime | None}
_login_failures: Dict[str, Dict[str, Any]] = {}
# 用户不存在时的假哈希：verify 一遍对齐真实校验耗时，堵计时侧信道枚举
_DUMMY_PASSWORD_HASH = pwd_context.hash("openlife-dummy-password-for-timing")


class LoginLockedError(ValueError):
    """登录失败次数过多被临时锁定（API 层转 423，detail 带 retry_after_seconds）"""

    def __init__(self, retry_after_seconds: int):
        super().__init__("尝试次数过多，账号已临时锁定，请稍后再试")
        self.retry_after_seconds = max(1, int(retry_after_seconds))


def _get_login_lock_remaining(key: str) -> int:
    """锁定中返回剩余秒数；未锁定返回 0（过期锁定顺带清零）"""
    rec = _login_failures.get(key)
    if not rec:
        return 0
    locked_until = rec.get("locked_until")
    if not locked_until:
        return 0
    now = datetime.now(timezone.utc)
    if now >= locked_until:
        _login_failures.pop(key, None)
        return 0
    return max(1, int((locked_until - now).total_seconds()))


def _record_login_failure(key: str) -> int:
    """记录一次失败；若因此触发锁定返回剩余锁定秒数，否则返回 0"""
    now = datetime.now(timezone.utc)
    rec = _login_failures.setdefault(key, {"fails": [], "locked_until": None})
    window_start = now - timedelta(seconds=LOGIN_FAIL_WINDOW_SECONDS)
    fails = [t for t in rec["fails"] if t > window_start]
    fails.append(now)
    rec["fails"] = fails
    if len(fails) >= LOGIN_FAIL_MAX_ATTEMPTS:
        rec["locked_until"] = now + timedelta(seconds=LOGIN_LOCK_SECONDS)
        logger.warning("登录失败次数过多，临时锁定: id=%s, fails=%d", key, len(fails))
        return LOGIN_LOCK_SECONDS
    return 0


def _clear_login_failures(key: str) -> None:
    _login_failures.pop(key, None)


def _normalize_email(email: Optional[str]) -> Optional[str]:
    val = (email or "").strip().lower()
    return val or None


def _normalize_phone(phone: Optional[str]) -> Optional[str]:
    val = (phone or "").strip()
    return val or None


def _hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256((raw_token or "").encode("utf-8")).hexdigest()


def _create_token(
    data: Dict, expires_delta: Optional[timedelta] = None, token_type: str = "access"
) -> str:
    """
    底层 JWT 编码：写入 exp 和 type，由上层业务方法调用。

    Args:
        data: Token 载荷（如 sub, email 等）
        expires_delta: 过期时间增量，None 时使用 ACCESS_TOKEN_EXPIRE_MINUTES
        token_type: token 类型标识（access / email_verify 等）

    Returns:
        JWT Token 字符串
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "type": token_type})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


class AuthService:
    """用户认证服务"""

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        验证密码

        Args:
            plain_password: 明文密码
            hashed_password: 加密后的密码

        Returns:
            是否匹配
        """
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def get_password_hash(password: str) -> str:
        """
        加密密码（内部会按 bcrypt 72 字节限制截断，避免报错）

        Args:
            password: 明文密码

        Returns:
            加密后的密码
        """
        return pwd_context.hash(password)

    @staticmethod
    async def _ensure_refresh_schema() -> None:
        global _refresh_schema_ready
        if _refresh_schema_ready:
            return
        async with engine.begin() as conn:
            await conn.run_sync(RefreshToken.__table__.create, checkfirst=True)
        _refresh_schema_ready = True

    @staticmethod
    def _create_refresh_token(
        user_id: str, family_id: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        exp = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        jti = uuid.uuid4().hex
        family = family_id or uuid.uuid4().hex
        payload = {
            "sub": user_id,
            "jti": jti,
            "family_id": family,
            "type": "refresh",
            "iat": int(now.timestamp()),
            "exp": exp,
        }
        token = jwt.encode(payload, REFRESH_TOKEN_SECRET_KEY, algorithm=ALGORITHM)
        return token, payload

    @staticmethod
    async def _persist_refresh_token(
        user_id: str,
        raw_token: str,
        payload: Dict[str, Any],
    ) -> None:
        await AuthService._ensure_refresh_schema()
        exp_dt = (
            datetime.fromtimestamp(int(payload["exp"]), tz=timezone.utc)
            if isinstance(payload.get("exp"), int)
            else (
                payload.get("exp")
                if isinstance(payload.get("exp"), datetime)
                else datetime.now(timezone.utc)
            )
        )
        async with AsyncSessionLocal() as db:
            rec = RefreshToken(
                user_id=user_id,
                token_hash=_hash_refresh_token(raw_token),
                jti=str(payload.get("jti") or ""),
                family_id=str(payload.get("family_id") or ""),
                expires_at=exp_dt,
            )
            db.add(rec)
            await db.commit()

    @staticmethod
    async def _issue_token_pair(user: Any, family_id: Optional[str] = None) -> Dict[str, Any]:
        access_token = AuthService.create_access_token(
            {"sub": user.id, "email": user.email, "phone": user.phone}
        )
        refresh_token, refresh_payload = AuthService._create_refresh_token(
            user.id, family_id=family_id
        )
        await AuthService._persist_refresh_token(user.id, refresh_token, refresh_payload)
        return {
            "token": access_token,
            "refresh_token": refresh_token,
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "refresh_expires_in": REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        }

    @staticmethod
    def _decode_refresh_token(token: str) -> Optional[Dict[str, Any]]:
        try:
            payload = jwt.decode(token, REFRESH_TOKEN_SECRET_KEY, algorithms=[ALGORITHM])
            if payload.get("type") != "refresh":
                return None
            return payload
        except JWTError:
            return None

    @staticmethod
    async def refresh_access_token(refresh_token: str) -> Dict[str, Any]:
        token = (refresh_token or "").strip()
        if not token:
            raise ValueError("缺少 refresh_token")

        payload = AuthService._decode_refresh_token(token)
        if not payload:
            raise ValueError("refresh_token 无效")

        user_id = str(payload.get("sub") or "").strip()
        jti = str(payload.get("jti") or "").strip()
        family_id = str(payload.get("family_id") or "").strip()
        if not user_id or not jti or not family_id:
            raise ValueError("refresh_token 载荷无效")

        await AuthService._ensure_refresh_schema()
        now = datetime.now(timezone.utc)
        token_hash = _hash_refresh_token(token)

        async with AsyncSessionLocal() as db:
            res = await db.execute(
                select(RefreshToken).where(RefreshToken.token_hash == token_hash)
            )
            rec = res.scalar_one_or_none()
            if not rec:
                # 可能是已轮换旧 token 的重放：按 family 做兜底撤销
                fam_res = await db.execute(
                    select(RefreshToken).where(
                        RefreshToken.user_id == user_id,
                        RefreshToken.family_id == family_id,
                    )
                )
                fam_items = list(fam_res.scalars().all())
                if fam_items:
                    for item in fam_items:
                        if not item.is_revoked:
                            item.is_revoked = True
                            item.revoked_at = now
                            item.revoked_reason = "reuse_detected"
                    await db.commit()
                raise ValueError("refresh_token 已失效，请重新登录")

            if rec.is_revoked:
                # 轮换宽限期内的并发重放（多标签页 / 流式与轮询同时 401 触发双通道 refresh）：
                # 旧 token 刚被轮换作废，视为正常并发刷新，继续走换发流程，不按攻击撤族
                revoked_at = rec.revoked_at
                if revoked_at is not None and revoked_at.tzinfo is None:
                    revoked_at = revoked_at.replace(tzinfo=timezone.utc)
                within_rotate_grace = (
                    rec.revoked_reason == "rotated"
                    and revoked_at is not None
                    and now - revoked_at <= timedelta(seconds=REFRESH_TOKEN_ROTATE_GRACE_SECONDS)
                )
                if not within_rotate_grace:
                    # 已撤销 token 再使用：撤销整族
                    fam_res = await db.execute(
                        select(RefreshToken).where(
                            RefreshToken.user_id == rec.user_id,
                            RefreshToken.family_id == rec.family_id,
                        )
                    )
                    for item in fam_res.scalars().all():
                        if not item.is_revoked:
                            item.is_revoked = True
                            item.revoked_at = now
                            item.revoked_reason = "reuse_detected"
                    await db.commit()
                    raise ValueError("refresh_token 已失效，请重新登录")

            # SQLite DateTime 读回为 naive datetime，统一按 UTC 转 aware 再比较
            expires_at = rec.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= now:
                rec.is_revoked = True
                rec.revoked_at = now
                rec.revoked_reason = "expired"
                await db.commit()
                raise ValueError("refresh_token 已过期，请重新登录")

            user_db = UserDB(db)
            user = await user_db.get_user_by_id(rec.user_id)
            if not user or not user.is_active:
                rec.is_revoked = True
                rec.revoked_at = now
                rec.revoked_reason = "user_invalid"
                await db.commit()
                raise ValueError("用户不可用，请重新登录")

            access_token = AuthService.create_access_token(
                {"sub": user.id, "email": user.email, "phone": user.phone}
            )

            rec.last_used_at = now
            if REFRESH_TOKEN_ROTATE:
                new_refresh_token, new_payload = AuthService._create_refresh_token(
                    user.id, family_id=rec.family_id
                )
                rec.is_revoked = True
                # 宽限期重放走这里时 revoked_at 已有值：保留首次轮换时间，防止反复重放给宽限期续期
                if rec.revoked_at is None:
                    rec.revoked_at = now
                rec.revoked_reason = "rotated"
                rec.replaced_by_jti = str(new_payload.get("jti") or "")
                db.add(
                    RefreshToken(
                        user_id=user.id,
                        token_hash=_hash_refresh_token(new_refresh_token),
                        jti=str(new_payload.get("jti") or ""),
                        family_id=rec.family_id,
                        expires_at=datetime.fromtimestamp(int(new_payload["exp"]), tz=timezone.utc),
                    )
                )
                await db.commit()
                await _record_auth_active(user.id)
                return {
                    "token": access_token,
                    "refresh_token": new_refresh_token,
                    "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                    "refresh_expires_in": REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
                }

            await db.commit()
            await _record_auth_active(user.id)
            return {
                "token": access_token,
                "refresh_token": token,
                "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                "refresh_expires_in": REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
            }

    @staticmethod
    async def revoke_refresh_token(refresh_token: str) -> None:
        token = (refresh_token or "").strip()
        if not token:
            return
        await AuthService._ensure_refresh_schema()
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            res = await db.execute(
                select(RefreshToken).where(RefreshToken.token_hash == _hash_refresh_token(token))
            )
            rec = res.scalar_one_or_none()
            if rec and not rec.is_revoked:
                rec.is_revoked = True
                rec.revoked_at = now
                rec.revoked_reason = "logout"
                await db.commit()

    @staticmethod
    def create_access_token(data: Dict, expires_delta: Optional[timedelta] = None) -> str:
        """
        创建访问令牌（JWT）

        Args:
            data: Token数据（通常包含user_id等）
            expires_delta: 过期时间增量

        Returns:
            JWT Token字符串
        """
        return _create_token(data, expires_delta=expires_delta, token_type="access")

    @staticmethod
    def create_email_verify_token(data: Dict, expires_delta: Optional[timedelta] = None) -> str:
        """
        创建邮箱验证令牌（JWT）

        Args:
            data: Token数据（需包含 sub 和 email）
            expires_delta: 过期时间增量，默认 24 小时

        Returns:
            JWT Token字符串
        """
        if expires_delta is None:
            expires_delta = timedelta(hours=24)
        return _create_token(data, expires_delta=expires_delta, token_type="email_verify")

    @staticmethod
    def verify_token(token: str, expected_type: str = "access") -> Optional[Dict]:
        """
        验证JWT Token

        Args:
            token: JWT Token字符串

        Returns:
            Token数据（如果有效），否则返回None
        """
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            token_type = payload.get("type")
            # 兼容历史 access token（没有 type 字段）
            if expected_type == "access":
                if token_type in (None, "access"):
                    return payload
                return None
            if token_type != expected_type:
                return None
            return payload
        except JWTError:
            return None

    # ===================== 找回密码相关 =====================

    @staticmethod
    async def request_password_reset(email: str) -> None:
        """
        申请重置密码：生成一次性验证码，并通过邮件发送（当前开发环境直接打印到日志）

        Args:
            email: 用户邮箱

        Raises:
            ValueError: 如果用户不存在或邮箱未绑定
        """
        email = _normalize_email(email)
        if not email:
            raise ValueError("邮箱不能为空")

        async with AsyncSessionLocal() as db:
            user_db = UserDB(db)
            user = await user_db.get_user_by_email(email)
            if not user:
                raise ValueError("用户不存在或未绑定该邮箱")
            if not user.is_active:
                raise ValueError("用户已被禁用")

        # 60 秒冷却期：避免连续轰炸发送
        last = _password_reset_email_codes.get(email)
        if (
            last
            and last.get("sent_at")
            and (datetime.now(timezone.utc) - last["sent_at"]).total_seconds() < 60
        ):
            raise ValueError("发送过于频繁，请 60 秒后再试")

        # 生成 6 位数字验证码（最新发送覆盖旧验证码）
        code = f"{random.randint(0, 999999):06d}"
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        # 通过 SMTP 发送邮件，发送成功后再写入本次验证码记录
        try:
            await EmailService.send_password_reset_code(
                to_email=email,
                code=code,
                valid_minutes=5,
            )
        except Exception as e:
            raise _friendly_email_send_error(e, "密码重置") from e
        _password_reset_email_codes[email] = {
            "code": code,
            "expires_at": expires_at,
            "sent_at": datetime.now(timezone.utc),
        }

    @staticmethod
    async def reset_password_with_code(email: str, code: str, new_password: str) -> None:
        """
        通过邮箱验证码重置密码

        Args:
            email: 用户邮箱
            code: 验证码
            new_password: 新密码

        Raises:
            ValueError: 如果验证码错误/过期，或用户不存在
        """
        email = _normalize_email(email)
        if not email:
            raise ValueError("邮箱不能为空")
        if not new_password:
            raise ValueError("新密码不能为空")

        record = _password_reset_email_codes.get(email)
        if not record:
            raise ValueError("请先申请验证码")

        # 检查过期
        if datetime.now(timezone.utc) > record["expires_at"]:
            del _password_reset_email_codes[email]
            raise ValueError("验证码已过期，请重新获取")

        # 检查验证码
        if record["code"] != code:
            raise ValueError("验证码错误")

        # 验证通过，更新密码
        async with AsyncSessionLocal() as db:
            user_db = UserDB(db)
            user = await user_db.get_user_by_email(email)
            if not user:
                raise ValueError("用户不存在")
            if not user.is_active:
                raise ValueError("用户已被禁用")

            password_hash = AuthService.get_password_hash(new_password)
            await user_db.update_user(user.id, password_hash=password_hash)

        # 一次性验证码，成功后删除
        _password_reset_email_codes.pop(email, None)

    @staticmethod
    async def request_password_reset_by_phone(phone: str) -> None:
        """
        申请重置密码：通过手机号生成一次性验证码（假短信，打印到日志）

        Args:
            phone: 用户手机号

        Raises:
            ValueError: 如果用户不存在或手机号未绑定
        """
        phone = _normalize_phone(phone)
        if not phone:
            raise ValueError("手机号不能为空")

        async with AsyncSessionLocal() as db:
            user_db = UserDB(db)
            user = await user_db.get_user_by_phone(phone)
            if not user:
                raise ValueError("用户不存在或未绑定该手机号")
            if not user.is_active:
                raise ValueError("用户已被禁用")

        # 60 秒冷却期
        last = _password_reset_phone_codes.get(phone)
        if (
            last
            and last.get("sent_at")
            and (datetime.now(timezone.utc) - last["sent_at"]).total_seconds() < 60
        ):
            raise ValueError("发送过于频繁，请 60 秒后再试")

        # 最新发送覆盖旧验证码
        code = f"{random.randint(0, 999999):06d}"
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        _password_reset_phone_codes[phone] = {
            "code": code,
            "expires_at": expires_at,
            "sent_at": datetime.now(timezone.utc),
        }
        # 假短信通道：仅在控制台打印，便于开发调试
        print(
            f"[DEV] SMS password reset code for {phone}: {code} (expires at {expires_at.isoformat()} UTC)"
        )

    @staticmethod
    async def reset_password_with_phone_code(phone: str, code: str, new_password: str) -> None:
        """
        通过手机短信验证码重置密码（开发环境假实现）
        """
        phone = _normalize_phone(phone)
        if not phone:
            raise ValueError("手机号不能为空")
        if not new_password:
            raise ValueError("新密码不能为空")

        record = _password_reset_phone_codes.get(phone)
        if not record:
            raise ValueError("请先申请验证码")

        if datetime.now(timezone.utc) > record["expires_at"]:
            del _password_reset_phone_codes[phone]
            raise ValueError("验证码已过期，请重新获取")

        if record["code"] != code:
            raise ValueError("验证码错误")

        async with AsyncSessionLocal() as db:
            user_db = UserDB(db)
            user = await user_db.get_user_by_phone(phone)
            if not user:
                raise ValueError("用户不存在")
            if not user.is_active:
                raise ValueError("用户已被禁用")

            password_hash = AuthService.get_password_hash(new_password)
            await user_db.update_user(user.id, password_hash=password_hash)

        _password_reset_phone_codes.pop(phone, None)

    @staticmethod
    async def admin_set_password(user_id: str, new_password: str) -> None:
        """超级管理员为指定用户设置新密码（不校验旧密码、不走验证码）。"""
        uid = (user_id or "").strip()
        if not uid:
            raise ValueError("用户 ID 不能为空")
        if not new_password:
            raise ValueError("新密码不能为空")
        if len(new_password) < 6:
            raise ValueError("密码至少 6 位")

        async with AsyncSessionLocal() as db:
            user_db = UserDB(db)
            user = await user_db.get_user_by_id(uid)
            if not user:
                raise ValueError("用户不存在")
            password_hash = AuthService.get_password_hash(new_password)
            await user_db.update_user(user.id, password_hash=password_hash)

    # ===================== 修改密码相关（已登录用户） =====================

    @staticmethod
    async def change_password(user_id: str, old_password: str, new_password: str) -> None:
        """
        已登录用户修改密码：校验旧密码 → 更新 hash → 撤销全部 refresh token（强制下线）
        → 站内信 + 邮件通知。

        防爆破：复用登录锁定机制——lock_key 与登录一致（email 小写 / phone），
        失败计数与登录共享，1 小时滑窗 5 次失败锁 15 分钟；锁定期间即使旧密码正确也拒绝。

        Args:
            user_id: 当前登录用户 ID
            old_password: 旧密码（明文）
            new_password: 新密码（明文，≥6 位，且不能与旧密码相同）

        Raises:
            ValueError: 参数校验失败 / 旧密码不正确 / 账户状态异常
            LoginLockedError: 失败次数过多被临时锁定（携带 retry_after_seconds）
        """
        if not old_password:
            raise ValueError("旧密码不能为空")
        if not new_password:
            raise ValueError("新密码不能为空")
        if len(new_password) < 6:
            raise ValueError("新密码至少 6 位")
        if new_password == old_password:
            raise ValueError("新密码不能与旧密码相同")

        uid = (user_id or "").strip()
        if not uid:
            raise ValueError("用户 ID 不能为空")

        async with AsyncSessionLocal() as db:
            user_db = UserDB(db)
            user = await user_db.get_user_by_id(uid)
            if not user or not user.is_active:
                raise ValueError("账户状态异常")
            email = _normalize_email(user.email)

            # 与登录共用 lock_key，失败计数互通（防爆破口径见模块注释）
            lock_key = email or _normalize_phone(user.phone) or uid
            locked_remaining = _get_login_lock_remaining(lock_key)
            if locked_remaining:
                raise LoginLockedError(locked_remaining)

            if not AuthService.verify_password(old_password, user.password_hash):
                remaining = _record_login_failure(lock_key)
                if remaining:
                    raise LoginLockedError(remaining)
                raise ValueError("旧密码不正确")

            _clear_login_failures(lock_key)
            await user_db.update_user(
                uid, password_hash=AuthService.get_password_hash(new_password)
            )

            # 撤销该用户全部未撤销 refresh token（含当前会话）→ 全部强制下线
            now = datetime.now(timezone.utc)
            tokens = (
                (
                    await db.execute(
                        select(RefreshToken).where(
                            RefreshToken.user_id == uid,
                            RefreshToken.is_revoked.is_(False),
                        )
                    )
                )
                .scalars()
                .all()
            )
            for rec in tokens:
                rec.is_revoked = True
                rec.revoked_at = now
                rec.revoked_reason = "password_changed"

            # 站内信通知（防盗号静默改密）
            from app.models.feedback import Notification

            db.add(
                Notification(
                    user_id=uid,
                    type="password_changed",
                    title="密码已修改",
                    content=(
                        "您的账号密码刚刚完成修改，全部登录会话已下线，需使用新密码重新登录。"
                        "如果这不是您的操作，请立即通过「忘记密码」重置密码，并联系我们处理。"
                    ),
                    read_at=None,
                    related_feedback_id=None,
                )
            )
            await db.commit()

        # 邮件通知（发送失败不影响修改结果，只记日志）
        if email:
            try:
                await EmailService.send_password_changed_notice(to_email=email)
            except Exception:
                logger.exception("密码修改通知邮件发送失败: user_id=%s", uid)

    # ===================== 邮箱验证相关 =====================

    @staticmethod
    async def request_email_verification(email: str) -> None:
        """发送邮箱验证链接（JWT token，24 小时有效，5 分钟冷却）"""
        email = _normalize_email(email)
        if not email:
            raise ValueError("邮箱不能为空")

        async with AsyncSessionLocal() as db:
            user_db = UserDB(db)
            user = await user_db.get_user_by_email(email)
            if not user:
                raise ValueError("用户不存在或未绑定该邮箱")
            if user.email_verified:
                raise ValueError("邮箱已验证，无需重复操作")

        # 5 分钟冷却
        last_sent = _email_verify_cooldowns.get(email)
        if last_sent and (datetime.now(timezone.utc) - last_sent).total_seconds() < 300:
            remaining = 300 - (datetime.now(timezone.utc) - last_sent).total_seconds()
            raise ValueError(f"发送过于频繁，请 {int(remaining // 60)} 分钟后再试")

        token = AuthService.create_email_verify_token(
            data={"sub": user.id, "email": email},
        )
        try:
            await EmailService.send_email_verification(to_email=email, token=token)
        except Exception as e:
            raise _friendly_email_send_error(e, "验证") from e
        _email_verify_cooldowns[email] = datetime.now(timezone.utc)

    @staticmethod
    async def verify_email_token(token: str) -> Dict:
        """验证邮箱验证 token，将 email_verified 设为 True"""
        payload = AuthService.verify_token(token, expected_type="email_verify")
        if not payload:
            raise ValueError("验证链接无效或已过期")

        user_id = str(payload.get("sub") or "").strip()
        if not user_id:
            raise ValueError("验证链接无效")

        async with AsyncSessionLocal() as db:
            user_db = UserDB(db)
            user = await user_db.get_user_by_id(user_id)
            if not user:
                raise ValueError("用户不存在")
            if user.email_verified:
                return {"user_id": user.id, "email": user.email, "already_verified": True}
            await user_db.update_user(user_id, email_verified=True)

        return {"user_id": user_id, "email": payload.get("email"), "already_verified": False}

    @staticmethod
    async def register(
        email: Optional[str] = None,
        phone: Optional[str] = None,
        username: Optional[str] = None,
        password: str = "",
    ) -> Dict:
        """
        用户注册

        Args:
            email: 邮箱（可选）
            phone: 手机号（可选）
            username: 用户名（可选）
            password: 密码

        Returns:
            注册结果（包含user_id和token）

        Raises:
            ValueError: 如果邮箱或手机号已存在
        """
        email = _normalize_email(email)
        phone = _normalize_phone(phone)
        username = (username or "").strip() or None

        if not email and not phone:
            raise ValueError("邮箱或手机号至少提供一个")

        if not password:
            raise ValueError("密码不能为空")

        async with AsyncSessionLocal() as db:
            user_db = UserDB(db)

            # 检查邮箱是否已存在
            if email:
                existing_user = await user_db.get_user_by_email(email)
                if existing_user:
                    raise ValueError("邮箱已被注册")

            # 检查手机号是否已存在
            if phone:
                existing_user = await user_db.get_user_by_phone(phone)
                if existing_user:
                    raise ValueError("手机号已被注册")

            # 创建用户
            password_hash = AuthService.get_password_hash(password)
            user = await user_db.create_user(
                email=email, phone=phone, username=username, password_hash=password_hash
            )
            # 新注册用户邮箱未验证
            if email:
                await user_db.update_user(user.id, email_verified=False)

            token_pair = await AuthService._issue_token_pair(user)
            await _record_auth_active(user.id)
            return {
                "user_id": user.id,
                "email": user.email,
                "phone": user.phone,
                "username": user.username,
                **token_pair,
            }

    @staticmethod
    async def login(
        email: Optional[str] = None, phone: Optional[str] = None, password: str = ""
    ) -> Dict:
        """
        用户登录

        Args:
            email: 邮箱（可选）
            phone: 手机号（可选）
            password: 密码

        Returns:
            登录结果（包含user_id和token）

        Raises:
            ValueError: 登录标识或密码错误（统一文案，不区分用户不存在）
            LoginLockedError: 失败次数过多被临时锁定（携带 retry_after_seconds）
        """
        email = _normalize_email(email)
        phone = _normalize_phone(phone)

        if not email and not phone:
            raise ValueError("邮箱或手机号至少提供一个")

        if not password:
            raise ValueError("密码不能为空")

        # 防爆破：锁定期间一律拒绝（即使密码正确），不重置倒计时
        lock_key = email or phone or ""
        locked_remaining = _get_login_lock_remaining(lock_key)
        if locked_remaining:
            raise LoginLockedError(locked_remaining)

        async with AsyncSessionLocal() as db:
            user_db = UserDB(db)

            # 查找用户
            if email:
                user = await user_db.get_user_by_email(email)
            else:
                user = await user_db.get_user_by_phone(phone)

            if not user:
                # 假哈希校验对齐耗时；失败计数含不存在的账号，统一文案防枚举
                AuthService.verify_password(password, _DUMMY_PASSWORD_HASH)
                remaining = _record_login_failure(lock_key)
                if remaining:
                    raise LoginLockedError(remaining)
                raise ValueError(LOGIN_FAIL_MESSAGE)

            if not user.is_active:
                # 已注销账户：验证密码后签发受限 token（仅供恢复流程，不签发 refresh token）
                if getattr(user, "deleted_at", None):
                    if not AuthService.verify_password(password, user.password_hash):
                        remaining = _record_login_failure(lock_key)
                        if remaining:
                            raise LoginLockedError(remaining)
                        raise ValueError(LOGIN_FAIL_MESSAGE)
                    _clear_login_failures(lock_key)
                    restricted_token = _create_token(
                        {"sub": user.id, "email": user.email, "phone": user.phone},
                        expires_delta=timedelta(minutes=30),
                        token_type="deleted_recovery",
                    )
                    return {
                        "user_id": user.id,
                        "email": user.email,
                        "phone": user.phone,
                        "username": user.username,
                        "token": restricted_token,
                        "expires_in": 30 * 60,
                        "account_status": "deleted",
                    }
                # admin 禁用场景保持原报错
                raise ValueError("用户已被禁用")

            # 验证密码
            if not AuthService.verify_password(password, user.password_hash):
                remaining = _record_login_failure(lock_key)
                if remaining:
                    raise LoginLockedError(remaining)
                raise ValueError(LOGIN_FAIL_MESSAGE)

            # 登录成功：清零失败计数
            _clear_login_failures(lock_key)

            # 更新最后登录时间
            await user_db.update_user(user.id, last_login_at=datetime.now(timezone.utc))

            token_pair = await AuthService._issue_token_pair(user)
            return {
                "user_id": user.id,
                "email": user.email,
                "phone": user.phone,
                "username": user.username,
                **token_pair,
            }

    @staticmethod
    async def get_current_user(token: str) -> Optional[Dict]:
        """
        从Token获取当前用户信息

        Args:
            token: JWT Token

        Returns:
            用户信息字典，如果Token无效则返回None
        """
        payload = AuthService.verify_token(token)
        if not payload:
            return None

        user_id = payload.get("sub")
        if not user_id:
            return None

        async with AsyncSessionLocal() as db:
            user_db = UserDB(db)
            user = await user_db.get_user_by_id(user_id)

            if not user or not user.is_active:
                return None

            return {
                "user_id": user.id,
                "email": user.email,
                "phone": user.phone,
                "username": user.username,
                "email_verified": getattr(user, "email_verified", True),
            }

    @staticmethod
    async def get_deleted_current_user(token: str) -> Optional[Dict]:
        """
        从注销恢复受限 Token 获取当前用户信息（仅恢复端点使用）

        要求 payload type == "deleted_recovery"、用户存在且 deleted_at 非空。

        Args:
            token: 注销恢复受限 JWT Token

        Returns:
            用户信息字典，如果 Token 无效或账户非注销状态则返回 None
        """
        payload = AuthService.verify_token(token, expected_type="deleted_recovery")
        if not payload:
            return None

        user_id = payload.get("sub")
        if not user_id:
            return None

        async with AsyncSessionLocal() as db:
            user_db = UserDB(db)
            user = await user_db.get_user_by_id(user_id)

            if not user or not getattr(user, "deleted_at", None):
                return None

            return {
                "user_id": user.id,
                "email": user.email,
                "phone": user.phone,
                "username": user.username,
            }

    # ===================== 账号恢复相关（已注销账户） =====================

    @staticmethod
    async def request_account_recovery_code(user_id: str) -> None:
        """
        发送账号恢复验证码到该用户邮箱（6 位数字，5 分钟有效，60 秒发送冷却）

        Args:
            user_id: 已注销用户 ID

        Raises:
            ValueError: 账户状态异常 / 未绑定邮箱 / 发送过于频繁
        """
        async with AsyncSessionLocal() as db:
            user_db = UserDB(db)
            user = await user_db.get_user_by_id(user_id)
            if not user or not getattr(user, "deleted_at", None):
                raise ValueError("账户状态异常")
            email = _normalize_email(user.email)
            if not email:
                raise ValueError("该账户未绑定邮箱，无法通过邮箱恢复")

        # 60 秒冷却期：避免连续轰炸发送
        last = _account_recovery_codes.get(email)
        if (
            last
            and last.get("sent_at")
            and (datetime.now(timezone.utc) - last["sent_at"]).total_seconds() < 60
        ):
            raise ValueError("发送过于频繁，请 60 秒后再试")

        # 生成 6 位数字验证码（最新发送覆盖旧验证码），发送成功后才写入
        code = f"{random.randint(0, 999999):06d}"
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        try:
            await EmailService.send_account_recovery_code(
                to_email=email,
                code=code,
                valid_minutes=5,
            )
        except Exception as e:
            raise _friendly_email_send_error(e, "恢复") from e
        _account_recovery_codes[email] = {
            "code": code,
            "expires_at": expires_at,
            "sent_at": datetime.now(timezone.utc),
        }

    @staticmethod
    async def confirm_account_recovery(user_id: str, code: str) -> Dict:
        """
        校验恢复验证码并恢复账户：清 deleted_at/deletion_purge_after、is_active=True，
        写审计 recovered，签发正式 access + refresh token 对。

        Args:
            user_id: 已注销用户 ID
            code: 6 位数字验证码

        Returns:
            恢复结果（含正式 token 对）

        Raises:
            ValueError: 验证码错误/过期，或账户状态异常
        """
        async with AsyncSessionLocal() as db:
            user_db = UserDB(db)
            user = await user_db.get_user_by_id(user_id)
            if not user or not getattr(user, "deleted_at", None):
                raise ValueError("账户状态异常")
            # 显式恢复期判断：超过 deletion_purge_after 即拒绝自助恢复
            # （admin 恢复不受此限，只要 users 行未被物理清除即可兜底）
            purge_after = getattr(user, "deletion_purge_after", None)
            if purge_after:
                if purge_after.tzinfo is None:
                    purge_after = purge_after.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) > purge_after:
                    raise ValueError("已超过账户恢复期，无法自助恢复，请联系管理员协助处理")
            email = _normalize_email(user.email)

        record = _account_recovery_codes.get(email)
        if not record:
            raise ValueError("请先获取恢复验证码")

        # 检查过期
        if datetime.now(timezone.utc) > record["expires_at"]:
            _account_recovery_codes.pop(email, None)
            raise ValueError("验证码已过期，请重新获取")

        # 检查验证码
        if record["code"] != (code or "").strip():
            raise ValueError("验证码错误")

        # 一次性验证码，验证通过即消费
        _account_recovery_codes.pop(email, None)

        async with AsyncSessionLocal() as db:
            user_db = UserDB(db)
            await user_db.update_user(
                user_id,
                deleted_at=None,
                deletion_purge_after=None,
                is_active=True,
            )
            user = await user_db.get_user_by_id(user_id)
            token_pair = await AuthService._issue_token_pair(user)

        from app.services.account_deletion_service import (
            EVENT_RECOVERED,
            append_account_deletion_audit,
        )

        append_account_deletion_audit(EVENT_RECOVERED, user_id, email)

        return {
            "user_id": user.id,
            "email": user.email,
            "phone": user.phone,
            "username": user.username,
            **token_pair,
        }
