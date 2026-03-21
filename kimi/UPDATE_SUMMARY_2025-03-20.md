# Kimi 文档更新摘要（2025-03-20）

> 本次更新同步了 `.cursor/` 目录中的架构变更到 `kimi/` 文档

---

## 一、架构变更来源

变更来自 `/home/gitclone/BeingDoing/.cursor/` 目录：

| 源文件 | 内容 |
|-------|------|
| `功能文档评审与后续计划.md` | 功能列表评审、Admin能力补齐计划 |
| `plans/2025-03-19_探索流程与AdminMock增强计划.md` | 聊天页布局、i18n、Admin Mock、Rumination流程 |
| `plans/rumination_与探索流程增强_1f73f7a4.plan.md` | Rumination Section级进度、Widget体系、跳步 |
| `plans/历史提炼与并发架构规划_c6219dd9.plan.md` | 锚点摘要、关键词提取、并发锁、API池 |

---

## 二、主要架构变更

### 1. Rumination（沉淀）阶段 - 第五步 🆕

**新增内容**：
- 第五步沉淀阶段，整合前四维结果
- Section级进度管理（6个主页面section + 9个筛选步骤）
- Python实现表格生成/筛选逻辑（非LLM Function Calling）
- Widget交互体系（表格、弹窗、Top3选择卡）

**涉及文件**：
- `src/backend/app/api/v1/simple_chat.py` - rumination分支
- `src/frontend/app/(main)/explore/chat/rumination/page.tsx`
- `src/frontend/components/explore/RuminationTableWidget.tsx`（规划中）

### 2. Admin Mock 数据系统 ✅

**新增内容**：
- Mock数据目录：`data/admin_mock/`
- 用于跳步测试，预填未完成阶段数据
- 支持将历史数据保存为Mock复用

**新增API**：
- `GET /admin/conversations/mock-info`
- `POST /admin/conversations/init-mock`
- `POST /admin/conversations/apply-mock-to-activation`
- `POST /admin/conversations/save-as-mock`
- `POST /admin/conversations/jump-to-rumination`

### 3. i18n 国际化 ✅

**新增内容**：
- 探索流程接入国际化
- 支持中英文切换
- 新增i18n键：阶段名、描述、hint、侧边栏等

**涉及文件**：
- `src/frontend/lib/i18n/locales/zh.ts`
- `src/frontend/lib/i18n/locales/en.ts`

### 4. 锚点摘要机制 🔄

**规划中**：
- 用结构化摘要替代完整历史消息
- 减少token消耗，提升响应速度
- 锚点内容：goals、性格、风格、冲突等
- 触发时机：结论卡后、step提交、每20轮

### 5. 文件级并发锁 ✅

**新增内容**：
- 解决多用户并发写文件丢失问题
- 锁粒度：按 `(report_id, category)` 即按文件加锁
- 使用 `filelock` 或 `fcntl.flock`

**涉及文件**：
- `src/backend/app/utils/conversation_file_manager.py`

### 6. API 池与 VIP 模型 🔄

**规划中**：
- 多厂商支持：DeepSeek(VIP1) + Kimi/Qwen(VIP2)
- 按用户/激活码映射VIP等级
- 改造 `factory.py` 和配置

---

## 三、文档更新详情

### 1. `1-项目目录和文件关系梳理.md`

**更新内容**：
- 新增更新时间标注
- 添加架构变更说明（Rumination、Admin Mock、i18n等）
- 更新后端目录结构：
  - 新增 `admin_mock.py`、`context_refiner.py`
  - 更新 `conversation_file_manager.py`（并发锁）
  - 更新 `steps.py`（rumination阶段）
- 更新前端目录结构：
  - 新增 `lib/i18n/` 目录
- 更新核心文件对应关系表

### 2. `2-前后端架构关系与调用逻辑.md`

