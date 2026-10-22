# BeingDoing 现行开发指南

本页维护当前开发环境、启动方式和工程约束。过去的设计、事故与部署过程保存在 [Wiki 历史资料库](../wiki/README.md)，不从历史文件恢复已被替代的命令或规则。

**已有 dev／prod 服务器的更新和重启请用 [服务器操作手册](OPERATIONS.md)**，涵盖配置选择、依赖安装、存量库迁移、DB／data 一致备份与回滚。下方空库初始化只用于新本地数据库，不能代替服务器升级。

## 独立环境

本次验证使用 Python 3.12.14。旧文 py310 指格式器目标，不是完整依赖矩阵已经在 Python 3.10 验证。Node 要求至少 20；使用项目锁文件安装，生产 Node 版本应与 CI 统一。

从仓库根目录：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r src/backend/requirements.lock
python -m pip install -r src/backend/requirements-dev.txt -c src/backend/requirements.lock
cd src/frontend
npm ci
```

`requirements.txt` 是核心依赖声明，`requirements.lock` 是 Python 3.12 的跨平台解析快照；Linux 实际启动仍须在目标机验收。开发工具在 requirements-dev，音频默认关闭，确需启用时额外安装 requirements-audio。刷新锁用 `uv pip compile src/backend/requirements.txt --python-version 3.12 --universal --output-file src/backend/requirements.lock`，再回归。

旧 requirements 缺少 aiofiles、email-validator、SQLAlchemy asyncio extra；passlib 1.7.4 对新 bcrypt 存在兼容问题，暂约束 bcrypt 4.0.x。密码哈希组件后续独立迁移，不能无验证升级。

## 本地启动

以下命令从仓库根目录执行，虚拟环境已激活。仅用于独立开发目录/数据库：

```bash
export APP_ENV=development
export DEBUG=False
export DATABASE_URL=sqlite+aiosqlite:///./local-dev.db
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
cd src/backend
```

**新建空库**不能直接 `alembic upgrade head`：历史迁移从已存在的用户库开始，003 会修改 `users`，没有创建完整基础表。本地空 SQLite 库先按当前 ORM 建表，再标记当前迁移版本；下列检查拒绝任何已有表的数据库，只有建表成功才执行 stamp：

```bash
python - <<'PY' && alembic stamp head && alembic current
import asyncio
from sqlalchemy import inspect
from app.models import Base, engine

async def initialize():
    try:
        if engine.url.get_backend_name() != "sqlite":
            raise RuntimeError("此流程仅用于本地空 SQLite 库")
        async with engine.begin() as conn:
            tables = await conn.run_sync(lambda sync: inspect(sync).get_table_names())
            if tables:
                raise RuntimeError("数据库已有表，拒绝初始化；存量库请走升级流程")
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()

