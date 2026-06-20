# Step3 矩阵默认优势 + 富 Meta 数据（2026-06-20）

> 依据：Grill 决策（2026-06-20）
> 上游文档：[claude-todo-list-0616-step3-combo-matrix](./claude-todo-list-0616-step3-combo-matrix.md)
> 范围：Step3 矩阵模式下的两个问题修复 + 后端富数据改造

---

## 一、问题来源

进入 step3 matrix 模式后，发现两个问题：

1. **切换热爱没有默认优势**：点击任一热爱，右侧优势区不会自动选中一个默认优势。
   要求：切换任意热爱都应默认有一个优势被选中；除非该热爱下五个优势全部被 step2 标记为不匹配，否则哪怕只剩一个 matchable，默认也应选中它。
2. **热爱上的 ✓ 标记疑问**：三个热爱中某个有 ✓，切换到其他热爱时这个 ✓ 仍在原热爱上。
   结论：**这不是 bug**。✓ 的语义是"该热爱下所有 matchable 组合都已完成（confirmed/skipped）"，独立于当前选中状态。

---

## 二、决策清单（16 项）

| # | 决策点 | 选择 | 说明 |
|---|--------|------|------|
| 1 | 默认优势选哪个 | **A** | strength_idx 顺序的第一个可选优势 |
| 2 | 切回旧热爱是否记住上次选择 | **A** | 不记住，永远回第一个可选优势 |
| 3 | 初始进入 step3 是否自动选 | **B** | 自动选第一个热爱 + 它下面第一个可选优势 |
| 4 | 全置灰热爱的处理 | **A** | `selStrengthName=null`，结论卡片显示明确占位 |
| 5 | Bug 2 (✓ 语义) | **A** | 不改，✓ 是完成度标记，独立于选中 |
| 6 | 全置灰占位文案 | **C** | "该热爱暂无组合可探讨，可切换其他热爱" |
| 7 | "全不匹配"判断位置 | **A** | 子组件算（后被问题 11 推翻为后端算） |
| 8 | 默认优势触发时机 | **A** | 点击热爱 onClick 里直接 set，一次到位 |
| 9 | 初始自动选触发点 | **A** | 子组件一次性 useEffect |
| 10 | 父组件占位触发方式 | （推翻） | 走 meta，见问题 11/14 |
| 11 | 架构路线 | **甲** | 后端富数据，前端纯渲染 |
| 12 | 动态 ✓ (passionDone/strengthDone) 放哪 | **A** | 保留前端 useMemo（渲染派生） |
| 13 | meta 数据结构 | **Q** | 顶层 `combo_matrix_meta`，按热爱/优势分行 |
| 14 | meta 是否入库 | **R'** | 写回 `progress.combo_matrix_meta` |
| 15 | 原子写边界 | **T** | 同次 `merge_rumination_progress_fields`，meta 用独立函数 |
| 16 | 老数据迁移 | **A** | 前端全程可选链兜底 |

---

## 三、架构原则

### 核心立场
**Step2 跑完那一刻，所有静态结论就该定死。前端只负责"读字段 → 渲染"，不负责"算业务结论"。**

### 静态 vs 动态
- **静态**（step2 跑完定死，跟用户操作无关）：`is_non_matching`、`matchable_count`、`all_disabled`、`default_strength_idx`、`default_combo_id`、`total_matchable` → **后端给**
- **动态**（随 confirmed/skipped 变化）：`passionDone`、`strengthDone`、`done_count` → **前端 useMemo 算**（渲染派生）

### 正交关系
"每个组合独立讨论、独享上下文"靠 `combo_id` + 消息过滤实现（已存在），跟 meta 数据设计**正交、无关**。

---

## 四、数据结构定稿

### `combo_matrix_meta`

```python
{
    "total_matchable": int,           # 矩阵里所有 is_non_matching=False 的 combo 数
    "default_combo_id": str | None,   # 第一个 matchable 的 combo_id；全不匹配时 None
    "passions": [
        {
            "idx": int,
            "name": str,
            "matchable_count": int,            # 该热爱下 matchable 数（0 即 all_disabled）
            "all_disabled": bool,              # == (matchable_count == 0)
            "default_strength_idx": int | None # 该热爱下第一个 matchable 的 strength_idx；None 表示全置灰
        },
        # ...按 passion_idx 升序，3 个
    ],
    "strengths": [
        {
            "idx": int,
            "name": str,
            "matchable_count": int   # 该优势列下 matchable 数
        },
        # ...按 strength_idx 升序，5 个
    ],
}
```

---

## 五、改动清单

### 后端（3 处）

**1. `src/backend/app/utils/rumination_combo_matrix.py`**
- 新增 `build_combo_matrix_meta(matrix) -> dict`
- 输入：已构建好的 `combo_matrix`（含 `is_non_matching`）
- 输出：见上节结构
- 纯派生函数，不读 progress，不写文件

