# API 契约与权限入口

完整路径和请求结构以运行中的 `/openapi.json` 为准；FastAPI `/docs` 可交互查看。路由挂载在 `src/backend/app/main.py`，前端类型在 `src/frontend/lib/api/`。以下记录跨模块边界及 clean 的兼容变化。

## 鉴权约定

访问令牌经 Authorization Bearer 提交；刷新令牌由既有 cookie/refresh 接口处理。服务端从令牌解析 current_user，不能信任 body 中自报的用户 ID。缺失登录返回 401，无权限返回 403；资源不存在通常 404，非法路径标识 400。管理员由 SUPER_ADMIN_* 判断，不由 user_type 标签决定。

## clean 变更

| 接口 | 当前约束与变化 |
| --- | --- |
| POST /api/v1/simple-auth/activation | 仅超级管理员；注册试用、购买交付与认领使用原有专用路径 |
| GET /api/v1/chat-optimized/cache/stats；POST .../cache/clear | 仅超级管理员 |
| /api/v1/chat 的消息、SSE、历史、打断、引导与重总结；/chat-optimized 的 SSE、notes、answer-cards | 必须拥有对应 SQLite Session；在读取/写入或发出 SSE 前校验 |
| /api/v1/answers 的创建/列表/读取/更新 | 回答继承所属会话权限，不能仅凭 answer_id 修改 |
| POST /api/v1/export/generate | session 与请求 user_id 均须属于当前用户；返回随机 export_id、format、download_url，不再返回服务器 file_path |
| GET /api/v1/export/download?export_id=... | 只接受 export_ 加 32 位十六进制标识，按账户隔离；旧路径型 ID 需重新生成，跨用户查找 404 |
| /api/v1/analytics/like、unlike、likes、likes/check、likes/message/{id} | 均需登录；写入校验探索归属，读取/取消按用户隔离；message_id 不作权限凭证 |
| POST /api/v1/analytics/report-generated | 需登录并拥有探索；不是报告已生成的可信账务证据 |
| POST /api/v1/export/report-pdf/{id}?force=true | 仅管理员可强制重新生成；用户走 report-recheck |
| /api/v1/auth/password/reset 的 phone 接口 | development/test 以外返回 503，真实短信通道未实现 |
| POST /api/v1/simple-chat/thread/complete | 线程须已有结论卡（confirmed final 或 pending draft），否则 400 且不执行 bind/select_session（2026-10-13 串会话防护） |

点赞 trace 仅返回自己保存的快照/预览，不再根据客户端曾提交的 session_id 扫描磁盘；历史匿名点赞不自动认领。匿名 page_view 仍可经 /analytics/event 提交，服务端限定事件类型，保持 ADR-0013 口径。

## 沉淀 v3 退役（ADR-0025）

- 删除 `/simple-chat/rumination-progress`、`rumination-step-opening`、`rumination-step-opening-stream`、`rumination-table-submit`、`rumination-combo-conclusion`、`rumination-combo-guide`、`rumination-combo-matrix-submit`、`rumination-combo-matrix`、`rumination-neg-resolve`、`rumination-get-table` 路由，OpenAPI 不再发布，旧路径返回404。
- 通用 `/simple-chat/message`、`message/stream`、`init`、`thread/reopen`、`thread/complete`、`conclusion/request`、`thread/delete` 对已认证请求的 `phase=rumination` 返回410，提示使用 `/simple-chat/rumination-v4`；在激活码读写与模型调用前拒绝。旧 row/step3/combo 请求字段从 Schema 移除。
- 现行 `/simple-chat/rumination-v4/*` 继续使用独立组合 `combo_id`；`/version` 保留响应形状，固定 v4/current，分配时间与比例为空，不创建 A/B 记录。
- 后台 `jump-to-rumination` 请求只保留 `activation_code`，仍要求超级管理员与沙箱；初始化 v4、不覆盖已有组合。旧 `target_section/target_filter_step/seed_table` 不再是契约。
- `/simple-chat/history` 继续经原权限边界读取历史消息；可选 `rumination_filter_step` 仅用于历史消息筛选。后台历史导出不写回、不补矩阵，`source_schema_version`注明原版本，`steps`保留原编号（schema1为九步），不将旧步骤重新编号为当前流程。当前批量导出增加 `raw/rumination_v4_progress.json`，缺少原生终选的包不判为当前完整报告。

这是明确退役，不是旧客户端无感兼容。已保存的历史 Markdown/PDF 继续按原归属及审核规则读取；未完成旧探索的数据迁移另行设计。

## 报告与新产品

报告 PDF 链路保留 activation_code + report_id 的现有权限检查、完成度和审核门控；导出会话与报告 PDF 是两类功能。新产品按激活码索引历史报告时必须调用有授权的服务，不能直接公开 record.json 或拼文件路径。接口命名涉及会话/线程时必须说明具体模型，见字段字典。

## 支付管理（2026-10-13 新增）

