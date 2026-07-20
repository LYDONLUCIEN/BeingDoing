# 寻路 (xunlu) - AGENTS.md

> 本文档面向 AI 编程助手，帮助快速理解项目架构和开发规范。

## 项目概述

**寻路（xunlu）** 是一个沉浸式的智能引导系统，帮助用户通过探索价值观、才能和兴趣，找到真正想做的事。

**核心公式**：喜欢的事 × 擅长的事 × 重要的事 = 真正想做的事

- **项目语言**: 中文（代码注释、文档、用户界面均为中文）
- **许可证**: MIT

## 技术栈

### 后端
- **框架**: FastAPI 0.104+ (Python 3.10+)
- **数据库**: SQLAlchemy 2.0+ (SQLite 开发 / PostgreSQL 生产)
- **智能体**: LangGraph 0.0.20+ (ReAct 范式)
- **LLM**: DeepSeek (默认) / OpenAI / GLM / Kimi / Claude
- **认证**: JWT (python-jose) + bcrypt
- **迁移**: Alembic
- **代码规范**: Black (line-length: 100), isort, flake8

### 前端
- **框架**: Next.js 14 (App Router)
- **语言**: TypeScript
- **样式**: Tailwind CSS
- **状态管理**: Zustand
- **表单**: React Hook Form + Zod
- **动画**: Framer Motion

## 项目结构

```
.
├── src/
│   ├── backend/              # FastAPI 后端
│   │   ├── app/
│   │   │   ├── api/v1/       # API 路由
│   │   │   ├── core/         # 核心服务
│   │   │   │   ├── agent/    # LangGraph 智能体框架
│   │   │   │   ├── llmapi/   # LLM 统一接口
│   │   │   │   ├── asr/      # 语音识别
│   │   │   │   ├── tts/      # 语音合成
│   │   │   │   ├── knowledge/# 知识库
│   │   │   │   └── payment/  # 支付渠道抽象（base + alipay；get_channel 工厂）
│   │   │   ├── domain/       # 业务领域层（步骤、提示词、知识配置）
│   │   │   ├── models/       # SQLAlchemy 数据模型
│   │   │   ├── services/     # 业务逻辑服务
│   │   │   ├── utils/        # 工具函数
│   │   │   └── config/       # 配置管理
│   │   ├── alembic/          # 数据库迁移
│   │   └── scripts/          # 工具脚本
│   └── frontend/             # Next.js 前端
│       ├── app/              # App Router 页面
│       ├── components/       # React 组件
│       ├── lib/              # 工具库
│       └── stores/           # Zustand 状态管理
├── test/                     # 测试文件
├── docs/                     # 项目文档
├── data/                     # 数据文件（CSV、对话记录）
└── deploy/                   # 部署配置
```

## 环境配置

### 必需配置（.env）

