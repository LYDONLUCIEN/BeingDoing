# 寻路·OpenLife (openlife) - AGENTS.md

> 本文档面向 AI 编程助手，帮助快速理解项目架构和开发规范。

## 项目概述

**寻路·OpenLife（openlife）** 是一个沉浸式的智能引导系统，帮助用户通过探索价值观、才能和兴趣，找到真正想做的事。

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
LLM_MODEL=deepseek-v4-pro
# ⚠️ 2026-08-19 起测试/生产 key 完全隔离：.env 只放测试 key，生产 key 只放 .env.prod
# （.env.prod 由 start.sh prod 叠加覆盖）；生产服务器另有 /etc/beingdoing.env（systemd）
DEEPSEEK_API_KEY=sk-xxx

# 模型场景分流（2026-08-19 起，仅 deepseek 生效）：按 usage_context 的 scene 在
# factory._get_vip_provider_config 内确定性选模型（优先级高于 LLM_VIP1_MODEL）——
# scene=chat（前四 phase values/strengths/interests/purpose 的对话+结论卡）→ flash；
# rumination / report / team_analysis / 未知 → pro。
# ⚠️ 2026-08-23 起全部场景统一 pro + 思维链（效果优先）：.env 里 LLM_FLASH_MODEL
# 已覆盖为 deepseek-v4-pro（分流机制保留，回退只改这一行）；LLM_THINKING_ENABLED=True。
# 配套：思维链模型 max_tokens 是「思维链+正文」合计上限，代码内所有调用点已统一
# 放大到 8192（balance 判定 8000/16000、团队分析 16384、报告 65536）——不传会被
# DeepSeek 默认 4096 截断（历史截断 bug 根因），新增加 LLM 调用点必须显式传大额度
# LLM_FLASH_MODEL=deepseek-v4-flash
# LLM_PRO_MODEL=deepseek-v4-pro
# 注意：vip_level=None 的链路（旧 ReAct agent）走 DB-first resolver（llm_model_configs
# 表 is_default 行，key 加密入库），换 key 后需同步：python scripts/sync_llm_db_config.py
# （--check 只读对比 env 与 DB），或 admin 后台「模型配置」页修改

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

# 报告 PDF 渲染引擎（ADR-0019，2026-08-20 起）
# weasyprint（默认，内置 Python 渲染）| xunlu（src/report-renderer 精简 Node 渲染器，子进程调用）
# 优先级：admin 运行时配置（报告页单选，存 data/report_render_config.json，即时生效）> 本 env > 默认
# RENDER_ENGINE=xunlu
# REPORT_RENDERER_DIR=src/report-renderer 绝对路径（默认自动推导）
# REPORT_RENDERER_NODE=node / CHROME_PATH=（留空自动探测 /usr/bin/google-chrome）
# REPORT_RENDER_TIMEOUT=120（单次渲染超时秒数）
# 注：xunlu 引擎需服务器有 Node ≥20 + Chrome/Chromium；dist/ 已入库无需构建，改源码后需 npm run build

# 可选：语音功能
AUDIO_MODE=False

# LLM token 用量统计（admin「埋点与 Token 统计」页，llm_usage_logs 表）
# 峰谷时段（Asia/Shanghai）：DeepSeek 2026-08-17 起峰时价 = 谷时 2 倍
LLM_PEAK_HOURS=09:00-12:00,14:00-18:00
# 可选：JSON 覆盖/增补内置费率表（app/utils/llm_pricing.py DEFAULT_PRICING，按 model 键整体替换）
# LLM_PRICING_JSON={"deepseek-v4-pro":[{"from":"2026-08-17T00:00:00+08:00","peak":{"hit":0.30,"miss":9.0,"out":27.0},"off_peak":{"hit":0.15,"miss":4.5,"out":13.5}}]}

# 可选：SMTP 邮件（忘记密码功能）
# 当前用 163 邮箱：465 端口 + SSL（SMTP_USE_SSL=True），密码为 163 客户端授权码
# （2026-08-19 试过换 Outlook：微软在账号层面禁用个人邮箱 SMTP/IMAP 基本认证，无解，回退 163）
SMTP_HOST=smtp.163.com
SMTP_PORT=465
SMTP_USER=xxx@163.com
SMTP_PASS=授权码
TEAM_ANALYSIS_EMAIL=soulhappylab@163.com  # 团队分析报告联系邮箱（前后端共用，ADR-0018；仅联系地址，与发信通道无关）

