# 0922 沉淀页（rumination v4）视觉对齐 + guided 左栏改造

> 日期：2026-09-22（0923 反馈修复轮见文末）
> 分支：`newui`
> 方式：grill-me 拷问（5 个决策点全部用户拍板，见 `0919/迁移决策记录.md` 0922 轮）
> 视觉准绳：`wiki/开发文档/0919/openlife-journey (21).html` + `0919/OpenLife-UI-Design-System.md`

## 用户反馈的 4 个问题与根因

| # | 反馈 | 根因 |
|---|---|---|
| 1 | 新建组合/完成并继续/05沉淀 与前 4 phase 不对齐 | 标题 24/32px vs 前4的 19px；按钮 font-bold+无右箭头+内联渐变；新建组合用蓝色（价值观阶段色） |
| 2 | 看不出紫色、背景不漂亮 | HTML 矩阵默认紫但实现默认 duo（用户拍板保留 duo）；卡片白度 0.58–0.72+blur18 偏闷；HTML 的四色流光 `.rumination-flow` 未实现；backdrop 暖纸 linear 0.68–0.88 罩死 |
| 3 | 选择矩阵纯平面 | 矩阵卡 `bg-white/70` 无质感；结论卡 3D = 对角渐变+顶部 inset 高光+分层阴影 |
| 4 | 左栏组合块看不到已选 tags | 单行截断文本 `热爱 × 优势1、优势2`，220px 窄栏 |

## 拍板决策（5 条）

1. 标题 19px + 保留副标题（13px muted）+ ✦ 保留
2. 毛玻璃按 HTML 还原：对话卡白度 0.55 / 左栏 0.45、blur 12、补四色淡流光 + 紫色 radial 主导
3. 矩阵默认配色**保持 duo**（珊瑚×雾蓝，用户拍板不改紫）；紫色靠背景/按钮/左栏体现
4. 左栏 chips 用**中性白底细边 + 紫编号**（遵守"一屏一个色彩上下文"）
5. **guided 三栏设为默认布局**（含存量迁移）

## 改动清单

### 组件
- `RuminationV4Page.tsx`
  - h1 24/32px → 19px（衬线 600、`var(--journey-ink)`），副标题去 sm:16px 固定 13px
  - 完成并继续：统一 `bd-btn-black` 同款（深墨、font-semibold、FileText 15 + ChevronRight 16、去内联渐变；`data-action-style='theme'` 紫色变体仍生效）
  - backdrop 新增 `.rumination-flow` 四色 blob 层（柔和淡彩 #9fcaff/#acead4/#ffc8d1/#ffe6a6，30s 错相漂移）
  - guided 选择器宽度 calc 244→262px（侧栏 238+间距 24）
- `V4ComboSidebar.tsx`（重写）
  - 220→238px；白度 0.70→0.45 + blur 12
  - 每块：紫编号 + chips 直出（热爱紫调细边 + 优势中性白底，flex-wrap 全显示）+ 状态 meta 行（已有结论/已搁置/探讨中·N轮/待探索；轮次=assistant 消息数）
  - min-height 74px；激活态白 96% + 紫描边 rgba(111,82,199,.4)；focus-visible 紫环
  - 新建组合：蓝 → 紫虚线（#cdbdf2/#6f52c7）；删除二次确认/终选环/键盘交互全保留
- `TopComboBar.tsx`：新建组合同步紫虚线（去 teal #008ea7）
- `V4ComboMatrixSelector.tsx`：默认态去 bg/shadow 内联类，交给 CSS 层
- `chatAppearanceStore.ts`：`ruminationLayout` 默认 'classic'→'guided'；persist version 1→2，migrate 把存量 'classic' 一并升级（旧默认值无法与显式选择区分，可在面板切回）

### CSS
- `openlife-journey.css`
  - `.journey-rumination-header` 加前4同款毛玻璃底（白 0.34 + blur 12）
  - backdrop `::before`：暖纸罩 0.68/0.88 → 0.30/0.42、紫 radial 0.14→0.18（透出色彩）
  - 新增 `.rumination-flow` 容器（opacity= 晕染滑杆×1.6≈HTML 0.35）+ 4 blob + 4 组 drift keyframes（复刻 HTML 数值）
  - `.rumination-beautiful-card` 白度 0.72→0.55、blur 18→12
