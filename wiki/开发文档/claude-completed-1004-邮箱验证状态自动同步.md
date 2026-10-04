# 邮箱验证状态自动同步（2026-10-04）

## 背景

用户报告：Gmail 用户（邮箱本地部分带 `.`，如 `chang.ownlife29@gmail.com`）反馈"邮箱验证不过"，后来又显示已完成。

排查结论：**与点号无关**（全链路检查：`_normalize_email` 仅 strip+lower、token 走 query param、后端无自定义正则，均对点号友好）。真实原因是**前端状态快照不同步**：

- `email_verified` 缓存在 Zustand authStore，**不跨标签页同步**
- 用户在原标签页（survey/chat）看到"请先验证邮箱" → 去邮箱点验证链接（新标签页）→ 验证成功只更新了新标签页的 store
- 切回原标签页，store 仍是 `email_verified: false`，继续拦截 → 用户以为验证失败
- 手动刷新后 activate/settings 页的挂载同步逻辑拉到最新状态才恢复

后端无延迟：`verify_email_token` 立即 commit（`user_db.py:70`），`get_current_user` 每次实时查库（`auth_service.py:1089`）。

## 改动

### 1. `src/frontend/app/(main)/explore/survey/page.tsx`（核心）

未验证拦截期间静默轮询后端（`/auth/me`）：

- 进入页面立即查一次——覆盖「早已验证、仅 store 陈旧」的情况（用户其实已验证完，进来 1 秒内直接解锁）
- 之后每 5s 查一次；后端返回已验证 → 更新 store → `emailUnverified` 重算为 false → 拦截 UI 自动消失、问卷表单出现
- 完全静默：**无新增 UI 元素、无需用户刷新页面、无需理解任何概念**
- store 更新遵循 activate 页既有模式（`getState()` 取最新 user、保留 avatar_url 等字段）
- 清理与竞态：卸载清 interval；`stopped` 标志防 in-flight 请求竞态；网络错误静默重试
- 已验证用户 effect 直接 return，零开销

### 2. `src/frontend/lib/i18n/locales/zh.ts` / `en.ts`

`auth.verifyEmailDesc`（仅 verify-email 成功页使用）文案更新：

- zh：`请回到之前操作的页面继续；若仍显示未验证，稍候片刻或刷新页面即可`
- en：`Return to the page you were on to continue; if it still shows unverified, wait a moment or refresh`

## 闭环时序（改后）

1. chat 页发现未验证 → 踢回 survey 页显示验证引导
2. 用户点「发送验证邮件」→ 去邮箱（新标签页）点验证 → 成功
3. 切回原标签页 survey → 最多 5s 内轮询发现已验证 → 自动解除拦截，表单出现
4. 流程继续（隐私弹窗、提交、进入 chat）

## 不改动的地方（及原因）

- **chat 页踢人 effect**：读 store，store 被轮询更新后自动失效，无需改
- **activate 页**：其未验证 UI 是「前往验证」跳转引导（有出路），且已有挂载时同步（刷新即恢复），不扩大改动面
- **后端**：无延迟问题，不动

## 验证

- ESLint 通过（改动文件零告警）
- 前端无测试框架（package.json 无 test 脚本），本次为纯前端 UI 行为改动，未新增测试基建
