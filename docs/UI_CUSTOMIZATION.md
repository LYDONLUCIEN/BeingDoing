# BeingDoing UI 定制指南

本文档说明如何定制 **答题卡（Answer Card）** 和 **建议标签（Suggestion Tags）** 的样式与行为。

---

## Answer Card（答题卡）

### 数据结构

后端 AI 在对话达到充分条件后自动生成答题卡，包含以下字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `question_id` | number | 题目 ID |
| `question_content` | string | 题目内容 |
| `user_answer` | string | 用户原话摘要 |
| `ai_summary` | string | AI 总结（1-2句核心观点，≤100字） |
| `ai_analysis` | string | AI 深层分析（反映的价值观/才能/兴趣倾向） |
| `key_insights` | string[] | 关键洞察标签（3-5个短语） |

### 触发条件

答题卡的生成由后端 `question_goals.py` 中每道题的配置控制：

```python
{
    "goal": "这道题的隐藏目标",
    "extract": ["需要提取的信息1", "信息2"],
    "min_turns": 2,       # 最少对话轮数（低于此不触发）
    "max_turns": 5,       # 最多对话轮数（达到此数强制触发）
    "sufficiency_hints": ["关键词1", "关键词2"],  # 判断充分性的关键词
}
```

- 修改 `min_turns` / `max_turns` 可控制每道题的对话深度
- 修改 `sufficiency_hints` 可调整何时认为用户回答充分
- 配置文件：`src/backend/app/domain/question_goals.py`

### 样式定制

答题卡使用语义化 CSS 类名，所有样式定义在 `src/frontend/app/globals.css` 中。

| CSS 类名 | 对应区域 | 说明 |
|----------|---------|------|
| `.answer-card` | 卡片容器 | 主容器，控制整体外观 |
| `.answer-card__header` | 头部 | 标题和题目内容 |
| `.answer-card__summary` | 核心发现 | AI 总结区域，左侧有 emerald 色竖线 |
| `.answer-card__analysis` | 深层分析 | AI 分析区域 |
| `.answer-card__insights` | 洞察容器 | 包含多个洞察标签的容器 |
| `.answer-card__insight-tag` | 洞察标签 | 单个洞察标签（圆角 pill） |
| `.answer-card__user-answer` | 用户原话 | 可折叠的用户原文区域 |
| `.answer-card__actions` | 操作按钮 | "确认并继续" 和 "继续讨论" 按钮 |
| `.answer-card--collapsed` | 折叠态 | 已确认卡片的折叠样式 |

**组件文件：** `src/frontend/components/explore/EnhancedAnswerCard.tsx`

### 卡片布局结构

```
┌─ Header: [✓] 回答总结 / 题目内容 ──────────────────┐
├─ 核心发现（.answer-card__summary）                   │
│  [✨] AI 总结文本                                    │
├─ 深层分析（.answer-card__analysis）                   │
│  [💡] AI 分析文本                                    │
├─ 关键洞察（.answer-card__insights）                   │
│  [tag] [tag] [tag] [tag]                             │
├─ 你的原话（.answer-card__user-answer，可折叠）        │
│  用户原文 [编辑]                                     │
├─ 操作按钮（.answer-card__actions）                    │
│  [确认并继续]          [继续讨论]                     │
└──────────────────────────────────────────────────────┘
```

确认后卡片折叠为一行（`.answer-card--collapsed`），点击可展开。

### AI 分析内容定制

答题卡的 AI 分析内容由 LLM 提示词模板控制：

- **文件：** `src/backend/app/domain/prompts/templates/answer_card_summary.yaml`
- 可调整项：
  - 总结长度和风格（修改 `ai_summary` 的描述）
  - 分析深度（修改 `ai_analysis` 的描述）
  - 洞察数量（修改 `key_insights` 的要求）
  - 整体语气（修改 "要求" 部分）

---

## Suggestion Tags（建议标签）

### 生成规则

每次 AI 回复时，后端自动生成 3 个建议方向标签。生成规则在 `reasoning.yaml` 提示词中定义：

- 一个**深入挖掘**方向（如"我想聊聊那次经历"）
- 一个**换角度思考**方向（如"换个角度看工作中的感受"）
- 一个**具体例子引导**方向（如"比如最近发生的一件事"）

修改提示词文件可调整标签生成策略：`src/backend/app/domain/prompts/templates/reasoning.yaml`

### 样式定制

| CSS 类名 | 对应区域 | 说明 |
|----------|---------|------|
| `.suggestion-tags` | 标签容器 | Flex 布局，控制间距和排列 |
| `.suggestion-tags__item` | 单个标签 | 圆角按钮，hover 有上浮和阴影效果 |

**组件文件：** `src/frontend/components/explore/SuggestionTags.tsx`

### 交互行为

- 点击标签：文本填入输入框（不自动提交，用户可继续编辑）
- 点击后标签消失（避免重复选择）
- 流式输出或显示答题卡时标签隐藏

可修改 `SuggestionTags` 组件的 `onSelect` 回调来改变行为（如自动提交）。

---

## 阶段配色（Phase Colors）

四个探索维度使用统一的 CSS 变量，首页与探索流程保持一致：

| 维度 | 变量 | 设计语义 | 默认（ideal 主题） |
|------|------|----------|--------------------|
| 信念 | `--bd-phase-values` | 蓝 | #6FAEE0 |
| 禀赋 | `--bd-phase-strengths` | 绿 | #83C290 |
| 热忱 | `--bd-phase-interests` | 红 | #EF837E |
| 使命 | `--bd-phase-purpose` | 黄 | #F4C062 |

### 用户自定义

- **入口**：登录后点击导航栏「配色」，或 Admin → 阶段配色定制
- **页面**：`/settings/colors`
- **存储**：localStorage `bd-phase-colors`，覆盖当前主题的默认阶段色
- **重置**：点击「使用主题默认」恢复单阶段，或「恢复全部默认」

### 主题定义

各主题在 `src/frontend/styles/themes/*.css` 中定义 `--bd-phase-*` 与 `--bd-phase-*-dim`。ideal、glimmer、slate-dark 已完整定义；其他主题继承 `:root` 默认值。

---

## 主题色说明

项目使用 Tailwind CSS 调色板：

| 用途 | 色系 | Tailwind 类前缀 |
|------|------|-----------------|
| 答题卡主色 | 绿色 | `emerald-*` |
| 答题卡分析区 | 琥珀色 | `amber-*` |
| 建议标签主色 | 靛蓝色 | `primary-*` |
| 对话背景 | 深灰色 | `slate-*` |

全局修改色调：编辑 `tailwind.config.js` 中的 `primary` 和 `emerald` 配置。

---

## 文件索引

| 文件 | 用途 |
|------|------|
| `src/frontend/components/explore/EnhancedAnswerCard.tsx` | 答题卡组件 |
| `src/frontend/components/explore/SuggestionTags.tsx` | 建议标签组件 |
| `src/frontend/app/(main)/settings/colors/page.tsx` | 阶段配色定制页 |
| `src/frontend/stores/phaseColorStore.ts` | 阶段配色覆盖 Store |
| `src/frontend/app/globals.css` | 可定制 CSS 样式 |
| `src/backend/app/domain/prompts/templates/answer_card_summary.yaml` | 答题卡 AI 分析提示词 |
| `src/backend/app/domain/prompts/templates/reasoning.yaml` | 建议标签生成提示词 |
| `src/backend/app/domain/question_goals.py` | 题目目标和轮数配置 |
