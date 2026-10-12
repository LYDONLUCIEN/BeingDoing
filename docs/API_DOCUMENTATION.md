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

点赞 trace 仅返回自己保存的快照/预览，不再根据客户端曾提交的 session_id 扫描磁盘；历史匿名点赞不自动认领。匿名 page_view 仍可经 /analytics/event 提交，服务端限定事件类型，保持 ADR-0013 口径。

## 沉淀 v3 退役（ADR-0025）

- 删除 `/simple-chat/rumination-progress`、`rumination-step-opening`、`rumination-step-opening-stream`、`rumination-table-submit`、`rumination-combo-conclusion`、`rumination-combo-guide`、`rumination-combo-matrix-submit`、`rumination-combo-matrix`、`rumination-neg-resolve`、`rumination-get-table` 路由，OpenAPI 不再发布，旧路径返回404。
- 通用 `/simple-chat/message`、`message/stream`、`init`、`thread/reopen`、`thread/complete`、`conclusion/request`、`thread/delete` 对已认证请求的 `phase=rumination` 返回410，提示使用 `/simple-chat/rumination-v4`；在激活码读写与模型调用前拒绝。旧 row/step3/combo 请求字段从 Schema 移除。
- 现行 `/simple-chat/rumination-v4/*` 继续使用独立组合 `combo_id`；`/version` 保留响应形状，固定 v4/current，分配时间与比例为空，不创建 A/B 记录。
- 后台 `jump-to-rumination` 请求只保留 `activation_code`，仍要求超级管理员与沙箱；初始化 v4、不覆盖已有组合。旧 `target_section/target_filter_step/seed_table` 不再是契约。
- `/simple-chat/history` 继续经原权限边界读取历史消息；可选 `rumination_filter_step` 仅用于历史消息筛选。后台历史导出不写回、不补矩阵。当前批量导出增加 `raw/rumination_v4_progress.json`，缺少原生终选的包不判为当前完整报告。

这是明确退役，不是旧客户端无感兼容。已保存的历史 Markdown/PDF 继续按原归属及审核规则读取；未完成旧探索的数据迁移另行设计。

## 报告与新产品

报告 PDF 链路保留 activation_code + report_id 的现有权限检查、完成度和审核门控；导出会话与报告 PDF 是两类功能。新产品按激活码索引历史报告时必须调用有授权的服务，不能直接公开 record.json 或拼文件路径。接口命名涉及会话/线程时必须说明具体模型，见字段字典。

## 前端适配

新增文件下载使用 download_url 并携带现有访问令牌；不要在页面显示磁盘路径。仓库现有前端未引用旧会话 export/generate 的 file_path；外部客户端如使用旧返回值需升级。新增 Markdown 统一使用 SafeMarkdownPreview。
