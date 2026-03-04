# 主题与配色系统说明

本文档详细说明黑白模式切换、Admin 主题选择、四维度配色、导引色的关系与配置方式。

---

## 一、黑白模式与 Admin 选中的主题

### 是否有实际使用？**是的，有实际使用。**

顶部导航栏的 ☀️/🌙 切换会调用 `toggleColorScheme()`，逻辑是：

| 当前模式 | 切换后 | 实际应用的主题 |
|----------|--------|----------------|
| 日间 | 夜间 | `darkThemeId`（Admin 中「夜间模式使用」选择的主题） |
| 夜间 | 日间 | `lightThemeId`（Admin 中「日间模式使用」选择的主题） |

- **日间模式使用**：可选 `ideal`、`glimmer`、`aurora`、`warm-light`、`sand`、`serene`、`insight` 共 7 个浅色主题
- **夜间模式使用**：可选 `slate-dark`、`forest` 共 2 个深色主题

切换时会把 `<html>` 的 `data-theme` 设为对应主题 ID，CSS 通过 `[data-theme="xxx"]` 选择器生效。

---

## 二、主题文件的配色覆盖情况

每个主题是一个独立的 CSS 文件，定义各自的变量。**并非所有主题都定义了完整配色**：

| 主题 | 定义 --bd-phase-* | 定义 --bd-ui-accent | 说明 |
|------|-------------------|---------------------|------|
| ideal | ✅ 完整 | ✅ #7c3aed | 四维蓝/绿/红/黄 + 紫色导引 |
| glimmer | ✅ 完整 | ✅ #8b7bb8 | 微光色系 |
| slate-dark | ✅ 完整 | ✅ #a78bfa | 深色紫导引 |
| forest | ❌ 未定义 | ❌ | 继承 --bd-accent-* 和 tailwind 默认 #a78bfa |
| warm-light, sand, serene, insight, aurora | ❌ 大多未定义 | ❌ | 继承 --bd-accent-* 和 tailwind 默认 |

未定义 `--bd-phase-*` 或 `--bd-ui-accent` 的主题会继承 CSS 层叠（父级或 Tailwind 默认），可能导致颜色不符合预期。

---

## 三、是否只需要维护两套黑白？

**当前设计**：日间 7 套 + 夜间 2 套 = 9 套主题，彼此独立。

**若简化为两套**：

1. **日间一套**：一个 light 主题（如 `ideal`），包含完整的 `--bd-phase-*`、`--bd-ui-accent`、`--bd-bg` 等
2. **夜间一套**：一个 dark 主题（如 `slate-dark`），同样完整定义

 Admin 中的「日间模式使用」「夜间模式使用」下拉可以只保留各一个选项，或继续保留多选作为未来扩展。维护成本会显著降低。

---

## 四、四维度配色与导引色在哪配置？

### 1. 四维度配色（信念/禀赋/热忱/使命）

| 变量 | 语义 | 默认（ideal） |
|------|------|---------------|
| `--bd-phase-values` | 信念 / Values | #6FAEE0 |
| `--bd-phase-strengths` | 禀赋 / Strengths | #83C290 |
| `--bd-phase-interests` | 热忱 / Interests | #EF837E |
| `--bd-phase-purpose` | 使命 / Purpose | #F4C062 |

**配置位置**：
- **主题级**：`src/frontend/styles/themes/*.css` 中各主题的 `[data-theme="xxx"]` 块
- **用户覆盖**：`/settings/colors` 页面，通过 PhaseColorStore 存 localStorage，PhaseColorInjector 注入覆盖样式，优先级高于主题默认

### 2. 导引色（导航、按钮、开始探索等）

| 变量 | 用途 | 默认（ideal 日间） | slate-dark 夜间 |
|------|------|-------------------|-----------------|
| `--bd-ui-accent` | 主按钮、链接、高亮 | #7c3aed（紫） | #a78bfa（浅紫） |
| `--bd-ui-accent-dim` | 浅色背景、悬停 | rgba(124,58,237,0.12) | rgba(167,139,250,0.2) |
| `--bd-ui-accent-fg` | 按钮上的文字 | #ffffff | #ffffff |

**配置位置**：**仅在各主题 CSS 中**，目前没有专门的用户配置界面。

---

## 五、是否能根据 Admin 选的主题配置？

**能**。逻辑是：

- Admin 选中的「日间/夜间模式使用」会写入 `lightThemeId` / `darkThemeId`
- 黑白切换时，`themeId` 会变成对应的 `lightThemeId` 或 `darkThemeId`
- `data-theme` 会更新为该主题 ID
- 该主题 CSS 文件中的 `--bd-phase-*`、`--bd-ui-accent` 等变量随之生效

因此，**不同 Admin 主题 = 不同的四维配色和导引色**，前提是该主题 CSS 中明确定义了这些变量。

---

## 六、配置入口汇总

| 配置项 | 入口 | 存储 |
|--------|------|------|
| 日间/夜间使用哪套主题 | /admin 主题切换区域 | localStorage `bd-theme` |
| 四维度颜色覆盖 | /settings/colors | localStorage `bd-phase-colors` |
| 导引色 | 各主题 CSS 文件 | 无用户界面，需改代码 |
| 效果预设（毛玻璃等） | /settings/style-lab | design-effects store |

---

## 七、若需「两套黑白 + Admin 可调导引色」

可考虑：

1. 在 themeStore 中增加 `uiAccentOverride`，存用户选的导引色
2. 在 PhaseColorInjector 或新建 UiAccentInjector 中注入 `--bd-ui-accent` 覆盖
3. 在 Admin 或 /settings 中增加导引色选择器

这样即可在保持两套黑白主题的基础上，让导引色也可由 Admin 或用户配置。
