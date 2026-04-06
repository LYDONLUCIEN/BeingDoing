# V2 新版本变更记录

> 日期：2026-04-06（持续更新）
> 范围：用户气泡 bug、结论卡设计、step 文案、多 Journey、自动跳转、rumination 9 步、字体本地化、进度条修复

---

## 一、功能变更总览

| # | 功能 | 状态 | 涉及端 |
|---|------|------|--------|
| 1 | 用户气泡换行 Bug 修复 | ✅ | 前端 |
| 2 | Conclusion Card Glass-Morphism 设计 | ✅ | 前端 |
| 3 | Step 文案预留机制 | ✅ | 前后端 |
| 4 | 多 Journey 后端接口 | ✅ | 后端 |
| 5 | 激活码自动跳转最新 Step | ✅ | 前端 |
| 6 | 多 Journey Dashboard 重写 | ✅ | 前端 |
| 7 | Rumination 完整 9 步流程 | ✅ | 后端 |
| 8 | 字体全量本地化 | ✅ | 前端 |
| 9 | Rumination 进度条修复 | ✅ | 前端 |
| 10 | Rumination 表格确认按钮修复 | ✅ | 前端 |

---

## 二、各功能详细说明

### 1. 用户气泡换行 Bug 修复 ✅

**问题**：输入 "确认！" 显示为 "确认\n!"，标点被换行。

**根因**：
- `page.tsx` 中有缺陷的文本拆分逻辑（`lines.every(l => l.length <= 2)` 判断）
- CSS `white-space: pre-wrap` 保留了换行符
- `word-break: keep-all` 禁止中文字间断行，与 `overflow-wrap: anywhere` 冲突导致在奇怪位置强制断开

**修复**：
- `page.tsx` — 移除 lines 拆分/合并逻辑，简化为直接渲染 content
- `flow-chat-light.css`:
  - `.flow-msg-user-content` — 移除 `min-width: min(25ch, 100%)`，改 `word-break: normal` + `overflow-wrap: break-word`
  - `.flow-msg-user-text` — 改 `word-break: normal` + `overflow-wrap: break-word`
  - 保留 `--compact` 变体的 `white-space: nowrap`（短消息单行展示）

### 2. Conclusion Card Glass-Morphism 设计升级 ✅

**设计来源**：`uidesign/beautiful/conclusion_card2.html`

**变更**：
- `DimensionConclusionCard.tsx` — Header 结构改为 icon-box（32x32 圆角方块）+ title 布局
- `flow-chat-light.css` — 全面替换 `.flow-conclusion-*` 样式：
  - 卡片：`background: rgba(255,255,255,0.65)`, `backdrop-filter: blur(24px)`, `border-radius: 20px`
  - 移除左侧 `border-left: 4px` 色条，改为整体 glass 效果
  - 每个阶段通过 `--cc-accent` / `--cc-accent-light` / `--cc-shadow` CSS 变量自动取色
  - Tags：白底圆角胶囊 `border-radius: 20px`，hover 放大 + 阴影
  - 主按钮：`linear-gradient(135deg, accent, accent-grad)` 渐变，白色文字，hover 上浮
  - 次按钮：半透明白底 `rgba(255,255,255,0.6)`
  - 已确认状态：绿色背景 `rgba(16,185,129,0.15)`

### 3. Step 文案预留机制 ✅

**新文件**：`src/backend/app/domain/prompts/templates/step_copy.yaml`

```yaml
# 编辑此文件即可修改所有阶段的引导文案，支持 Markdown
values:
  intro: "欢迎来到价值观探索！..."
  outro: "恭喜你完成了价值观探索！..."
strengths:
  intro: "..."
  outro: "..."
# interests, purpose, rumination 同理
```

**新函数**：`get_step_copy(phase, position)` — `src/backend/app/domain/prompts/loader.py`

**API 集成**：
- `POST /simple-chat/init` 响应增加 `step_intro` 字段
- `POST /simple-chat/thread/complete` 响应增加 `step_outro` 字段
- 前端可在对话开始前和结论确认后展示这些文案

### 4. 多 Journey 后端接口 ✅

**新端点**：`GET /simple-auth/journeys`

- 返回当前登录用户的所有激活码 + 进度摘要
- 按 `last_activity_at` 倒序排列，最近使用的排第一
- 最近使用的标记 `is_latest: true`
- 清除浏览器缓存后仍可从此接口恢复全部 Journey

