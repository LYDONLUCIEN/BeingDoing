# LLM 模型配置后台（Admin-Managed）

**完成日期**：2026-07-16
**分支**：rumination
**关联迁移**：alembic `009_llm_model_configs`

## 背景

原 LLM 配置完全依赖 `.env`（`LLM_PROVIDER`/`LLM_BASE_URL`/`LLM_MODEL`/`*_API_KEY`），切换模型需改环境变量并重启，且无法为不同用户分配不同 API key。

本次开发新增一个 admin 后台页面，可：
1. 配置多个 LLM 模型端点（provider/model/base_url/api_key）
2. 指定一个为**默认模型**
3. 为单个用户**绑定专属模型**（未绑定 → 走默认）
4. 内置**联通测试**：输入 prompt 看响应 + 延迟，或一键 ping

**关键决策**：DB 为主、`.env` 兜底。迁移时把当前 `.env` 值 seed 为一条默认记录。

## 架构

```
Admin UI (model-config 页)
    ↓ /api/v1/admin/model-configs/*
Admin Router (CRUD + test + user-bindings)  ── 写后同步 invalidate_cache
    ↓
LLM Model Config 表 (DB, api_key Fernet 加密)
    ↓ 同步读 + 30s TTL 缓存
Resolver (DB-first, .env fallback)
    ↓ 被现有 factory 透明调用
factory.get_default_llm_provider() / get_llm_provider_for_vip()  ← 签名不变
    ↓
8+ 个 chat 调用点（simple_chat_routes 等）—— 无需改动
```

核心约束：现有 factory 是同步函数、被多处同步调用，因此 resolver 使用**同步读路径**（独立 sync engine）+ `threading.Lock` 守护的内存快照，TTL 30s；admin 写操作后立即 `invalidate_cache()` 让更改即时生效。DB 异常时保留上次快照，最坏回退 `.env`。

## 数据库

### 新增表

**`llm_model_configs`** — 一条 = 一个可用模型端点
| 字段 | 类型 | 说明 |
|---|---|---|
| id | String(32) PK | uuid4().hex |
| name | String(120) | 管理员可读标签 |
| provider | String(32) | openai / deepseek / kimi / qwen |
| model | String(128) | 模型名 |
| base_url | String(255) | 可选 |
| api_key_enc | Text | Fernet 密文，绝不存明文 |
| is_default | Boolean | 默认模型（admin 层保证唯一） |
| enabled | Boolean | 启用开关 |
| notes | Text | 备注 |
| created_at / updated_at | DateTime | 时间戳 |

**`user_llm_model_configs`** — 用户 → 模型 绑定
| 字段 | 类型 | 说明 |
|---|---|---|
| id | String(32) PK | uuid4().hex |
| user_id | String(36) FK→users.id CASCADE | 每用户唯一 |
| config_id | String(32) FK→llm_model_configs.id CASCADE | |
| created_at / updated_at | DateTime | |

约束：`UniqueConstraint("user_id", name="uq_user_llm_config_user")` 保证一人一绑定。

### 迁移

`src/backend/alembic/versions/009_llm_model_configs.py`（`down_revision = "008_rumination_ab"`）
- 建两表
- 从当前 `.env` 读出 `LLM_PROVIDER/LLM_MODEL/LLM_BASE_URL/(OPENAI|DEEPSEEK|...)_API_KEY`，**seed 一条默认记录**：
  - `id = "envseed0000000000000000000000"`（确定性 32 字符）
  - `is_default=True, enabled=True`
  - api_key 用 Fernet 加密
  - 幂等保护：`SELECT 1 WHERE id='envseed...'` 避免重复

## API 端点

所有端点仅超级管理员可访问（`is_super_admin_user`），所有写操作末尾 `resolver.invalidate_cache()`。
统一响应 `{code:200, message, data}`。

