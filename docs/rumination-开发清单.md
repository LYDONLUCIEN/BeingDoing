# Rumination（第 5 步）开发清单

> 配合：[rumination-左右分栏-开发计划.md](./rumination-左右分栏-开发计划.md)  
> 目标：**左右分栏 UI** + **每个激活码下 rumination 仅一条对话线程（历史只展示最新，未来只维护一条）**

---

## 一、布局与视觉（左右版本）

- [ ] **`page.tsx`**：`phase === 'rumination'` 时走独立布局分支，**不再**与 values～purpose 共用「侧栏 + 单栏消息流」骨架。
- [ ] **隐藏或收缩** `ChatPhaseSidebar`（rumination 专用：避免左侧再占一列线程列表；线程策略见第三节）。
- [ ] **主体 `flex-row`**：`min-h-0`，左栏固定比例（如 42%～48%）+ 右栏 `flex-1`。
- [ ] **左栏**：毛玻璃卡片承载 `RuminationTableWidget`（或拆出的 Workbench）；表内/底部 **Confirm**；`overflow-auto`。
- [ ] **右栏**：仅用户/AI 文本气泡 + 输入区；**表格不再作为 `table_widget` 消息插入竖向时间线**。
- [ ] **状态**：`tablePayload` 用独立 `useState`（来自 `getTable` / `submitTable` 的 `next_table_widget`），与 `messages` 解耦（见开发计划阶段 B）。
- [ ] **`flow-chat-light.css`**：右栏气泡左右留白、避免贴边；左栏毛玻璃厚度与设计稿对齐。
- [ ] **（可选）** 标题区下 **6 步渐变进度条**（蓝→红），与 `filter_step` / 产品 6 段映射一致。

---

## 二、数据流与表格（避免「多条表格消息」）

- [ ] 初始化：`ruminationApi.getTable` 结果写入 **`tablePayload` state**，不依赖 `messages` 里找 `table_widget`。
- [ ] 确认：`handleTableConfirm` 成功后仅用接口返回的 **`next_table_widget` 更新 `tablePayload`**。
- [ ] **停止** 向 `messages` 追加 `type: 'table_widget'` 的新消息（或兼容：启动时从旧数据迁移一条到 state 后删除消息中的表格块）。
- [ ] 流式 SSE 若仍下发 `table_widget`：在 rumination 分支 **只更新 `tablePayload`**，不 `push` 到 `messages`。

---

## 三、仅一条 rumination 线程（前端 localStorage + 交互）

**现状问题**：[`page.tsx`](../src/frontend/app/(main)/explore/chat/[phase]/page.tsx) 中 `canCreateMoreThreads = !stepLocked && (adminDebugBypass || threads.length < 5)` 对 **所有阶段** 生效，沉淀阶段仍可多达 **5 条线程**，侧栏会列出多条 → 与「只维护一条」冲突。

- [ ] **`canCreateMoreThreads`**：当 `phase === 'rumination'` 时固定为 **`false`**（超级管理员调试若需多线程，可单独 `adminDebugBypass && ...` 再议）。
- [ ] **`handleNewChat`**（及同类入口）：`rumination` 阶段 **直接 return** 或 toast「沉淀阶段仅支持单条对话」。
- [ ] **hydrate / 与后端同步线程列表后**：对 `rumination` 做 **归一**：
  - 若 `threads.length > 1`：按 **最后活动时间 `updatedAt` / `createdAt` 最大** 保留 **1 条**，其余从 [`setThreadsForPhase`](../src/frontend/lib/explore/threads.ts) 写入的列表中 **删除**。
  - `setActiveThreadId` 指向保留的那条。
- [ ] **一次性迁移**（可选函数 `normalizeRuminationThreads(code)`）：在 `rumination` 页 `useEffect` 首屏执行，写回 `explore_threads_${code}`，避免老用户长期看到多条。
- [ ] **侧栏**：rumination 若隐藏侧栏，则「切换线程」入口自然消失；若保留窄条，只展示 **当前一条** 且无「新对话」按钮。

---

## 四、仅一条 rumination 会话（后端 / report，与未来写入一致）

**目标**：同一 `(activation_code, user_id)` 下，`record.json` 的 `rumination` 步骤 **`session_ids` 长期只保留一个主会话**（或「最新」覆盖策略）。

- [ ] **盘点写入路径**：[`simple_chat.py`](../src/backend/app/api/v1/simple_chat.py) 中 rumination 流式/开线程时是否 **`bind_session(..., 'rumination', new_id)`** 不断追加。
- [ ] **策略（二选一或组合）**：
  - **A**：新开 rumination 线程前，若已有 `session_ids`，则 **不再新增**，始终复用 `selected_session_id` 或 `session_ids[0]`。
  - **B**：允许历史上多条，但在 **ensure_report / 进入 rumination** 时 **合并为一条**（清掉多余 `session_ids`，仅保留最新；需评估是否影响旧文件路径）。
- [ ] 与已有 [`ReportRegistry`](../src/backend/app/utils/report_registry.py) 的 `bind_session` 跨 report 校验兼容，避免误绑到其他激活码。

---

## 五、验收标准（自测勾选）

- [ ] 进入沉淀页：**肉眼可见** 左表右聊（非侧栏+中间混排表格）。
- [ ] 同一激活码：侧栏或存储中 **看不到第二条** rumination 线程；刷新后仍为一条。
- [ ] `localStorage` `explore_threads_<code>` 中 `rumination` 数组 **长度 ≤ 1**（归一后）。
- [ ] 表格确认后：左表更新，右栏 **不出现第二块** 重复表格消息。
- [ ] （若做后端单会话）新对话请求 **不增加** `rumination` 的 `session_ids` 条目数。

---

## 六、与「restore 恢复错了」的关系说明

- Git **restore 只会恢复文件内容**，不会自动实现「左右布局」；若 `page.tsx` 仍是通用布局，**属实现未做，不是 restore 回滚错布局**。
- 若曾出现 **文件缺失**，restore 后应已与 `origin/main` 一致；**本清单第一节～第三节** 仍需按产品补开发。

---

## 七、建议实现顺序

1. 第三节（单线程 + 归一）— 改动面小、立刻减少「多条沉淀」困惑。  
2. 第二节（表格与消息解耦）— 避免多条 `table_widget` 消息。  
3. 第一节（左右分栏壳 + 左表右聊）— 视觉与信息架构对齐设计稿。  
4. 第四节（后端单 `session_id`）— 与前端策略对齐后做。

---

*清单可随时把 `[ ]` 改为 `[x]` 跟踪进度；需要拆 issue 时可按「节」建 ticket。*
