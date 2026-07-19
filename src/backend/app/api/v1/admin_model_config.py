"""
Admin: LLM 模型配置管理。

功能：
- 多个模型条目的 CRUD（provider/model/base_url/api_key，api_key Fernet 加密入库）
- 设置默认模型
- 联通测试：发送 prompt → 返回响应 + 延迟
- 用户 → 模型 绑定（未绑定走默认）

所有端点仅超级管理员可访问。所有写操作后调用 resolver.invalidate_cache()。
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.config.settings import settings
from app.core.llmapi import LLMMessage, OpenAIProvider
from app.core.llmapi.resolver import invalidate_cache
from app.models.database import AsyncSessionLocal
from app.models.llm_model_config import LlmModelConfig, UserLlmModelConfig
from app.models.user import User
from app.utils import llm_config_crypto
from app.utils.super_admin import is_super_admin_user

router = APIRouter(prefix="/admin", tags=["Admin-ModelConfig"])


def _ok(data):
    return {"code": 200, "message": "success", "data": data}


def _require_super_admin(current_user) -> None:
    if not is_super_admin_user(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")


# ===================== Schemas =====================

PROVIDER_PATTERN = r"^(openai|deepseek|kimi|qwen)$"


class ModelConfigCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    provider: str = Field(..., pattern=PROVIDER_PATTERN)
    model: str = Field(..., min_length=1, max_length=128)
    base_url: Optional[str] = Field(None, max_length=255)
    api_key: Optional[str] = Field(None, max_length=512)  # 明文入参，加密入库
    is_default: bool = False
    enabled: bool = True
    notes: Optional[str] = None


class ModelConfigUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    provider: Optional[str] = Field(None, pattern=PROVIDER_PATTERN)
    model: Optional[str] = Field(None, min_length=1, max_length=128)
    base_url: Optional[str] = Field(None, max_length=255)
    api_key: Optional[str] = Field(None, max_length=512)  # None=不变；""=清空
    is_default: Optional[bool] = None
    enabled: Optional[bool] = None
    notes: Optional[str] = None


class ModelConfigOut(BaseModel):
    id: str
    name: str
    provider: str
    model: str
    base_url: Optional[str]
    api_key_masked: str
    has_api_key: bool
    is_default: bool
    enabled: bool
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


class ModelConfigOutRevealed(ModelConfigOut):
    api_key_revealed: Optional[str] = None


class ModelConfigTestRequest(BaseModel):
    prompt: str = Field("ping", max_length=2000)
    temperature: float = Field(0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(64, ge=1, le=2048)


class ModelConfigTestResult(BaseModel):
    success: bool
    content: str
    model: str
    latency_ms: int
    error: Optional[str] = None


class UserBindingCreate(BaseModel):
    user_id: str = Field(..., min_length=1)
    config_id: str = Field(..., min_length=1)


class UserBindingOut(BaseModel):
    id: str
    user_id: str
    config_id: str
    config_name: str
    config_provider: str
    config_model: str
    user_email: Optional[str] = None
    user_username: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ===================== Helpers =====================

def _to_out(row: LlmModelConfig, reveal: bool = False) -> dict:
    api_key_plain = llm_config_crypto.decrypt(row.api_key_enc) if reveal else None
    base = {
        "id": row.id,
        "name": row.name,
        "provider": row.provider,
        "model": row.model,
        "base_url": row.base_url,
        "api_key_masked": llm_config_crypto.mask(
            llm_config_crypto.decrypt(row.api_key_enc)
        ),
        "has_api_key": bool(llm_config_crypto.decrypt(row.api_key_enc)),
        "is_default": bool(row.is_default),
        "enabled": bool(row.enabled),
        "notes": row.notes,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
    if reveal:
        base["api_key_revealed"] = api_key_plain
    return base


async def _clear_other_defaults(db: AsyncSession, except_id: Optional[str] = None) -> None:
    stmt = update(LlmModelConfig).where(LlmModelConfig.is_default.is_(True))
    if except_id:
        stmt = stmt.where(LlmModelConfig.id != except_id)
    stmt = stmt.values(is_default=False)
    await db.execute(stmt)


# ===================== Model Config CRUD =====================

@router.get("/model-configs")
async def list_model_configs(
    current_user: Optional[dict] = Depends(get_current_user),
):
    _require_super_admin(current_user)
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(LlmModelConfig).order_by(
                    LlmModelConfig.is_default.desc(),
                    LlmModelConfig.created_at.asc(),
                )
            )
        ).scalars().all()
        return _ok([_to_out(r) for r in rows])


@router.post("/model-configs")
async def create_model_config(
    req: ModelConfigCreate,
    current_user: Optional[dict] = Depends(get_current_user),
):
    _require_super_admin(current_user)
    async with AsyncSessionLocal() as db:
        if req.is_default:
            await _clear_other_defaults(db)
        row = LlmModelConfig(
            name=req.name,
            provider=req.provider,
            model=req.model,
            base_url=req.base_url,
            api_key_enc=llm_config_crypto.encrypt(req.api_key) if req.api_key else None,
            is_default=req.is_default,
            enabled=req.enabled,
            notes=req.notes,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        out = _to_out(row)
    invalidate_cache()
    return _ok(out)


@router.get("/model-configs/{config_id}")
async def get_model_config(
    config_id: str,
    reveal: bool = Query(False),
    current_user: Optional[dict] = Depends(get_current_user),
):
    _require_super_admin(current_user)
    async with AsyncSessionLocal() as db:
        row = await db.get(LlmModelConfig, config_id)
        if not row:
            raise HTTPException(status_code=404, detail="配置不存在")
        return _ok(_to_out(row, reveal=reveal))


@router.patch("/model-configs/{config_id}")
async def update_model_config(
    config_id: str,
    req: ModelConfigUpdate,
    current_user: Optional[dict] = Depends(get_current_user),
):
    _require_super_admin(current_user)
    async with AsyncSessionLocal() as db:
        row = await db.get(LlmModelConfig, config_id)
        if not row:
            raise HTTPException(status_code=404, detail="配置不存在")

        data = req.model_dump(exclude_unset=True)
        # api_key 特殊处理：None=不动；""=清空；其他=加密入库
        if "api_key" in data:
            ak = data.pop("api_key")
            if ak is None or ak == "":
                # 明确传空串 → 清空；None（未传）不会进入 exclude_unset
                if ak == "":
                    row.api_key_enc = None
            else:
                row.api_key_enc = llm_config_crypto.encrypt(ak)

        if "is_default" in data and data["is_default"] is True:
            await _clear_other_defaults(db, except_id=config_id)

        for k, v in data.items():
            setattr(row, k, v)
        await db.commit()
        await db.refresh(row)
        out = _to_out(row)
    invalidate_cache()
    return _ok(out)


@router.delete("/model-configs/{config_id}")
async def delete_model_config(
    config_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    _require_super_admin(current_user)
    async with AsyncSessionLocal() as db:
        row = await db.get(LlmModelConfig, config_id)
        if not row:
            raise HTTPException(status_code=404, detail="配置不存在")
        # 统计启用的配置数量
        enabled_count = len(
            (
                await db.execute(
                    select(LlmModelConfig.id).where(LlmModelConfig.enabled.is_(True))
                )
            ).scalars().all()
        )
        if row.is_default and row.enabled and enabled_count <= 1:
            raise HTTPException(
                status_code=400, detail="不能删除唯一启用的默认配置；请先切换默认或新增配置"
            )
        was_default = bool(row.is_default)
        await db.delete(row)
        await db.commit()
        # 删除的若是默认，挑一个 enabled 的顶上
        if was_default:
            new_default = (
                await db.execute(
                    select(LlmModelConfig)
                    .where(LlmModelConfig.enabled.is_(True))
                    .order_by(LlmModelConfig.created_at.asc())
                    .limit(1)
                )
            ).scalars().first()
            if new_default:
                new_default.is_default = True
                await db.commit()
    invalidate_cache()
    return _ok({"deleted": config_id})


@router.post("/model-configs/{config_id}/set-default")
async def set_default_model_config(
    config_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    _require_super_admin(current_user)
    async with AsyncSessionLocal() as db:
        row = await db.get(LlmModelConfig, config_id)
        if not row:
            raise HTTPException(status_code=404, detail="配置不存在")
        if not row.enabled:
            raise HTTPException(status_code=400, detail="不能将禁用的配置设为默认")
        await _clear_other_defaults(db, except_id=config_id)
        row.is_default = True
        await db.commit()
        await db.refresh(row)
        out = _to_out(row)
    invalidate_cache()
    return _ok(out)


# ===================== 连通测试 =====================

@router.post("/model-configs/{config_id}/test")
async def test_model_config(
    config_id: str,
    req: ModelConfigTestRequest,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    用指定配置发送一条测试 prompt，返回响应文本 + 延迟。
    不经过 resolver / 缓存，直接用数据库里的配置临时构造 provider。
    """
    _require_super_admin(current_user)
    async with AsyncSessionLocal() as db:
        row = await db.get(LlmModelConfig, config_id)
        if not row:
            raise HTTPException(status_code=404, detail="配置不存在")
        api_key = llm_config_crypto.decrypt(row.api_key_enc)

    provider = OpenAIProvider(
        model=row.model, api_key=api_key, base_url=row.base_url
    )
    t0 = time.monotonic()
    try:
        resp = await provider.chat(
            messages=[LLMMessage(role="user", content=req.prompt)],
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        result = ModelConfigTestResult(
            success=True,
            content=resp.content or "",
            model=resp.model or row.model,
            latency_ms=latency_ms,
        )
    except Exception as e:
        latency_ms = int((time.monotonic() - t0) * 1000)
        result = ModelConfigTestResult(
            success=False,
            content="",
            model=row.model,
            latency_ms=latency_ms,
            error=str(e),
        )
    return _ok(result.model_dump())


# ===================== 用户绑定 =====================

@router.get("/user-bindings")
async def list_user_bindings(
    current_user: Optional[dict] = Depends(get_current_user),
):
    _require_super_admin(current_user)
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(UserLlmModelConfig).order_by(
                    UserLlmModelConfig.created_at.desc()
                )
            )
        ).scalars().all()
        # 一次取出关联 config 和 user 简略信息
        config_ids = {r.config_id for r in rows}
        user_ids = {r.user_id for r in rows}
        configs: dict[str, LlmModelConfig] = {}
        if config_ids:
            for c in (
                await db.execute(
                    select(LlmModelConfig).where(LlmModelConfig.id.in_(config_ids))
                )
            ).scalars().all():
                configs[c.id] = c
        users: dict[str, User] = {}
        if user_ids:
            for u in (
                await db.execute(select(User).where(User.id.in_(user_ids)))
            ).scalars().all():
                users[u.id] = u

        out: List[dict] = []
        for r in rows:
            c = configs.get(r.config_id)
            u = users.get(r.user_id)
            out.append(
                UserBindingOut(
                    id=r.id,
                    user_id=r.user_id,
                    config_id=r.config_id,
                    config_name=c.name if c else "(已删除)",
                    config_provider=c.provider if c else "",
                    config_model=c.model if c else "",
                    user_email=u.email if u else None,
                    user_username=u.username if u else None,
                    created_at=r.created_at,
                    updated_at=r.updated_at,
                ).model_dump()
            )
    return _ok(out)