**更新内容**：
- 新增技术栈：i18n、并发控制
- 更新用户旅程流程图（添加rumination）
- 更新简单模式对话流程：
  - 文件级并发锁
  - 锚点摘要 + 最近20轮
- 新增API路由对应表：
  - Rumination API
  - Admin Mock API
- 更新状态持久化流（锚点摘要、Mock数据）

### 3. `3-AI对话提示词与对话逻辑分析.md`

**更新内容**：
- AI对话架构概览新增Rumination模式
- 更新简单模式对话流程：
  - 阶段定义添加rumination
  - 锚点摘要替代完整历史
  - 文件级并发锁
- 新增Rumination Prompt结构说明
- 更新题目进度管理：
  - 新增 `RuminationProgress` 模型
- 更新简单模式vs完整模式对比表（添加Rumination列）
- 更新未来优化建议（标记已实现项）

### 4. `4-核心API文档汇总.md`

**更新内容**：
- API概览添加Rumination、Admin Mock分类
- 更新所有phase参数说明（添加rumination）
- 新增Admin Mock API详细文档：
  - mock-info、init-mock
  - apply-mock-to-activation
  - save-as-mock
  - jump-to-rumination
- 新增Rumination API详细文档：
  - rumination-progress（GET/POST）
  - rumination-table-submit

### 5. `5-过期文档分析与标注.md`

**更新内容**：
- 新增分析方法（Rumination支持、i18n支持）
- 更新docs/目录分析：
  - API_DOCUMENTATION.md（缺少Rumination、Admin Mock API）
  - ARCHITECTURE.md（缺少Rumination、i18n、并发锁）
- 添加新增架构变更标注

### 6. `6-未来演进与规划建议.md`

**更新内容**：
- 更新技术栈现状（Rumination、i18n、并发锁）
- 更新当前对话架构图（添加Rumination）
- 更新演进路径（标记已实现的锚点摘要、i18n、并发锁）
- 更新2024 Q2路线图：
  - 主题改为"基础强化 + Rumination交付"
  - 添加Rumination阶段开发任务
  - 添加Admin Mock系统任务
  - 添加性能优化任务（并发锁、锚点摘要）
- 更新核心建议（标记当前重点）
- 新增架构变更总结表

---

## 四、关键新增概念

### 1. Rumination Section 级进度

```typescript
interface RuminationProgress {
  main_section: string;       // opening/review/filter/final_choice/recommend/end
  review_sub_index: number;   // 0=values 1=strengths 2=interests 3=purpose
  filter_step: number;        // 0=未进入 1~9=筛选步骤
  filter_table: object | null; // 当前表格数据
}
```

### 2. 锚点摘要

```typescript
interface AnchorSummary {
  goals: string[];           // 必须捕获的目标信息
  personality: string;       // 用户性格特征
  style: string;             // 对话风格偏好
  conflicts: string[];       // 冲突矛盾点
  // 可扩展字段...
}
```

### 3. Widget 消息协议

```typescript
interface StructuredMessage {
  role: 'assistant' | 'conclusion_card' | 'table_widget' | 'top3_card';
  content?: string;
  card_payload?: Record<string, unknown>;
  widget_type?: 'rumination_table' | 'dimension_conclusion' | 'top3_choice';
}
```

### 4. 文件级并发锁

```python
# 锁粒度：按 (report_id, category) 即按文件
lock_key = f"{report_id}:{category}"
# 不同文件独立锁，同文件串行写
```

---

## 五、后续建议

1. **继续跟踪.cursor目录**：定期检查新的架构变更文档
2. **保持文档同步**：每次架构变更后更新kimi文档
3. **完善Rumination文档**：待Rumination开发完成后补充详细设计文档
4. **API文档维护**：及时更新API_DOCUMENTATION.md中的新接口

---

**更新时间**：2026-03-20  
**变更来源**：/home/gitclone/BeingDoing/.cursor/  
**文档位置**：/home/gitclone/BeingDoing/kimi/
