"""
智能体运行配置：支持「思考链 + 用户侧输出」的灵活调用方式。
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentRunConfig:
    """
    运行配置：
    - use_user_agent_node: 结束时是否经过 user_agent 节点，将 final_response 写入用户可见 messages（默认 True）
    - max_iterations: 全局最大推理-行动-观察轮数（默认 10）
    - compress_context: 是否在推理前做消息级上下文压缩（默认 True）
    - max_rounds_per_step: 每个 current_step 内最大轮数（默认 5），可被 context.limits 覆盖
    """
    use_user_agent_node: bool = True
    max_iterations: int = 10
    compress_context: bool = True
    max_rounds_per_step: int = 5


DEFAULT_RUN_CONFIG = AgentRunConfig()
