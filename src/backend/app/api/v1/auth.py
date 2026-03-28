"""
认证API
"""
from fastapi import APIRouter, HTTPException, Depends, status, Header, Response, Cookie
from pydantic import BaseModel, EmailStr
from typing import Optional
from app.services.auth_service import AuthService
from app.config.settings import settings
from app.utils.super_admin import is_super_admin_user

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


class PasswordResetRequest(BaseModel):
    """找回密码验证码请求"""
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    """通过验证码重置密码请求"""
    email: EmailStr
    code: str
    new_password: str


class PasswordResetSMSRequest(BaseModel):
    """通过手机号获取验证码请求（假短信）"""
    phone: str


class PasswordResetSMSConfirmRequest(BaseModel):
    """通过手机验证码重置密码请求（假短信）"""
    phone: str
    code: str
    new_password: str


class RefreshTokenRequest(BaseModel):
    refresh_token: Optional[str] = None


class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = None


class AuthResponse(BaseModel):
    """认证响应"""
    code: int = 200
    message: str = "success"
    data: dict


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=getattr(settings, "REFRESH_COOKIE_NAME", "bd_refresh_token"),
        value=refresh_token,
        max_age=int(getattr(settings, "REFRESH_TOKEN_EXPIRE_DAYS", 30) * 24 * 60 * 60),
        httponly=True,
        secure=bool(getattr(settings, "REFRESH_COOKIE_SECURE", True)),
        samesite=str(getattr(settings, "REFRESH_COOKIE_SAMESITE", "lax")).lower(),
        domain=getattr(settings, "REFRESH_COOKIE_DOMAIN", None),
        path=getattr(settings, "REFRESH_COOKIE_PATH", "/api/v1/auth"),
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=getattr(settings, "REFRESH_COOKIE_NAME", "bd_refresh_token"),
        domain=getattr(settings, "REFRESH_COOKIE_DOMAIN", None),
        path=getattr(settings, "REFRESH_COOKIE_PATH", "/api/v1/auth"),
    )


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


async def get_current_user_optional(token: Optional[str] = Depends(get_token_from_header)) -> Optional[dict]:
    """可选获取当前用户，无 token 或无效时返回 None，不抛异常"""
    if not token:
        return None
    user = await AuthService.get_current_user(token)
    return user


def _is_super_admin(user: Optional[dict]) -> bool:
    """是否超级管理员（仅超级管理员可看 debug 日志等）"""
    return is_super_admin_user(user)


def _is_debug_admin(user: Optional[dict]) -> bool:
    """是否 Debug 模式下的调试管理员（需 DEBUG_MODE=true 且在 SUPER_ADMIN 名单中）"""
    if not user or not getattr(settings, "DEBUG_MODE", False):
        return False
    return _is_super_admin(user)


@router.post("/register", response_model=AuthResponse)
async def register(request: RegisterRequest, response: Response):
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
        
        refresh_token = (result or {}).pop("refresh_token", None)
        if refresh_token:
            _set_refresh_cookie(response, refresh_token)
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
async def login(request: LoginRequest, response: Response):
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
        
        refresh_token = (result or {}).pop("refresh_token", None)
        if refresh_token:
            _set_refresh_cookie(response, refresh_token)
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


@router.post("/password/reset/code", response_model=AuthResponse)
async def request_password_reset(request: PasswordResetRequest):
    """
    申请重置密码验证码（通过邮箱）
    
    邮箱找回密码验证码申请。
    """
    try:
        await AuthService.request_password_reset(email=request.email)
        return AuthResponse(
            code=200,
            message="验证码已发送到该账号的注册邮箱（5分钟有效，60秒内不可重复发送）",
            data={}
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/password/reset/confirm", response_model=AuthResponse)
async def confirm_password_reset(request: PasswordResetConfirmRequest):
    """
    使用邮箱验证码重置密码
    """
    try:
        await AuthService.reset_password_with_code(
            email=request.email,
            code=request.code,
            new_password=request.new_password
        )
        return AuthResponse(
            code=200,
            message="密码重置成功",
            data={}
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/password/reset/code/phone", response_model=AuthResponse)
async def request_password_reset_sms(request: PasswordResetSMSRequest):
    """
    申请重置密码验证码（通过手机号）
    """
    try:
        await AuthService.request_password_reset_by_phone(phone=request.phone)
        return AuthResponse(
            code=200,
            message="验证码已发送（5分钟有效，60秒内不可重复发送）",
            data={}
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/password/reset/confirm/phone", response_model=AuthResponse)
async def confirm_password_reset_sms(request: PasswordResetSMSConfirmRequest):
    """
    使用手机短信验证码重置密码（开发环境假实现）
    """
    try:
        await AuthService.reset_password_with_phone_code(
            phone=request.phone,
            code=request.code,
            new_password=request.new_password
        )
        return AuthResponse(
            code=200,
            message="密码重置成功",
            data={}
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
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
    data = {**current_user, "is_super_admin": _is_super_admin(current_user)}
    return AuthResponse(code=200, message="success", data=data)


@router.post("/refresh", response_model=AuthResponse)
async def refresh_token(
    response: Response,
    request: Optional[RefreshTokenRequest] = None,
    refresh_cookie: Optional[str] = Cookie(
        default=None,
        alias=getattr(settings, "REFRESH_COOKIE_NAME", "bd_refresh_token"),
    ),
):
    """使用 refresh token 换取新的 access token（并按配置轮换 refresh token）。"""
    try:
        input_refresh_token = (
            (request.refresh_token if request else None)
            or refresh_cookie
            or ""
        )
        data = await AuthService.refresh_access_token(input_refresh_token)
        rotated_refresh_token = (data or {}).pop("refresh_token", None)
        if rotated_refresh_token:
            _set_refresh_cookie(response, rotated_refresh_token)
        return AuthResponse(code=200, message="success", data=data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )


@router.post("/logout", response_model=AuthResponse)
async def logout(
    response: Response,
    request: Optional[LogoutRequest] = None,
    refresh_cookie: Optional[str] = Cookie(
        default=None,
        alias=getattr(settings, "REFRESH_COOKIE_NAME", "bd_refresh_token"),
    ),
):
    """
    退出登录：
    - 若传入 refresh_token，则后端撤销该 refresh token
    - 前端仍需清理本地 access/refresh token
    """
    try:
        input_refresh_token = (
            ((request.refresh_token if request else None) or refresh_cookie or "").strip()
        )
        await AuthService.revoke_refresh_token(input_refresh_token)
        _clear_refresh_cookie(response)
        return AuthResponse(code=200, message="success", data={"logged_out": True})
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
