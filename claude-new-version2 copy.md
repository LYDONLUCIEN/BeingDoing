# V2 新版本变更记录

> 日期：2026-04-05
> 范围：用户气泡 bug、结论卡设计、step 文案、多 Journey、自动跳转、rumination 9 步

---

## 已完成

### 1. 用户气泡换行 Bug 修复 ✅

**问题**：输入 "确认！" 显示为 "确认\n!"，标点被换行。

**根因**：`page.tsx:1659` 的文本处理逻辑有缺陷（`lines.every(l => l.length <= 2)` 判断），加上 CSS `white-space: pre-wrap` 保留了换行符。

**修复**：
- `page.tsx` — 移除有缺陷的 lines 拆分/合并逻辑，简化为直接渲染 content
- `flow-chat-light.css` — `.flow-msg-user-text` 改为 `white-space: normal`

### 2. Conclusion Card Glass-Morphism 设计升级 ✅

**设计来源**：`uidesign/beautiful/conclusion_card2.html`

**变更**：
- `DimensionConclusionCard.tsx` — Header 结构改为 icon-box + title 布局
- `flow-chat-light.css` — 全面替换结论卡样式：
  - 卡片：glass 效果（`backdrop-filter: blur(24px)`，半透明白底，`border-radius: 20px`）
  - 移除左侧色条，改为整体 glass 效果
  - 每个阶段通过 `--cc-accent` CSS 变量自动取色
  - Tags：白底圆角胶囊，hover 放大效果
  - 主按钮：渐变背景 + 阴影，hover 上浮
  - 次按钮：半透明白底

### 3. Step 文案预留机制 ✅

**新文件**：`src/backend/app/domain/prompts/templates/step_copy.yaml`
- 定义每个阶段的 intro（开始文案）和 outro（结束文案）
- 支持 Markdown 格式
- 编辑此文件即可修改所有阶段的引导文案

**新函数**：`get_step_copy(phase, position)` — `src/backend/app/domain/prompts/loader.py`

**API 集成**：
- `POST /simple-chat/init` 响应增加 `step_intro` 字段
- `POST /simple-chat/thread/complete` 响应增加 `step_outro` 字段

### 4. 多 Journey 后端接口 ✅

**新端点**：`GET /simple-auth/journeys`
- 返回当前用户的所有激活码 + 进度摘要
- 按 `last_activity_at` 倒序排列
- 最近使用的标记 `is_latest: true`
- 清除浏览器缓存后仍可从此接口恢复

**响应格式**：
```json
{
  "journeys": [
    {
      "activation_code": "CODE",
      "mode": "values",
      "status": "active",
      "created_at": "...",
      "last_activity_at": "...",
      "explore_resume": {
        "resume_phase": "strengths",
        "unlocked_phases": ["values", "strengths"]
      },
      "is_latest": true
    }
  ]
}
```

---

## 待实现

（全部已完成）

---

### 5. 激活码自动跳转最新 Step + 多 Journey Dashboard ✅

**自动跳转**：已有机制正常工作 — 后端 `compute_explore_resume()` 返回 `resume_phase`，前端 `applyExploreResumeToSession()` 设置 `currentPhase`，`activate/page.tsx` 路由到对应 step。

**Dashboard 重写**：
- `src/frontend/app/(main)/dashboard/page.tsx` — 完全重写
- 调用 `GET /simple-auth/journeys` 从后端获取所有 Journey
- 最近使用的 Journey 显示为大卡片（featured），其余为小卡片
- 每个 Journey 显示 5 个阶段的进度圆圈
- 点击已解锁阶段直接跳转到对应 step
- 清除浏览器缓存后仍可从后端恢复

### 6. Rumination 完整 9 步 ✅

**后端变更** — `simple_chat_routes.py`：

新增 imports：
- `structure_hypothesis_round1_table`, `generate_hypotheses_round2_table`, `generate_hypotheses_round3_finalize`
- `value_filter`, `passion_filter`, `reality_filter`, `similar_filter`
- `fill_hypothesis_columns_for_table`（LLM 假设生成服务）

`rumination-table-submit` 端点（改为 async）：
- Step 1→2: filter_strength + filter_match（已有）
- Step 2→3: structure_hypothesis_round1_table + LLM fill_hypothesis_columns_for_table
- Step 3→4: generate_hypotheses_round2_table + LLM fill（only_empty_hypothesis_slots=True）
- Step 4→5: generate_hypotheses_round3_finalize（空行标记"待定"）
- Step 5→6: value_filter（移除"待定"，添加工作目的列）
- Step 6→7: passion_filter（移除"都不符合"，添加激情标记列）
- Step 7→8: reality_filter（移除"应该做"，添加现实标记列）
- Step 8→9: similar_filter（移除"未来"，保留最终假设）

`rumination-get-table` 端点（改为 async）：
- 先查快照（submitted/initial），有则直接返回
- 无快照时从前一步 submitted 动态生成（step 3/4 含 LLM 调用）

---

## 完整文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `src/frontend/app/(main)/explore/chat/[phase]/page.tsx` | 修改 | 用户气泡渲染逻辑简化 + isCacheStale import |
| `src/frontend/styles/components/flow-chat-light.css` | 修改 | 用户气泡 CSS + 结论卡 glass 设计 |
| `src/frontend/components/explore/DimensionConclusionCard.tsx` | 修改 | Header 结构改为 icon-box 布局 |
| `src/frontend/lib/explore/threads.ts` | 修改 | 添加 `isCacheStale`, `markSynced`, `clearThreadCache` |
| `src/frontend/app/(main)/dashboard/page.tsx` | 重写 | 多 Journey 展示，后端数据源 |
| `src/backend/app/domain/prompts/templates/step_copy.yaml` | 新增 | 阶段引导文案 |
| `src/backend/app/domain/prompts/loader.py` | 修改 | 添加 `get_step_copy()` |
| `src/backend/app/domain/prompts/__init__.py` | 修改 | 导出 `get_step_copy` |
| `src/backend/app/api/v1/simple_chat_routes.py` | 修改 | init/complete 增加 step_intro/outro + rumination 9 步完整逻辑 |
| `src/backend/app/api/v1/simple_auth.py` | 修改 | 新增 `GET /journeys` 端点 |

## 验证结果

- 后端测试：14 passed, 0 failed
- TypeScript 编译：无错误
- ESLint：无警告或错误
