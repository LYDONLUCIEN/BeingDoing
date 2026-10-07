# 咨询师介绍页（2026-10-06 完成）

## 需求

参考 https://lumina-lab.cn/coaches/ ，新增「咨询师介绍」模块：背景配色、UI 风格与「关于我们」页一致。统一介绍/咨询范围/咨询条件/咨询形式文案由需求方给定；咨询师数据来自 `wiki/开发文档/10-05/咨询师.md`（祝余 / Mary / Lena）。

## grill-me 定稿决策

| 决策点 | 结论 |
| --- | --- |
| 形态 | 独立页 `/consultants`（与 /about 同款 bd-mesh-page 纸纹底 + bd-glass-card 玻璃卡 + framer-motion） |
| 首页顶部入口 | 导航栏 `journey-navbar-links` 内「关于我们」旁新增 `journey-nav-link` 同款链接（**不是** hero 横幅），文案「咨询团队」 |
| 卡片布局 | **v4（2026-10-07 定稿）**：在 v3（一次一位、左右切换、三栏全量直出）基础上换首页用户评价同款质感：卡片 `ol-reading-glass rounded-[20px]` 玻璃纸面 + `ol-kicker` 眉标（COUNSELOR PROFILE · 0X）+ 小节标题后随 hairline + 价值观 chips 加底色；**md:min-h-[710px] / xl:min-h-[470px] 统一三位卡片高度**；箭头直接用全局 `ol-round-arrow` 绝对定位骑跨卡片两缘（`-left-4/-right-4`，卡片与上方介绍卡同宽；≤720px 自动隐藏），移动端用 `ol-review-dots` 圆点（外层 md:hidden 控制，因该类 display 无层叠层会压过 tailwind）。~~v2 两列矮卡+折叠~~（被否：内容显得少）；~~v3 裸 bd-glass-card+边框圆钮~~（被否：不高级、尺寸不一） |
| 须知布局 | 单张玻璃卡内分三节（咨询范围 / 咨询条件 / 咨询形式），横向分隔线，正文限宽 42rem |
| 其它入口 | 首页 footer「咨询师团队」链接；关于我们页文末「了解咨询师团队 →」 |
| i18n | 仅导航/footer 标签走 i18n（`nav.consultants`=咨询团队 / `footer.consultants`=咨询师团队）；页面文案中文硬编码（与 About 口径一致） |

## 改动文件

- `src/frontend/lib/nav.ts` — NAV_ITEMS 增 `{ labelKey: 'nav.consultants', href: '/consultants' }`（about 之前），桌面中间导航 + 移动端菜单自动生效
- `src/frontend/lib/i18n/locales/zh.ts` / `en.ts` — 增 `nav.consultants`（咨询师/Consultants）、`footer.consultants`（咨询师团队/Consultants）
- `src/frontend/app/(main)/consultants/page.tsx` — 新页面（结构与 about/page.tsx 同款：data-mesh-page、PaperVeilLayers、ol-reading-glass、ol-about-qr 小红书入口）
- `src/frontend/app/(main)/page.tsx` — LandingFooter 增「咨询师团队」链接
- `src/frontend/app/(main)/about/page.tsx` — 文末增「了解咨询师团队 →」（next/link）

## 验证

- `npx tsc --noEmit` 通过
- `./start.sh restart frontend`（clean build + start）
- `curl /consultants` 200，关键词（咨询师团队/祝余/Mary/Lena/适合人群/价值观/免费更换机会/提交问题反馈）均在 SSR HTML 中
- 首页导航 `href="/consultants">咨询师`、footer `咨询师团队`；/about 文末链接在

## 备注

- 文案中「右下角提交问题反馈」指现有反馈浮窗，「小红书店铺」由页面右上角 XiaohongshuQrEntry 承接（与 About 同款）。
- 咨询师内容变更时只需改 `consultants/page.tsx` 顶部 `COACHES` 常量。
