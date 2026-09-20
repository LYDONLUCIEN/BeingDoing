# OpenLife New UI 设计范式与实现标准

> 文档版本：1.0
>
> 更新日期：2026-09-19
>
> 适用分支：`newui` 及后续合并分支
>
> 状态：当前 UI 实现的基准文档（Source of Truth）

## 1. 文档目的

本文件统一 OpenLife 新版首页、探索流程、Chat、Rumination 与个人空间的视觉语言和实现边界。它解决三个问题：

1. 后续页面知道应该复用哪一种视觉范式；
2. 视觉改造不会误伤既有接口、支付、数据与业务状态机；
3. 设计稿、HTML 参考稿和真实产品不一致时，有明确的取舍顺序。

历史配色文档仍可用于理解阶段色来源，但不再作为当前页面布局和组件样式的唯一依据。

## 2. 决策优先级与不可破坏边界

### 2.1 决策优先级

当参考 HTML 与真实产品不一致时，按以下顺序处理：

1. 真实产品的业务功能、数据内容与后端接口；
2. 当前已经上线或已验证的交互逻辑；
3. 本文规定的视觉范式；
4. 外部 HTML 或网站参考稿的视觉表达。

参考稿多出的功能不得直接接入或伪造后端能力。可以复刻视觉入口，但必须标记“开发中”或先确认产品决策。

### 2.2 不可破坏边界

- UI 任务默认只改展示、布局、动画和必要的前端交互反馈。
- 不因视觉改造改变 API 参数、鉴权、存档、恢复、结论生成或报告数据结构。
- Rumination 必须保留当前“组合选择 → 解锁 → 对话 → 结论”的布局与状态逻辑。
- 个人空间必须保留所有现有服务入口，不能因为参考稿缺少入口而删除真实功能。
- 支付模块单独维护。没有明确需求时，不复刻参考 HTML 的支付界面，也不改支付逻辑与购买弹窗。
- 首页、Chat、个人空间采用页面级作用域样式；修改其中一处时不得依靠无作用域的全局选择器影响其他页面。

## 3. 品牌视觉语言

OpenLife 的新版 UI 关键词是：安静、温和、有依据、带有呼吸感。

- 页面背景：接近白色的冷暖纸张底色，叠加低透明度阶段色光晕。
- 卡片：半透明磨砂表面、细描边、顶部高光和非常克制的投影。
- 文字：深墨色用于核心内容，灰蓝色用于说明文字，不使用大面积纯黑。
- 圆角：信息卡通常为 `16–22px`，主要按钮和标签使用胶囊圆角。
- 层级：主要依靠留白、透明度、描边与轻阴影建立，不依靠厚重色块。
- 装饰：线稿、植物、纸张纹理和光晕只用于氛围，不得遮挡文字和交互区域。

## 4. 颜色与阶段语义

### 4.1 核心中性色

| 角色 | 建议值 | 用途 |
|---|---|---|
| 深墨 | `#202832` | 用户气泡、主操作、关键标题 |
| 主文字 | `#24313E` / `#273540` | 正文与个人空间标题 |
| 次级文字 | `#72808D` / `#84919D` | 说明、时间、辅助信息 |
| 页面底色 | `#F8FAFB` | 个人空间与浅色页面基础 |
| 白色表面 | `rgba(255,255,255,.56–.82)` | 磨砂卡片和浮层 |
| 细描边 | `rgba(211,221,228,.78–.90)` | 卡片、输入框与分区 |

### 4.2 阶段色

| 阶段 | 语义 | 主色 | 柔和底色 |
|---|---|---|---|
| 价值观 Values | 冷静、清晰、坚定 | `#6FAEE0` | `#F1F7FC` |
| 优势 Strengths | 能力、成长、轻松发挥 | `#83C290` | `#F2F9F3` |
| 热爱 Interests | 热情、投入、生命力 | `#EF837E` | `#FDF2F1` |
| 使命 Purpose | 方向、照亮、指引 | `#F4C062` | `#FEF8F0` |
| 沉淀 Rumination | 内省、组合、汇聚 | `#967DDB` | `#F3EFFC` |

阶段色用于光晕、边框、状态点、标签和结论卡渐层，不应用作大面积高饱和背景。

## 5. 通用组件范式

### 5.1 磨砂卡片

标准卡片应同时具备：

- 半透明浅色背景；
- `1px` 低对比度描边；
- `inset 0 1px` 白色高光；
- 柔和向下投影；
- `backdrop-filter` 与 `-webkit-backdrop-filter`；
- 静态背景回退，确保不支持毛玻璃时仍可阅读。

禁止只依赖高透明度或强模糊制造质感。内容对比度与可读性优先。

### 5.2 按钮