```bash
# 基础配置
SECRET_KEY=your-secret-key
APP_ENV=production
DEBUG=False

# 数据库
DATABASE_URL=sqlite+aiosqlite:///./app.db

# LLM 配置（当前默认使用 DeepSeek）
LLM_PROVIDER=deepseek
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
DEEPSEEK_API_KEY=sk-xxx

# VIP 档位（按激活码 vip_level 选模型）
# P-A 起（ADR-0008）：试用码 vip_level=1、完整码 vip_level=2，两档均配置为 DeepSeek
LLM_VIP1_PROVIDER=deepseek
LLM_VIP2_PROVIDER=deepseek   # deepseek | kimi | qwen；切高级档需同时配对应 KEY

# VIP 档位（试用码 vip_level=1 / 完整码 vip_level=2，ADR-0008）
# 配置口径：当前两档均走 DeepSeek（LLM_VIP2_PROVIDER=deepseek 为默认值，
# 复用 DEEPSEEK_API_KEY / LLM_BASE_URL）；如需高级模型，改 LLM_VIP2_PROVIDER=kimi|qwen 并配对应密钥
LLM_VIP2_PROVIDER=deepseek

# 架构模式
ARCHITECTURE_MODE=simple  # simple | full

# 可选：语音功能
AUDIO_MODE=False

# 可选：SMTP 邮件（忘记密码功能）
SMTP_HOST=smtp.163.com
SMTP_PORT=465
SMTP_USER=xxx@163.com
SMTP_PASS=授权码

# 可选：支付模块（P1 折扣券；P2a 支付宝闭环已上线，微信 P2b 预留）
# 商品目录（ADR-0008：季度/年度套餐、延期激活、咨询；旧 activation_code SKU 已下架）
QUARTERLY_PRICE=6900              # 季度套餐（分，90 天，升级 1 码）
ANNUAL_PRICE=9900                 # 年度套餐（分，365 天，1 升级 + 2 赠品码）
RENEWAL_QUARTERLY_PRICE=2300      # 季度码延期（分，+90 天）
RENEWAL_ANNUAL_PRICE=3300         # 年度码延期（分，+365 天）
CONSULTATION_PRICE=29800          # 报告解读咨询（分/次）
QUARTERLY_DAYS=90
ANNUAL_DAYS=365
ACTIVATION_CODE_PRICE=9900        # 旧 SKU 价（历史订单展示用）
ACTIVATION_CODE_TTL_DAYS=180      # 旧 SKU 有效期（历史用）
DEFAULT_COUPON_AMOUNT=5000        # 券池空时邮件发券自动创建的面额（分）
ORDER_TIMEOUT_MINUTES=30          # pending 订单超时关单（分钟）
MEMBERSHIP_ENABLED=False          # 会员（保留不上线，ADR-0006/0007）
WECHAT_MCH_ID=                    # 微信支付 V3（P2b 预留，空值占位）
ALIPAY_APP_ID=                    # 支付宝（空值时支付接口转 503，部署可先于密钥到位）
ALIPAY_PRIVATE_KEY_PATH=          # 应用私钥 PEM（建议放 src/backend/certs/，已 gitignore）
ALIPAY_PUBLIC_KEY_PATH=           # 支付宝公钥 PEM
ALIPAY_NOTIFY_URL=                # 支付回调公网地址（需 nginx 放行 /api/v1/payment/notify/*）
ALIPAY_GATEWAY=https://openapi.alipay.com/gateway.do  # 沙箱切 openapi-sandbox

# 可选：支付模块（P1 折扣券；P2 渠道 WECHAT_*/ALIPAY_* 预留）
ACTIVATION_CODE_PRICE=9900      # 全程激活码价格（分）
DEFAULT_COUPON_AMOUNT=5000      # 邮件发券池空时自动创建的面额（分）
ORDER_TIMEOUT_MINUTES=30        # pending 订单超时关单
MEMBERSHIP_ENABLED=False        # 会员开关（P3 预留）
```

## 启动命令

### 开发环境（推荐）

使用 `start.sh` 脚本（基于 tmux）：

```bash
# 启动后端 + 前端（默认生产模式）
./start.sh

# 开发模式启动
./start.sh start-dev

# 生产模式（清理构建缓存）
./start.sh start-run

# 其他命令
./start.sh stop           # 停止服务
./start.sh restart        # 重启全部
./start.sh restart backend    # 仅重启后端
./start.sh attach         # 附加到 tmux session 查看日志
```

### 手动启动

```bash
# 后端
cd src/backend
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 前端
cd src/frontend
npm run dev        # 开发模式
npm run build      # 构建
npm run start      # 生产模式
```

### Docker 部署

```bash
docker-compose up -d
```

## 测试

```bash
# 从项目根目录运行
pytest test/backend -v

# 查看覆盖率
pytest test/backend --cov=src/backend/app --cov-report=html

# 运行特定测试
pytest test/backend/test_config.py -v
```

测试配置位于 `pytest.ini`：
- 测试目录: `test/`
- 测试文件: `test_*.py`
- Python path: `src/backend`

## 代码规范

### Python

