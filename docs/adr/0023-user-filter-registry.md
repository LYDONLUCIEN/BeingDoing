# ADR-0023: 通用用户筛选系统（过滤器注册表 + schema 下发）

**状态**: accepted
**日期**: 2026-10-09
**决策者**: 产品 + 开发 Grill（四轮拷问定稿）

## 背景

admin 数据导出页（2026-10-06 上线）筛选能力单薄：`user_type` 单选、`has_report` 单选，无法满足「多类别同时导出」「按探索阶段筛选」的运营需求。现有筛选参数扁平散落在各端点（`UsersExportRequest`: user_type/q/created_*/has_report；用户管理页另有活跃状态/profile 完成度等），每加一个维度要改三处（前端 select、API 类型、后端 SQL/内存分支）。

更关键的驱动：**多个产品近期确定复用同一套用户体系与用户库**（产品已确认是近期需求而非远期愿望），需要一套可复用的检索/筛选机制，而不是每个产品每个页面重写。

## 关键定义（拷问钉死，改动需重开本 ADR）

- **付费状态（paid_status）**：只分两档。名下存在 `PaymentOrder.status ∈ {paid, granted}` 订单 = `paid`（已付费），否则 = `unpaid`（未付费）。**不区分试用/完整档**——买了套餐但还在用试用码的人算「已付费」，这是有意口径（只关心花没花过钱）。
- **码类型（code_kind）**：补偿 paid_status 的盲区（被赠码的完整版用户没花过钱）。取名下**非 consumed** 激活码的最高档：`full` > `trial` > `none`（无码）。**过期码计入**（反映「曾经/当前是完整版用户」）；`consumed` 码不计（已消耗进他人升级）。典型组合：`unpaid × full` = 被赠码用户。
- **探索三态（stage）**：`not_started`（名下无任何 report record，含未激活用户）/ `exploring`（有 record 但未全锁定）/ `report_unlocked`（**任一** record 五阶段全锁定，即 `_report_portal_unlocked` 口径——与产品内「报告入口解锁」一致，用户真正看到报告才算出报告；**不采用**审核 `approved` 口径）。用户有多条 record（多激活码）时按**最前进度**归一。
- 旧 `has_report` 参数**废弃**，被 stage 完全吸收（`has_report=yes` ≡ `stage ∈ {exploring, report_unlocked}`）。
- 「用户类型」两套分类并存且正交，都可多选：运营手打标签 `user_type`（real/beta/test/admin，PATCH /admin/users/{id}/meta）与上述业务维度（paid_status / code_kind）。

## 决策

### 1. 后端过滤器注册表（Filter Registry）

单一注册表声明全部用户过滤器，每个过滤器是一个注册项：

```
key / label / 类型(multi_enum | enum | date_range | text) / 选项集 / 执行层(sql | memory) / apply 函数
```

首批过滤器：

| key | 标签 | 类型 | 执行层 | 语义 |
|---|---|---|---|---|
| `user_type` | 用户类型 | multi_enum(real/beta/test/admin) | SQL（IN） | 运营标签 |
| `paid_status` | 付费状态 | multi_enum(unpaid/paid) | SQL（EXISTS 订单子查询） | 见上方定义 |
| `code_kind` | 码类型 | multi_enum(none/trial/full) | 内存 | 见上方定义 |
| `stage` | 探索阶段 | multi_enum(not_started/exploring/report_unlocked) | 内存 | 见上方定义 |
| `q` | 关键词 | text | SQL | email/username 模糊 |
| `created_range` | 注册时间 | date_range | SQL | created_at 区间 |

用户管理页现有筛选（活跃状态 / profile 完成度 / 注册日期）按**现有语义平移**迁入注册表（实现时逐一核对现有口径，不改语义）。

### 2. 筛选语义（系统级，所有消费方一致）

- 过滤器**内部**多值 = **OR**（并集）；过滤器**之间** = **AND**；空选/未传 = 不限。
- **两层执行**：SQL 可下推条件先收窄 → 内存过滤器精筛 → （列表场景）分页切片。
- 存在内存过滤器时分页退化为「全量拉取 + 过滤后切片」。当前用户量级（数百）无感；**数万用户时再上预聚合表**（非目标，届时重开 ADR）。

### 3. schema 下发 + 通用前端筛选条

- 新增 `GET /admin/filters/schema`（admin 鉴权）：下发注册表声明（key/label/类型/选项），前端按 schema 渲染，**新增过滤器前端零改动**。
- 前端通用组件 `components/admin/FilterBar.tsx`：multi_enum 用 checkbox 组（项目无多选下拉组件，沿用现有「原生 checkbox + Set」风格，与表格勾选一致）、enum 用原生 select、date_range 用两个 date input、text 用 input。
- 新产品接入 = 后端注册新过滤器 + 页面挂 FilterBar，前端筛选 UI 零重写。

### 4. 消费方与 API

第一个迭代**同时接两个消费方**（单消费方的抽象必然设计成「刚好适配导出页」的伪通用）：

- **数据导出页**：`POST /admin/users/export` payload 从扁平字段改为 `{filters: {key: values}}`。**兼容映射层**：旧扁平参数（user_type/q/created_after/created_before/has_report）保留，内部映射为 filters（约 10 行），下个大版本移除。无数据风险（导出全程只读），双保险防前后端部署不同步。
- **用户管理页**：列表接口同步接 filters，现有筛选条迁到 FilterBar。

### 5. 非目标（明确不做）

- 保存筛选预设（saved filters）。
- 任意字段自由组合的 filter DSL / 自定义筛选字段。
- 预聚合 / 物化视图 / 筛选结果缓存。
- 抽成独立 pip 包（多产品在同一 monorepo + 同一后端，模块级抽象即可；跨仓库再议）。
- 导出硬上限 `MAX_EXPORT_USERS=50` 保留不变。

## 实现要点

- 后端：`app/services/user_filters/`（registry + 各过滤器 apply）；内存过滤器复用现成推导函数——stage 用 `report_registry.compute_explore_resume` / `_report_portal_unlocked`，code_kind 遍历激活码 JSON，paid_status 走 `PaymentOrder` EXISTS 子查询（SQL 下推，不进内存层）。
- 导出链路保持「分页 500 循环拉取」骨架，内存过滤器插入在拉取后、拼装前（与现 `has_report` 内存过滤同位）。
- 测试：每个过滤器 apply 的单测（含三态归并、code_kind 最高档、paid/unpaid 边界）、schema 端点、旧参数兼容映射、两消费方集成测试。
- **运营视角命名（2026-10-09 补）**：admin 用户表格首列 = 昵称（主）+ 邮箱（次行）；导出 zip 用户目录按「昵称+邮箱」命名（`user_export_service.build_user_export_dirname`：无昵称退邮箱、无邮箱退手机号、皆无退 `user-{id前8}`，非法字符转 `_`，撞名加 `-{id前8}` 去重），`index.json` 带 `export_dir`。FilterBar 单行不折行 + 横向滚动（`.bd-filterbar-scroll`）。

## 后果

- 新增筛选维度 = 注册表加一项 + apply 函数，前端零改动（schema 下发）；多产品复用路径成立。
- 内存过滤器（stage/code_kind）为 O(N) 遍历 JSON 文件，用户量数百时无感；量级增长后按「非目标」节升级。
- 导出 API 短期双轨（新旧参数并存），下个大版本删兼容层。
