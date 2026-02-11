import pytest
import sys
sys.path.append("/home/gitclone/BeingDoing/src/backend")

from app.core.agent.state import AgentState
from app.core.agent.nodes.reasoning import reasoning_node
from app.core.agent.nodes.observation import observation_node
from app.core.llmapi.base import LLMResponse


class FakeLLM:
    """简单的假 LLM，用于单元测试，避免真实网络调用。"""

    def __init__(self, responses):
        # responses 是一个生成器或可迭代对象，每次 chat 取下一条
        self._responses = iter(responses)
        self.model = "fake-model"

    async def chat(self, messages, temperature: float = 0.7, max_tokens=None, **kwargs):
        content = next(self._responses)
        return LLMResponse(content=content, model=self.model)


@pytest.mark.asyncio
async def test_observation_updates_step_summary(monkeypatch):
    """验证 observation_node 会把本轮 analysis 写入按步骤划分的 summaries 中，并做长度控制。"""

    # 构造一个包含工具结果的状态（含双轨 messages / inner_messages 与 logs）
    state: AgentState = {
        "messages": [],
        "inner_messages": [],
        "logs": [],
        "context": {},
        "current_step": "values_exploration",
        "tools_used": ["guide_tool"],
        "tool_results": [
            {
                "tool": "guide_tool",
                "output": {"dummy": "tool output"},
            }
        ],
        "user_input": "我想探索自己的价值观",
        "user_id": None,
        "session_id": None,
        "iteration_count": 0,
        "should_continue": True,
        "final_response": None,
        "error": None,
    }

    # Fake LLM 返回一个带有 analysis 字段的 JSON
    fake_observation_json = """
    {
        "should_continue": false,
        "next_action": "respond",
        "analysis": "这是针对价值观探索步骤的阶段性总结，用于后续深度思考。",
        "response": "阶段性回答"
    }
    """

    fake_llm = FakeLLM([fake_observation_json])

    # 替换 observation_node 内部使用的 get_default_llm_provider
    monkeypatch.setattr(
        "app.core.agent.nodes.observation.get_default_llm_provider",
        lambda: fake_llm,
    )

    new_state = await observation_node(state)

    assert new_state["error"] is None
    assert new_state["should_continue"] is False
    assert new_state["final_response"] == "阶段性回答"

    # 关键：summaries 里应该有当前步骤的总结
    summaries = new_state["context"].get("summaries", {})
    assert "values_exploration" in summaries
    assert "阶段性总结" in summaries["values_exploration"]

    # step_rounds 和 iteration_count 应该被更新（用于深度控制）
    step_rounds = new_state["context"].get("step_rounds", {})
    assert step_rounds.get("values_exploration", 0) == 1
    assert new_state["iteration_count"] == 1

    # profile.notes 中应包含一条记录
    profile = new_state["context"].get("profile", {})
    notes = profile.get("notes", [])
    assert len(notes) == 1
    assert notes[0]["step"] == "values_exploration"
    assert "阶段性总结" in notes[0]["analysis"]


@pytest.mark.asyncio
async def test_reasoning_uses_step_summary_in_system_prompt(monkeypatch):
    """验证 reasoning_node 在构造 system prompt 时会带入当前步骤的摘要信息。"""

    # 预先在 context.summaries 中放入一段历史摘要
    summary_text = "这是历史上的价值观阶段性总结。"
    state: AgentState = {
        "messages": [],
        "inner_messages": [],
        "logs": [],
        "context": {
            "summaries": {"values_exploration": summary_text},
        },
        "current_step": "values_exploration",
        "tools_used": [],
        "tool_results": [],
        "user_input": "我想继续探索自己的价值观",
        "user_id": None,
        "session_id": None,
        "iteration_count": 0,
        "should_continue": True,
        "final_response": None,
        "error": None,
    }

    captured_system_prompt = {}

    class InspectLLM:
        async def chat(self, messages, temperature: float = 0.7, max_tokens=None, **kwargs):
            # 记录下 system 消息内容
            system_msg = next(m for m in messages if m.role == "system")
            captured_system_prompt["content"] = system_msg.content
            # 返回一个简单的 JSON，避免解析失败
            return LLMResponse(
                content='{"action": "respond", "response": "ok", "reasoning": "test"}',
                model="fake-model",
            )

    monkeypatch.setattr(
        "app.core.agent.nodes.reasoning.get_default_llm_provider",
        lambda: InspectLLM(),
    )

    new_state = await reasoning_node(state)

    assert new_state["error"] is None
    # system prompt 里应该包含我们预先写入的摘要文本
    assert summary_text in captured_system_prompt["content"]


def test_should_continue_respects_step_round_limit():
    """验证 should_continue 会根据每个步骤的轮数进行深度控制。"""
    from app.core.agent.graph import make_should_continue

    state: AgentState = {
        "messages": [],
        "inner_messages": [],
        "logs": [],
        "context": {
            "step_rounds": {"values_exploration": 5},  # 已经达到默认上限 5
        },
        "current_step": "values_exploration",
        "tools_used": [],
        "tool_results": [],
        "user_input": "test",
        "user_id": None,
        "session_id": None,
        "iteration_count": 3,
        "should_continue": True,
        "final_response": None,
        "error": None,
    }
    should_continue = make_should_continue(10)
    decision = should_continue(state)
    assert decision == "end"

