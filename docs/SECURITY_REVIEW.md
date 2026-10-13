# 安全评估（2026-10-12）

基线 `v1.8.0 / e6181d4e8dc34270e6948d2c78695e6855931368`；改动分支 `clean`。本次评估覆盖代码、依赖和仓库内配置，优先验证匿名/普通账户能否越权，以及用户/模型内容是否跨越信任边界。未登录真实服务器、未导入真实 data/app.db、未进行线上攻击测试。

## 结论

基线存在可复现的权限、导出文件读取和前端内容注入问题；对应改动与回归测试已在 clean 落地。不能据此称整个系统已经安全：依赖、部署配置、存储一致性和既有失败测试仍有明确后续事项。下列严重度是本项目影响判断，与依赖公告的 CVSS 分开。

## 已修复的可复现问题

| 级别 | 基线行为与影响 | 修复边界 | 验证 |
| --- | --- | --- | --- |
| 高 | 匿名 POST simple-auth/activation 可创建完整码；普通用户也可创建 | 仅 super_admin；合法后台路径保留 | 匿名 401、普通账户 403、管理员成功 |
| 高 | 旧 chat/answers/optimized 已登录后只凭 session_id 或 answer_id 读写其他人的数据，SSE 还可消耗 LLM | 共享会话/回答归属校验，在文件访问、模型调用及 SSE 返回前执行；拒绝非法标识 | 15 类跨用户 HTTP 操作拒绝，缺失/穿越标识拒绝 |
| 高 | export/download 直接把 export_id 当路径，可读取本机指定 JSON/MD/PDF | 随机 ID、账户临时目录；不返回磁盘路径，不接受用户路径 | 绝对路径攻击失败；本账户生成/下载成功，另一账户 404 |
| 高 | 点赞列表、原文追溯、状态可匿名或跨用户读取，取消也可能影响别人的记录 | 登录、写入归属、按 user_id 查询/删除；去掉按客户端 session_id 扫描历史文件的兜底 | 两用户真实 SQLite + HTTP；未绑定/异主探索拒绝，合法两种客户端标识可用 |
| 高 | Markdown 保留 iframe/script/javascript 链接；优势名称直接作为 HTML 注入 | SafeMarkdownPreview 在全部 rehype 处理后清洗并限制 URL；名称由 React 转义 | 实际组件 SSR 注入用例先失败后通过，正常表格/链接保留 |
| 高 | 邮箱/手机找回及管理员重置密码未撤销旧 refresh token | UserDB 同一事务修改密码并撤销该账户刷新令牌 | 三种重置后旧刷新失败，另一用户令牌可继续使用 |
| 中 | 找回验证码使用普通随机数且没有逐条尝试预算 | secrets 生成 6 位码，单次记录最多 5 次猜测，成功后消费；恢复账户验证码共用校验 | 5 次错误后正确码仍拒绝 |
| 中 | 生产可能带默认签名密钥、DEBUG 与不安全刷新 cookie 启动；假短信找回写日志 | prod/production 启动校验；假短信仅 development/test | 不安全配置拒绝，合规配置可创建；生产假短信接口 503 |
| 中 | 应用直接信任任意 X-Forwarded-For，削弱注册/激活限流 | 只用 ASGI client，由受信 Uvicorn 代理层解析 | 伪造头不改变限流键；代理实际配置仍需现场核对 |
| 中 | 缓存清空/统计未授权；用户可直接 force 重生成报告绕过复核流程 | 缓存操作与 force 限 super_admin | 匿名/成员/管理员组合及 force 拒绝回归 |

测试文件见 test/backend/test_security_boundaries.py、test_analytics_privacy.py、test_security_config.py、test_password_reset_sessions.py 及 src/frontend/test/security-rendering.tsx。会话导出与报告 PDF 是独立功能，未移除现有报告/支付业务。

## 覆盖范围与未证明部分

