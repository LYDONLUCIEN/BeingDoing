# 2026-10-05 chat 页面性能优化 Phase 1（完成记录）

## 背景

用户反馈老电脑进入 `/explore/chat/[phase]` 卡死。排查确认两层病因（合成层 + React 层），用户拍板：保持布局与审美、装饰动画全员移除、保留功能动效、先重灾区后推广。完整决策见 `docs/adr/0022-static-performance-skin.md`。

## 验证结论

软件渲染实测（headless 模拟老电脑，基线 → 改后）：

| 场景 | 平均帧耗时 | 帧率 | 掉帧(>32ms) |
|---|---|---|---|
| values 空闲 10s | 386.7ms → **16.6ms** | 2.6 → **60fps** | 25/26 → **0/602** |
| values 滚动 5s | 368ms → **16.6ms** | 2.7 → 60fps | 13/13 → 0/301 |
| 沉淀 空闲 10s | 170.3ms → **16.6ms** | 5.9 → 60fps | 57/59 → 0/602 |
| 沉淀 滚动 5s | 152.9ms → **16.6ms** | 6.5 → 60fps | 31/32 → 0/301 |

- 视觉：3 视口 × 4 状态前后截图对比一致（仅 blob 静止、磨砂略实）；截图存档 `/tmp/perf-shots/{baseline,after,final}/`（临时目录，重启丢失）
- 构建：`next build` ✓（临时副本验证，未动生产 `.next`）；chat 页 JS 1688KB → **690KB（-59%）**；tsc 仅剩 survey 页 1 个既有错误；lint 仅既有警告
- 真实流式全链路（发消息/停止/出卡）需登录态，留人工回归

## 改动清单

- `styles/components/bd-static-skin.css`（新增）：动画冻结（silk/flow/mesh blob、send-glow）+ 12 处 backdrop-filter→实色 + mask→父级渐变遮罩条 + loading-dot 功能动效
- `app/globals.css`：+1 import（置于最后）
- `app/(main)/explore/chat/[phase]/page.tsx`：ConclusionRow memo + O(n²)消除（aiLogIndexById 单遍 Map）+ SSE chunk rAF 批量提交（retrying/结论卡/done/finally 四处先 flush，中断不丢尾部）+ 滚动跟随并入 rAF + 侧栏解耦（threads + 3 个原始值）+ 去 framer-motion（loading 三点改 CSS）
- `components/explore/FlowAiMessage.tsx` / `MessageContent.tsx`：memo；onSavepoint(messageId) 化
- `components/explore/ChatPhaseSidebar.tsx`：memo + activePreview/activeTurnCount/activeLastAt 可选 props + 删除确认遮罩实色
- `lib/explore/sidebarMeta.ts`（新增）：侧栏预览/元信息共用计算
- `components/explore/ruminationV4/`（7 文件）：zustand 整店订阅→窄选择器；V4ChatPanel 单遍 logIndex + MessageRow memo + streamStartRef + 滚动 rAF 节流；3 处内联 backdropFilter 移除

## 审计后修正（同日）

独立审计复检 4 项疑点，实测核验（Playwright 读 DOM computed style）：

1. ❌ 不成立：「顶栏实色被 journey !important 压掉」——journey 616-623 无 !important，实测 `rgba(251,252,251,0.88)` + `backdrop-filter:none` 生效
2. ❌ 不成立（chat 页）：输入区在 `.flow-chat-box` 外（实测 `dockInsideBox=false`）
3. ✅ 成立（V4）：`V4ChatPanel.tsx:173` 的 box 内含 `.careering-input-dock`，`::after`（z-index:1）蒙在输入区上 → 修复：skin 增加 `.rumination-beautiful-root .careering-input-dock { position: relative; z-index: 2; }`，复测 60fps 维持
4. ❌ 不成立：top fade 2rem 与原 mask 渐隐范围一致

## 后续 Phase 2 待办

1. dashboard：4× `ol-profile-glow`（blur78 28s 无限）冻结 + 磨砂卡实色（fallback 模板 openlife-profile.css:421-423）
2. 首页：植物呼吸/光晕/玻璃卡 + blur30 条带（fallback reference-home:1597-1609）
3. 全站外壳：TopNavbar blur16、反馈浮窗抽屉 blur28
4. report view：PaperVeilLayers 叠层核查
5. activate/transition：磨砂栈
6. admin「动效暂停」开关文案更新（视觉上已失效）
7. 真实流式全链路人工回归（需登录态）
