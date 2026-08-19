# 报告复核体系实施计划（替代用户重新生成）

> 2026-08-18 定稿。核心原则：**用户不能重新生成，管理员也不能随意重新生成**——重新生成必须挂在用户主动发起的复核单上，且新稿经 admin 确认发布后才对用户可见。

## 1. 总体变更

- **下线**用户侧重新生成能力：删除报告页「重新生成（剩 N 次）」按钮、后端 `_MAX_USER_REGEN` 限额与 403 拦截、`report_regen_count` 计数逻辑。存量 record.json 中的 `report_regen_count` 字段不迁移、不清理（无害残留）。
- **新增**「申请复核」入口：报告 ready 后出现在下载按钮旁，鼠标悬停 tooltip 解释复核含义（「报告内容有问题？提交后由管理员人工复核，必要时重新生成，期间你仍可查看当前报告」）。
- **error 状态与复核无关**：首次生成失败显示「重新尝试生成」（走原有非 force 触发），用户可自行反复点击，不产生复核单。

## 2. 用户申请复核

- 弹窗：**分类必选**（`content_issue` 内容有问题 / `download_issue` 下载或打开失败）+ 描述**选填**。
- **download_issue** → 直接进现有 Feedback 通道，与右侧「反馈 bug」完全同流程同结果；**不建复核单**，不出现重新生成按钮。
- **content_issue** → 建复核单（record.json 为权威数据源）+ **双写一条 Feedback 工单**（带 report_id 跳转链接，保证 admin 在反馈列表可见、不漏单）。
- **频率限制**：同一报告每天最多 1 次；存在未关闭复核单时按钮禁用（显示「复核处理中」）；总次数不限。

## 3. 复核状态机（存 record.json `review_request`）

```
pending（用户已申请）
  → regenerating（admin 已触发重新生成）
  → pending_confirm（新稿已出，待 admin 确认）
  → done（已发布）
rejected（驳回：必须填理由，经 Feedback 回复 + 站内信告知用户）
```

- regenerating 中 LLM 生成失败 → 退回 `pending`，admin 可重试。
- 复核单关闭（done/rejected）后清理 staging 文件。

## 4. staging 影子隔离（关键）

- 重新生成写入 `data/simple/reports/{id}/report_markdown.staging.md`，**正式 `report_markdown.md` 不动**（PDF 下载时即时渲染，故用户始终看到旧版）。
- admin 预览 = 下载用 staging 即时渲染的 PDF（专用端点），**不做 diff 视图**，与旧版 PDF 各自打开人工对比。
- 「确认发布」：二次确认弹窗 → staging **原子替换**正式文件，旧版留 `.bak` 备份。

## 5. admin 侧权限门控

- **前端**：报告详情/列表的「重新生成」按钮**仅当存在未关闭复核单时出现**（pending/regenerating/pending_confirm），期间可**反复重新生成**（每次覆盖 staging，直到满意）；复核单关闭后按钮消失。
- **后端**：`force` 能力**永久保留**、不设限，供脚本/运维直接调用（API 层不强制要求复核单）。

## 6. 发布与通知

admin 确认发布后：

1. staging 原子替换正式 markdown（旧版 `.bak`）；
2. **站内信**通知用户「报告复核已完成，内容已更新」（复用 `report_approved` 幂等通知模式，带报告页入口）；
3. **邮件**同步通知（SMTP 现成）；
4. 报告页「复核中」提示条消失；
5. Feedback 工单置 done。

## 7. 用户可见性（不锁定模式）

- 复核全程报告**不锁定**，随时可看可下（旧版）。
- 复核进行中：报告页顶部提示条「报告复核中，内容可能更新，完成后将通知你」；申请按钮禁用态「复核处理中」。
- 被驳回：Feedback 工单内 admin 回复 + 站内信告知，不发邮件。

## 8. 涉及文件（预估）

**后端**：
- `src/backend/app/api/v1/export.py` — 删用户 regen 限额/403；`trigger_report_pdf` 支持 staging 目标
- `src/backend/app/services/report_pdf_service.py` — staging 写/读/原子替换/`.bak`/清理
- `src/backend/app/api/v1/admin.py` — 复核单列表操作：触发重新生成（挂复核单）、staging 预览下载、确认发布、驳回
- record.json `review_request` 字段（状态机、申请记录、理由）
- Feedback 双写 + 站内信（`report_review_done` / `report_review_rejected` 类型）+ 邮件
- 删除：`_MAX_USER_REGEN`、`report_regen_count` 计数、`test/backend/test_report_regen_limit.py` 改写

**前端**：
- `app/(main)/explore/report/view/page.tsx` — 删重新生成按钮；加「申请复核」入口（tooltip）+ 弹窗 + 复核中提示条 + error 态「重新尝试生成」
- `app/(main)/admin/reports/page.tsx` — 复核单门控的「重新生成 / 预览新稿 / 确认发布 / 驳回」按钮组
- admin Feedback 列表 — 复核工单展示与跳转

## 9. 待实现前确认的小事

- staging 预览端点路径命名（如 `GET /admin/reports/{id}/staging-pdf`）
- 复核「每天 1 次」按自然日（Asia/Shanghai）计算