| 范围 | 检查结果与限制 |
| --- | --- |
| 入口/认证/权限 | 检查 main 挂载、API 依赖、JWT/refresh、管理员、会话与报告归属；未穷举所有用户状态与管理员沙箱组合 |
| 输入/输出 | 重点检查 Markdown/HTML、文件路径、上传、日志、子进程调用、SQL 使用；没有动态模糊测试所有表单或 native 图像/Chrome |
| 支付/退款/券 | 读取近期模型与设计，回归现有支付、取消竞态、退款、券用例；未进行真实支付、扣款/退款或外部 Webhook 联调 |
| 文件/数据 | 检查 DB/JSON 双源、报告索引、历史兼容、临时导出；未验证真实用户数据一致性、备份恢复或服务器文件权限 |
| 静态扫描 | Bandit 基线 83 low、3 high；3 个 high 是用于纯文本 LLM prompt 的 Jinja autoescape 提示，不是已证明 HTML XSS。没有为消除告警擅改 prompt 转义 |
| 秘密管理 | 检查配置入口及跟踪文件的密钥模式，输出不记录候选值；没有完整 Git 历史秘密扫描，不证明旧提交或服务器无泄漏 |
| 依赖 | 锁文件/实际 Python 包审计与维护方公告核对；npm 完整审计请求 ECONNRESET，未获得可靠完整 JSON 清单 |
| 部署 | 只读仓库内启动/代理配置；HTTPS、端口暴露、可信代理、环境覆盖、数据库备份、Chrome 系统依赖都未现场验证 |

## 依赖处置

