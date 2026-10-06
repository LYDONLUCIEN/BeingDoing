# admin 用户类型标签 + 按用户全量数据导出

**日期**：2026-10-06
**需求来源**：用户反馈四项（rumination 前聊天看不到 / 用户类型区分 / 完整数据内容 / 全量筛选下载 + 备注）

## 定稿决策（AskUserQuestion 确认）

1. **用户类型四类**：`real` 真实用户（默认）/ `beta` 内测用户 / `test` 测试账号 / `admin` 管理员账号。存量与新建用户默认 `real`，管理员手动把内部账号标出，不做自动探测。
2. **导出粒度两种都保留**：老的按 report 批量导出（`/admin/reports/export/batch`）不动；新增按**用户**聚合导出（`/admin/users/export`），一人一目录、自动含名下全部 report（跨激活码旅程完整）。
3. **报告形式**：直接附带缓存的 `report_markdown.md` 全文（不现场生成 PDF）。
4. **只做 admin 端**：用户侧已有报告 PDF 下载，本次不加用户自助导出。

## 问题 1 根因（rumination 之前的聊天看不到）

导出按 report（= 激活码）为单位，而用户旅程常跨多个激活码：真实数据中用户 `e1481764` 的 rumination 在 report `d117e364`，前四阶段对话在**另一个** report `1df8bc45`；用户 `fc8267de` 名下 7 个 report。导出 rumination 那个 report 自然缺前四阶段。另外 `BatchExportService._pick_session` 每阶段只导出 selected/最新一个会话线程，其余线程与 record 未登记的孤儿文件（如 `df0b212f` values 有 6 个文件只登记 2 个）不导出。

## 改动清单

### 后端

- **迁移 `025_user_type_admin_note`**：`users` 加 `user_type`（String16，server_default 'real'）+ `admin_note`（Text）。注：并行的优惠券工作已占 `024_coupon_multi_redemption`，本迁移排 025。
- **`models/user.py`**：`USER_TYPES` 枚举常量 + 两字段。
- **`core/database/user_db.py`**：`list_users` 加 `user_type` 筛选。
- **`api/v1/admin.py`**：
  - `GET /users` 加 `user_type` 查询参数，返回 `user_type` / `admin_note`（详情接口同样补充）
  - 新增 `PATCH /users/{id}/meta`：改类型+备注（类型校验枚举，`admin_note` 传空串清空）
  - 新增 `POST /users/export`：显式 `user_ids[]` 或服务端筛选（`user_type`/`q`/注册时间/`has_report`）二选一；单次 ≤50 用户；产出 zip：`index.json`（用户→邮箱/类型/report 数索引）+ 每用户 `users/{uid}/profile.json` + `users/{uid}/reports/{rid}/...`
- **`services/user_export_service.py`（新）**：`collect_user_export` 聚合用户资料（邮箱/用户名/user_type/admin_note/membership/注册时间/profile+survey/工作履历+项目/激活码全列表含 sandbox 与套餐类型）+ 名下全部 report。
- **`services/batch_export_service.py`**：
  - raw 层改为打包 report 目录下**全部** `{step}__{session}.json`（含未选中线程与孤儿文件），md/stats 口径不变（仍按选中会话）
  - 附带缓存的 `report_markdown.md`（存在才附）

### 前端

- **`lib/api/admin.ts`**：`AdminUserType` 类型 + `ADMIN_USER_TYPES`；`AdminUserItem/Detail` 加字段；`fetchAdminUsers` 加 `user_type`；新增 `patchAdminUserMeta`、`exportUsersFullData`（blob 下载）。
- **`admin/users/page.tsx`**：用户类型筛选下拉、「用户类型」彩色 tag 列（真实绿/内测蓝/测试灰/管理员橙）、Drawer 内类型下拉+备注 textarea+保存。
- **`admin/data-export/page.tsx`（新）**：独立导出页——筛选（类型/搜索/注册时间）、跨页勾选、本页全选、「导出选中」与「按筛选全量导出」两种模式（全量模式可附加 has_report 条件）、>50 提示缩小范围。
- **`admin/layout.tsx`**：侧边栏新增「数据导出」入口（用户管理下方）。

## 测试

- `test/backend/test_admin_user_meta_and_export.py`（新，9 用例）：meta 修改/非法值 400/非管理员 403/列表类型筛选/导出 403·400·zip 结构（index+profile+report 全套+report_markdown）/筛选模式/空结果 404。
- `test/backend/test_admin_batch_export.py`（重写修复）：原文件是**早已损坏的陈旧测试**（路径缺 `/api/v1` 前缀 + mock 的 service 内部结构 `export_service.collect_export_data` 已不存在，与现行实现漂移数月）。重写为真实 service + registry 重定向 tmp 的集成测试（5 用例全过），顺带覆盖 raw 全量打包与 `_skipped.txt`。
- 真实数据验证：用户 `fc8267de`（8 report）导出 8 个 report 子目录全量；report `df0b212f` values 6 个会话线程全部导出；`report_markdown.md` 附带成功。

## 已知边界

- `POST /users/export` 是同步收集 + 内存 zip：50 用户×多 report 时响应可能较慢（当前数据量 44 report 无压力），后续量大可改后台任务。
- report `6a3d8242` 的 record.json 本身损坏（Extra data），导出时该 report 被跳过，不影响其他。
- admin 区 UI 均为硬编码中文（与既有 admin 页一致），未走 i18n。