| Method | Path | 功能 |
|---|---|---|
| GET | `/api/v1/admin/model-configs` | 列表（api_key 掩码） |
| POST | `/api/v1/admin/model-configs` | 新建 |
| GET | `/api/v1/admin/model-configs/{id}?reveal=true` | 详情（reveal=true 返明文） |
| PATCH | `/api/v1/admin/model-configs/{id}` | 更新（api_key 为 None=不变；""=清空） |
| DELETE | `/api/v1/admin/model-configs/{id}` | 删除（拒绝删除唯一启用的默认） |
| POST | `/api/v1/admin/model-configs/{id}/set-default` | 设为默认（清其他） |
| POST | `/api/v1/admin/model-configs/{id}/test` | **联通测试** |
| GET | `/api/v1/admin/user-bindings` | 用户绑定列表 |
| POST | `/api/v1/admin/user-bindings` | 绑定/更新（upsert） |
| DELETE | `/api/v1/admin/user-bindings/{user_id}` | 解绑 |

### 联通测试

请求：`{prompt: "ping", temperature: 0.2, max_tokens: 64}`
响应：`{success, content, model, latency_ms, error?}`

实现：临时用数据库中的配置构造 `OpenAIProvider`，直接 `await provider.chat(...)`，**不经过 resolver/缓存**。失败时返回 `success=false + error`，不抛异常。

## 加密

`src/backend/app/utils/llm_config_crypto.py`
- Fernet 对称加密
- 密钥派生：`SHA-256(settings.MODEL_CONFIG_ENC_KEY or settings.SECRET_KEY)` → url-safe base64
- 新增 settings 字段 `MODEL_CONFIG_ENC_KEY: Optional[str] = None`，缺省回退 `SECRET_KEY`，无需新增 env 即可工作
- 导出 `encrypt / decrypt / mask`
- `decrypt` 失败返回 None 不抛异常，避免日志泄漏
- `mask`：`sk-1234abcd → sk-••••••••def`

**注意**：轮换 `MODEL_CONFIG_ENC_KEY` 会让历史密文不可解密，需在 admin 重新填 api_key。

## Resolver（缓存层）

`src/backend/app/core/llmapi/resolver.py`

关键函数：
- `get_default_config()` — DB 中 `is_default=True and enabled=True`；DB 空/异常 → `.env` 派生
- `get_config_for_user(user_id)` — 有绑定走绑定，否则默认；`user_id=None` 直接返回默认
- `get_config_for_vip(vip_level)` — 桥接 VIP 路由（当前仍走 `.env`，保留 VIP1/VIP2 原行为）
- `invalidate_cache()` — admin 写后调用

缓存策略：
- `_snapshot_lock = threading.Lock()`，`_snapshot` 内存对象（default + by_user map）
- TTL **30s**，过期 `_refresh_snapshot_blocking()` 同步 SELECT
- 同步 engine 惰性创建（`sqlite+aiosqlite → sqlite`、`postgresql+asyncpg → postgresql+psycopg2`）
- 失败保留上次快照；快照空则 `.env` 兜底

## Factory 改造（签名不变）

`src/backend/app/core/llmapi/factory.py`
- `get_default_llm_provider(vip_level=None)`：
  - 有 vip_level（1/2）→ 走原 VIP 路径
  - 无 vip_level → 先查 resolver；resolver 异常时 `except: create_llm_provider()` 完全回退
- `get_llm_provider_for_vip` 保持不变
- `_get_vip_provider_config` 保留（env 兜底 + resolver 的 env seed 都依赖它）

**8+ 个 chat 调用点零改动**（simple_chat_routes.py 等）。

## 前端

### 新页面 `src/frontend/app/(main)/admin/model-config/page.tsx`

客户端组件，仿 `system/page.tsx` 风格。四个区块：
1. **配置列表**：表格 — 名称、provider、model、API Key（掩码 + 查看按钮）、状态（默认/启用徽章）、操作（设默认 / 测试 / 编辑 / 删除）
2. **编辑/新建 Modal**：name、provider 下拉、model、base_url、api_key（password 输入，编辑时留空=不修改）、enabled、is_default、notes
3. **联通测试 Modal**：textarea 输入 prompt + "发送测试" 按钮 + "一键 ping" 按钮，展示 success/content/latency_ms/error
4. **用户绑定区**：填 user_id + 选目标 config → 绑定；列表展示当前绑定，支持解绑