asyncio.run(initialize())
PY
```

确认输出版本为 `026_refund_revoke_codes (head)` 后启动：

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

该空库流程不执行历史数据回填，也不执行 009 的环境密钥 seed。LLM 先按本地环境配置，确需 DB 配置时参考 `scripts/sync_llm_db_config.py`。后续新增迁移需同步这里的预期 head。

**存量库升级**先备份并在独立副本验证，核对 `alembic current` 后执行 `alembic upgrade head`。不要对存量库运行上述初始化或用 `stamp head` 跳过迁移；没有版本记录的历史库需要先核对真实表结构与迁移历史，不能推断其已到 head。更多迁移操作见 [迁移说明](../src/backend/alembic/README.md)。

另一终端在 src/frontend 执行 `npm run dev`。前端经 next.config.js 的 `/api` rewrites 连接默认 127.0.0.1:8000；需要改后端地址时设置 NEXT_PUBLIC_API_URL。API 结构见 `/docs` 和 `/openapi.json`。

`start.sh` 是既有 tmux/Conda 服务编排脚本，会加载环境配置、管理进程和构建；不是无副作用的开发安装器。先读 `./start.sh help` / 文件头命令说明，再在对应环境使用；本次未对真实服务器运行。

## 配置要点

- `.env` 不入库；`.env.dev/.env.test` 为已跟踪的环境覆盖，生产配置另行管理。settings 从根 `.env` 读取，环境变量优先；start.sh 还会按启动参数加载覆盖层。
- 生产必须显式 APP_ENV=production、DEBUG=False、随机 SECRET_KEY（至少 32 字符）、REFRESH_COOKIE_SECURE=True 和 HTTPS。可独立设置同等强度 REFRESH_TOKEN_SECRET_KEY。校验不通过会拒绝启动。
- 注册验证和邮件找回依赖 SMTP。假短信找回仅 development/test 可用；手机存量登录未删除。
- SUPER_ADMIN_USER_IDS/SUPER_ADMIN_EMAILS 决定真实管理员权限。user_type 只是运营标签。
- 模型场景由 admin_runtime_config 的 llm_scene_config 优先配置（chat/rumination/report/conclusion）；未覆盖场景走环境分流。vip_level 不是订阅资格，也不能当成固定模型名。
- 旧 Agent 默认模型可能走 llm_model_configs 的 DB-first 配置；换密钥时核对 `scripts/sync_llm_db_config.py --check`。不把测试密钥覆盖到生产。
- 报告只有 xunlu：REPORT_RENDERER_DIR、REPORT_RENDERER_NODE、CHROME_PATH、REPORT_RENDER_TIMEOUT；需要 Node 和 Chrome/Chromium。RENDER_ENGINE/report_render_config 已废弃。
- 汇率/模型费率、套餐价格及券有效期要核对当前环境和后台配置。年度套餐文档 ¥159 与 settings 默认 ¥128 存在冲突，见字段字典；本次不擅自调价。
- 应用只使用 ASGI `request.client` 作为限流来源。由 Uvicorn 信任明确的反向代理，代理应覆盖外来 X-Forwarded-For；不要将可信代理范围设成任意来源。

## 前端与探索约束

- 对话外壳使用 `.chat-shell-h` 提供 vh→dvh 回退；新 CSS 特性先有静态回退，内联 backdropFilter 带 WebkitBackdropFilter。浏览器能力用特性检测，不用 UA 猜测。
- 非哈希静态资源 URL 带 `?v=yyyymmdd`，更新资源递增版本；新图片优先 WebP，非首屏 lazy/async，原 PNG 母版保留。framer-motion 避免进入首屏 bundle。
- 登录门控在 AuthGate；未登录重定向首页并弹登录框；后端鉴权仍必须独立执行。所有 refresh 用 apiClient.refreshAccessToken；恢复注销账户的 recoveryMode 仅能访问恢复流程。
- authStore 的 hydration 标记通过 persist.hasHydrated/onFinishHydration 管理，不能在同步 onRehydrateStorage 中引用尚未初始化的 store。
- 前四阶段完成确认后锁定；沉淀走自己的终选流程。卡片与提示词规则见产品规则，不从历史原型恢复已淘汰协议。

## 检查

见 [TESTING.md](TESTING.md) 的命令、实际结果和基线失败清单。真实支付、SMTP、LLM、OSS、Chrome 与生产代理配置需要各自在测试环境验收；普通单测不应消耗真实服务或修改真实用户数据。

## 管理员测试中心

开发交付需同步固定用例与变更关联，运行目录覆盖检查。dev 开启、独立 worker、数据隔离及证据保留见 [测试中心指南](TEST_CENTER.md)。手机首页按屏幕尺寸调整布局和评价分页，首版不增加 UA 分流。

全量后端测试必须使用 `PYTHONPATH=src/backend:. .venv/bin/python -m test_agent.center.verify_backend --output output/backend-<唯一名称>`。该入口复制源码到临时目录，另建数据库与文件根，不继承业务凭据，禁止真实外部调用；不要直接在工作区启动全量 pytest，部分旧测试仍沿用默认数据库。证据目录禁止复用，保留首次运行记录。

固定测试统一维护于 [test_agent/catalog](../test_agent/catalog/README.md)。开发完成的定义包含可执行测试、独立输入/断言、测试目的、有效规范来源和变更登记；不能只完成业务代码后让 admin 补测试。历史用例默认保持可选，由 admin 决定核心或归档；读取新代码自动登记，保留人工修订和分类。文档推导的预期须先核对最新规则，代码当前行为不是自动正确的判据。

2026-10-14 追加适配约束：普通 PC 100% 缩放下的正常布局优先；不能因统一高度门槛改变整个工作台结构。验收同时覆盖宽度和高度、输入/按钮可见性、内部滚动与草稿保持；宽度不足时辅助面板允许用户主动展开为覆盖层。实现和真机/缩放验收分别记录，不能只用手机测试通过代表桌面无退化。


## 手机探索工作区（阶段二）

用户端按 768px 断点适配，不按 UA 分流：前四阶段的同一份会话侧栏在手机通过原生 dialog 抽屉打开，桌面常驻；沉淀手机端用「对话 / 组合与结论」面板和组合抽屉。消息、卡片、业务接口、素材仍复用原实现。admin 保持桌面优先。

`useChatViewport` 对支持 `visualViewport` 的浏览器跟随可视高度及偏移，CSS 保留 vh→dvh 回退；用户缩放时不强制校正。聊天输入字体至少 16px，发送/导航主要按钮保留触控空间。输入法组合状态和旧 WebKit 的 229 键码不会触发回车发送。手机聊天反馈入口放入顶栏菜单，避免浮动按钮遮挡输入区。

沉淀未发送文字和结论草稿由页级 `ConversationDraftProvider` 按激活码、组合、输入种类隔离；切换面板、组合及响应式重排可恢复，关闭/刷新页面清除，不持久化到 localStorage。服务端已保存原文变化时，草稿回到新原文。前四阶段既有服务端会话归属与流式禁用规则不变。

固定 UI 用例 `chat-ui`、`rumination-ui`、`account-mobile-ui` 验证真实页面与受控 API；注册、个人空间、报告和现有支付布局通过复用已有组件验收。没有增加微信支付或更换支付宝渠道。真机键盘/地址栏、真实支付返回和系统 PDF 保存仍须现场验证，自动化不会把它们标成已通过。