- `openlife-chat-defaults.css`
  - root 紫 radial 0.11→0.14；卡片 0.58→0.55、blur 12
  - 新增 `.choice-card` 3D 基础质感（对角渐变浅底 + inset 顶部高光 + 分层阴影）+ hover 抬升阴影（`:not(.selected):not(:disabled)`）
- `openlife-chat-appearance.css`
  - duo soft 选中态阴影补 inset 顶部高光（与 3D 同款）
  - `data-background='tint'` 隐藏流光；`data-motion='off'`/`prefers-reduced-motion` 暂停/关闭流光动画

## 边界遵守

- 未动任何 API/状态机/store 业务逻辑（仅外观 store 默认值+迁移）
- backdrop-filter 均带 -webkit- 前缀；color-mix 规则保留静态回退
- 页面级作用域（.rumination-v4-root / .rumination-journey-backdrop 前缀），未触碰首页/支付
- 流光遵循设计系统：中心留白、blob 全部贴边、`prefers-reduced-motion` 停用

## 验收

- `git diff --check` ✓、`npm run lint` ✓（仅存量 warning）、`npm run build` ✓
- 编译产物抽查：流光 blob/3D 卡/玻璃 0.55 规则均已进入 chunk（.next 为 dev+prod 混写，按 chunk 内容抽查）
- 视觉验收：dev 服务热更新，用户硬刷新 `/explore/chat/rumination` 确认（guided 已设默认；老 localStorage 存量自动迁移）

## 0923 反馈修复轮（结构对齐，用户验收 0922 后提出）

用户反馈：①新建组合应属左侧、外层 div.v4-outer-shell 建议删掉、层级太多；②对话卡应是画面主体、整体颜色仍看不见；③选择矩阵内容应在最上层、左栏白 chips 不好看。

**根因（0922 遗漏的两个大罩子）：**
- `.v4-outer-shell` = 整页玻璃罩（白 0.66 + blur22）——设计系统明令"禁止整页大磨砂玻璃"，0922 只减薄了卡片没动它，流光全被闷死
- `.v4-inner-pane`（白 0.74）+ V4MatrixLeftPanel 两层面板（白 0.46）再叠三层（玻璃套玻璃）
- `rumination-journey-ribbon` 照片纹理 0.55 不透明度整页铺盖（HTML rumination 无此层）

**改动：**

| 文件 | 改动 |
|---|---|
| `RuminationV4Page.tsx`（重构） | guided 分支：V4ComboSidebar 直接挂根级（全高左栏），内容列 = header + 对话卡（flex-1 主体）+ 透明选择器列 + 收拢条；**不再渲染 outer-shell / inner-pane / ribbon**。classic（备选）保留原壳结构（mist/folio/modules/editorial 皮肤依赖）。共享节点（header/banner/selector/collapse/chat）提取为 JSX 常量，两分支零重复。workbenchRef 双分支挂载，ResizeObserver effect deps 补 `ruminationLayout` |
| `V4ComboSidebar.tsx` | 浮动圆角卡 → 全高扁平左栏（`border-r` + 白 0.45 + 无 blur，同 HTML .sidebar/前四阶段侧栏）；chips 白底 → **duo 色**（热爱 `#fdeef1`/`#c8455a` × 优势 `#eef3fd`/`#3569d4`，与矩阵选中态同源） |
| `V4MatrixLeftPanel.tsx` | 两层面板 div（白 0.46 + 边框 + 阴影）→ 纯布局透明容器；选择卡/结论卡自带表面直接落在流光背景上（矩阵层级 4→1） |
| `openlife-journey.css` | workbench/toolbar 宽度覆盖 `calc(100%-24px)` 排除 guided（右缘对齐修复） |
| `rumination-beautiful.css` | 小高度媒体查询删 `hero h1{font-size:24px}`（保持 19px 对齐前四阶段） |

验收：`git diff --check` ✓ `npm run lint` ✓ `npm run build` ✓（0923）
