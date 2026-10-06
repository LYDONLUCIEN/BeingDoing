# ADR-0022: 静态性能皮肤——装饰动画与磨砂玻璃对全员移除

**状态**: accepted
**日期**: 2026-10-05
**决策者**: 开发（用户确认范围与边界）
**范围**: explore chat 前四阶段 + 沉淀 V4（Phase 1）；dashboard/首页/全站外壳留待 Phase 2

## 背景与动机

用户反馈老电脑（集显/驱动旧回退软件合成）进入 `/explore/chat/[phase]` 直接卡死。排查确认两层病因：

1. **合成层**：3×80vw `blur(120px)` silk blob 无限旋转（38s）+ 侧栏/结论卡/输入框等 12 处 `backdrop-filter`（12~24px）叠在动画背景上——页面空闲时合成器也满负荷逐帧重采样；滚动容器还挂 `mask-image`。headless 软件渲染实测（模拟老电脑）：values 页空闲平均帧 386ms（≈2.6fps）、沉淀 170ms（≈5.9fps），掉帧率 ~100%。
2. **React 层**：每个 SSE chunk 触发整页 `setMessages` → 全部历史消息 markdown 重新 parse（`@uiw/react-markdown-preview` 无 memo）；render 内 O(n²)（`findIndex` + `slice+filter`）；侧栏随 `messages` 逐 chunk 重渲染。V4 另有 7 个组件无 selector 整店订阅 `ruminationV4Store`。

## 决策

1. **装饰动画对全员冻结，不做设备检测分档**。理由：用户无法在真机上逐档对比视觉，统一静态最可控；blob 旋转周期 25~38s 本就难以察觉，冻结在 keyframe 0% 位（=布局位）视觉无损。功能性状态动效（思考呼吸点、加载转圈、重试脉冲、庆祝粒子）**保留**。
2. **backdrop-filter 一律换视觉等价半透明实色**（近白纸底上 `α'≈α+(1-α)·0.85`）。只删动画不够：动画停了磨砂仍在逐帧重采样背景，这是空闲掉帧的根源。
3. **实现收口在单一覆盖文件** `styles/components/bd-static-skin.css`（globals.css 最后一个 import），沿用项目分层覆盖惯例；不在 6 个源 CSS 里散改。
4. **不做 `data-motion` 门控**：admin「动效暂停」开关保留但不再控制背景 blob（对全员冻结），后续可改文案。
5. **滚动容器 mask 换父级渐变遮罩条**（`.flow-chat-box::before/::after`，`pointer-events:none`）；V4 输入区在 box 内部，需 `z-index:2` 提到遮罩之上。
6. **React 层**：`FlowAiMessage`/`MessageContent`/`ConclusionRow`/`MessageRow`/`ChatPhaseSidebar` memo 化 + props 稳定化（单遍 logIndex Map、ref 桥接回调）；SSE chunk rAF 批量提交（每帧最多一次 setMessages，`retrying`/结论卡/`done`/`finally` 四处先 flush 再走原逻辑，保证中断流式不丢尾部）；V4 store 全部改窄选择器。

## 验证结论（2026-10-05）

软件渲染实测：空闲/滚动全部 2.6~5.9fps → **稳定 60fps（16.6ms/帧）、掉帧≈0**；前后截图对比（3 视口×4 状态）布局/配色/质感一致，仅 blob 静止与磨砂略实；chat 页 JS 1688KB → 690KB（-59%，framer-motion 移出）。

## 后果

- admin「动效暂停」开关视觉上失效（见决策 4）。
- 磨砂面通透度略降（0.68+blur24 → 0.94 实色量级），感知差异微小。
- 后续任何「去动画」清理不得触碰 skin 文件第 4 节功能动效清单。
- Phase 2 追加对象：dashboard `ol-profile-glow`、首页植物呼吸/玻璃卡、全站导航与反馈浮窗磨砂、report view PaperVeilLayers 叠层、activate/transition 磨砂栈。