- **格式化**: Black (line-length: 100)
- **导入排序**: isort (profile: black)
- **代码检查**: flake8 (max-line-length: 100)
- **类型提示**: 使用 `typing` 模块
- **文档字符串**: Google 风格

```python
from typing import Optional, List, Dict

async def get_user(user_id: str) -> Optional[Dict]:
    """获取用户信息
    
    Args:
        user_id: 用户ID
    
    Returns:
        用户信息字典，如果不存在则返回None
    """
    pass
```

### TypeScript

- 使用 ESLint 配置
- 类型定义使用接口
- 组件文档使用 JSDoc

## 数据库迁移

```bash
cd src/backend

# 创建迁移
alembic revision --autogenerate -m "描述"

# 应用迁移
alembic upgrade head

# 回滚
alembic downgrade -1

# 初始化数据
python scripts/init_db.py
```

## 架构模式

项目支持两种架构模式，通过 `ARCHITECTURE_MODE` 控制：

### Simple 模式（当前）
- 数据库: SQLite
- 缓存: 内存
- 向量存储: 内存
- 静态文件: FastAPI 内置

### Full 模式（预留接口）
- 数据库: PostgreSQL
- 缓存: Redis
- 向量存储: ChromaDB/FAISS
- 网关: Nginx

## 试用激活码体系（P-A，ADR-0008）

- **试用码（trial）**：注册即送、自动绑定、不过期（`expires_at=None`）、`vip_level=1`；老用户 0 码时在 `GET /simple-auth/journeys` 懒补发。仅限 values 阶段问答 10 轮（轮=用户消息条数，排除 `internal` 消息；第 11 条起拦截）。
- **完整码（full）**：全阶段解锁。存量码一律 `code_type=full`（`_load_all` setdefault 兼容）。
- **试用门控**：写端点非 values → HTTP 402 `{"type":"trial_phase_locked"}`；values 超 10 轮 → HTTP 402 `{"type":"trial_limit_reached","used":N,"limit":10}`（detail 为 JSON 字符串）。只读 GET 不拦；admin/沙箱走 `_can_bypass_flow_limits` 豁免。
- **关键文件**：`app/utils/trial_codes.py`（发放/补发/计数）、`app/api/v1/simple_chat_routes.py`（`_assert_trial_phase_allowed` / `_assert_trial_message_allowed` / `_peek_trial_phase_lock`）、`GET /simple-auth/my-codes`（我的激活码列表）。

## 智能体架构

使用 LangGraph 实现 ReAct 范式：

```
用户消息 → reasoning_node → action_node → observation_node → 判断继续/结束
                ↑                                      │
                └──────────────────────────────────────┘（循环）
```

**节点说明**:
- `reasoning`: 推理分析
- `action`: 执行工具（搜索、引导等）
- `observation`: 观察结果
- `guide`: 生成回复

## 业务领域层 (Domain)

业务知识集中在 `src/backend/app/domain/`，便于修改：

- **`steps.py`**: 流程步骤定义
- **`prompts/templates/*.yaml`**: 智能体节点提示词
- **`knowledge_config.py`**: 知识库配置
- **`knowledge_rules.py`**: 知识检索规则

修改指南：
- 调整流程步骤 → 改 `steps.py`
- 调整提示词 → 改 `prompts/templates/*.yaml`
- 知识源配置 → 改 `knowledge_config.py`

## API 设计

### 统一响应格式

```json
{
  "code": 200,
  "message": "success",
  "data": {}
}
```

### 错误响应

```json
{
  "code": 400,
  "message": "错误描述",
  "detail": "详细错误信息"
}
```

### 主要 API 路由

- `/api/v1/auth/*` - 认证
- `/api/v1/users/*` - 用户
- `/api/v1/sessions/*` - 会话
- `/api/v1/questions/*` - 问题
- `/api/v1/answers/*` - 回答
- `/api/v1/chat/*` - 对话
- `/api/v1/search/*` - 检索
- `/api/v1/formula/*` - 公式
- `/api/v1/export/*` - 导出
- `/api/v1/admin/*` - 管理（含 `/admin/coupons` 折扣券、`/admin/payment/orders` 订单与退款、`/admin/consultations` 咨询管理）
- `/api/v1/payment/*` - 支付（用户侧：products / coupons/validate / orders；`/payment/notify/alipay` 为渠道回调，无登录鉴权）
- `/api/v1/consultation/*` - 报告解读咨询（用户侧：my-reports / bookings / survey）
- `/api/v1/team-analysis/*` - 团队分析（candidates / 创建 / 列表 / 详情）