### 客户端 API `src/frontend/lib/api/admin.ts`

追加类型与函数：
- `AdminModelConfig` / `ModelConfigTestResult` / `AdminUserLlmBinding` / `LlmProvider`
- `fetchAdminModelConfigs` / `createAdminModelConfig` / `updateAdminModelConfig` / `deleteAdminModelConfig` / `setAdminDefaultModelConfig` / `revealAdminModelConfigKey` / `testAdminModelConfig`
- `fetchAdminUserLlmBindings` / `bindAdminUserLlm` / `unbindAdminUserLlm`

### 导航

`src/frontend/app/(main)/admin/layout.tsx` 的 `ADMIN_NAV_ITEMS` 在"系统设置"前插入：
```ts
{ path: '/admin/model-config', icon: Cpu, label: 'LLM 模型配置' },
```

## 文件清单

**新增（6）：**
- `src/backend/app/models/llm_model_config.py`
- `src/backend/app/utils/llm_config_crypto.py`
- `src/backend/app/core/llmapi/resolver.py`
- `src/backend/app/api/v1/admin_model_config.py`
- `src/backend/alembic/versions/009_llm_model_configs.py`
- `src/frontend/app/(main)/admin/model-config/page.tsx`

**修改（7）：**
- `src/backend/app/config/settings.py` — 新增 `MODEL_CONFIG_ENC_KEY`
- `src/backend/app/models/__init__.py` — 注册新模型
- `src/backend/alembic/env.py` — import 新模型
- `src/backend/app/core/llmapi/factory.py` — `get_default_llm_provider` 接入 resolver
- `src/backend/app/main.py` — 挂载 router
- `src/frontend/app/(main)/admin/layout.tsx` — 导航条加入口
- `src/frontend/lib/api/admin.ts` — 追加客户端函数

## 验证

| 项 | 结果 |
|---|---|
| Crypto round-trip（`sk-test-12345`） | ✅ 加解密一致，`mask → sk-••••••••def` |
| `alembic upgrade head` | ✅ 008 → 009 |
| 表结构 + seed 行 | ✅ 两表字段齐全；seed `deepseek / deepseek-v4-pro / is_default=1 / api_key_enc长度=140` |
| 后端 import + router 注册 | ✅ `/api/v1/admin/model-configs` 及子路由全部注册 |
| resolver 读 DB 默认 | ✅ `source=db, provider=deepseek, has_key=True` |
| `get_config_for_user(None)` | ✅ 回退默认 |
| 前端 TypeScript 类型检查 | ✅ 无报错 |

## 使用说明

1. `./start.sh restart backend` 重启后端
2. 浏览器访问 `/admin/model-config`
3. **配置新模型**：右上"+ 新建配置" → 填 name/provider/model/base_url/api_key → 保存
4. **设默认**：列表点"设默认"
5. **联通测试**：点"测试" → 输入 prompt 或"一键 ping" → 查看响应/延迟
6. **用户绑定专属模型**：从"用户管理"页复制 `user_id`，在"用户→模型 绑定"区填入 + 选目标模型 → 绑定。未绑定的用户走默认模型

## 风险与注意

- **同步 factory + 异步 DB**：resolver 用独立 sync engine + lock + 30s TTL，热路径仅 dict 查询；admin 写后主动 invalidate。
- **密钥轮换**：轮换 `MODEL_CONFIG_ENC_KEY` 会让历史密文不可解密；迁移注释已说明，需在 admin 重新填 api_key。
- **唯一默认并发竞争**：set-default 在单事务内 `UPDATE SET is_default=false` → `UPDATE target SET is_default=true`。
- **VIP 路由**：`get_config_for_vip` 当前仍走 `.env`（保留 VIP1=DeepSeek / VIP2=Kimi|Qwen 原行为），将来若要按 VIP 分流再扩展。
- **chat 调用点 user_id 缺失**：`get_config_for_user(None)` 直接返回默认；用户绑定通过 resolver 的 by_user map 自动生效，无需改 chat 调用点。
