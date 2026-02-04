"""
认证API
"""
from fastapi import APIRouter, HTTPException, Depends, status, Header
from pydantic import BaseModel, EmailStr
from typing import Optional
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["认证"])


class RegisterRequest(BaseModel):
    """注册请求"""
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    username: Optional[str] = None
    password: str


class LoginRequest(BaseModel):
    """登录请求"""
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    password: str


class AuthResponse(BaseModel):
    """认证响应"""
    code: int = 200
    message: str = "success"
    data: dict


def get_token_from_header(authorization: Optional[str] = Header(None)) -> Optional[str]:
    """
    从请求头获取Token
    
    Args:
        authorization: Authorization头（格式：Bearer {token}）
    
    Returns:
        Token字符串，如果无效则返回None
    """
    if not authorization:
        return None
    
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            return None
        return token
    except:
        return None


async def get_current_user(token: Optional[str] = Depends(get_token_from_header)) -> dict:
    """
    获取当前用户（依赖注入）
    
    Args:
        token: JWT Token
    
    Returns:
        用户信息字典
    
    Raises:
        HTTPException: 如果Token无效或用户不存在
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证Token"
        )
    
    user = await AuthService.get_current_user(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token无效或用户不存在"
        )
    
    return user


@router.post("/register", response_model=AuthResponse)
async def register(request: RegisterRequest):
    """
    用户注册
    
    Args:
        request: 注册请求
    
    Returns:
        注册结果
    """
    try:
        result = await AuthService.register(
            email=request.email,
            phone=request.phone,
            username=request.username,
            password=request.password
        )
        
        return AuthResponse(
            code=200,
            message="注册成功",
            data=result
        )
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    """
    用户登录
    
    Args:
        request: 登录请求
    
    Returns:
        登录结果
    """
    try:
        result = await AuthService.login(
            email=request.email,
            phone=request.phone,
            password=request.password
        )
        
        return AuthResponse(
            code=200,
            message="登录成功",
            data=result
        )
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )


@router.get("/me", response_model=AuthResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    """
    获取当前用户信息
    
    Args:
        current_user: 当前用户（从Token获取）
    
    Returns:
        用户信息
    """
    return AuthResponse(
        code=200,
        message="success",
        data=current_user
    )
