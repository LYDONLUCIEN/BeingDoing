# 当前架构

基线为 v1.8.0 + clean，以下描述当前实现，不代表计划中的迁移已经发生。为什么这样设计、替代了什么、约束何时退出，见 [架构与开发决策](DECISIONS.md)。

```text
Next.js 页面 → lib/api（访问令牌、刷新、SSE）
                 ↓ /api/v1
FastAPI main.py → 路由与权限边界 → services / core / domain
                 ↓                         ↓
SQLite（账户、订单、券、退款、统计）   JSON（激活码、探索、报告、对话）
                                           ↓
                               report_pdf_service（Markdown 缓存）
                                           ↓ 子进程
                          src/report-renderer → Chrome → PDF bytes
```

## 模块地图

| 模块 | 职责与入口 |
| --- | --- |
| `src/backend/app/main.py` | 路由、中间件、定时任务注册；检查公开面先从此处开始 |
| `api/security.py` | 旧会话/回答归属、管理员和点赞所属探索校验 |
| `api/v1/simple_chat/`、`simple_chat_routes.py` | 前四阶段写接口与历史读取；拒绝旧沉淀写请求。多个模块仍通过兼容入口互引，不能只凭静态导入删除 |
| `api/v1/rumination_v4_routes.py`、`services/rumination_v4_service.py` | 当前唯一沉淀运行链路，组合创建/讨论/用户卡/独立判断/终选；无 A/B 分流 |
| `utils/rumination_inputs.py` | 四阶段结论输入提取，按确认卡、anchor、prior_text 优先级读取 |
| `utils/legacy_rumination_export.py` | 仅为历史数据导出读取旧格式，不生成/更新旧状态、不向 v4 转换 |
| `core/agent/` | 仍挂载的旧 LangGraph 链路，与 simple-chat 共存 |
| `services/auth_service.py`、`core/database/user_db.py` | 登录、令牌轮换、找回密码、密码重置事务 |
| `utils/simple_activation_manager.py` | 激活码状态、归属、升级、数据根选择 |
| `utils/report_registry.py` | 报告记录和阶段/线程索引；record.json 为报告权威源 |
| `services/payment_service.py`、`refund_service.py`、`coupon_service.py` | 交易交付、退款审批/执行、券名额 |
| `services/user_filters/` | 统一后台筛选，SQL 与文件数据筛选分层 |
| `domain/prompts/`、`domain/` | 提示词与领域定义；v4 prompt 另有专用模块 |
| `src/frontend/lib/api/`、`stores/` | API 契约与状态；所有 refresh 收敛到 client 的 single-flight |
| `src/frontend/components/common/SafeMarkdownPreview.tsx` | 不可信 Markdown 的统一清洗边界 |
| `src/report-renderer/` | 唯一报告 PDF 渲染器，dist 随仓库发布，设计母版只读 |

## 数据边界

SQLite 存账户、订单、退款、券/核销、会员预留数据及统计；`data/simple/activations.json` 存激活码，`data/simple/reports/{report_id}/record.json` 存报告状态。沙箱根由激活码记录确定，不能拼接用户提交的任意路径。旧会话还有 `data/conversations/{session_id}` 等存储。

迁移历史在 `src/backend/alembic/versions/`。ADR-0011 的 JSON → SQLite → 条件触发 PostgreSQL 是路线，当前仍有 DB/文件双写、进程内锁与缓存；不要直接增加多 worker 来扩容。文件锁能否跨进程有效取决于所用锁和共享文件系统，不能把所有 `.lock` 一概称为仅单进程锁；真正需要单实例的还包括内存状态和跨存储事务缺口。

DB 与 data 必须来自一致快照。只恢复 app.db 会丢失报告/激活码关联，只恢复 data 会丢失账户与交易关系。恢复及新迁移均需在隔离副本演练。

## 适合下一步拆分的边界

优先保持外部契约稳定：把激活码/报告解析、退款权益核销、用户筛选数据读取各自收敛到明确服务接口。旧大路由的全面拆分、存储全量迁移和 Next 主版本升级分别验收；本次先统一已确认的安全边界，避免同时改变多个核心状态机。