# 可选：支付模块（P1 折扣券；P2a 支付宝闭环已上线，微信 P2b 预留）
# 商品目录（ADR-0008；2026-07-28 起对外口径改回：季度套餐 / 年度套餐，内部 SKU 仍为 quarterly_package/annual_package）
# 套餐码有效期（ADR-0018，2026-08-16 起）：支付成功（交付）即起算，交付时 expires_at = now + 套餐天数；
# 存量未激活码（expires_at=None）不溯及既往，仍由 maybe_start_validity 首次创建对话 session 时起算
QUARTERLY_PRICE=6900              # 季度套餐（分，90 天，1 个未绑定码）
ANNUAL_PRICE=15900                # 年度套餐（分，365 天，3 个未绑定码；99→128→159，2026-08-05 起）
# 交付口径（ADR-0014，2026-08-05 起）：套餐一律发未绑定码，不再自动升级试用码/自动绑定；
# 用户可消耗 1 个未绑定码把试用码原地升级为完整码（POST /simple-auth/codes/apply-to-trial）
RENEWAL_PRICE=990                  # 延期激活（分；ADR-0016，2026-08-08 起任意完整码统一 9.9 元 / +7 天，不分套餐）
RENEWAL_DAYS=7                    # 延期时长（天，统一 +7 天）
FREE_RENEWAL_DAYS=7               # 首次过期免费续期时长（天，每码一次）
ACTIVATION_EXPIRY_SCAN_CRON=0 10 * * *  # 过期扫描（每日 10:00，发免费续期邮件+站内信）
# RENEWAL_QUARTERLY_PRICE / RENEWAL_ANNUAL_PRICE 已弃用（旧分档延期，仅历史兼容保留）
CONSULTATION_PRICE=29800          # 报告解读咨询（分/次）
QUARTERLY_DAYS=90
ANNUAL_DAYS=365
ACTIVATION_CODE_PRICE=9900        # 旧 SKU 价（历史订单展示用）
ACTIVATION_CODE_TTL_DAYS=180      # 旧 SKU 有效期（历史用）
DEFAULT_COUPON_AMOUNT=5000        # 券池空时邮件发券自动创建的面额（分）
ORDER_TIMEOUT_MINUTES=30          # pending 订单超时关单（分钟）
ACCOUNT_DELETION_RETENTION_DAYS=30  # 账户注销冷存天数（float，0=立即删除）
MEMBERSHIP_ENABLED=False          # 会员（保留不上线，ADR-0006/0007）
WECHAT_MCH_ID=                    # 微信支付 V3（P2b 预留，空值占位）
ALIPAY_APP_ID=                    # 支付宝（电脑网站支付 page.pay；空值时支付接口转 503，部署可先于密钥到位）
ALIPAY_PRIVATE_KEY_PATH=          # 应用私钥 PEM（建议放 src/backend/certs/，已 gitignore）
ALIPAY_PUBLIC_KEY_PATH=           # 支付宝公钥 PEM
ALIPAY_NOTIFY_URL=                # 支付回调公网地址（需 nginx 放行 /api/v1/payment/notify/*）
ALIPAY_RETURN_URL=                # 电脑网站支付同步回跳地址（前端 /payment/result 结果页）
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
# 启动后端 + 前端（默认，仅加载 .env）
./start.sh

# 开发环境（加载 .env → .env.dev，clean build + start）
./start.sh dev            # 等同 ./start.sh start dev（start-dev 为旧兼容写法）

# 生产环境（加载 .env → .env.prod，clean build + start）
./start.sh prod           # 等同 ./start.sh start prod（start-run 为旧兼容写法）

# 热更新模式（npm run dev）
./start.sh dev --hot