**响应格式**：
```json
{
  "journeys": [
    {
      "activation_code": "CODE",
      "mode": "values",
      "status": "active",
      "created_at": "...",
      "last_activity_at": "...",
      "explore_resume": {
        "resume_phase": "strengths",
        "unlocked_phases": ["values", "strengths"]
      },
      "is_latest": true
    }
  ]
}
```

### 5. 激活码自动跳转最新 Step ✅

**问题**：从激活码页面进入时，可能跳转到 values 而非用户实际进度所在的 step。

**根因**：Admin bypass 模式下 `explore_resume` 的应用顺序有问题，且 localStorage 旧数据可能覆盖后端进度。

**修复**（`activate/page.tsx`）：
- 重构会话生成逻辑：**永远以后端 `explore_resume` 为准**
- 先应用 `explore_resume`，再处理 admin bypass
- Admin bypass 仅在后端无进度时才全部解锁
- 合并了重复的 `router.push` 分支

### 6. 多 Journey Dashboard 重写 ✅

**文件**：`src/frontend/app/(main)/dashboard/page.tsx` — 完全重写

**变更**：
- 数据源从 `localStorage.getItem('explore_last_code')` 改为 `GET /simple-auth/journeys`
- 最近使用的 Journey 显示为大卡片（featured），其余为小卡片
- 每个 Journey 显示 5 个阶段的进度圆圈（values → strengths → interests → purpose → rumination）
- 点击已解锁阶段直接跳转到对应 step 的对话页面
- 清除浏览器缓存后仍可从后端恢复所有 Journey

### 7. Rumination 完整 9 步流程 ✅

**后端变更** — `simple_chat_routes.py`：

新增 imports：
```python
from app.utils.rumination_ops import (
    structure_hypothesis_round1_table,
    generate_hypotheses_round2_table,
    generate_hypotheses_round3_finalize,
    value_filter, passion_filter, reality_filter, similar_filter,
)
from app.utils.rumination_hypothesis_service import fill_hypothesis_columns_for_table
```

**`rumination-table-submit` 端点**（改为 async）— 完整 step 转换链：

| 提交 Step | 生成 Step | 转换函数 | 需要 LLM |
|-----------|-----------|----------|----------|
| 1 | 2 | `filter_strength` + `filter_match` | 否 |
| 2 | 3 | `structure_hypothesis_round1_table` + `fill_hypothesis_columns_for_table` | 是（副业+公司双轨假设） |
| 3 | 4 | `generate_hypotheses_round2_table` + `fill_hypothesis_columns_for_table(only_empty=True)` | 是（仅空行） |
| 4 | 5 | `generate_hypotheses_round3_finalize`（空行标记"待定"） | 否 |
| 5 | 6 | `value_filter`（移除"待定"，添加工作目的列） | 否 |
| 6 | 7 | `passion_filter`（移除"都不符合"，添加激情标记列） | 否 |
| 7 | 8 | `reality_filter`（移除"应该做"，添加现实标记列） | 否 |
| 8 | 9 | `similar_filter`（移除"未来"，保留最终假设） | 否 |

**`rumination-get-table` 端点**（改为 async）：
- 先查快照（submitted/initial），有则直接返回
- 无快照时从前一步 submitted 动态生成（step 3/4 含 LLM 调用）

### 8. 字体全量本地化 ✅

**问题**：`next build` 时从 Google Fonts CDN 下载字体失败（服务器网络不稳定）。

**修复**（`app/layout.tsx`）：
- 4 个字体全部改为 `next/font/local` 加载
- 不再依赖 Google Fonts CDN，build 时零网络请求

**字体文件位置**：`src/frontend/public/fonts/`

| 字体 | 文件 | 大小 | 用途 |
|------|------|------|------|
| Noto Sans SC | 4 个静态 TTF (Light/Regular/Medium/SemiBold) | 41MB | 中文正文 |
| Inter | Variable TTF | 855KB | 英文/数字 |
| Playfair Display | Variable TTF + Italic | 580KB | 标题装饰 |
| Noto Serif SC | Regular + SemiBold TTF | 27MB | 中文衬线 |

### 9. Rumination 进度条修复 ✅

**问题**：
- Step 1 显示 ~5.5% 而非 0%
- 进度条显示不必要的行级进度（"行 1/10"）

