# 1007 对话区贴线渐隐：去掉 header 灰线下的「无形卡片」

> 日期：2026-10-07
> 触发：用户标注截图（`wiki/开发文档/10-07/image.png`，灰线=header 底边缘）——气泡不在灰线处渐隐，中间多出一段空白「无形卡片」挡内容
> 前置：claude-completed-2026-10-06-静态皮肤视觉回调.md（二轮：header/dock 透明 + 遮罩条背景色）

## 根因（grill-me 确认后定位）

真实页面 `app/(main)/explore/chat/[phase]/page.tsx` 结构：

```
header.careering-header            → 底边灰线 y=180
  div.overflow-hidden.py-4         ← ★ 上下各 16px padding（"无形卡片"）
    flow-chat-box                  → y=196 才开始：裁切线比灰线低 16px
      flow-chat-body(滚动容器)     → 气泡在 y=196 被裁，遮罩条 196-228 渐隐
```

气泡实际裁切/渐隐起点在灰线下方 16px，且渐隐带（0.55 遮罩）起点更低——视觉上"还有一段距离才开始渐变"。预览壳 ChatUiPreview.tsx 同样带 py-4（预览忠实镜像）。

## 用户拍板（AskUserQuestion）

1. **渐隐终态：贴线开始渐变**——内容从灰线处开始渐隐，线处留隐约残影，往下 ~32px 完全清晰（非"贴线全隐"）。现参数（遮罩 0.55/2rem）正好是该行为，未改
2. **底部对称收紧**——py-4 上下全去

## 改动

| 文件 | 改动 |
|---|---|
| `app/(main)/explore/chat/[phase]/page.tsx:2268` | `py-4` 移除（裁切线上移到灰线、box 下沿贴 dock 顶） |
| `components/explore/ChatUiPreview.tsx:585` | 同步移除（预览壳保持镜像） |

几何结果：flow-chat-box = [180, 786]，上=header 底边、下=dock 顶边，全部齐平；遮罩条随 box 移动，渐隐起点=灰线=裁切线三者合一。

## 验证（playwright 预览 + 像素亮度剖面）

注入克隆消息加长对话 → 滚动让气泡骑住裁切线 → 逐行亮度（x480-1360 均值）：

```
168-176px: 234  灰线上方纯背景
180px:     191  ← 灰线处气泡已开始渐隐（非硬切）
180-208px: 191→135 平滑渐变（遮罩条 2rem 区）
208-236px: ~135 气泡实色
```

边界复检：仅剩 navbar 底边、header 发丝线（设计稿元素）、侧栏底部插画三类设计线，无新增色带。
`npm run lint` 0 错误、`npm run build` 56 页通过；**视觉需硬刷新**（3000 为 next start，旧标签页引用旧 chunk）。

## 遗留

- V4 沉淀页结构不同（py-1 仅 4px + 状态行自带 border-b 分隔），无需处理；其遮罩条与前四阶段共用规则已受益
- `/tmp/pw-tools/`：clip-verify.js（骑线测试）、pixel-analysis.js（支持文件参数）——视觉回归可复用

---

# 同日追加：沉淀 V4 贴线 + 渐隐条换横向渐变（用户二轮反馈）

## 用户反馈（grill-me 澄清后）

> div.mb-2.shrink-0 和 div.careering-chat-messages-inner 并不是无缝衔接，有一段空隙；且 flow-chat-body 的边缘太明显，是一个颜色对不上的方块。背景颜色对吗？是我们想要的偏几种颜色融合的效果吗？

**用户明确**：气泡纯白没问题（admin white 模式保留不动）；背景就是想要的四色融合（代码注释：「前四阶段色的极淡回声」blue/green/coral/gold blob，紫色锚点）✓ 无需改。

## 根因

1. **空隙**：V4ChatPanel 状态行 wrapper `mb-2`（8px）+ 对话 wrapper `py-1`（4px）= 12px
2. **方块**：1006 的 V4 渐隐条是**平色** (240,241,246,0.55)，而 V4 背景横向色差实测 28 RGB 单位（左薰衣草 222,228,247 → 右近白 250,251,252）——平色条在彩底上必然压出一块「颜色对不上」的方带（正是用户看到的边缘）

## 修复（V4ChatPanel.tsx + bd-static-skin.css）

| 处 | 改动 |
|---|---|
| `V4ChatPanel:177` | 状态行去 `mb-2`，面板与 border-b 细线无缝衔接（同前四阶段） |
| `V4ChatPanel:205` | 对话 wrapper 去 `py-1` |
| 静态皮肤 §3 V4 | 渐隐条底色改 **90° 横向三色渐变**（色样取自用户截图实测：224,229,247 → 240,242,250 → 250,251,252），纵向 0.7→0 渐隐改 **mask 挂条自身** |
| 静态皮肤 §3 V4 | `.rumination-chat-body-fade` 补 `padding-top: 1.25rem`（原无 top padding，首条消息会落进条弱alpha区） |

**关键技巧**：mask 挂在**不滚动的静态条**上 = 只栅格化一次，滚动零成本——性能禁令的 mask 只针对滚动容器。这样条底色可以只管横向匹配背景，纵向渐隐交给 mask，突破了「单个 linear-gradient 无法同时做横向配色×纵向渐隐」的限制。若换分辨率后 blob 偏移致轻微色偏，重采样更新色值即可（已注释在 CSS）。

## 验证

- `npm run lint` 0 错误；`npm run build` 56 页通过；构建产物 grep 确认横向渐变 + mask 编译进 static-skin chunk
- V4 真页需激活码未能实测（同 1006 遗留）；**视觉请硬刷新沉淀页确认**
- 用户气泡 white 模式、四色融合背景：确认无改动
