"""
simple_chat 包：将原 simple_chat.py 拆分为多个子模块。

子模块：
- stream_utils: SSE 流处理、STATE_JSON 解析
- llm_providers: LLM 模型选择与路由
- prompt_builder: 提示词构建、题库加载
- context_resolver: 激活码校验、报告上下文解析、权限检查

路由定义在 simple_chat_routes.py 中，通过本包导出 router。
"""

# 导出路由（供 app 注册使用）
from app.api.v1.simple_chat_routes import router  # noqa: F401
