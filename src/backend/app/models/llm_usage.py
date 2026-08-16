"""
LLM 调用级 token 用量与预估成本模型

每次 LLM API 调用落一行（调用粒度，区别于 AnalyticsChatTurn 的对话轮次粒度）：
- 覆盖全部场景（chat / report / rumination / team_analysis / ...），scene 字段区分
- cost_yuan 在落库时按「当时费率表 × 调用时刻峰/谷」算好存死，日后涨价不影响历史
- user_id 可能为空（如后台任务拿不到登录态），此时靠 activation_code / session_id 归属
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String

from app.models.database import Base


class LlmUsageLog(Base):
    """单次 LLM 调用的 token 用量与预估成本（人民币元）"""

    __tablename__ = "llm_usage_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), nullable=True, index=True)  # 登录用户；后台任务可能为空
    session_id = Column(String(128), nullable=True, index=True)  # report_id / 会话 ID
    activation_code = Column(String(64), nullable=True, index=True)  # simple 模式激活码
    scene = Column(
        String(50), nullable=False, index=True
    )  # chat / report / rumination / team_analysis / dimension_check / anchor_refine / admin_test / unknown
    provider = Column(String(32), nullable=True)  # deepseek / kimi / qwen / openai
    model = Column(String(64), nullable=True, index=True)
    prompt_tokens = Column(Integer, default=0)
    cache_hit_tokens = Column(Integer, default=0)  # DeepSeek prompt_cache_hit_tokens
    cache_miss_tokens = Column(Integer, default=0)  # DeepSeek prompt_cache_miss_tokens
    completion_tokens = Column(Integer, default=0)
    reasoning_tokens = Column(Integer, default=0)  # 思维链 token（含在 completion 内，仅拆分展示）
    cost_yuan = Column(Float, nullable=True)  # 预估成本（元）；费率表未覆盖该模型时为 NULL
    is_peak = Column(Boolean, default=False)  # 调用时刻是否高峰时段（Asia/Shanghai）
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