**2. `src/backend/app/api/v1/simple_chat_routes.py`**（rumination-combo-matrix endpoint，~L3290-3351）
- `matrix = build_combo_matrix(...)` 之后加 `meta = build_combo_matrix_meta(matrix)`
- `progress_fields` 字典里加 `"combo_matrix_meta": meta`
- 一次 `merge_rumination_progress_fields` 原子写（matrix 和 meta 同源同次）
- `response.data` 里加 `"combo_matrix_meta": meta`

**3. schema 不动**
- `combo_matrix_meta` 由 endpoint 写入，`rumination_progress.py` 的 normalize 不主动补
- 老数据下次进 step3 走 GET combo-matrix endpoint 时自动补上

### 前端（3 处）

**4. `src/frontend/lib/api/rumination.ts`**
- `RuminationProgress` 加 `combo_matrix_meta?: ComboMatrixMeta | null`
- 新增类型：`ComboMatrixMeta` / `ComboMatrixMetaPassion` / `ComboMatrixMetaStrength`

**5. `src/frontend/components/explore/step3/ComboMatrixSelector.tsx`**
- **删** `isStrengthDisabled` useMemo → 改读 `meta?.passions[i].all_disabled` 判全置灰、优势按钮置灰读 `meta.strengths` 里该优势的 matchable_count
- **删** 当前从 selectedComboId derive 的 useEffect 的旧逻辑分支
- **新增初始 useEffect**：`selPassionName == null && meta?.default_combo_id` 时，derive 第一个热爱 + 第一个默认优势（按问题 9 的 A）
- **改热爱 onClick**（问题 8 的 A）：`setSelPassionName(pName)` 同时读该热爱的 `default_strength_idx` set 对应优势名；若该热爱 `all_disabled=true`，set `selStrengthName(null)` 并通过新 prop 通知父组件
- **保留** `passionDone` / `strengthDone` 两个 useMemo（动态 ✓）
- **全置灰分支**：通过新 prop `onPassionAllDisabledChange?: (allDisabled: boolean) => void` 通知父组件

**6. `src/frontend/components/explore/step3/Step3MatrixLeftPanel.tsx`**
- **删** `matchableCombos` useMemo（line 390-393）→ 改读 `meta.total_matchable`
- 进度条分母、`completedCount/N` 显示用 `meta.total_matchable`
- 占位卡片（line 613-636）加分支：当 `currentCombo == null && 全置灰信号` 时显示文案 **"该热爱暂无组合可探讨，可切换其他热爱"**
- 接收并透传子组件的 `onPassionAllDisabledChange` 信号（用 state 存住）

---

## 六、竞态与死循环防护

| 风险 | 防护 |
|------|------|
| meta 写循环 | meta 只在 `rumination-combo-matrix` endpoint 写，其他 endpoint 不碰；前端只读不写 |
| matrix 与 meta 不一致 | 同源（同份 `non_matching_pairs` + passions/strengths）、同次 `merge_rumination_progress_fields` 原子写 |
| step2 重填后 meta 不更新 | endpoint 每次都重建 matrix + meta（注释见 `simple_chat_routes.py:3305-3306`），下次 GET 自动重算重写 |
| 老数据无 meta | 前端全程可选链（`meta?.passions?.find(...)`），老数据不报错；下次进 step3 走 endpoint 自动补 |

---

## 七、自测清单

- [ ] 初始进入 step3：自动选中第一个热爱 + 第一个 matchable 优势，结论卡片和聊天区有内容
- [ ] 点击切换热爱：右侧优势自动跳到该热爱的第一个 matchable 优势
- [ ] 切回旧热爱：不记住上次选择，仍回到第一个 matchable 优势
- [ ] 某热爱 5 个优势全置灰：切到该热爱时优势区空，结论卡片显示"该热爱暂无组合可探讨，可切换其他热爱"
- [ ] ✓ 标记：某热爱下所有 matchable 组合 confirmed/skipped 后该热爱亮 ✓，切换其他热爱不影响
- [ ] Step2 重新填写不匹配标记后，下次进 step3 meta 正确重算（matchable_count / all_disabled / default_strength_idx 跟着变）
- [ ] 老用户（progress 无 combo_matrix_meta）首次升级后进 step3 不报错，自动补上 meta

---

## 八、关键代码位置参考

| 文件 | 行号 | 说明 |
|------|------|------|
| `rumination_combo_matrix.py` | 12-40 | `build_combo_matrix`（meta 的新函数跟在后面） |
| `simple_chat_routes.py` | 3290-3351 | rumination-combo-matrix endpoint |
| `simple_chat_routes.py` | 2073 | `_resolve_non_matching_pairs` |
| `ComboMatrixSelector.tsx` | 55-64 | 旧 `isStrengthDisabled`（待删） |
| `ComboMatrixSelector.tsx` | 67-92 | 旧 derive / onSelectCombo useEffect（待改） |
| `ComboMatrixSelector.tsx` | 95-128 | `passionDone` / `strengthDone`（保留） |
| `Step3MatrixLeftPanel.tsx` | 390-393 | 旧 `matchableCombos`（待删） |
| `Step3MatrixLeftPanel.tsx` | 613-636 | 占位卡片（待加全置灰分支） |
| `rumination.ts` | 40-73 | `RuminationProgress` / `ComboItem` 类型 |
