# 咨询师卡片 v4：按 consultants.html 设计稿重做卡内布局与配色

> 完成日期：2026-10-08
> 设计稿：`wiki/开发文档/10-07/consultants.html`
> 前置版本：v3（2026-10-07，一次一位左右切换 + 卡内三栏铺开，见 claude-completed 同期记录）
> 背景：用户反馈 v3 三个咨询师的卡片不好看，要求参考 consultants.html 的配色/UI 风格/布局重做；
> 约束：**卡片宽度不变**（与上方介绍卡对齐）、**仍一次一位左右切换**、内容不增删。

## 改动内容

卡面从「kicker + 姓名 + 行内元信息 + 三栏并列」改为设计稿的「左人物栏 + 右内容栏」：

- **左人物栏（aside）**：accent 渐变底 + 右下角同心圆装饰；头像块（祝/M/L 字母，Georgia 斜体）、
  `CONSULTANT 01..03` 编号、姓名（30px/730）、风格标签副标题、元信息 dl（行业/形式/工作年限竖排）
- **右内容栏（content）**：背景要点（accent 圆点 + soft 色光环）、咨询风格/适合人群双栏
  （竖条小标题）、底部价值观 chips（soft 底 + deep 字）
- **每人独立 accent**（`data-coach`）：祝余=蓝 `#3569d4`、Mary=绿 `#147b65`、Lena=紫 `#6f52c7`
- 副标题文案取自设计稿（如「结构化梳理 · 优势挖掘 · 职业转型」），其余内容不动

## 布局断点（与设计稿对齐）

| 宽度 | 布局 |
|---|---|
| ≥981px | aside 290px + 内容栏，卡片 min-height 580px |
| 761–980px | aside 240px + 内容栏，min-height 700px |
| 521–760px | 上下堆叠，元信息横排三列 |
| ≤520px | 堆叠，元信息退化为「58px 标签 + 值」横行 |

min-height 让三位咨询师切换时高度稳定（实测 1440px 下三张卡片均为 580px）。

## 深色模式

文字色走 `--bd-fg*` 主题变量；aside 渐变、编号、summary 圆点光环、chips 底色在
`[data-color-scheme='dark']` 下改用 accent 的 color-mix 透明色调，深色下无白色残留
（已截图验证）。左右切换圆箭头（`.ol-round-arrow`）为全站共用组件，保持原样。

## 文件清单

| 文件 | 改动 |
|---|---|
| `src/frontend/styles/components/consultants-coach.css` | 新增：`.ol-coach-*` 全套卡内样式（accent 变量、深色适配、断点） |
| `src/frontend/app/globals.css` | 引入上述 css（bd-static-skin 之前） |
| `src/frontend/app/(main)/consultants/page.tsx` | 卡片 JSX 重写为 aside+content 结构；Coach 数据补 `id`/`initial`/`subtitle` 字段；删除旧 META_LABEL/BODY_LIST 常量；轮播（页签/箭头/圆点/AnimatePresence）与卡片宽度不变 |

## 验证

生产模式 build + start.sh restart 后 Playwright（headless Chrome）截图：

- 1440px：三张卡片逐一切换，accent 蓝/绿/紫正确，高度一致 580px，与上方介绍卡左右边缘对齐
- 820px / 390px：分栏→堆叠正常，无横向溢出（scrollWidth-clientWidth=0）
- 深色模式：卡片深色底浅色字，无刺眼白色块
- 临时验证账号：`shot-ui-test2@test.com`（仅本机开发库，用于登录后截图）
