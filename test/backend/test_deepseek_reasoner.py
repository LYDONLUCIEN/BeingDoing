"""
DeepSeek Reasoner API 集成测试

验证 deepseek-reasoner 调用是否成功，以及 reasoning_content 与 content 的返回结构。

运行方式（在项目根目录）：

  # 推荐：直接运行（加载 .env 中的 DEEPSEEK_API_KEY）
  python test/backend/test_deepseek_reasoner.py

  # 或用 pytest
  pytest test/backend/test_deepseek_reasoner.py -v -s

  测试 1：原始 API 调用，打印 delta 中的 reasoning_content/content 结构
  测试 2：项目 Provider（需项目配置正确，否则会跳过）
"""
import asyncio
import os
import sys
from pathlib import Path

# 确保能加载项目模块
project_root = Path(__file__).resolve().parents[2]
backend_path = project_root / "src" / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

# 加载 .env（项目根目录）
env_path = project_root / ".env"
if env_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
    except ImportError:
        pass


async def test_deepseek_reasoner_stream():
    """测试 DeepSeek reasoner 流式调用，打印 delta 结构（不依赖项目配置）"""
    from openai import AsyncOpenAI

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key or api_key == "sk-xxx":
        print("⚠️  请设置 DEEPSEEK_API_KEY（.env 或环境变量）")
        return False

    base_url = os.getenv("LLM_BASE_URL") or "https://api.deepseek.com"
    question = "9.11 和 9.8，哪个更大？请简要回答。"
    print("=" * 60)
    print("测试问题:", question)
    print("=" * 60)

    # 直接调用 API 查看原始 chunk 结构
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    stream = await client.chat.completions.create(
        model="deepseek-reasoner",
        messages=[{"role": "user", "content": question}],
        stream=True,
    )

    reasoning_content = ""
    content = ""
    chunk_count = 0
    has_reasoning = False
    has_content = False

    async for chunk in stream:
        chunk_count += 1
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta

        # 打印前 3 个 chunk 的 delta 结构（调试用）
        if chunk_count <= 3:
            delta_dict = delta.model_dump() if hasattr(delta, "model_dump") else {}
            print(f"\n[Chunk {chunk_count}] delta 字段: {list(delta_dict.keys())}")
            for k, v in delta_dict.items():
                if v:
                    print(f"  {k}: {repr(v)[:80]}...")

        rc = getattr(delta, "reasoning_content", None) or ""
        cc = getattr(delta, "content", None) or ""
        if hasattr(delta, "model_dump"):
            try:
                d = delta.model_dump()
                rc = rc or d.get("reasoning_content") or ""
                cc = cc or d.get("content") or ""
            except Exception:
                pass

        if rc:
            has_reasoning = True
            reasoning_content += rc
        if cc:
            has_content = True
            content += cc

    print("\n" + "=" * 60)
    print("统计: 总 chunk 数 =", chunk_count)
    print("reasoning_content 存在:", has_reasoning, "| 长度:", len(reasoning_content))
    print("content 存在:", has_content, "| 长度:", len(content))
    print("=" * 60)
    if reasoning_content:
        print("\n【思考过程】 (前 300 字):\n", reasoning_content[:300], "...")
    if content:
        print("\n【最终回答】:\n", content)
    print()

    return has_reasoning or has_content


async def test_project_provider_stream():
    """使用项目 LLM Provider 测试流式输出（与 simple_chat 一致）"""
    from app.core.llmapi import get_default_llm_provider
    from app.core.llmapi.base import LLMMessage

    provider = get_default_llm_provider(vip_level=1)
    if "reasoner" not in (provider.model or "").lower():
        print("⚠️  当前 VIP1 模型不是 reasoner，请检查 LLM_VIP1_MODEL / .env")
        print("   当前模型:", provider.model)
        return False

    messages = [LLMMessage(role="user", content="1+1=? 一个字回答。")]
    print("=" * 60)
    print("项目 Provider 测试 (model=%s)" % provider.model)
    print("问题:", messages[0].content)
    print("=" * 60)

    think_chunks = []
    content_chunks = []
    events = []

    async for item in provider.chat_stream(messages):
        if isinstance(item, dict):
            t = item.get("_t")
            if t == "think_start":
                events.append("think_start")
                print("\n[事件] think_start")
            elif t == "think_end":
                events.append("think_end")
                think_chunks.append(item.get("content", ""))
                print("[事件] think_end, 长度=%d" % len(item.get("content", "")))
        else:
            content_chunks.append(item)
            if len(content_chunks) <= 3:
                print("[chunk] %r" % item[:50] if len(item) > 50 else item)

    full_content = "".join(content_chunks)
    full_think = "".join(think_chunks)
    print("\n" + "=" * 60)
    print("事件序列:", events)
    print("think 总长:", len(full_think))
    print("content 总长:", len(full_content))
    if full_think:
        print("\n【思考过程】 (前 200 字):", full_think[:200], "...")
    if full_content:
        print("\n【最终回答】:", full_content)
    print("=" * 60)

    return True


def run_standalone():
    """直接运行脚本时的入口"""
    print("\n>>> 1. 原始 API 测试（查看 delta 结构）\n")
    ok1 = asyncio.run(test_deepseek_reasoner_stream())
    print("\n>>> 2. 项目 Provider 测试（与 simple_chat 一致）\n")
    try:
        ok2 = asyncio.run(test_project_provider_stream())
    except Exception as e:
        print("⚠️  项目 Provider 测试跳过:", e)
        ok2 = False
    print("\n>>> 完成: 原始API=%s 项目Provider=%s\n" % (ok1, ok2))


# ============ pytest 入口 ============
try:
    import pytest

    @pytest.mark.asyncio
    async def test_deepseek_reasoner_stream_pytest():
        """pytest: 原始 API 流式调用测试"""
        await test_deepseek_reasoner_stream()

    @pytest.mark.asyncio
    async def test_project_provider_stream_pytest():
        """pytest: 项目 Provider 流式测试"""
        await test_project_provider_stream()
except ImportError:
    pass


if __name__ == "__main__":
    run_standalone()
