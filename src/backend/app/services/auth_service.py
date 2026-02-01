"""
用户认证服务
"""
from typing import Optional, Dict
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.core.database import UserDB
from app.models.database import AsyncSessionLocal
from app.config.settings import settings

# 密码加密上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT配置
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30 * 24 * 60  # 30天


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
        加密密码
        
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
