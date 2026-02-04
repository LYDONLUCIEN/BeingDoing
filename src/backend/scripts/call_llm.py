#!/usr/bin/env python3
"""
从 .env 文件读取配置并调用 LLM（支持 OpenAI / DeepSeek）。
用法：
  cd src/backend && python scripts/call_llm.py
  # 或从项目根目录：
  python -c "import sys; sys.path.insert(0, 'src/backend'); exec(open('src/backend/scripts/call_llm.py').read())"
需先在项目根目录的 .env 中配置，例如 DeepSeek：
  LLM_PROVIDER=deepseek
  DEEPSEEK_API_KEY=sk-xxx
  LLM_MODEL=deepseek-chat
"""
import asyncio
import sys
from pathlib import Path

# 在导入 app 之前加载 .env（项目根目录）
_backend_dir = Path(__file__).resolve().parent.parent
_project_root = _backend_dir.parent.parent
_env_file = _project_root / ".env"
if _env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_file)

sys.path.insert(0, str(_backend_dir))

from app.core.llmapi.factory import create_llm_provider
from app.core.llmapi.base import LLMMessage


async def main():
    # 从 .env / 环境变量创建 Provider（openai 或 deepseek）
    provider = create_llm_provider()
    messages = [
        LLMMessage(role="system", content="You are a helpful assistant."),
        LLMMessage(role="user", content="Hello"),
    ]
    response = await provider.chat(messages, stream=False)
    print(response.content)


if __name__ == "__main__":
    asyncio.run(main())