**修复**（`RuminationSectionProgress.tsx`）：
- 进度计算改为：Step 1 = 0%，Step 2 完成 = 12.5%，...，Step 9 完成 = 100%（filter section 内线性映射）
- 移除 `Claude Code`、`totalRows` 变量和 `rowDetail` 显示
- 进度条只显示 "筛选 N/9"，不再显示行级进度

### 10. Rumination 表格确认按钮修复 ✅

**问题**：已提交过的步骤再次查看时，只显示"重新填写"按钮，没有"确认"按钮。

**根因**：`tableRefillMode` 为 true 时，原逻辑用"重新填写"**替换**了"确认"按钮。

**修复**（`RuminationTableWidget.tsx`）：
- 当 `tableRefillMode` 为 true 时，**同时显示**"重新填写"（次级按钮）和"确认"（主按钮）
- 用户可以选择重新填写表格，也可以直接确认当前内容继续下一步

---

## 三、完整文件变更清单

### 前端

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `app/layout.tsx` | 修改 | 4 个字体改为 `next/font/local` |
| `app/(main)/explore/chat/[phase]/page.tsx` | 修改 | 用户气泡渲染简化 + isCacheStale import |
| `app/(main)/explore/activate/page.tsx` | 修改 | 自动跳转逻辑重构，后端进度优先 |
| `app/(main)/dashboard/page.tsx` | 重写 | 多 Journey 展示，后端数据源 |
| `components/explore/DimensionConclusionCard.tsx` | 修改 | Header 改为 icon-box 布局 |
| `components/explore/RuminationSectionProgress.tsx` | 修改 | 进度计算修正 + 移除行级显示 |
| `components/explore/RuminationTableWidget.tsx` | 修改 | 确认+重新填写按钮并存 |
| `styles/components/flow-chat-light.css` | 修改 | 用户气泡 CSS + 结论卡 glass 设计 |
| `lib/explore/threads.ts` | 修改 | 添加 `isCacheStale`, `markSynced`, `clearThreadCache` |
| `public/fonts/` | 新增 | 9 个本地字体文件 |

### 后端

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `app/api/v1/simple_chat_routes.py` | 修改 | init/complete 增加 step_intro/outro + rumination 9 步完整逻辑 |
| `app/api/v1/simple_auth.py` | 修改 | 新增 `GET /journeys` 端点 |
| `app/domain/prompts/templates/step_copy.yaml` | 新增 | 阶段引导文案 |
| `app/domain/prompts/loader.py` | 修改 | 添加 `get_step_copy()` |
| `app/domain/prompts/__init__.py` | 修改 | 导出 `get_step_copy` |

---

## 四、开发者注意事项

### 字体管理
- 字体文件在 `src/frontend/public/fonts/`，通过 `next/font/local` 加载
- 如需添加新字体，在 `app/layout.tsx` 中配置 `localFont()` 即可
- 原始字体包存放在 `uidesign/font/`（不参与构建）

### Step 文案编辑
- 编辑 `src/backend/app/domain/prompts/templates/step_copy.yaml` 即可修改所有阶段的开始/结束文案
- 支持 Markdown 格式
- 通过 `get_step_copy(phase, 'intro')` / `get_step_copy(phase, 'outro')` 调用

### Rumination 9 步数据流
```
Step 1: gen_table() → 热爱×优势组合
Step 2: filter_match() → 匹配性分析
Step 3: structure_hypothesis + LLM → 假设生成（副业+公司双轨）
Step 4: round2 + LLM → 空行重新生成假设
Step 5: round3_finalize → 空行标记"待定"
Step 6: value_filter → 价值观筛选
Step 7: passion_filter → 激情筛选
Step 8: reality_filter → 现实筛选
Step 9: similar_filter → 最终方向
```

### 多 Journey API
- `GET /simple-auth/journeys` — 返回当前用户所有激活码 + 进度
- Dashboard 从此接口获取数据，不依赖 localStorage
- 清除浏览器缓存后 Journey 列表不会丢失

### 构建注意
- 构建前清除 `.next` 缓存：`rm -rf .next && npx next build`
- 字体文件较大（~70MB），首次 clone 后需确认 `public/fonts/` 完整

---

## 五、验证结果

- 后端测试：14 passed, 0 failed
- TypeScript 编译：无错误
- ESLint：无警告或错误
- Production build：`Compiled successfully`
