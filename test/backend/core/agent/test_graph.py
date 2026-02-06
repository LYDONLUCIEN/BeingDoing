import pytest
import sys
sys.path.append("/home/gitclone/BeingDoing/src/backend")
from app.core.agent import create_agent_graph
from app.core.agent.graph import create_initial_state
from app.config.settings import settings
@pytest.mark.asyncio
async def test_agent_graph_basic_flow(monkeypatch):
    # 1. 构建智能体图
    graph_app = create_agent_graph()

    # 2. 构建初始状态
    state = create_initial_state(user_input="我想探索自己的价值观", current_step="values_exploration")

    # 3. 这里可以 monkeypatch 掉真正的 LLM 调用，避免依赖外部 API
    #    例如：替换 get_default_llm_provider().chat 为一个假的实现
    #    以保证测试可重复、离线运行

    # 4. 运行一次或若干步图
    result = await graph_app.ainvoke(state)
    # 5. 断言：状态里至少有一条 assistant 消息 / 没有 error / should_continue 为 False 等
    assert result.get("error") is None
    assert len(result.get("messages", [])) > 0
    

@pytest.mark.asyncio
async def test_agent_graph_basic_flow_deepseek(monkeypatch):
    # 1. 强制使用 deepseek 配置（覆盖 .env / 环境变量）
    monkeypatch.setattr(settings, "LLM_PROVIDER", "deepseek")
    monkeypatch.setattr(settings, "LLM_MODEL", "deepseek-chat")  # 按你实际模型名改
    # 这里不动 DEEPSEEK_API_KEY 和 LLM_BASE_URL，它们继续从 .env 里来

    # 可选：打印一下当前配置，确认真的生效
    print("LLM_PROVIDER =", settings.LLM_PROVIDER)
    print("LLM_MODEL =", settings.LLM_MODEL)
    print("DEEPSEEK_API_KEY set =", bool(settings.DEEPSEEK_API_KEY))
    print("LLM_BASE_URL =", settings.LLM_BASE_URL)

    # 2. 构建智能体图
    graph_app = create_agent_graph()

    # 3. 构建初始状态
    state = create_initial_state(
        user_input="我想探索自己的价值观",
        current_step="values_exploration",
    )

    # 4. 运行一次图（这里会真实调用 deepseek）
    result = await graph_app.ainvoke(state)

    # 5. 断言：没有错误，且生成了至少一条 assistant 消息
    assert result.get("error") is None
    assert len(result.get("messages", [])) > 0