- 前端新增 rehype-sanitize；Axios 锁到 1.20.0、根 PostCSS 锁到 8.5.29，生产构建与渲染回归通过。Next 仍为 14.2.35，内部 PostCSS 仍 8.4.31，不能因根包升级宣称全部副本修复。
- Python 提高 multipart/Jinja2/jose/Pillow 下限，补全 aiofiles/email-validator/SQLAlchemy asyncio，核心依赖增加 Python 3.12 跨平台锁。实际验证 Pillow 12.3.0 的头像回归通过；这不是替服务器自动升级。
- pip-audit 对本地 133 个依赖返回 3 条记录（同一 ecdsa 问题重复出现），去重为 **2 个未修复公告**：ecdsa 0.19.2 的 P-256 计时问题、python-jose 3.5.0 的 DER 公钥/HMAC 算法混淆问题。目前 AuthService 固定 HS256 且 decode 显式限定算法，用私有随机对称密钥；未发现使用 ECDSA 签名或 DER 公钥验证的路径，因此没有证明这两条在本应用可利用。不可删除公告或称漏洞清零；更换 JWT 库需另做令牌兼容验证。[ECDSA 维护方讨论](https://github.com/tlsfuzzer/python-ecdsa/issues/381)、[python-jose 公告](https://github.com/advisories/GHSA-3qf3-8w2g-rqmx)。
- Next 14 命中维护方新公告范围，已查代码没有 next/image/next/og 与 sharp，但这不能证明部署的图像优化端点不可达。Windows 专属公告不能套到 Linux。需迁移至受支持版本并做独立构建/路由/认证验收，不能无验证使用 npm audit fix --force。[Next 图像处理公告](https://github.com/vercel/next.js/security/advisories/GHSA-2xp9-vwfh-vxw4)。
- 原 Axios 范围与 PostCSS 风险分别涉及已有原型污染、恶意 CSS/source map 输入；本次只确认版本与使用条件，不将所有依赖命中都说成线上可利用。[Axios](https://github.com/axios/axios/security/advisories/GHSA-pf86-5x62-jrwf)、[PostCSS](https://github.com/postcss/postcss/security/advisories/GHSA-fxqj-rqcc-2cmp)。
- 其他核查：[multipart](https://github.com/Kludex/python-multipart/security/advisories/GHSA-5rvq-cxj2-64vf)、[Jinja2 3.1.6](https://jinja.palletsprojects.com/en/stable/changes/#version-3-1-6)、[Pillow](https://github.com/python-pillow/Pillow/security/advisories/GHSA-6r8x-57c9-28j4)、[Markdown 维护方安全说明](https://github.com/uiwjs/react-markdown-preview#security)。

## 仍需处理的事项

| 优先级 | 事项 | 下一步 / 验收边界 |
| --- | --- | --- |
| P1，部署前 | Next 14 维护版本与嵌套依赖；npm audit 未完整返回 | 在联网 CI 获取完整审计；制定受支持 Next 迁移，运行路由/SSR/认证与安全回归 |
| P1，部署前 | 启动新校验会拒绝不合规生产环境 | 现场确认 APP_ENV、随机密钥、Secure cookie、HTTPS；轮换密钥会使既有 token 失效，先排上线窗口 |
| P1，部署前 | 代理 IP 信任、HTTP 请求体/上传大小限制 | 核对 Uvicorn 信任具体代理，代理覆盖外来转发头；用两个真实客户端验证独立限流，保持后端仅内网/localhost |
| P1，稳定性 | 完整后端仍有基线失败/缺数据；DB 与 JSON 缺统一事务 | 按 TESTING 清单修复基线，在一致快照副本上验收迁移、交付、恢复和回滚 |
| P1，运维流程（2026-10-13 补核） | deploy.sh 在停服务前 cp 默认 app.db、不备份 data、未安装依赖；与 start prod 的 Conda 默认值不同，输出的旧回滚仅恢复 DB | 当前按 [服务器手册](OPERATIONS.md) 停写、一致备份和逐步更新；部署自动化另行改造验收，未执行现有脚本 |
| P2，进程管理（2026-10-13 补核） | start.sh 的 prod 后端仍带 reload；tmux 不负责开机恢复，启动提示不证明构建成功 | 当前手工验证日志与健康；后续 prod 迁 systemd 时统一路径、环境、监听和构建，现有模板不可直接套用 |
| P2 | 内存验证码、登录限流、生成锁与缓存 | 仅单实例假设；多进程/多实例前迁到共享原子存储，验证重启与并发 |
| P2 | access token 已签发后不会因重置密码立即撤销 | 当前仅撤销刷新能力，旧 access 到过期前仍有效；需要即时撤权时引入账户 token version/时间边界及迁移 |
| P2 | LLM 轮次日志含正文/推理内容，报告与导出含敏感数据 | 核对保留天数、权限与日志备份；不得作为普通前端可读资源。临时会话导出目前依赖系统临时目录清理，无应用 TTL |
| P2 | 某些旧路由返回 str(exception)，可能泄露内部细节 | 按模块收敛外部错误码与内部日志，保留可排障追踪 ID；本次只收敛改动的会话导出路径 |
| P2 | Chrome PDF 子进程使用无 sandbox 参数；图像/LLM 内容属于不可信输入 | 测试环境验证容器/OS 隔离、超时和资源限额；未进行 Chrome 漏洞利用或全套渲染内容隔离验证 |
| P2 | JWT/哈希库维护与 Python runtime 兼容 | 审计公告保持可见；单独设计 PyJWT/joserfc 等替换评估与 passlib 迁移，不原地破坏历史密码/令牌 |

## 服务器数据何时需要

代码体检和清理不依赖数据副本。下一步若验证历史字段与一致性，需要同一时点的脱敏 app.db 与 data 快照（包含激活码索引、报告 record、对话及运行配置结构），排除密钥、支付证书和真实令牌；在隔离目录恢复，先只读检查孤儿索引/用户归属/金额行和券计数，之后再做迁移演练。未取得副本前，不对历史数据是否完整作结论。

## 第二轮退役带来的边界收敛

ADR-0025 删除旧沉淀七步/矩阵运行端点与 A/B 分配，通用写入口在读激活码/调用模型前拒绝旧阶段。历史导出只读且不自动生成矩阵/终选；后台跳转与模拟资料使用沙箱数据根并保留已有v4组合。拒绝路径、沙箱隔离、原生导出和当前v4均有离线行为回归。

这减少了维护的旧运行入口，不构成已清除所有漏洞或完成真实数据迁移的证明。第一轮剩余安全风险及部署前条件继续有效；全量后端仍有44项既有失败和6个错误，见TESTING。
