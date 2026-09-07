# ADR-0020: 旧浏览器内核兼容底线——视口高度 vh→dvh 回退与新 CSS 特性静态回退

**状态**: accepted
**日期**: 2026-09-06
**决策者**: 产品 + 开发 Grill

## 背景

收到用户反馈：使用搜狗浏览器时 rumination 页面布局错乱、「完成并继续」无法点击，而其他浏览器正常。无一手复现环境（无截图/console），走 v4 链路。静态排查确认根因方向：

1. **裸写 `100dvh` 无回退（根因，可信度最高）**：`chat/[phase]/page.tsx` 的 rumination v3/v4 外壳及全部 chat 阶段外壳使用 `h-[calc(100dvh-3.5rem)] max-h-[calc(100dvh-3.5rem)]`。`dvh` 需 Chrome 108+，旧内核（搜狗/360/QQ 双核浏览器的高速模式常为旧 Chromium）直接丢弃整条 height 声明 → 外壳高度变 auto → 内部 `min-h-0 flex-1 overflow-hidden` 链失去约束 → 布局塌陷、按钮被挤出可视区。
2. **`color-mix()` 无回退**：flow-chat-light.css 四阶段用户气泡 + rumination 气泡渐变（需 Chrome 111+），旧内核气泡底色/描边整个声明失效（纯视觉）。
3. **内联 `backdropFilter` 无 `-webkit-` 前缀**：RuminationV4Page 外壳与 V4FinalSelectionModal 两处（React 内联样式不会自动加前缀；老 WebKit 毛玻璃失效，纯视觉）。
4. 项目整体无 `browserslist` 配置、无 polyfill、无浏览器检测——兼容策略是隐式假设现代 Chrome。

次要嫌疑（未证实，保留观察）：V4IntroModal（z-[230] 全屏遮罩）若在异常状态下无法关闭会挡住所有点击；v3 `canContinue` 依赖后端同步完成，SSE 异常时按钮常灰。

## 决策

- **修复口径：兼容修复 + 旧内核检测提示双轨**（2026-09-06 产品拍板）。不建 browserslist/polyfill 等系统性工程。目标：现代浏览器效果**零变化**（纯 CSS 双声明回退，新浏览器稳定命中后者）；旧内核「可用、不错乱」+ 明确引导换浏览器。
- **支持矩阵**：承诺主流现代浏览器（Chrome/Edge/Safari/Firefox 近两年版本）完整体验；搜狗/360/QQ 等国产双核浏览器高速模式（旧 Chromium）保证功能可用并弹窗引导；IE 及双核 IE 兼容模式不支持应用运行（Next.js 14 本身不支持），但提供静态提示层避免白屏无提示。
- **检测方式：特性检测而非 UA 嗅探**（`lib/utils/browserCompat.ts`）——双核浏览器 UA 不可靠且可切换内核，直接探测硬依赖特性：不支持 `dvh`（Chrome 108+）或 `color-mix`（Chrome 111+）即判定旧内核。SSR 返回 false，客户端水合后判定，避免误报闪烁。
- **提示弹窗 `LegacyBrowserNotice`**：挂载在首页 `(main)/page.tsx` 与 chat 页（values → rumination 各 phase 共用组件，v4 分支与通用分支均挂载），「不再提示」前每个入口页都会弹；「我知道了」仅关本次。持久化用 **localStorage（浏览器维度）**而非账号 preferences——提示针对的是当前浏览器，换浏览器应重新检测。z-[250] 盖过页面其他弹层（V4IntroModal z-[230]）。
- **IE/极老内核静态兑底**：React bundle 在 IE 模式根本无法解析执行，检测弹窗无从谈起——在 root `app/layout.tsx` head 加 ES5 内联脚本（IE 条件注释 + `document.documentMode` + `Promise` 三重检测），命中即插全屏静态提示层（纯 DOM，不用 flex 等新特性），引导切高速模式或换 Edge/Chrome。现代浏览器此脚本为空操作。
- **规范（后续新增代码必须遵守）**：
  1. 视口高度一律用 `.chat-shell-h`（`flow-chat-light.css`，vh 在前 dvh 在后），禁止在 TSX 裸写 `h-[calc(100dvh-…)]` / `svh` / `lvh`。
  2. 新 CSS 特性（`color-mix`、`oklch`、`:has()` 等）必须在同规则内先写一条静态近似值回退，再写新特性声明（不支持的浏览器丢弃后者，自动落到前者）。
  3. 内联样式写 `backdropFilter` 时必须同时写 `WebkitBackdropFilter`。

## 实现

- `styles/components/flow-chat-light.css`：新增 `.chat-shell-h`（`100vh` → `100dvh` 双声明覆盖）；values/strengths/interests/purpose/rumination 五组用户气泡的 `background`/`border-color` 各加静态近似色回退（按 color-mix 比例手算近似 hex）。
- `styles/components/rumination-beautiful.css`：rumination 气泡渐变加静态近似渐变回退。
- `app/(main)/explore/chat/[phase]/page.tsx`：4 处 `h-[calc(100dvh-3.5rem)] max-h-[calc(100dvh-3.5rem)]` 全部替换为 `.chat-shell-h`（覆盖 v4 外壳、v3 外壳、版本判定 loading 态、非 rumination 各阶段外壳）。
- `ruminationV4/RuminationV4Page.tsx`、`V4FinalSelectionModal.tsx`：内联 `backdropFilter` 补 `WebkitBackdropFilter`。
- **检测与提示（2026-09-06 追加）**：`lib/utils/browserCompat.ts`（特性检测 + localStorage 不再提示）；`components/layout/LegacyBrowserNotice.tsx`（弹窗，样式同 TeamAnalysisNoticeModal）；挂载点 `app/(main)/page.tsx`（首页）、`explore/chat/[phase]/page.tsx`（v4 分支 + 通用分支，覆盖 values→rumination 全部 phase）；`app/layout.tsx` head ES5 静态兑底脚本（IE/无 Promise 环境）。
- 验证：`npx tsc --noEmit` 通过；全仓 grep 确认 TSX 中无残留裸 `dvh`；headless Chrome 实测检测逻辑（现代内核 `legacy=false`，弹窗与 IE 脚本均不触发）；ES5 脚本过 `node --check` 语法校验。

## 备注

- 「不再提示」存 localStorage（`bd-legacy-browser-dismissed`），隐私模式写入失败时降级为本次会话仍提示。
- 已知代价：移动端旧内核落 `100vh` 时地址栏可能遮底部几十 px（桌面无此问题）；气泡静态回退色为手算近似值，主题改版需同步更新回退色（详见与本文同日的会话记录）。
- 复现/验收建议：Windows 虚拟机装搜狗高速浏览器旧版，或在 Chrome DevTools 删 CSS 中 dvh 行模拟旧内核布局；检测弹窗可通过 DevTools 覆盖 `CSS.supports` 后刷新验证。
