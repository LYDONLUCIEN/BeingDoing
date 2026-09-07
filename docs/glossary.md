# 术语表（Glossary）

> 跨文档共享的领域/技术术语定义，按拼音排序。新增 ADR 引入的术语应同步补充到这里。

## L

- **dvh / svh / lvh（动态视口单位）**：CSS 视口高度单位。`dvh` 随移动端地址栏伸缩动态变化，`svh` 取最小、`lvh` 取最大。需 Chrome 108+；旧内核不识别时会**丢弃整条 CSS 声明**（不是按 100vh 解析），因此必须在前写 `vh` 回退（见 `.chat-shell-h`，ADR-0020）。
- **color-mix()**：CSS 颜色混合函数（如 `color-mix(in srgb, red 40%, white)`），需 Chrome 111+。不支持的浏览器丢弃整条声明，需静态近似色回退（ADR-0020）。

## R

- **Rumination（沉淀阶段）**：探索流程的最后一个阶段，用户从「热爱 × 优势」组合中做最终方向选择。线上存在 v3（旧版，`RuminationTableWidget` 体系）与 v4（新版，`ruminationV4/` 组件体系）两个版本，由后端 `rumination_ab_assignments` 表 AB 分流，`?v4=1`/`?v3=1` 可调试覆盖。

## S

- **双核浏览器**：国产浏览器（搜狗/360/QQ 等）同时具备 Chromium 内核（「高速模式」）与 IE 内核（「兼容模式」）并自动/手动切换。高速模式内核版本可能显著落后于同期 Chrome（触发 ADR-0020 的兼容问题）；IE 兼容模式本项目不支持（Next.js 14 不含 IE 转译），由 root layout 的 ES5 内联脚本提供静态提示层避免白屏无提示。
- **`.chat-shell-h`**：探索/沉淀页外壳高度类（`flow-chat-light.css`），封装 `100vh → 100dvh` 回退，是所有 chat 阶段外壳高度的唯一合法写法（ADR-0020）。

## T

- **特性检测（feature detection）**：通过 `CSS.supports()` 等 API 直接探测浏览器是否支持某特性，而非解析 UA 字符串推断。本项目旧内核判定用特性检测（dvh + color-mix，见 `lib/utils/browserCompat.ts`），因为双核浏览器 UA 不可靠且内核可切换。

## W

- **完整码 / 试用码（full / trial）**：激活码两档（ADR-0008）。试用码注册即送、不过期、仅 values 阶段限 10 轮；完整码解锁全阶段。可消耗 1 个未绑定完整码把试用码原地升级（ADR-0014）。
