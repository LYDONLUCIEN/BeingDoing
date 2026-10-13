# ADR-0026：注册邮箱验证前置化与纯手机老账号强制绑邮箱

- 日期：2026-10-13
- 决定来源：维护者明确要求注册时先验证邮箱再建号，验证通过后登录只需邮箱+密码；登录/注册均不允许「只有手机号、没有邮箱」完成。
- 状态：接受并实施；未部署，未迁移真实数据。
- 替代：2026-09-27 口径「注册后自动发验证链接、验证通过才发试用码」与 PRODUCT_RULES「历史手机号登录保留」。

## 背景与取舍

旧流程先建账号后发验证链接，未验证用户可登录浏览、仅探索写操作被 403 门控，注册转化漏斗在「验证」一环断裂且账号体系中沉淀未验证账号。前置化后，注册页单页分三步：邮箱 → 验证码 → 密码。

关键取舍（均经维护者逐项确认）：

- **验证码+链接双形态**：页内输 6 位码不断流程；链接在任何设备点开仅完成服务端验证，原注册页 5 秒轮询领 ticket（解决电脑注册、手机点链接的跨设备断点）。未选「链接直接带 ticket」——跨设备时原设备流程会断。
- **registration ticket 防绕过**：验证通过签发 JWT（type=register_ticket，30 分钟，绑定邮箱），注册接口无 ticket 或邮箱不符一律 400，无法绕过验证直接调接口建号。ticket 重放无害：邮箱唯一约束兜底。
- **验证码内存存储**：与找回密码码同口径（进程内内存，重启失效）。已论证接受：恰好「注册验证中遇服务重启」概率低，生产不随意重启；DECISIONS 已标注内存方案是阶段条件，将来多进程/高可用时随找回密码码一起升级。
- **已注册邮箱明确提示+仍发通知邮件**：接受注册侧枚举风险（Google/GitHub 同口径），登录侧假哈希防枚举不变。通知邮件受 60 秒冷却限制防轰炸。
- **纯手机老账号硬门禁**：手机+密码认证通过后签发受限 token（type=email_binding_required，30 分钟，仿 deleted_recovery 模式），仅可访问绑定邮箱端点；绑定邮箱需验证码确认，绑定即 email_verified=True 并换发正式 token 对。不允许绑定已注册邮箱（不合并账号，见 HISTORY_EVIDENCE）。未选「只读可用」——每个写端点加判断的实现面太大。
- **试用码发放时点平移**：邮箱已前置验证，发放从「验证通过后」平移到「注册完成/绑定完成」，ensure_* 幂等保护不变。存量未验证老用户的重发验证、403 门控、journeys 懒补发路径保持原样。
- **手机号不收集**：注册/绑定均不收手机号（无真实短信通道，无法验证真实性），等短信通道上线再做绑定流程。

## 实施边界

- 新端点：`POST /auth/register/code`（IP 10 次/小时 + 单邮箱 60 秒冷却）、`POST /auth/register/verify`、`GET /auth/register/verify-link`、`POST /auth/register/poll`、`POST /auth/bind-email/code`、`POST /auth/bind-email/confirm`。
- `POST /auth/register` 必须携带 ticket；注册 IP 频控 5 次/小时保留（无 ticket 的 400 请求同样计数）。
- 验证码 10 分钟有效、单码错 5 次作废、一次性消费；链接 token 与验证码同窗口。
- 前端：`/auth/register` 与 AuthModal 注册 Tab 步骤化（共享 `useRegisterVerification` hook）；`/bind-email`（硬门禁页，AuthGate/bindingMode 同 recoveryMode 模式）、`/register-verify`（链接落地页）新增；登录页/AuthModal 处理 `email_binding_required` 分支。
- 参数默认值（可运行调整）：码 10 分钟、冷却 60 秒、ticket 30 分钟、发码 IP 10 次/小时、单码 5 次试错。

## 文档边界和后果

「历史手机号登录保留」条款废止，手机登录仅作为进入强制绑定流程的认证手段。本次不迁移存量数据：纯手机老账号首次登录时走绑定流程即可完成迁移；未验证邮箱老账号路径不变。

人机验证（CAPTCHA）经讨论本次不做：阶梯锁定+频控已覆盖当前风险；将来如需，首选 Cloudflare Turnstile 或国产行为验证（错 N 次后渐进出现），不自建图片点选类。

验证见 [TESTING](../TESTING.md)；测试：`test/backend/test_register_preverification.py`（新流程 16 项）、`test_register_email_verification.py`（存量路径回归）。
