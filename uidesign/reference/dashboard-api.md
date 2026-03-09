# Dashboard & 探索报告 API 说明文档

本文档面向后续开发者，说明「个人空间 / 仪表盘」中的**报告生成**、**报告查看**、**当前进度**、**登录与头像**等的数据来源与设计，便于快速对接后端或扩展功能。

---

## 零、登录与探索逻辑

### 0.1 探索流程

- **仅使用 simple-chat 逻辑**：`/explore` 及之后的探索流程（信念/禀赋/热忱/使命四阶段）均走 simple-chat API，不开发 flow-chat 逻辑。
- **登录后跳转**：登录/注册成功后，**留在当前页面**或**仅跳转到唤起登录弹窗时的目标页**（`redirectTo`），不做随意跳转。

### 0.2 右上角用户头像

- **设计参考**：`uidesign/reference/dashboard/` 中的 `TopMenu.tsx`
- **交互**：登录后右上角显示用户头像（圆形），点击可展开下拉菜单
- **头像展示**：
  - 有 `avatar_url` 时：展示头像图片
  - 无头像时：显示用户名/邮箱前两字母的缩写（渐变背景）
- **下拉菜单**：
  - 顶部：用户名、邮箱
  - 个人空间：跳转 `/dashboard`
  - 上传头像：跳转 `/profile/setup`（后续可接入头像上传 API）
  - 管理员：配色、效果实验室
  - 退出登录

### 0.3 头像上传（待实现）

- **前端**：`User` 类型已预留 `avatar_url` 字段
- **后端**：需提供头像上传接口（如 `POST /api/v1/users/avatar`），返回图片 URL 后更新 `authStore.user.avatar_url`
- **存储**：可使用 OSS 或本地静态资源目录

---

## 一、整体架构

### 1.1 数据流概览

```
用户激活码 → session_id → data/simple/{session_id}/
                              ├── basic_info.json      # 调研问卷
                              ├── values.json          # 信念阶段对话历史
                              ├── strengths.json       # 禀赋阶段对话历史
                              ├── interests_goals.json # 热忱阶段对话历史
                              ├── purpose.json         # 使命阶段对话历史
                              ├── prior_context_strengths.txt   # 信念→禀赋的摘要
                              ├── prior_context_interests_goals.txt
                              └── prior_context_purpose.txt
```

### 1.2 探索四阶段与映射

| 前端 PhaseKey | 后端 phase | 文件/分类 | 中文 |
|---------------|------------|-----------|------|
| values | values | values | 信念 |
| strengths | strengths | strengths | 禀赋 |
| interests | interests_goals | interests_goals | 热忱 |
| purpose | purpose | purpose | 使命 |

---

## 二、当前进度（Current Progress）

### 2.1 如何判断进度？

进度由**客户端**和**后端**共同决定：

- **客户端**：`src/frontend/lib/explore/session.ts`
  - `ExploreSession` 存于 `localStorage`，key: `explore_session_{activationCode}`
  - 字段：`unlockedPhases`、`currentPhase`、`surveyCompleted`、`reportReady`
  - 用户完成某阶段后，前端调用 `unlockNextPhase()` 更新

- **后端**：每个阶段有**历史消息**即视为「有进度」
  - 通过 `GET /api/v1/simple-chat/history?activation_code=xxx&phase=values` 等接口可判断该阶段是否有对话

### 2.2 进度相关接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/v1/simple-chat/history` | GET | 获取指定阶段对话历史，有数据即该阶段有进度 |
| `/api/v1/simple-auth/activate` | POST | 验证激活码，返回 session_id、status 等 |

### 2.3 如何查看当前进度？

1. **前端**：`loadSession(activationCode)` 得到 `ExploreSession`，其中 `unlockedPhases` 即已解锁阶段列表
2. **后端**：按阶段依次请求 history，有 `messages` 且非空则对应阶段有进度

```http
GET /api/v1/simple-chat/history?activation_code=XXXX&phase=values
GET /api/v1/simple-chat/history?activation_code=XXXX&phase=strengths
GET /api/v1/simple-chat/history?activation_code=XXXX&phase=interests_goals
GET /api/v1/simple-chat/history?activation_code=XXXX&phase=purpose
```