| 接口 | 约束 |
| --- | --- |
| GET /api/v1/admin/payment/revenue-summary | 仅超级管理员；实时 SQL 聚合，净实收口径 = Σ实付 − Σ已退款（计收状态 paid/granted/partially_refunded/refunding/refunded），今日/本月按 paid_at 以 +08:00 日界归属；与漏斗统计（排除已退款订单）口径不同，不可混用 |
| GET /api/v1/admin/payment/orders/export | 仅超级管理员；xlsx 下载，遵循 status/channel 筛选、无分页，单批上限 20000 行（超出 400 提示分批）；响应含用户邮箱（个人敏感信息），每次导出追加审计到 `data/admin_export_audit.jsonl` |

## 前端适配

新增文件下载使用 download_url 并携带现有访问令牌；不要在页面显示磁盘路径。仓库现有前端未引用旧会话 export/generate 的 file_path；外部客户端如使用旧返回值需升级。新增 Markdown 统一使用 SafeMarkdownPreview。

## 管理员测试中心（dev）

统一前缀 `/api/v1/admin/test-center`；真实超级管理员，且 `APP_ENV` 为 development/dev/test、`TEST_CENTER_ENABLED=1` 并配置独立 `TEST_CENTER_ROOT`。普通身份 403，关闭/生产环境 404，缺控制目录配置 503。成功返回 `{code:200,message:"ok",data:...}`；非法用例/验收条件 400，缺资源 404。

| 方法 | 路径 | 行为 |
| --- | --- | --- |
| GET | `/catalog` | 自动登记固定定义，返回核心/版本/归档状态、输入与断言、构建和覆盖缺口、执行器心跳与容量 |
| PUT | `/cases/{id}` | `{core:boolean,archived:boolean}`，保存人工覆盖并留调整记录 |
| POST | `/runs` | `{case_ids:string[],mode:"diagnostic"或"release",budget?:{max_calls,max_tokens}}`，202 入队；只运行登记入口，验收禁止子集/脏源码/无 tag/缺覆盖 |
| GET | `/runs` | 最近 100 批摘要（不重复返回上下文/消息），完整证据与历史可按 ID 查询 |
| GET | `/runs/{id}` | 固定修订、构建/清单摘要、逐例状态、断言计数、错误和证据名 |
| POST | `/runs/{id}/cancel` | 申请取消；普通测试终止进程组，AI 等已发调用结算后停止后续请求 |
| GET | `/runs/{id}/artifacts/{case_id}/{name}` | 鉴权下载登记证据；不接受任意文件路径 |
| GET | `/capabilities` | 非敏感模型配置与 worker 凭据就绪状态；不返回密钥 |
| POST/GET | `/drafts` | 分开的输入/断言编译固定草稿或待澄清草稿；列最近 100 份 |
| POST | `/cases` | `{draft_id}` 确认保存可执行草稿；基于旧修订的覆盖被拒绝 |
| GET | `/cases/{id}/revisions` | 不可变定义修订，可供导出 |
| POST/GET | `/contexts` | 保存固定起点 / 列表；strict schema，不接受任意路径 |
| GET | `/contexts/{id}` | 按内容摘要读取不可变上下文 |
| POST | `/contexts/preview` | `{activation_code,phase,thread_id,name}` 读取调试工作区当前起点，供检查脱敏，不自动保存 |
| POST | `/runs/{id}/reviews` | `{case_id,attempt,verdict,reason}`，attempt 从 0 开始；已结束 AI 次数的追加复核，操作者取登录身份 |

草稿请求：`title/kind/inputs/assertions` 必填；`purpose` 单独描述目的（最多 4000 字）；API/UI 使用 `template_id`，UI 可组合明确步骤；修改已有用例带 `case_id/base_revision`。AI 使用 `context_id/repeats`（1–10，默认 1）、`conversation_mode`（`independent` 默认独立单轮，`sequence` 连续聊天历史，`workflow` 通过既有业务接口推进状态）；允许逐轮/逐步断言，整组重复仍恢复起点。来源 `sources` 随原用例保留。未知操作/断言返回 `state=needs_clarification`，不能确认保存。语法与业务状态限制见下方指南。

业务回放的上下文扩展 `workflow_seed`（前置完成阶段、基本资料、结论、线程状态、锚点）；未知字段或权限/路径配置拒绝。已有预览入口可返回结构化状态，仍只允许 dev 调试工作区。步骤与逐步标准通过已有草稿入口固定，未新增用户业务 endpoint。

运行详情额外返回 `ai` 固定模型/预算/上下文、逐次 `attempts`、`calls` 调用账本、`usage` 已知与预留用量、追加 `reviews`。业务回放的 attempt 另含 `request/http_status/response/before_state/state/model_calls`，没有模型调用的步骤不要求提示词摘要；calls 记录该次产品请求使用的 `max_output_tokens`。自动结论和复核独立。状态：`queued/running/pass/fail/error/incomplete/cancelled/needs_review`。只有有效断言完整执行且全部通过才是 pass。部署与语义详见 [测试中心指南](TEST_CENTER.md)。
