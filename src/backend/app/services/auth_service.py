"""
用户认证服务
"""
from typing import Optional, Dict
from datetime import datetime, timedelta
import random
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.core.database import UserDB
from app.models.database import AsyncSessionLocal
from app.config.settings import settings

# 密码加密上下文
# 说明：
# - 当前环境里的 bcrypt 库与 passlib 有兼容性问题（找不到 __about__），并触发 72 字节限制错误
# - 为了简单稳定，本地开发环境改用 pbkdf2_sha256（业界常用方案之一，无额外依赖）
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# JWT 配置（有效期从 .env 的 ACCESS_TOKEN_EXPIRE_MINUTES 读取，默认 60 分钟 = 1 小时内免登录）
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

# 简单的内存级找回密码验证码存储（开发环境用，进程重启后会失效）
# key: email/phone, value: {"code": str, "expires_at": datetime}
_password_reset_email_codes: Dict[str, Dict[str, any]] = {}
_password_reset_phone_codes: Dict[str, Dict[str, any]] = {}


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
        
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    
    @staticmethod
    def verify_token(token: str) -> Optional[Dict]:
        """
        验证JWT Token
        
        Args:
            token: JWT Token字符串
        
        Returns:
            Token数据（如果有效），否则返回None
        """
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
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
        async with AsyncSessionLocal() as db:
            user_db = UserDB(db)
            user = await user_db.get_user_by_email(email)
            if not user:
                raise ValueError("用户不存在或未绑定该邮箱")
            if not user.is_active:
                raise ValueError("用户已被禁用")
        
        # 生成 6 位数字验证码
        code = f"{random.randint(0, 999999):06d}"
        expires_at = datetime.utcnow() + timedelta(minutes=10)
        _password_reset_email_codes[email] = {
            "code": code,
            "expires_at": expires_at,
        }
        
        # 开发环境下，直接打印到控制台 / 日志，方便手动查看
        print(f"[DEV] Password reset code for {email}: {code} (expires at {expires_at.isoformat()} UTC)")

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
        async with AsyncSessionLocal() as db:
            user_db = UserDB(db)
            user = await user_db.get_user_by_phone(phone)
            if not user:
                raise ValueError("用户不存在或未绑定该手机号")
            if not user.is_active:
                raise ValueError("用户已被禁用")
        
        code = f"{random.randint(0, 999999):06d}"
        expires_at = datetime.utcnow() + timedelta(minutes=10)
        _password_reset_phone_codes[phone] = {
            "code": code,
            "expires_at": expires_at,
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
            
            # 生成Token
            token_data = {"sub": user.id, "email": email, "phone": phone}
            token = AuthService.create_access_token(token_data)
            
            return {
                "user_id": user.id,
                "email": user.email,
                "phone": user.phone,
                "username": user.username,
                "token": token,
                "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60  # 秒
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
            
            # 生成Token
            token_data = {"sub": user.id, "email": user.email, "phone": user.phone}
            token = AuthService.create_access_token(token_data)
            
            return {
                "user_id": user.id,
                "email": user.email,
                "phone": user.phone,
                "username": user.username,
                "token": token,
                "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60  # 秒
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
