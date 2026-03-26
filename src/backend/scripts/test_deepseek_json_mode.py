#!/usr/bin/env python3
"""
测试 DeepSeek JSON Output 在 chat/reasoner 上的兼容性。

用法（在项目根目录）:
  python src/backend/scripts/test_deepseek_json_mode.py

可选:
  python src/backend/scripts/test_deepseek_json_mode.py --base-url https://api.deepseek.com
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from openai import OpenAI


def _load_env() -> None:
    backend_dir = Path(__file__).resolve().parent.parent
    project_root = backend_dir.parent.parent
    env_file = project_root / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(env_file)
        except Exception:
            pass
    sys.path.insert(0, str(backend_dir))


def _build_prompt() -> list[dict]:
    prompt = (
        '请仅输出 JSON，不要额外文字。'
        '格式示例：{"state":"confirmed|rejected|continue","content":"一句话"}。'
        '用户回复：我确认！'
    )
    return [{"role": "user", "content": prompt}]


def _run_once(client: OpenAI, model: str) -> None:
    print(f"\n=== model={model} ===")
    messages = _build_prompt()

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
            max_tokens=4096,
        )
        print(resp)
        content = (resp.choices[0].message.content or "").strip()
        
        print("[json_mode] success=True")
        print(f"[json_mode] content={content}")
        try:
            parsed = json.loads(content)
            print(f"[json_mode] parsed_ok=True parsed={parsed}")
        except Exception as e:
            print(f"[json_mode] parsed_ok=False err_type={type(e).__name__} err={e}")
    except Exception as e:
        print("[json_mode] success=False")
        print(f"[json_mode] err_type={type(e).__name__} err={e}")

    try:
        resp2 = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=4096,
        )
        print(resp2)
        content2 = (resp2.choices[0].message.content or "").strip()
        print("[plain_mode] success=True")
        print(f"[plain_mode] content={content2}")
    except Exception as e:
        print("[plain_mode] success=False")
        print(f"[plain_mode] err_type={type(e).__name__} err={e}")


async def main() -> None:
    _load_env()

    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"))
    parser.add_argument("--api-key", default=os.getenv("DEEPSEEK_API_KEY"))
    args = parser.parse_args()

    if not args.api_key:
        raise RuntimeError("缺少 DEEPSEEK_API_KEY，请先在 .env 或环境变量中配置。")

    print(f"base_url={args.base_url}")
    client = OpenAI(api_key=args.api_key, base_url=args.base_url)

    _run_once(client, "deepseek-chat")
    _run_once(client, "deepseek-reasoner")


if __name__ == "__main__":
    asyncio.run(main())