- 主要操作：深墨背景、白字、胶囊轮廓、轻投影。
- 次要操作：半透明白底、灰色描边、深灰文字。
- 危险操作：仅在注销、删除等真实危险行为中使用红色。
- Hover：最多上移 `1–2px` 并增强阴影；不要大幅缩放。
- Disabled：降低透明度且移除悬浮位移与阴影。

### 5.3 标签和状态

- 标签默认使用柔和胶囊形态：`border-radius: 999px`。
- 可用 `4–6px` 圆点表达阶段或状态色。
- 标签只承担索引与状态，不做主要按钮。
- 文本过长时优先换行或省略，不能撑破卡片。

### 5.4 输入框与弹窗

- 输入框使用白色或半透明白色表面，焦点态以阶段色细边框和低透明度光圈提示。
- 弹窗必须包含：明确标题、关闭按钮、遮罩、键盘可访问的表单控件和清晰的主次操作。
- 文字型内容弹窗沿用统一磨砂卡片，不为每类文档创造新的视觉体系。

## 6. 页面级规范

### 6.1 首页

- 首页负责品牌叙事，可以使用更丰富的滚动动画、报告预览扇形动画和轻量自动高亮。
- 报告预览使用三张独立图片素材，不直接把 Base64 放在源码中。
- 用户评价卡尺寸统一，Hover 时允许轻微抬升和阴影变化。
- 参考文献、常见问题、用户评价等大区块使用一致的磨砂边框语言。
- 参考文献标题和摘要属于真实内容，视觉参考稿缺失的内容不能反向覆盖产品内容。
- FAQ 的展开符号必须视觉居中，并有清晰的 `+ / ×` 状态。
- 首页改动必须与 Chat 和个人空间样式隔离。

### 6.2 激活与探索入口

- 延续首页的浅色纸张、植物与路径意象。
- 激活码输入与产品真实绑定接口对接，不新增参考稿中不存在的业务能力。
- 页面只能帮助用户理解下一步，不能修改激活码验证、绑定或跳转逻辑。

### 6.3 Chat 默认主题

Chat 默认组合固定为：

- 背景：浅色阶段主题背景；
- AI 回复：阶段色混入约 `10%` 的浅色气泡，细描边，无硬质左侧色条；
- 用户消息：深墨 `#202832` 气泡，浅色文字；
- 发送按钮：深墨底、白色图标；
- 结论卡：当前阶段色的柔和渐层；
- 标签：阶段色柔和胶囊；
- 输入区：浅色悬浮输入胶囊，保持清晰焦点态。

Chat 的展示规则集中在：

- `src/frontend/styles/components/flow-chat-light.css`
- `src/frontend/styles/components/careering-chat-matte.css`
- `src/frontend/styles/components/openlife-chat-defaults.css`

其中 `openlife-chat-defaults.css` 是当前 New UI 的最终视觉覆盖层，必须保持页面作用域。

### 6.4 Rumination

Rumination 沿用 Chat 的深墨用户气泡、浅色 AI 气泡与深墨发送按钮，同时使用紫色内省主题。

必须保留：

- 当前 V4 组合矩阵；
- 组合解锁条件；
- 左右工作区结构；
- 对话与结论的状态机；
- 草稿、提交、重试、证据判断等现有逻辑。

允许调整：背景、卡片透明度、描边、阴影、气泡、结论卡渐层、标签和响应式视觉。

### 6.5 个人空间

个人空间的定位是“安静的个人档案”，不是传统后台管理系统。

- 桌面端采用约 `238px` 的侧栏与内容区布局；侧栏可吸顶。
- 手机和平板切换为横向滚动导航，避免压缩菜单文字。
- 所有真实服务入口必须保留：当前进度、使用指南、帮助中心、回收站、激活码、报告解读、团队分析和设置。
- 个人资料摘要按“基本信息 / 教育与生活 / 职业背景”分组，只显示后端已有且非空字段。
- 账号安全使用并列卡片呈现邮箱与密码；修改密码放入弹窗，但继续复用原接口、锁定与退出登录逻辑。
- 暂未上线的团队能力可以展示参考稿入口，但点击后必须提示开发中并提供真实联系渠道。

个人空间主要样式集中在 `src/frontend/styles/components/openlife-profile.css`。

### 6.6 支付模块

支付模块不是 New UI 通用改造的默认范围。

- 不因为其他页面更新而修改购买流程、价格、订单、支付回调或支付弹窗。
- 如需改支付，必须单独提出需求、单独核对后端字段，并完成支付专项回归。

## 7. 动效标准

- 动效服务于状态与阅读，不做持续干扰。
- 页面滚动动效应使用滚动进度或进入视口状态驱动，避免无限高频计算。
- Hover 位移建议 `1–4px`；卡片缩放应非常轻微。
- 自动高亮组件在用户 Hover 后应立即让位于用户选择。
- 所有持续动画必须响应 `prefers-reduced-motion: reduce`。
- 装饰层设置 `pointer-events: none`，不得拦截按钮或文本选择。