启动后端后访问 Swagger UI: http://localhost:8000/docs

## 安全注意事项

1. **密钥管理**: `SECRET_KEY` 和 API 密钥必须保密，不要提交到 Git
2. **密码加密**: 使用 bcrypt 存储密码哈希
3. **JWT 验证**: Token 有效期默认 60 分钟
4. **超级管理员**: 通过 `SUPER_ADMIN_USER_IDS` 或 `SUPER_ADMIN_EMAILS` 配置
5. **Debug 模式**: `DEBUG_MODE=True` 仅对超级管理员生效

## 常用开发任务

### 添加新 API

1. 在 `src/backend/app/api/v1/` 创建路由文件
2. 在 `src/backend/app/services/` 实现业务逻辑
3. 在 `src/backend/app/main.py` 注册路由
4. 更新 `docs/API_DOCUMENTATION.md`

### 添加新组件

1. 在 `src/frontend/components/` 创建组件
2. 在 `src/frontend/lib/api/` 添加 API 调用（如需要）
3. 在页面中使用组件

### 修改智能体行为

1. 修改提示词: `src/backend/app/domain/prompts/templates/*.yaml`
2. 修改节点逻辑: `src/backend/app/core/agent/nodes/`
3. 修改工具: `src/backend/app/core/agent/tools/`

## 文档索引

- `docs/QUICK_START.md` - 快速开始
- `docs/DATA_STORAGE_SIMPLE.md` - Simple 模式 data 目录、Thread 概念与后端同步逻辑
- `docs/DEVELOPMENT.md` - 开发指南
- `docs/ARCHITECTURE.md` - 架构设计
- `docs/DATABASE_SCHEMA.md` - 数据库设计
- `docs/API_DOCUMENTATION.md` - API 文档
- `docs/TESTING.md` - 测试说明
- `docs/DEPLOYMENT.md` - 部署指南
- `docs/DOCKER.md` - Docker 使用
- `docs/ADMIN_SANDBOX_FORK.md` - 管理员调试沙箱（Fork 正式激活码）
- `CONTEXT.md` - 领域术语（探索流程 + 支付与商业化：试用/完整码、套餐、折扣券、报告审核、团队分析）
- `docs/adr/` - 架构决策记录（0005 双线支付 / 0006-0007 会员体系保留 / 0008 套餐与试用码 / 0009 报告审核自动批复 / 0010 码双角色与报告授权）
- `tasks/payment-module-plan.md` - 支付模块实施计划（P1 折扣券 ✅ / P2a 支付宝 ✅ / P2b 微信待做）
- `tasks/packages-trial-plan.md` - 套餐与试用体系实施计划（P-A~P-E 全部 ✅）
- `wiki/开发文档/0720-支付模块.md` - 支付配置操作手册（支付宝平台/.env/沙箱联调）

## 调试技巧

### 后端

```python
import logging
logger = logging.getLogger(__name__)
logger.debug("调试信息")

# 断点
import pdb; pdb.set_trace()
```

### 前端

- 浏览器控制台查看日志
- React DevTools 调试组件状态
- Network 面板查看 API 请求

## 注意事项

1. **环境变量冲突**: `start.sh` 会自动清理冲突的环境变量，确保只加载项目 `.env`
2. **前端 API 代理**: 开发模式下，前端通过 `next.config.js` 的 rewrites 代理到后端
3. **对话记录存储**: 存储在 `data/conversations/{session_id}/` 目录下
4. **知识库文件**: CSV 文件位于项目根目录，Docker 部署时通过 volume 挂载