---

## 三、报告（Report）

### 3.1 报告如何生成？

当前版本：**报告内容尚未有独立后端生成接口**，前端展示为占位页。

报告的数据基础已具备，可由以下数据组装：

- **基础信息**：`GET /api/v1/simple-chat/survey?activation_code=xxx` → `basic_info`
- **各阶段对话**：`GET /api/v1/simple-chat/history?activation_code=xxx&phase=values|strengths|interests_goals|purpose`
- **阶段间摘要**：`GET /api/v1/simple-chat/prior-context?activation_code=xxx&phase=strengths|interests_goals|purpose`

### 3.2 报告生成逻辑（建议实现）

1. **子报告（Sub Report）**：每个阶段对应一个子报告
   - 数据源：`history` 中该阶段的 `messages` + 可选 `prior_context`
   - 可对 AI 回复做摘要/提取关键词，或直接展示对话摘要

2. **主报告（Master Report）**：综合职业发展计划
   - 汇总四个阶段的结论
   - 生成时间：用户完成「使命」阶段后，进入报告预备页（`/explore/report`）时

3. **建议后端接口**（待开发）：
   - `POST /api/v1/simple-chat/generate-report`：根据 activation_code 生成报告，返回结构化 JSON/Markdown
   - `GET /api/v1/simple-chat/report?activation_code=xxx`：获取已生成的报告

### 3.3 如何查看报告？

- **前端路由**：`/explore/report`（预备页）→ `/explore/report/view`（报告详情）
- **条件**：`unlockedPhases` 包含 `purpose` 且用户点击「完成此步」进入下一阶段后
- **当前实现**：报告详情页为占位，提示「综合报告功能正在开发中」

---

## 四、关键接口汇总

### 4.1 激活与会话

| 接口 | 方法 | 请求体/参数 | 说明 |
|------|------|-------------|------|
| `/api/v1/simple-auth/activate` | POST | `{ "code": "激活码" }` | 激活会话，返回 activation_code、session_id、status |
| `/api/v1/simple-auth/activation` | POST | `{ "mode": "values", "ttl_minutes": 60 }` | 创建激活码（开发用） |

### 4.2 调研与基础信息

| 接口 | 方法 | 参数 | 说明 |
|------|------|------|------|
| `/api/v1/simple-chat/survey` | GET | `activation_code` | 获取调研问卷数据（basic_info） |
| `/api/v1/simple-chat/survey` | POST | `{ activation_code, survey_data }` | 保存调研问卷 |

### 4.3 对话历史与上下文

| 接口 | 方法 | 参数 | 说明 |
|------|------|------|------|
| `/api/v1/simple-chat/history` | GET | `activation_code`, `phase` | 获取指定阶段对话历史 |
| `/api/v1/simple-chat/init` | POST | `{ activation_code, phase }` | 初始化阶段，无历史时生成首轮引导问题 |
| `/api/v1/simple-chat/message` | POST | `{ activation_code, message, phase }` | 发送消息（非流式） |
| `/api/v1/simple-chat/message/stream` | POST | 同上 | 发送消息（流式） |
| `/api/v1/simple-chat/prior-context` | GET | `activation_code`, `phase` | 获取上一阶段摘要 |
| `/api/v1/simple-chat/prior-context` | POST | `{ activation_code, phase, context_text }` | 保存阶段间摘要 |

---

## 五、存储路径说明

- **激活码索引**：`data/simple/activations.json`
- **会话数据**：`data/simple/{session_id}/`
  - `basic_info.json`：调研
  - `values.json`、`strengths.json`、`interests_goals.json`、`purpose.json`：对话历史
  - `prior_context_{phase}.txt`：阶段摘要

---

## 六、设计参考

个人空间 UI 参考 `uidesign/reference/dashboard/` 目录：

- `TopMenu.tsx`：右上角用户头像、点击展开详情/个人主页/退出
- `DashboardLayout.tsx`：左侧边栏 + 头像 + 导航
- `CurrentProgress.tsx`：当前进度（阶段节点、完成/进行中/未解锁）
- `Report.tsx`：主报告 + 子报告列表、下载/分享/删除

可根据本文档中的接口与数据流，将参考设计接入实际 API。
