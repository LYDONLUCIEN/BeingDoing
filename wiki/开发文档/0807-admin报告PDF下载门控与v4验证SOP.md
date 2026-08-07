# 0807-admin 报告 PDF 下载门控修复 + rumination v4 一致性验证 SOP

## 背景

**Bug**：`/admin/reports` 页面里，五阶段（含 rumination）未完成的 report 也能点击「下载PDF」，
生成出一份只有占位文案的残缺 PDF。

**根因（三层缺口叠加）**：

1. 前端「下载PDF」按钮零门控，不看完成状态（`admin/reports/page.tsx`）。
2. 后端 `_review_block_payload` 对 super admin 直接 `return None`（`export.py`），
   豁免本意是绕过「审核中」阻塞（审阅需要看内容），但连带绕过了「五阶段未完成」这道闸。
3. `ReportPdfService` 对缺失数据只输出占位文案不抛错，残缺 session 也能"成功"产出 PDF。

## 修复内容（2026-08-07）

| 层 | 改动 | 文件 |
|---|---|---|
| 后端 | `POST /export/report-pdf/{id}` 新增完成度门控：`_report_portal_unlocked` 为 false 一律 **409**（admin 也不例外）；admin 豁免仅限审核状态阻塞 | `src/backend/app/api/v1/export.py` |
| 后端 | `GET /admin/reports` 新增 `report_unlocked` 字段；`completed_steps` 修 v4 口径（rumination locked 计入，v4 终选只 lock 不写 session） | `src/backend/app/api/v1/admin.py` |
| 前端 | `report_unlocked === false` 的行禁用下载按钮 + 悬浮提示「用户尚未完成全部探索阶段，暂不可下载」（disabled 按钮不触发 hover，tooltip 包在 span 上） | `src/frontend/app/(main)/admin/reports/page.tsx`、`src/frontend/lib/api/admin.ts` |
| 测试 | 既有 not_started 用例改断 409；新增 admin 未完成 409 / v4 locked 放行 / 列表字段用例 | `test/backend/test_report_review.py` |
| 工具 | 一次性验证脚本 `scripts/dump_report_pdf_input.py` | 见下 |

**设计决策**：不留 admin 逃生舱（调试直接看服务器数据文件）；`force=true` 保持单一语义（跳过缓存重新生成），不复用为权限绕过。

## PDF 数据口径（与 rumination v4 的关系）

PDF 底层数据**就是最新 v4 结构**，不存在旧结构残留：

- 4 维结论：`data/simple/reports/{report_id}/dimension_conclusions.json`
- rumination 块：`data/simple/reports/{report_id}/rumination_v4_progress.json`
  → `final_selection.selected_combo_ids` ∩ `combo_sessions[].conclusion_card`
  （只取用户**终选提交**的方向，discussing/abandoned 的不进报告）
- 缓存过期判断：比对结论卡 `updated_at` + `dimension_conclusions.json` mtime，
  数据更新后自动重新生成（`report_pdf_service.py _is_cache_expired`）

注意：PDF 正文是 LLM 基于上述数据**重写**的，不是结论卡原文。
所以验证分两层：① 数据层（确定性，脚本验证）；② LLM 忠实度（人工对比）。

## 验证 SOP

### 1. 门控验证（修复是否生效）

1. 打开 `https://career.beyondego.me/admin/reports`，找一行 `完成步骤 < 5/5` 的 report：
   - 「下载PDF」按钮应为禁用态，悬浮显示「用户尚未完成全部探索阶段，暂不可下载」。
2. 直接调 API 验证后端兜底（替换 `{rid}` 为未完成 report 的 ID）：

   ```bash
   curl -i -X POST "https://career.beyondego.me/api/v1/export/report-pdf/{rid}" \
     -H "Authorization: Bearer <admin_token>"
   # 期望：HTTP 409 {"detail":"用户尚未完成全部探索阶段，暂不可生成报告 PDF"}
   ```

3. 已完成（5/5）的 report：按钮可点，生成/下载流程不变。

### 2. 数据层验证（v4 结构一致性，确定性）

在服务器项目根目录执行：

```bash
python scripts/dump_report_pdf_input.py <report_id>            # 人类可读
python scripts/dump_report_pdf_input.py <report_id> --json     # 完整 JSON
```

核对点：

- `step_status` 五阶段应全 ✅，`report_unlocked: True`；
- `rumination_v4.schema_version` 应为 `4`；
- `final_selection.submitted` 应为 `true`，`selected_combo_ids` 是用户终选方向；
- `rumination_block` 里**只出现终选 combo 的结论卡**，且内容与
  `combo_sessions[].conclusion_card` 逐字段一致（脚本同屏输出两者，直接比对）；
- 4 维 block 与 `dimension_conclusions.json` 对应字段一致。

### 3. LLM 忠实度验证（人工对比）

1. 在 admin 页下载该 report 的 PDF（如怀疑缓存旧，可先强制重新生成：
   用户报告页带 `force=true`，或直接删除 `report_markdown.md` 缓存后再下载）。
2. 对照脚本输出的 `phase_blocks`：PDF 各章节的结论点应能在 block 里找到出处，
   不允许出现 block 之外编造的结论（占位文案如「暂无结论数据」不应出现在已完成报告中）。

### 4. 缓存新鲜度验证（可选）

修改某结论卡（或等用户数据自然更新）后重新下载 PDF，
内容应反映最新数据（缓存按结论卡 `updated_at` 自动失效，无需手工清）。
