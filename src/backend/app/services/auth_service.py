"""
用户认证服务
"""
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
import random
import hashlib
import uuid
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from app.core.database import UserDB
from app.models.database import AsyncSessionLocal, engine
from app.config.settings import settings
from app.services.email_service import EmailService
from app.models.refresh_token import RefreshToken

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
REFRESH_TOKEN_SECRET_KEY = settings.REFRESH_TOKEN_SECRET_KEY or SECRET_KEY

# 简单的内存级找回密码验证码存储（开发环境用，进程重启后会失效）
# key: email/phone, value: {"code": str, "expires_at": datetime, "sent_at": datetime}
_password_reset_email_codes: Dict[str, Dict[str, any]] = {}
_password_reset_phone_codes: Dict[str, Dict[str, any]] = {}
_refresh_schema_ready: bool = False


def _normalize_email(email: Optional[str]) -> Optional[str]:
    val = (email or "").strip().lower()
    return val or None


def _normalize_phone(phone: Optional[str]) -> Optional[str]:
    val = (phone or "").strip()
    return val or None


def _hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256((raw_token or "").encode("utf-8")).hexdigest()


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
    def _create_refresh_token(user_id: str, family_id: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
        now = datetime.utcnow()
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
        exp_dt = datetime.utcfromtimestamp(int(payload["exp"])) if isinstance(payload.get("exp"), int) else (
            payload.get("exp") if isinstance(payload.get("exp"), datetime) else datetime.utcnow()
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
        refresh_token, refresh_payload = AuthService._create_refresh_token(user.id, family_id=family_id)
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
        now = datetime.utcnow()
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

            if rec.expires_at <= now:
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
                rec.revoked_at = now
                rec.revoked_reason = "rotated"
                rec.replaced_by_jti = str(new_payload.get("jti") or "")
                db.add(
                    RefreshToken(
                        user_id=user.id,
                        token_hash=_hash_refresh_token(new_refresh_token),
                        jti=str(new_payload.get("jti") or ""),
                        family_id=rec.family_id,
                        expires_at=datetime.utcfromtimestamp(int(new_payload["exp"])),
                    )
                )
                await db.commit()
                return {
                    "token": access_token,
                    "refresh_token": new_refresh_token,
                    "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                    "refresh_expires_in": REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
                }

            await db.commit()
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
        now = datetime.utcnow()
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
        创建JWT Token
        
        Args:
            data: Token数据（通常包含user_id等）
            expires_delta: 过期时间增量
        
        Returns:
            JWT Token字符串
        """
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode.update({"exp": expire, "type": "access"})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    
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
        if last and last.get("sent_at") and (datetime.utcnow() - last["sent_at"]).total_seconds() < 60:
            raise ValueError("发送过于频繁，请 60 秒后再试")

        # 生成 6 位数字验证码（最新发送覆盖旧验证码）
        code = f"{random.randint(0, 999999):06d}"
        expires_at = datetime.utcnow() + timedelta(minutes=5)
        # 通过 SMTP 发送邮件，发送成功后再写入本次验证码记录
        await EmailService.send_password_reset_code(
            to_email=email,
            code=code,
            valid_minutes=5,
        )
        _password_reset_email_codes[email] = {
            "code": code,
            "expires_at": expires_at,
            "sent_at": datetime.utcnow(),
        }

    @staticmethod
    async def reset_password_with_code(
        email: str,
        code: str,
        new_password: str
    ) -> None:
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
        if datetime.utcnow() > record["expires_at"]:
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
        if last and last.get("sent_at") and (datetime.utcnow() - last["sent_at"]).total_seconds() < 60:
            raise ValueError("发送过于频繁，请 60 秒后再试")

        # 最新发送覆盖旧验证码
        code = f"{random.randint(0, 999999):06d}"
        expires_at = datetime.utcnow() + timedelta(minutes=5)
        _password_reset_phone_codes[phone] = {
            "code": code,
            "expires_at": expires_at,
            "sent_at": datetime.utcnow(),
        }
        # 假短信通道：仅在控制台打印，便于开发调试
        print(f"[DEV] SMS password reset code for {phone}: {code} (expires at {expires_at.isoformat()} UTC)")

    @staticmethod
    async def reset_password_with_phone_code(
        phone: str,
        code: str,
        new_password: str
    ) -> None:
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
        
        if datetime.utcnow() > record["expires_at"]:
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
    async def register(
        email: Optional[str] = None,
        phone: Optional[str] = None,
        username: Optional[str] = None,
        password: str = ""
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
                email=email,
                phone=phone,
                username=username,
                password_hash=password_hash
            )
            
            token_pair = await AuthService._issue_token_pair(user)
            return {
                "user_id": user.id,
                "email": user.email,
                "phone": user.phone,
                "username": user.username,
                **token_pair,
            }
    
    @staticmethod
    async def login(
        email: Optional[str] = None,
        phone: Optional[str] = None,
        password: str = ""
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
            ValueError: 如果用户不存在或密码错误
        """
        email = _normalize_email(email)
        phone = _normalize_phone(phone)

        if not email and not phone:
            raise ValueError("邮箱或手机号至少提供一个")
        
        if not password:
            raise ValueError("密码不能为空")
        
        async with AsyncSessionLocal() as db:
            user_db = UserDB(db)
            
            # 查找用户
            if email:
                user = await user_db.get_user_by_email(email)
            else:
                user = await user_db.get_user_by_phone(phone)
            
            if not user:
                raise ValueError("用户不存在")
            
            if not user.is_active:
                raise ValueError("用户已被禁用")
            
            # 验证密码
            if not AuthService.verify_password(password, user.password_hash):
                raise ValueError("密码错误")
            
            # 更新最后登录时间
            await user_db.update_user(user.id, last_login_at=datetime.utcnow())
            
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
                "username": user.username
            }
