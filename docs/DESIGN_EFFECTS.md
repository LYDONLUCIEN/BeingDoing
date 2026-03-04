# 设计效果系统

效果层与**主题**、**阶段配色**相互独立，可自由组合。用于快速尝试毛玻璃、素描纸、扁平化等视觉效果。

## 架构

```
主题 (theme)     → 提供基础色、边框、阴影
    ↓
阶段配色 (phase) → 覆盖信念/禀赋/热忱/使命四个维度的颜色
    ↓
设计效果 (effects) → 覆盖卡片背景、模糊、纹理等
```

## 配置位置

**`src/frontend/config/design-effects.json`**

你可直接编辑此文件新增或修改预设，保存后刷新效果实验室页面即可看到变更。

### 结构示例

```json
{
  "presets": {
    "my-effect": {
      "name": "我的效果",
      "vars": {
        "--bd-bg-card": "rgba(255,255,255,0.6)",
        "--bd-eff-card-blur": "12px",
        "--bd-eff-bg-pattern": "url(...)"
      }
    }
  }
}
```

### 可用变量

| 变量 | 说明 | 示例 |
|------|------|------|
| `--bd-bg` | 页面背景色 | `#f8f6f0` |
| `--bd-bg-card` | 卡片背景 | `rgba(255,255,255,0.55)` |
| `--bd-bg-card-alt` | 次要卡片背景 | `rgba(255,255,255,0.45)` |
| `--bd-nav-bg` | 顶部导航背景 | `rgba(255,255,255,0.75)` |
| `--bd-eff-card-blur` | 卡片毛玻璃模糊半径 | `12px` |
| `--bd-eff-nav-blur` | 导航毛玻璃模糊 | `14px` |
| `--bd-eff-bg-pattern` | 页面背景纹理 | `url("...")` |
| `--bd-border` | 边框色 | `rgba(180,170,150,0.35)` |
| `--bd-shadow-card` | 卡片阴影 | `0 1px 2px rgba(0,0,0,0.04)` |

效果层仅在元素具有 `bd-eff-card` 或 `bd-eff-bg` 类时才会应用模糊/纹理。新增卡片时记得添加相应类。

## 入口

- **效果实验室**：`/settings/style-lab` — 切换预设、即时预览
- **导航**：登录后顶部栏「效果」
- **Admin**：管理视图 → 效果实验室

## 存储

- localStorage 键：`bd-design-effects`
- 与主题、阶段配色分开存储，互不影响

## 文件索引

| 文件 | 用途 |
|------|------|
| `src/frontend/config/design-effects.json` | 效果预设配置（你可编辑） |
| `src/frontend/stores/designEffectsStore.ts` | 效果选择 Store |
| `src/frontend/components/layout/DesignEffectsInjector.tsx` | 注入 CSS 变量 |
| `src/frontend/styles/base/design-effects.css` | 效果层基础规则 |
| `src/frontend/app/(main)/settings/style-lab/page.tsx` | 效果实验室页面 |
