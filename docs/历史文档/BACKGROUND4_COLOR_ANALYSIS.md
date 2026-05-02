# 首页色彩与 background4.html 差异分析

## 1. 底色不同

| 项目 | background4 | 当前首页 |
|------|-------------|----------|
| 基础色 | `#faf9f8`（暖米白） | `#F2F5F8`（偏冷灰蓝） |
| 来源 | body { background-color } | ideal 主题 --bd-bg |

background4 的 `#faf9f8` 更暖；ideal 主题的 `#F2F5F8` 偏冷，整体会显得更灰、更淡。

---

## 2. 内容层是否有遮罩（最关键）

| 项目 | background4 | 当前首页 |
|------|-------------|----------|
| 内容区背景 | **无**（.container 透明） | 有：linear-gradient 48–62% --bd-bg |
| 叠加效果 | 直接露出 mesh + body 底色 | 在 mesh 上再叠一层半透明白灰 |

background4 的 .container 没有 `background`，mesh 会直接与 body 底色混合。  
当前首页对 `landing-mesh-content` 使用了 48–62% 不透明度的渐变，相当于在 mesh 上盖了一层白灰，会把 mesh 的颜色冲淡很多。

---

## 3. 层级结构对比

**background4：**
```
body (#faf9f8)
  → .bg-layer (mesh 4 个 blob，fixed)
  → .noise-overlay (0.05)
  → .container（无背景，内容透明）
```

**当前首页：**
```
landing-mesh-wrap
  → landing-mesh-bg (mesh 6 个 blob)
  → landing-mesh-noise (0.05)
  → landing-mesh-content（48–62% 渐变遮罩）← 主要差异
```

---

## 4. 修复方向

1. **首页底色**：在首页范围内使用 `#faf9f8` 作为基础色，或增加 `--bd-landing-bg` 覆盖 ideal 的 `--bd-bg`。
2. **去除 / 大幅减弱内容遮罩**：将 `landing-mesh-content` 的渐变改为透明或极低不透明度（约 5–10%），或直接设为透明。
3. **可选**：首页下可单独覆盖 `--bd-bg` 为 `#faf9f8`，使整页与 background4 的观感一致。
