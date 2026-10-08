# chat/沉淀页静态皮肤视觉修复全记录（10-06 ~ 10-07 三轮）

> 日期：2026-10-08（存档）
> 存档 issue：[#103](https://github.com/LYDONLUCIEN/BeingDoing/issues/103)
> 提交：`bd8d66f`（静态皮肤 + ADR 修订）→ `68d18f2`（贴线 + V4 + 文档）
> 背景：10-05 性能优化（ADR-0022）引发视觉回归，用户三轮验收否决后修复

## 一句话总结

chat 前四阶段与沉淀 V4 恢复「**整页一块连续画布**」：header/输入区完全透明直通背景、遮罩条与背景同色隐形、对话区**贴线渐隐**（裁切线 = header 灰线 = 渐隐起点三者合一）——性能约束全程未放松（无 backdrop-filter、无动画解冻、零滚动成本）。

## 三轮脉络（每轮根因都不同）

| 轮 | 用户否决点 | 真根因 | 终案 |
|---|---|---|---|
| 一 10-05 | 「整个页面都变丑了，明显三段」 | 换算公式在近白背景上过曝成 0.88–0.94 实心白带 | alpha 回调（不够） |
| 二 10-06 | 「三段感仍在，要看不出过渡、模糊处理」 | **通栏叠层无论多低 alpha 都自成色带**；遮罩条纸白 vs 背景实测差 13 单位 | header **transparent** / dock **background:none** / 遮罩条**背景实测色** |
| 三 10-07 | 「灰线下有无形卡片，气泡不在线处渐隐」 | 对话区外包 **`py-4`**（16px×2）压低裁切线 | 删 py-4/mb-2/py-1，贴线渐隐 |

## 改动文件

| 文件 | 改动 |
|---|---|
| `styles/components/bd-static-skin.css` | §2 二轮定稿取值口径；§3 chat 条背景实测色 + 下沿 7rem；§3 V4 条改**横向三色渐变 + mask 纵向渐隐**；V4 body 补 `padding-top: 1.25rem` |
| `app/(main)/explore/chat/[phase]/page.tsx` | 删对话区 wrapper `py-4` |
| `components/explore/ChatUiPreview.tsx` | 同步删 `py-4`（预览壳镜像真实页） |
| `components/explore/ruminationV4/V4ChatPanel.tsx` | 状态行删 `mb-2`、对话 wrapper 删 `py-1`（面板贴 border-b 细线） |
| `docs/adr/0022` | 修订二节：三处清零定稿 + 像素验证 |

## 关键认知（后续维护必读）

1. **旧观感本质 = 整页连续画布**：无内容穿过的面（header/dock 通栏）必须完全透明，任何 alpha 的通栏叠层都在带色背景上自成色带
2. **遮罩条颜色必须用背景实测色**（纸白会留 Δ8 端点跳变）；条对背景隐形、只对墨色内容渐隐
3. **彩底渐隐技巧**：横向配色 × 纵向渐隐无法用单个 gradient 表达 → 底色 90° 横向渐变 + **mask 挂静态条**（静态层 mask 只栅格化一次，滚动零成本；性能禁令仅针对滚动容器）
4. **实色 alpha 绘制成本与数值无关**——视觉回调永远零性能代价
5. V4 气泡 white 模式与四色融合背景经用户拍板**不动**

## 验证资产（可复用）

- `/tmp/pw-tools/pixel-analysis.js`：截图 → 浏览器 canvas → 逐行 ΔRGB 边缘检测（量化「还有没有色带」）
- `/tmp/pw-tools/clip-verify.js`：骑线滚动测试（渐隐起点 vs 灰线位置）
- 视觉工具链：截图 CDN URL → analyze_image 对比描述（zai 本地路径 401 时用 4_5v 远程）

## 遗留

- 生产（60.205.194.159）跑 deploy.sh 后硬刷新验收
- V4 真页无自动化实测（需激活码）；分辨率差异致渐隐条色偏时重采样更新色值
- 详细过程文档：`claude-completed-2026-10-06-静态皮肤视觉回调.md`、`claude-completed-2026-10-07-对话区贴线渐隐.md`
