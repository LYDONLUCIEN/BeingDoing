# 数据库设计文档

## 📊 数据库概览

### 数据库选择

- **开发环境**: SQLite (文件数据库)
- **生产环境**: PostgreSQL (关系型数据库)
- **切换方式**: 通过 `ARCHITECTURE_MODE` 和 `DATABASE_URL` 配置

### 数据库文件位置

- SQLite: `data/app.db`
- 对话记录: `data/conversations/{session_id}/{category}.json` (JSON文件)

## 📋 数据表设计

### 用户相关表

#### users
用户基础信息表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| email | String | 邮箱（可选） |
| phone | String | 手机号（可选） |
| username | String | 用户名（可选） |
| password_hash | String | 密码哈希 |
| is_active | Boolean | 是否激活 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |
| last_login_at | DateTime | 最后登录时间 |

#### user_profiles
用户详细信息表

| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | UUID | 外键 → users.id |
| gender | String | 性别 |
| age | Integer | 年龄 |
| profile_completed | Boolean | 信息是否完成 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

#### work_histories
工作履历表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| user_id | UUID | 外键 → users.id |
| company | String | 公司名称 |
| position | String | 职位 |
| start_date | Date | 开始日期 |
| end_date | Date | 结束日期（NULL表示当前工作） |
| evaluation | Text | 工作评价 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

#### project_experiences
项目经历表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| work_history_id | UUID | 外键 → work_histories.id |
| name | String | 项目名称 |
| description | Text | 项目描述 |
| role | String | 担任角色 |
| achievements | Text | 成就描述 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

### 会话相关表

#### sessions
会话表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| user_id | UUID | 外键 → users.id（可选） |
| device_id | String | 设备ID（可选） |
| current_step | String | 当前探索步骤 |
| status | String | 会话状态 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |
| last_activity_at | DateTime | 最后活动时间 |

#### progress
进度表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| session_id | UUID | 外键 → sessions.id |
| step | String | 探索步骤 |
| completed_count | Integer | 已完成数量 |
| total_count | Integer | 总数量 |
| started_at | DateTime | 开始时间 |
| completed_at | DateTime | 完成时间（可选） |

### 问答相关表

#### questions
问题表（从question.md加载，不存数据库）

#### answers
回答表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| session_id | UUID | 外键 → sessions.id |
| question_id | Integer | 问题ID（可选） |
| category | String | 问题分类 |
| content | Text | 回答内容 |
| metadata | JSON | 元数据（可选） |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

### 选择相关表

#### user_selections
用户选择表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| session_id | UUID | 外键 → sessions.id |
| category | String | 分类（values/strengths/interests） |
| selected_items | JSON | 选中的项目列表 |
| created_at | DateTime | 创建时间 |

#### guide_preferences
引导偏好表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| session_id | UUID | 外键 → sessions.id |
| preference | String | 偏好（normal/quiet） |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

#### exploration_results
探索结果表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| session_id | UUID | 外键 → sessions.id |
| values_selected | JSON | 选中的价值观 |
| strengths_selected | JSON | 选中的才能 |
| interests_selected | JSON | 选中的兴趣 |
| wanted_thing | Text | 想做的事 |
| true_wanted_thing | Text | 真正想做的事 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

## 📁 文件存储

### 对话记录

**位置**: `data/conversations/{session_id}/{category}.json`

**结构**:
```json
{
  "session_id": "uuid",
  "category": "main_flow",
  "messages": [
    {
      "id": "msg_1",
      "role": "user",
      "content": "消息内容",
      "context": {},
      "created_at": "2024-01-01T00:00:00Z"
    }
  ],
  "metadata": {
    "total_messages": 1,
    "last_updated": "2024-01-01T00:00:00Z"
  }
}
```

**分类**:
- `main_flow.json`: 主流程对话
- `guidance.json`: 引导对话
- `clarification.json`: 澄清对话
- `other.json`: 其他对话

## 🔄 数据关系

```
users
  ├── user_profiles (1:1)
  ├── work_histories (1:N)
  │   └── project_experiences (1:N)
  └── sessions (1:N)
      ├── progress (1:N)
      ├── answers (1:N)
      ├── user_selections (1:N)
      ├── guide_preferences (1:1)
      └── exploration_results (1:1)
```

## 🗄️ 数据库迁移

### 使用Alembic

```bash
# 创建迁移
alembic revision --autogenerate -m "描述"

# 应用迁移
alembic upgrade head

# 回滚迁移
alembic downgrade -1
```

### 初始化数据库

```bash
python scripts/init_db.py
```

## 📊 索引设计

### 主要索引

- `users.email`: 唯一索引
- `users.phone`: 唯一索引
- `sessions.user_id`: 索引
- `sessions.device_id`: 索引
- `answers.session_id`: 索引
- `answers.category`: 索引

## 🔒 数据安全

### 敏感数据

- **密码**: 使用bcrypt加密存储
- **Token**: 不存储，仅验证
- **对话记录**: JSON文件，按session隔离

### 数据备份

- **数据库**: 定期备份SQLite/PostgreSQL
- **对话记录**: 备份 `data/conversations/` 目录
- **知识库**: 版本控制（Git）

## 🔗 相关文档

- 模型定义: 查看 `src/backend/app/models/`
- 迁移脚本: 查看 `src/backend/alembic/versions/`
- API文档: 查看 `docs/API_DOCUMENTATION.md`