@router.post("/user-bindings")
async def upsert_user_binding(
    req: UserBindingCreate,
    current_user: Optional[dict] = Depends(get_current_user),
):
    _require_super_admin(current_user)
    async with AsyncSessionLocal() as db:
        # 校验 config 和 user 存在
        cfg = await db.get(LlmModelConfig, req.config_id)
        if not cfg:
            raise HTTPException(status_code=404, detail="模型配置不存在")
        usr = await db.get(User, req.user_id)
        if not usr:
            raise HTTPException(status_code=404, detail="用户不存在")
        # upsert：同 user 已有绑定则更新 config_id
        existing = (
            await db.execute(
                select(UserLlmModelConfig).where(
                    UserLlmModelConfig.user_id == req.user_id
                )
            )
        ).scalars().first()
        if existing:
            existing.config_id = req.config_id
            row = existing
        else:
            row = UserLlmModelConfig(user_id=req.user_id, config_id=req.config_id)
            db.add(row)
        await db.commit()
        await db.refresh(row)
        c = await db.get(LlmModelConfig, row.config_id)
        out = UserBindingOut(
            id=row.id,
            user_id=row.user_id,
            config_id=row.config_id,
            config_name=c.name if c else "",
            config_provider=c.provider if c else "",
            config_model=c.model if c else "",
            user_email=usr.email,
            user_username=usr.username,
            created_at=row.created_at,
            updated_at=row.updated_at,
        ).model_dump()
    invalidate_cache()
    return _ok(out)


@router.delete("/user-bindings/{user_id}")
async def delete_user_binding(
    user_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    _require_super_admin(current_user)
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(UserLlmModelConfig).where(
                UserLlmModelConfig.user_id == user_id
            )
        )
        await db.commit()
    invalidate_cache()
    return _ok({"unbound": user_id})
