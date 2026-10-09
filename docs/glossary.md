# 术语表（Glossary）

> 跨文档共享的领域/技术术语定义，按拼音排序。新增 ADR 引入的术语应同步补充到这里。

## F

- **付费状态（paid_status）**：用户筛选维度（ADR-0023），只分两档：名下存在 `PaymentOrder.status ∈ {paid, granted}` 订单 = `paid`（已付费），否则 = `unpaid`（未付费）。有意不区分试用/完整档——买过套餐但还在用试用码的人算已付费。被赠码的完整版用户落在 `unpaid`，由码类型（code_kind）维度补偿识别。

## G

- **过滤器注册表（Filter Registry）**：用户筛选系统的后端单一注册表（ADR-0023），每个过滤器声明 key/label/类型（multi_enum/enum/date_range/text）/选项/执行层/apply 函数；经 `GET /admin/filters/schema` 下发前端，通用 FilterBar 组件按 schema 渲染。筛选语义：过滤器内多值 OR、过滤器间 AND、空选不限。
- **SQL 下推过滤器 / 内存过滤器**：注册表过滤器的两个执行层（ADR-0023）。SQL 下推（如 user_type/paid_status/注册时间）先在数据库收窄；内存过滤器（如 stage/code_kind，数据在 JSON 文件）在全量候选上精筛。存在内存过滤器时分页退化为全量拉取+切片。

## L

- **dvh / svh / lvh（动态视口单位）**：CSS 视口高度单位。`dvh` 随移动端地址栏伸缩动态变化，`svh` 取最小、`lvh` 取最大。需 Chrome 108+；旧内核不识别时会**丢弃整条 CSS 声明**（不是按 100vh 解析），因此必须在前写 `vh` 回退（见 `.chat-shell-h`，ADR-0020）。
- **color-mix()**：CSS 颜色混合函数（如 `color-mix(in srgb, red 40%, white)`），需 Chrome 111+。不支持的浏览器丢弃整条声明，需静态近似色回退（ADR-0020）。

## M

- **码类型（code_kind）**：用户筛选维度（ADR-0023），取名下**非 consumed** 激活码的最高档：`full` > `trial` > `none`（无码）。过期码计入（曾经/当前是完整版用户），consumed 码不计（已消耗进他人升级）。`unpaid × full` = 被赠码用户。

## R

- **Rumination（沉淀阶段）**：探索流程的最后一个阶段，用户从「热爱 × 优势」组合中做最终方向选择。线上存在 v3（旧版，`RuminationTableWidget` 体系）与 v4（新版，`ruminationV4/` 组件体系）两个版本，由后端 `rumination_ab_assignments` 表 AB 分流，`?v4=1`/`?v3=1` 可调试覆盖。

## S

- **双核浏览器**：国产浏览器（搜狗/360/QQ 等）同时具备 Chromium 内核（「高速模式」）与 IE 内核（「兼容模式」）并自动/手动切换。高速模式内核版本可能显著落后于同期 Chrome（触发 ADR-0020 的兼容问题）；IE 兼容模式本项目不支持（Next.js 14 不含 IE 转译），由 root layout 的 ES5 内联脚本提供静态提示层避免白屏无提示。
- **`.chat-shell-h`**：探索/沉淀页外壳高度类（`flow-chat-light.css`），封装 `100vh → 100dvh` 回退，是所有 chat 阶段外壳高度的唯一合法写法（ADR-0020）。

## T

- **探索三态（stage）**：用户筛选维度（ADR-0023）：`not_started`（名下无任何 report record，含未激活）/ `exploring`（有 record 未全锁定）/ `report_unlocked`（任一 record 五阶段全锁定，`_report_portal_unlocked` 口径，与产品内报告入口解锁一致；不采用审核 approved 口径）。多 record 取最前进度归一。
- **特性检测（feature detection）**：通过 `CSS.supports()` 等 API 直接探测浏览器是否支持某特性，而非解析 UA 字符串推断。本项目旧内核判定用特性检测（dvh + color-mix，见 `lib/utils/browserCompat.ts`），因为双核浏览器 UA 不可靠且内核可切换。

## W

- **完整码 / 试用码（full / trial）**：激活码两档（ADR-0008）。试用码注册即送、不过期、仅 values 阶段限 10 轮；完整码解锁全阶段。可消耗 1 个未绑定完整码把试用码原地升级（ADR-0014）。
