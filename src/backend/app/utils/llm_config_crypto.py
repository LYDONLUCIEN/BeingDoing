"""
LLM 配置中 api_key 的对称加密 / 掩码工具。

密钥派生：
- 优先 settings.MODEL_CONFIG_ENC_KEY
- 缺省回退 settings.SECRET_KEY

注意：轮换密钥会让历史密文无法解密 —— 此时 admin 需要重新填一次 api_key。
"""
from __future__ import annotations

import base64
import hashlib
from typing import Optional

from app.config.settings import settings

try:
    from cryptography.fernet import Fernet, InvalidToken
except Exception as e:  # pragma: no cover - 依赖缺失的兜底
    Fernet = None  # type: ignore
    InvalidToken = Exception  # type: ignore
    _IMPORT_ERROR = e
else:
    _IMPORT_ERROR = None


def _derive_key() -> bytes:
    """Fernet 需要 32 字节 url-safe base64 密钥。"""
    raw_key = settings.MODEL_CONFIG_ENC_KEY or settings.SECRET_KEY
    digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _fernet() -> Fernet:
    if Fernet is None:
        raise RuntimeError(
            f"cryptography 未安装，无法加解密 LLM 配置: {_IMPORT_ERROR!r}"
        )
    return Fernet(_derive_key())


def encrypt(plaintext: Optional[str]) -> Optional[str]:
    """加密明文 api_key，返回 url-safe base64 密文。空值原样返回。"""
    if not plaintext:
        return None
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(ciphertext: Optional[str]) -> Optional[str]:
    """解密密文。无效/损坏返回 None（不抛异常，避免日志泄漏）。"""
    if not ciphertext:
        return None
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken:
        return None
    except Exception:
        return None


def mask(key: Optional[str]) -> str:
    """生成掩码字符串：sk-1234abcd → sk-1••••abcd。"""
    if not key:
        return ""
    if len(key) <= 8:
        return "•" * len(key)
    return key[:3] + "•" * (len(key) - 6) + key[-3:]