# 其他命令
./start.sh stop           # 停止服务
./start.sh restart        # 重启全部（自动沿用 .start_env 记录的上次 start 环境，不会丢 .env.<env> 覆盖）
./start.sh restart backend    # 仅重启后端
./start.sh attach         # 附加到 tmux session 查看日志
```

> **conda 环境按目标环境自动选择**（2026-08-21 起）：`prod` 用生产小机的 base 环境（默认 `/root/miniconda3`），`dev/test`/无参数用开发机 py312（默认 `/mnt/vdb1/miniconda3`）；路径不对时启动前会直接报错提示。可用环境变量覆盖：`CONDA_BASE=/path CONDA_ENV=xxx ./start.sh prod`。注意：生产机上裸跑 `./start.sh`（不带 prod）会走 dev 的 conda 默认值，**生产请始终用 `./start.sh prod`**。

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
- **消耗升级（ADR-0014）**：购买套餐不再自动升级试用码——季度发 1 个、年度发 3 个**未绑定**完整码（可自用/转赠）；用户可消耗 1 个未绑定码（自购或被赠均可）把已开聊试用码**原地升级**为完整码：被消耗码置 `status=consumed`（+`consumed_into` 审计），试用码走 `upgrade_to_full`（码字符串/对话记录/session 全保留，ADR-0018 起**继承被消耗码的剩余有效期**——`upgrade_to_full(expires_at=...)`；存量未激活码未传入则保持首次使用起算老口径）。入口：支付结果页弹窗（可「不再提醒」，存 `users.preferences`）、两种 402 拦截点（直购 intent=upgrade_trial 支付后自动消耗升级 / 用已有码升级，按 `has_upgrade_codes` 分级显示）、我的激活码页（「升级完整版」按钮始终可见，作为手动输入常驻入口）。UpgradeTrialModal 空态（无自购未绑定码）提供「手动输入激活码」（覆盖被赠码：purchaser 非本人的码不进 unbound_codes 列表，但 apply-to-trial 实际允许消耗）；`has_started_trial=false` 时弹窗提示「建议直接用新码开始」并可跳激活页，保留仍要升级兼底。
- **试用门控**：写端点非 values → HTTP 402 `{"type":"trial_phase_locked"}`；values 超 10 轮 → HTTP 402 `{"type":"trial_limit_reached","used":N,"limit":10}`（detail 为 JSON 字符串）。两种 402 detail 均带 `has_upgrade_codes`（`_has_upgrade_codes`，口径=自购+未绑定+active+full，与 upgrade-context 共用 `list_unbound_full_codes_purchased_by`）：前端 chat 页据此做引导分级——无码时仅「购买升级」单选项；有码时「使用已有激活码升级」升为主按钮、购买降为次按钮。只读 GET 不拦；admin/沙箱走 `_can_bypass_flow_limits` 豁免。
- **邮箱验证门控（2026-08-08 起）**：绑定了邮箱但 `email_verified=False` 的用户禁止一切探索写操作——`_assert_email_verified_for_explore` 挂在 `_assert_trial_phase_allowed` 统一入口（覆盖 init/message/stream/thread/rumination/prior-context 全部写端点）+ `POST /simple-chat/survey`，返回 HTTP 403 `{"type":"email_not_verified"}`。只读 GET 不拦；无邮箱（手机注册）与 `_can_bypass_flow_limits` 豁免。前端：`/explore/survey` 对未验证用户显示验证引导卡（替代问卷表单，可重发验证邮件），chat 页检测未验证主动跳回问卷页。背景：注册即送试用码自动绑定后，未验证用户曾可绕过激活页验证提示直接开聊。
- **问卷昵称同源（2026-08-08 起）**：调研问卷 `nickname` 与注册昵称 `users.username` 同源——前端 `/explore/survey` 未保存过昵称时预填 username；后端 `/simple-chat/survey` 与 `/user-survey` 保存时昵称空白自动回填 username（`_survey_data_with_nickname_default`）。
- **退款口径（ADR-0014）**：套餐订单任一码被 claim/consumed → 整单不可退；全部码未动 → 可退并 revoke 全部码；延期维持不可退。
- **Admin 手动创建试用码（2026-08-18 起）**：`POST /admin/activations/batch-create` 新增 `code_type`（`full` 默认 / `trial`），复用 `create_activation_batch(code_type=...)` 创建**未绑定**临时试用码（不过期、vip_level=1、values 阶段限 10 轮），任意登录用户在激活页输入即 claim，便于测试；admin 激活码列表透传 `code_type`/`vip_level` 并对试用码显示「试用」badge，创建表单带类型选择（选 trial 时有效期输入禁用）。
- **结论卡出卡机制（2026-09-02 修订，撤销 2026-08-25 的 ≤10 轮强制压制门控）**：模型自然出卡**不设最小轮数**——四阶段（values/strengths/interests/purpose）任何轮数下，模型判断用户明确点头确认即可输出 `STATE_JSON(pending_ready)` 正常落库出卡，后端不拦截、提示词注入段单一口径（「明确点头确认 → 输出 STATE_JSON」），原「深入探索期不收口」压制与提示词冲突一并移除。背景：原门控是「试用期不出卡促转化」的产品决策（见 `wiki/开发文档/0825-结论卡不出卡根治-*.md` 决策表 #3/#4），现转化改由 trial 402 阶段锁承担——**试用码用户 10 轮内出卡确认后，点「完成并继续」进非 values 阶段时 init 被 402 `trial_phase_locked` 拦截，前端 chat 页 init catch 解析 402 弹 TrialLimitModal**（与超 10 轮 `trial_limit_reached` 同一购买/升级引导层）。**手动兜底按钮维持 11 轮门槛**：满 `CONCLUSION_MIN_USER_TURNS`(11) 轮且**当前无待表态卡**（从未出过，或「再聊聊」后旧卡折叠——rejected 状态下按钮恢复显示，防止 retrigger/模型重新出卡双双失效后用户无入口）时，前端输入框上方显示「对话结束无法进行下一步?点击这里」按钮（首次冒泡长出动画 + 闲置 10s/60s 抖动提醒各一次封顶 2 次；**点击后冻结输入框与发送、复用「正在生成结论卡片」提示条，防止生成期间新请求进入**）→ `POST /simple-chat/conclusion/request` 直接走 `check_dimension_complete(skip_completion_check=True)` 生成草案置 pending（与 retrigger 同链路；已有 pending/confirmed 幂等返回；<11 轮 400；生成失败 503 前端「生成失败，点击重试」不静默）。试用码 10 轮硬顶（第 11 条 402）天然使按钮对试用用户不可见。rejected 后 retrigger=3 轮不变。关键文件：`simple_chat_routes.py`（`request_conclusion_card` + path A 出卡链路）、`app/domain/conclusion_card_payload.py`（状态注入）、前端 `components/explore/ConclusionRequestButton.tsx` + chat 页接入；测试 `test/backend/test_conclusion_min_turns_gate.py`。
- **关键文件**：`app/utils/trial_codes.py`（发放/补发/计数/`get_started_trial_code`）、`app/utils/simple_activation_manager.py`（`consume_for_trial_upgrade`/`upgrade_to_full`）、`app/api/v1/simple_chat_routes.py`（`_assert_trial_phase_allowed` / `_assert_trial_message_allowed` / `_peek_trial_phase_lock`）、`GET /simple-auth/my-codes`（我的激活码列表）、`POST /simple-auth/codes/apply-to-trial` + `GET /simple-auth/upgrade-context`（消耗升级）、`GET/PATCH /simple-auth/preferences`（用户偏好）。
- **消耗升级溯源与去向展示（2026-08-08 起）**：试用码记录新增 `upgraded_from_code` 字段（consume 升级时由 `consume_for_trial_upgrade` 写入，存量数据用 `scripts/backfill_upgraded_from_code.py --dry-run` 预演后回填）。`/dashboard/codes` 页为双 tab 结构（2026-08-15 起，支持 `?tab=orders` 定位）：tab「激活码」= owner 视角激活码模块（被消耗码无 owner 天然不出现），对升级来的码显示「付费升级」badge（点击展开才显示来源付费码），标题右侧有「购买激活码」按钮；tab「订单记录」= 订单列表（`components/dashboard/OrdersSection.tsx`，原 `/dashboard/orders` 页主体，`/dashboard/orders` 已改为重定向）。**2026-08-24 起职责拆分**：订单 tab 只保留订单详情 + 本单交付的激活码列表（纯码值可复制，不含去向）；码的去向/使用情况统一收敛到激活码 tab 底部的「我购买的激活码」**平铺**列表（不再按订单分组，按创建时间倒序；每码去向 5 态：未绑定/已绑定自己/已绑定他人/已用于升级试用码 XXXX/已作废退款 + 报告状态），`my-purchased-codes` 接口透传 `source_order_id`/`consumed_into` 并联查订单金额（订单字段当前前端未展示，保留供追溯）。Admin 订单详情（`GET /admin/payment/orders/{id}`）新增 `delivered_codes[].destination_type/destination_detail`（去向判定，admin 不脱敏）。计划文档：`tasks/consumed-code-destination-plan.md`。
- **延期体系（ADR-0016，2026-08-08 起）**：完整码首次过期当天，每日扫描 job（`activation_expiry_scan`，默认 10:00）给激活人发邮件+站内信送**免费 7 天续期**（每码一次，`free_renewal_offered_at`/`free_renewal_claimed_at` 幂等；存量已过期码首次扫描全量补发）；链接 → `/dashboard/codes?free_renewal=<code>` 弹窗手动领取，不限时、领取后从当天起 +7 天。付费续期统一 **9.9 元 / 7 天**（`RENEWAL_PRICE=990`/`RENEWAL_DAYS=7`，旧 20 元/90 天下线仅历史订单展示），与免费解耦、不限次、active/expired 均可买、不可退。关键文件：`app/services/activation_expiry_scan.py`、`POST /simple-auth/codes/free-renewal/claim`、前端 `FreeRenewalClaimModal`。
- **多码展示口径（2026-08-08 起）**：交付码等价、不区分用途——订单页（`dashboard/orders`）、支付结果页、PurchaseModal 成功视图对多码套餐一律平级列出全部码（`激活码（共 N 个）`，meta.codes 并集 delivered_code/gift_codes 去重），单码订单才保留「你的激活码」单独展示；弹窗消耗升级后通过 `onUpgraded(trialCode, consumedCode)` 把已消耗码从展示列表排除。前端请求被取消（页面刷新/导航，`isRequestCanceled`，含 axios ERR_CANCELED/“Request aborted”）一律静默忽略，不作为错误展示。
- **团队分析报告提示（2026-08-10 起）**：年度套餐（3 人团队码）交付时引导用户邮件申请团队分析报告——后端 `_deliver_order` 随单发站内信（`type=team_analysis_notice`，交付幂等故仅一次）并在交付邮件附同一文案（`payment_service._team_analysis_notice()` 动态生成，邮箱独占一行避免纯文本邮件误识别链接）；前端支付结果页交付后弹 `TeamAnalysisNoticeModal`（每单一次，关闭后再弹消耗升级避免叠加），PurchaseModal 成功视图内嵌 `TeamAnalysisNoticeBox`。**团队分析页占位（2026-08-24 起）**：团队报告解析能力暂未开放，`/dashboard/team-analysis` 页（page.tsx）已替换为「开发中」占位（展示 TEAM_ANALYSIS_EMAIL 联系邮箱），原完整实现保留在同目录 `page.impl.tsx`，上线时用它替换 page.tsx 即可；侧边栏入口保留。
- **团队分析联系邮箱（ADR-0018，2026-08-16 起）**：环境变量 `TEAM_ANALYSIS_EMAIL`（默认 soulhappylab@163.com，2026-08-19 起发件邮箱从 163 切换为 Outlook）统一管理——后端交付邮件/站内信经 `_team_analysis_notice()` 使用；前端经 `GET /payment/products` 响应字段 `team_analysis_email` 下发（`lib/api/payment.ts` 的 `getTeamAnalysisEmail()` 模块级缓存 + `TEAM_ANALYSIS_EMAIL_FALLBACK` 兑底）。

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
- `/api/v1/export/*` - 导出（`POST /export/report-pdf/{id}` 有完成度门控：五阶段未完成一律 409，admin 也不例外，2026-08-07 起；admin 豁免仅限审核状态阻塞。审核计时锚点（2026-08-23 起前移）：rumination v4 终选提交（`final-selection/submit`）成功即 `start_review`（随机 3~24h）+ 后台预生成 markdown，进报告页（`my-report-id`）的 `_ensure_review_started` 保留作存量 not_started 懒触发兜底；报告批复通过瞬间——人工 `POST /admin/reports/{id}/approve` 或超时自动批复 job——后台兜底再生成报告 markdown（`report_review_service.kick_report_generation`，2026-08-10 起）。用户侧「生成报告」按钮已于 2026-08-23 下线：approved 且无缓存/生成失败时改为警示块（失败→「重新尝试生成」+「申请复核」，无缓存→「报告异常」+「申请复核」），下载按钮带「下载中…」态（`useReportPdfDownload.downloading`）。**报告复核体系（2026-08-18 起，`tasks/report-review-plan.md`）**：用户侧重新生成已下线（按钮 + `_MAX_USER_REGEN` + `report_regen_count` 计数全删），改「申请复核」——`POST /export/report-recheck/{id}` 分类必选（`content_issue` 建复核单 + 双写 Feedback 工单 / `download_issue` 仅进 Feedback 通道同「反馈 bug」；每报告每天限 1 次、有未关闭单 409）；复核单存 record.json `recheck_requests`（append-only，状态机 pending→regenerating→pending_confirm→done/rejected，LLM 失败退回 pending 可重试）；重新生成写 staging `report_markdown.staging.md`（PDF 即时渲染故用户始终看旧版，报告不锁定只加提示条），admin 确认发布才原子替换正式缓存（旧版留 `.bak`）+ 站内信 + 邮件；admin 端点 `/admin/reports/{id}/recheck/*`（regenerate / staging-pdf / publish / reject 必填理由），「重新生成」按钮仅随未关闭复核单出现、期间可反复生成、关闭即消失，后端 force 保留供运维脚本；关键文件 `app/services/report_recheck_service.py`、`report_pdf_service` staging 方法、前端 `components/explore/ReportRecheckModal.tsx` + `components/admin/ReportRecheckPanel.tsx`）；三条生成路径（审核预生成/批复/手动）共用 `report_pdf_service` 单轨锁，同报告不并发。PDF 页面顺序（2026-08-16 起）：封面 → 阅读指南 → 报告内容总览（原「报告模块总览」，已去掉日期/版本/密级档案头）→ 其余章节（`_markdown_to_pdf` 在第一个分页符处切开正文插入总览页，找不到分页符降级为旧顺序）；正文表格有行级分页保护（`.content tr/th/td { break-inside: avoid }`，防同一行左右格被拦腰分到两页）；「开篇：职业角色」章由后处理规范化（ADR-0017：`_normalize_role_opener` 保证 H2 标题必有，渲染侧 `_markdown_to_pdf` 也跑、存量缓存下载即生效；描述 >800 字时 `_compress_role` LLM 压缩至 600-750 字，仅生成侧，验收失败回退原文））。**渲染引擎双轨（ADR-0019，2026-08-20 起）**：`RENDER_ENGINE=weasyprint`（默认）| `xunlu`（`src/report-renderer/` 精简 Node 渲染器，抽自只读母版 `report/xunlu`，子进程调用，契约 markdown→bytes 不变），分流点 `_markdown_to_pdf`，用户下载与 admin staging 预览同时生效；xunlu 引擎自带存量方言归一化（旧式分页符/`*` 列表/h5-h6/`##`·`###` 章节标题提升/动态角色名识别）；xunlu 分页为 JS 估算分页（`markdown-parser.ts` paginateReport，2026-08-31 已按 report.css 校准行高/每行字数常数：表格 15.5px/行、每格字数按 694px 实宽÷列数、段落 53 字/行），跨页拆块（段落/列表/表格）打 splitGroup 同源标记，rebalanceSectionEnd 合并尾页时按标记拼回——修复同页出现「表格中间断开+重复表头/段落拦腰截断」）
- `/api/v1/admin/*` - 管理（含 `/admin/coupons` 折扣券、`/admin/payment/orders` 订单与退款、`/admin/consultations` 咨询管理、`/admin/users` 用户管理：deleted 筛选 / `restore-deletion` 注销恢复 / PATCH status 对已注销用户启用会 400 拦截；`/admin/reports` 列表含 `report_unlocked` 字段，`completed_steps` 已修 v4 口径：rumination locked 计入；`POST /admin/render-pdf-from-md` md 直渲 PDF 与 `GET /admin/reports/{id}/render-pdf` 报告重渲染——均 super admin、强制走 xunlu 渲染器（ADR-0019）；`GET/POST /admin/report-render-config` 渲染引擎运行时配置（报告页单选即时生效）；`GET /admin/reports/generating` 生成中列表（前端恢复按钮态）；admin 列表「下载PDF」为纯渲染下载（md 不存在不隐式触发 LLM 生成）；运维脚本 `scripts/rerender_report.sh <激活码>`）
- `/api/v1/payment/*` - 支付（用户侧：products / coupons/validate / orders；`/payment/notify/alipay` 为渠道回调，无登录鉴权）
- `/api/v1/analytics/*` - 埋点（点赞、报告生成、`POST /analytics/event` 通用事件上报：PV 不依赖登录，auth_active 仅服务端内部写；漏斗统计 `GET /admin/analytics/funnel`，ADR-0013）
  - LLM token 用量统计（2026-08-16 起）：`GET /admin/analytics/llm-usage/summary`（总量+分场景+按天+峰谷）/ `users`（按用户聚合）/ `calls`（单次调用明细），数据源 `llm_usage_logs` 表（调用粒度，落库时按当时费率表+峰谷定价存死 cost_yuan）。采集在 `OpenAIProvider.chat/chat_stream` 出口统一埋点，归属（user_id/scene/activation_code）经 `core/llmapi/usage_context.py` contextvar 在各入口设置；费率表 `app/utils/llm_pricing.py`（内置 DeepSeek 8-17 前后两套价，`LLM_PRICING_JSON` 可覆盖，`LLM_PEAK_HOURS` 配峰时）；前端 `components/admin/LlmUsagePanel.tsx` 并入 `/admin/analytics` 页
- `/api/v1/consultation/*` - 报告解读咨询（用户侧：my-reports / bookings / survey；admin `POST /admin/consultations/{id}/schedule` 确定时间后发站内信 `consultation_scheduled` 通知用户，admin_note 为内部备注不透出，2026-08-10 起；2026-09-01 起站内信/交付邮件入口统一为 `/dashboard/consultation` 列表页（新增 page.tsx），不透出 booking_id；问卷「选择报告」下拉框显示激活码而非 report_id）

> **用户可见标识约定（2026-09-01 起）**：一切面向用户的文案（站内信/邮件/页面）中，报告的用户可见标识一律用**激活码**（报告↔激活码 1:1），不写内部 report_id/booking_id 等 UUID；report_id 仅保留在复核 Feedback 工单正文（admin 定位用）与后端日志。`notify_report_approved` 幂等去重同步改为按正文中的激活码匹配。
- `/api/v1/team-analysis/*` - 团队分析（candidates / 创建 / 列表 / 详情）

启动后端后访问 Swagger UI: http://localhost:8000/docs

## 安全注意事项

1. **密钥管理**: `SECRET_KEY` 和 API 密钥必须保密，不要提交到 Git
2. **密码加密**: 使用 bcrypt 存储密码哈希
3. **JWT 验证**: Token 有效期默认 60 分钟
4. **超级管理员**: 通过 `SUPER_ADMIN_USER_IDS` 或 `SUPER_ADMIN_EMAILS` 配置
5. **Debug 模式**: `DEBUG_MODE=True` 仅对超级管理员生效
6. **登录防爆破（2026-08-21 起）**: `AuthService.login` 按登录标识（email 小写/phone，**含不存在的账号**）进程内内存计数——1 小时滑动窗口 5 次失败锁 15 分钟（固定不续期、锁定期密码正确也拒绝、成功登录清零、重启失效）；锁定返回 HTTP 423 + detail JSON `{"type":"login_locked","retry_after_seconds":N}`（对齐试用 402 风格）；失败统一文案「邮箱/手机号或密码错误」防枚举（不存在的账号走假哈希校验对齐耗时）。关键文件：`app/services/auth_service.py`（`_login_failures` / `LoginLockedError` / `LOGIN_FAIL_*` 常量）、`app/api/v1/auth.py` 423 分支、前端 `AuthModal.tsx` 倒计时；测试 `test/backend/test_login_lockout.py`
7. **用户自助修改密码（2026-08-24 起）**: `POST /auth/password/change`（需登录，旧密码+新密码，新密码 ≥6 位且不能与旧密码相同）→ `AuthService.change_password`：旧密码错误**复用登录锁定机制**（同一 lock_key、失败计数与登录互通，423 口径一致）；成功后撤销该用户全部 refresh token（`revoked_reason=password_changed`，含当前会话，全部强制下线）+ 清 refresh cookie + 站内信（`type=password_changed`）+ 邮件通知（`EmailService.send_password_changed_notice`，发送失败不阻断）。前端入口：个人空间 `/dashboard/settings`「修改密码」区块（423 倒计时与 AuthModal 同口径；成功后 toast 提示并 logout 跳首页引导重新登录）；测试 `test/backend/test_change_password.py`
8. **Refresh 轮换宽限期（2026-08-25 起）**: `REFRESH_TOKEN_ROTATE_GRACE_SECONDS`（默认 10s）——已轮换旧 refresh token 在宽限期内被重放视为**并发刷新**（多标签页/流式与轮询同时 401），照常换发不撤族；宽限窗外维持 `reuse_detected` 撤销整族的防盗语义；窗口锚定首次轮换时间（重放不续期，rotation 分支仅在 `revoked_at is None` 时写）。前端所有 refresh 统一收敛到 `apiClient.refreshAccessToken()`（single-flight，`client.ts`），聊天页流式/ruminationStepOpening/ruminationV4Api 的 401 处理均走该入口，不再自行调 `authApi.refresh()`。另修复 SQLite 下 `refresh_access_token` 对 `rec.expires_at`（naive datetime）与 aware now 比较抛 TypeError 致 refresh 500 的问题（按 UTC 转 aware 再比较）。测试 `test/backend/test_refresh_token_rotation.py`

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
- `CONTEXT.md` - 领域术语（探索流程 + 支付与商业化：试用/完整码、激活码（季度套餐/年度套餐）、折扣券、报告审核、团队分析）
- `docs/adr/` - 架构决策记录（0005 双线支付 / 0006-0007 会员体系保留 / 0008 套餐与试用码 / 0009 报告审核自动批复 / 0010 码双角色与报告授权 / 0011 存储演进路线：SQLite 全量入库→条件触发 PG / 0012 品牌更名 OpenLife / 0013 统计看板：事件时间口径漏斗 + 埋点业务同库 / 0014 套餐全量未绑定码交付 + 消耗升级 + 年度 ¥159 / 0016 延期改版：首过免费送 7 天 + 付费 9.9 元/7 天 / 0017 报告后处理修正管线：一次生成 + 按章节分步修正 / 0018 套餐码支付成功起算 + 团队分析邮箱变量化 / 0019 报告渲染接入 xunlu 精简渲染器：子进程 + RENDER_ENGINE 开关共存）
- `tasks/payment-module-plan.md` - 支付模块实施计划（P1 折扣券 ✅ / P2a 支付宝 ✅ / P2b 微信待做）
- `tasks/packages-trial-plan.md` - 套餐与试用体系实施计划（P-A~P-E 全部 ✅）
- `wiki/开发文档/0720-支付模块.md` - 支付配置操作手册（支付宝平台/.env/沙箱联调）
- `wiki/开发文档/0726-激活码schema迁移脚本说明.md` - 存量激活码字段补全迁移（影响/风险/执行 SOP/回滚）
- `wiki/开发文档/0731-迁移计划.md` - 新生产服务器迁移计划（v1.5.1→HEAD 变化总览 + openlife.beyondego.me 切流步骤）
- `wiki/开发文档/0821-迁移计划-v1.5.1-to-v1.6.0.md` - **生产迁移完整手册（v1.5.1→v1.6.0，0731 版的完整替代）**：12 个 migration（007→019）/ xunlu 渲染引擎 / 延期改版 / LLM key 隔离与 sync_llm_db_config / SMTP 163 授权码 / 逐步 todo list + 验收与回滚
- `wiki/开发文档/0821-测试环境升级指引-v1.6.0.md` - 测试服务器维护人员用：测试/生产数据独立不同步、**无需数据迁移**，只需代码升级 v1.6.0 + 依赖 + 测试库 007→019 + 激活码 schema 脚本（含测试数据根）+ .env 测试口径核对
- `wiki/开发文档/0821-nginx-openlife-prod.md` - openlife.beyondego.me 新生产站 1Panel/nginx 配置指南（0705 xunlu 版的改写：建站+TLS+双反代+维护模式三段配置+旧站 301+验证）
- `wiki/开发文档/0812-报告配色配置说明.md` - 报告 PDF 配色配置（只改 `app/static/styles/report_theme.json` + 重启后端；PDF 下载时即时渲染故无需重生成报告）
- `wiki/开发文档/0823-全部场景切deepseek-pro思维链与max_tokens整治.md` - 全部场景统一 v4-pro+思维链（chat 从 flash 切 pro）+ max_tokens 额度整治；含结论卡/复读/截断三类历史问题根因分析（GitHub #84，关联 #82）
- `wiki/开发文档/0823-提交即审核与报告页异常态.md` - rumination v4 终选提交即开始审核计时+预生成（锚点分析）、「生成报告」按钮下线、下载中/报告异常警示块（GitHub #83）

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

## 前端登录门控（AuthGate）

- **位置**: `src/frontend/components/layout/AuthGate.tsx`，挂在 `app/(main)/layout.tsx`；`app/profile/layout.tsx` 单独包一层（profile 在 (main) 组之外）。
- **公开页白名单**: `/`、`/about`、`/community`、`/verify-email`（隐私声明/用户协议是首页弹窗组件，随首页公开；`/auth/*`、`/account-recovery` 不经过 AuthGate）。其余页面一律要求登录。
- **未登录行为**: 直接 `router.replace('/')` 退回首页并弹全局登录框（`authModalStore`），不渲染受保护内容；API 401 且 refresh 失败时同样统一退回首页。
- **Dashboard 侧边栏（2026-08-15 起）**：「报告」列表页下线（`/dashboard/report` 重定向到 `/dashboard`，报告入口改为当前进度页旅程卡的「查看报告」按钮与报告节点），「订单记录」并入「我的激活码」页 tab（`/dashboard/orders` 重定向到 `/dashboard/codes?tab=orders`）；NAV_ITEMS 现为 7 项：当前进度/使用指南/帮助中心/回收站/我的激活码/团队分析/设置。报告已解锁（`report_unlocked`）的激活码进入 `/explore/chat/[phase]` 为只读历史模式（隐藏输入、顶部提示条引导查看报告）。
- **会话校验**: 每次页面加载对已登录用户调一次 `/auth/me` 校验 token 有效性（拦截器自动尝试 refresh）。
- **账户恢复会话（recoveryMode）**: 已注销账户登录得到受限 token（`deleted_recovery`，30 分钟），登录时在 `authStore` 置 `recoveryMode=true`（持久化）。此期间：AuthGate 跳过 `/auth/me` 校验并把用户导向 `/account-recovery`（唯一可停留页面）；axios 401 拦截器不做 refresh/logout/弹登录框（由恢复页自行处理 401）；恢复页加载时自动发送一次邮箱验证码。恢复成功（`POST /auth/account/recovery/confirm`）或 logout 时清回 `false`。
- **注意**: `authStore._hasHydrated` 不能放在 `onRehydrateStorage` 回调里设置——同步 localStorage 会让回调在 `create()` 期间执行，TDZ 引用 `useAuthStore` 报错；当前实现用 `persist.hasHydrated()` / `persist.onFinishHydration` 在模块加载后设置。

## 注意事项

1. **环境变量冲突**: `start.sh` 会自动清理冲突的环境变量，确保只加载项目 `.env`
2. **前端 API 代理**: 开发模式下，前端通过 `next.config.js` 的 rewrites 代理到后端
3. **对话记录存储**: 存储在 `data/conversations/{session_id}/` 目录下
4. **知识库文件**: CSV 文件位于项目根目录，Docker 部署时通过 volume 挂载
