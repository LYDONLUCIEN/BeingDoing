#!/usr/bin/env python3
"""
同步 LLM 默认模型配置：当前环境变量 → 数据库 llm_model_configs 的 is_default 行。

背景（2026-08-19 key 环境隔离）：
- 后端模型配置为 DB 优先（core/llmapi/resolver.py）：vip_level=None 的链路
  （旧 ReAct agent 等）读取 llm_model_configs 的 is_default 行，其 api_key
  为 Fernet 加密入库；DB 命中时 .env 的 key 对这些链路不生效。
- 因此更换 DEEPSEEK_API_KEY 时，除 env 文件外还需同步本表。

用法（在仓库根目录，先确保 env 已加载或使用 --env-file）：

    # 同步（默认读 .env；prod 环境传 --env-file .env.prod 或直接 source 后执行）
    python scripts/sync_llm_db_config.py

    # 只读检查 env 与 DB 是否一致（打码输出，不写库）
    python scripts/sync_llm_db_config.py --check

生产服务器：更新 /etc/beingdoing.env 后，在应用工作目录用同一环境执行本脚本，
或直接在 admin 后台「模型配置」页修改 key（二者等价，均走加密入库）。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "src" / "backend"
sys.path.insert(0, str(BACKEND_DIR))


def _load_env(env_file: str | None) -> None:
    """加载 .env（base）+ 可选覆盖文件，与 start.sh 的加载顺序一致。"""
    try:
        from dotenv import load_dotenv
    except ImportError:
        print("缺少 python-dotenv，请先 pip install python-dotenv", file=sys.stderr)
        sys.exit(2)
    base = PROJECT_ROOT / ".env"
    if base.exists():
        load_dotenv(base)
    if env_file:
        overlay = PROJECT_ROOT / env_file
        if not overlay.exists():
            print(f"覆盖文件不存在: {overlay}", file=sys.stderr)
            sys.exit(2)
        load_dotenv(overlay, override=True)


def _mask(key: str | None) -> str:
    if not key:
        return "(空)"
    if len(key) <= 10:
        return "***"
    return f"{key[:6]}*****{key[-4:]}"


def main() -> None:
    parser = argparse.ArgumentParser(description="同步 LLM 默认模型配置到数据库")
    parser.add_argument("--env-file", help="在 .env 之上叠加的环境文件（如 .env.prod）")
    parser.add_argument("--check", action="store_true", help="只读检查，不写库")
    args = parser.parse_args()

    _load_env(args.env_file)

    from app.config.settings import settings  # noqa: E402
    from app.models.database import get_database_url  # noqa: E402
    from app.utils import llm_config_crypto  # noqa: E402

    env_key = settings.DEEPSEEK_API_KEY or ""
    env_provider = (settings.LLM_PROVIDER or "deepseek").lower()
    env_base_url = settings.LLM_BASE_URL or "https://api.deepseek.com"
    env_model = settings.LLM_PRO_MODEL or settings.LLM_MODEL or "deepseek-v4-pro"

    url = get_database_url()
    if url.startswith("sqlite+aiosqlite"):
        url = url.replace("sqlite+aiosqlite", "sqlite", 1)
    elif url.startswith("postgresql+asyncpg"):
        url = url.replace("postgresql+asyncpg", "postgresql+psycopg2", 1)

    # sqlite 相对路径以后端工作目录为基准（与 uvicorn 运行目录一致）
    if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
        os.chdir(BACKEND_DIR)

    from sqlalchemy import create_engine, select  # noqa: E402
    from sqlalchemy.orm import Session  # noqa: E402

    from app.models.llm_model_config import LlmModelConfig  # noqa: E402

    engine = create_engine(url, future=True)
    with Session(engine) as session:
        row = session.execute(
            select(LlmModelConfig).where(LlmModelConfig.is_default.is_(True))
        ).scalars().first()
        if row is None:
            row = session.execute(
                select(LlmModelConfig).where(LlmModelConfig.enabled.is_(True))
            ).scalars().first()

        db_key = llm_config_crypto.decrypt(row.api_key_enc) if row else None

        print(f"数据库: {url.split('@')[-1]}")
        print(f"env : provider={env_provider} model={env_model} key={_mask(env_key)}")
        if row is None:
            print("db  : (无 is_default/enabled 配置行)")
        else:
            print(
                f"db  : provider={row.provider} model={row.model} "
                f"key={_mask(db_key)} (id={row.id}, is_default={row.is_default})"
            )

        consistent = (
            row is not None
            and (db_key or "") == env_key
            and row.provider == env_provider
        )
        print("一致性:", "✅ 一致" if consistent else "❌ 不一致")

        if args.check:
            return
        if not env_key:
            print("\n错误：当前环境 DEEPSEEK_API_KEY 为空，拒绝写入。", file=sys.stderr)
            print("请先在 .env（或 --env-file 指定的文件）中填入 key。", file=sys.stderr)
            sys.exit(2)
        if consistent:
            print("\n无需同步。")
            return

        if row is None:
            row = LlmModelConfig(
                name="env 同步默认配置",
                provider=env_provider,
                model=env_model,
                base_url=env_base_url,
                api_key_enc=llm_config_crypto.encrypt(env_key),
                is_default=True,
                enabled=True,
                notes="由 scripts/sync_llm_db_config.py 创建",
            )
            session.add(row)
        else:
            row.provider = env_provider
            row.model = env_model
            row.base_url = env_base_url
            row.api_key_enc = llm_config_crypto.encrypt(env_key)
            row.enabled = True
            row.is_default = True
        session.commit()
        print(f"\n已写入数据库: provider={env_provider} model={env_model} key={_mask(env_key)}")


if __name__ == "__main__":
    main()