## 8. 响应式与兼容标准

### 8.1 断点

- `>1040px`：完整桌面布局；
- `761–1040px`：收起或重排侧栏；
- `521–760px`：单列内容、缩小标题和卡片间距；
- `<=520px`：按钮尽量满宽，复杂网格改单列。

具体组件可根据内容增加断点，但不能只为某一张截图硬编码尺寸。

### 8.2 CSS 兼容

- 使用 `color-mix()` 时，必须先写一条静态颜色或渐变回退。
- 使用 `backdrop-filter` 时，同时写 `-webkit-backdrop-filter`。
- 高度优先写 `vh` 回退，再写 `dvh`；Chat 统一复用项目的壳层高度类。
- 不用 Base64 长字符串承载正式图片；解码后放入 `public/assets/` 并由 Git 跟踪。

## 9. 样式组织与代码规范

全局加载顺序：

1. `styles/themes/`：语义变量；
2. `styles/base/`：重置、字体和基础效果；
3. `styles/components/`：组件与页面级样式；
4. Tailwind 指令。

实施规则：

- 新页面优先复用语义变量和现有组件，不复制整段 HTML 内联样式。
- 页面级样式使用稳定前缀，例如 `.ol-profile-*`、`.flow-*`。
- 最终覆盖层放在其依赖样式之后导入，并明确作用范围。
- JSX 内联样式只用于真实运行时数据，例如用户头像 URL 或动态阶段色。
- 视觉改造不改接口返回值，不伪造生产数据。
- 参考 HTML 只作为视觉输入，不直接作为运行时依赖提交。

## 10. 本地 UI 预览模式

开发环境可通过 `ui_preview=1` 在没有真实后端数据时验收界面。该模式由 `NODE_ENV === 'development'` 限制，生产构建不能绕过鉴权。

常用入口：

```text
/explore/chat/values?ui_preview=1&preview_state=conversation
/explore/chat/values?ui_preview=1&preview_state=streaming
/explore/chat/values?ui_preview=1&preview_state=conclusion
/explore/chat/rumination?ui_preview=1&preview_state=conversation
/dashboard?ui_preview=1
/dashboard/settings?ui_preview=1
/dashboard/codes?ui_preview=1
```

Chat 支持的 `preview_state`：`conversation`、`streaming`、`conclusion`、`loading`、`empty`、`error`。

预览模式只能提供本地展示数据，不得触发真实绑定、支付、删除或生产写入。

## 11. 验收清单

每次 UI 提交至少完成：

- 确认分支与改动范围；
- `git diff --check`；
- `npm run lint`；
- `npm run build`；
- 桌面尺寸视觉检查；
- `390px` 左右手机尺寸检查；
- Chat 正常对话、流式、结论、空态和错误态；
- Rumination 组合选择、解锁、对话与结论；
- 个人空间导航、资料、账号安全弹窗；
- 键盘焦点、禁用态、长文本与无数据状态；
- 确认首页和支付模块未被无作用域样式误伤；
- 确认图片素材位于 `public/assets/` 且被 Git 跟踪。

## 12. 当前实现索引

| 领域 | 主要文件 |
|---|---|
| 首页 | `app/(main)/page.tsx`、`styles/components/openlife-reference-home.css` |
| 激活与过渡 | `app/(main)/explore/activate/page.tsx`、`styles/components/openlife-transition.css` |
| 纸层背景（intro/社区/关于） | `components/explore/PaperVeilLayers.tsx`、`styles/components/openlife-paper-veil.css`（6px 毛玻璃，2026-09-19） |
| 站内信 | `components/feedback/FloatingFeedbackWidget.tsx`（抽屉形态）、`components/feedback/NotificationList.tsx`（卡片+详情视图）、`styles/components/openlife-support.css` |
| Chat | `app/(main)/explore/chat/[phase]/page.tsx`、`components/explore/ChatUiPreview.tsx`、`styles/components/openlife-chat-defaults.css` |
| Chat 外观弹层 | `components/explore/ChatAppearancePopover.tsx`、`stores/chatAppearanceStore.ts`、`styles/components/openlife-chat-appearance.css`（A/B 三开关，定稿后删落选分支） |
| Rumination | `components/explore/ruminationV4/`、`styles/components/rumination-beautiful.css`（2026-09-19 起紫色主题+HTML 面板配方） |
| 个人空间 | `app/(main)/dashboard/`、`components/dashboard/DashboardPageHeader.tsx`、`styles/components/openlife-profile.css`（含 `.ol-pill` 状态胶囊体系） |
| Admin 换肤 | `styles/components/openlife-admin.css`（scoped `.ol-admin-root`，功能零改动） |
| FAQ 内容 | `lib/content/faq.ts` |
| 全局样式入口 | `app/globals.css` |
