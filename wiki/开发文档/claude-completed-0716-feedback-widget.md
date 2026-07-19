# AI 客服浮窗（Feedback Widget）— 实施完成

> ✅ 设计已收敛，2026-07-16 grill-me 完成
> ✅ OSS 基础设施已验证可用
> ✅ **2026-07-16 实施完成**（后端 + 前端 + admin + 定时任务）
> ⚠️ 待人工收尾：RAM 权限收紧（详见末尾「上线检查清单」）

## 一、范围

**显示位置：** 仅登录后页面（`(main)` 路由组）
- ✅ 显示：dashboard、explore、报告页、profile、community、theory、settings、contact、about 等
- ❌ 不显示：`auth/*`、`admin/*`

**匿名：** 不支持，必须登录。

**浮窗挂载点：** `(main)/layout.tsx`

## 二、核心设计哲学

**通知用站内信，沟通用邮件。** 各做各擅长的事。

- 站内信 = 通知通道（告诉双方"有事发生"）
- 邮件 = 沟通通道（实际多轮对话）
- **邮件往返不归档到 DB**（v1 限制，简化架构）

## 三、完整流程

### 用户提反馈
1. 用户在浮窗提交：`type`(bug/idea) + `content` + 截图(可选)
2. 后端事务内：
   - 插 `feedbacks`(status=received)
   - 关联 attachments 到 feedback
   - 插 `notification` 给**用户**：「【留言反馈】感谢您的反馈，我们将在 3 天内通过邮箱与您联系」
   - 插 `notification` 给**每个 super_admin**：「【留言反馈】新反馈来自 {user_email}：{content 前 60 字}…」
3. 用户浮窗红点+，打开看到 auto_ack

### admin 处理
4. admin 后台红点+，看到「新反馈」通知
5. 点通知 → 跳 `/admin/feedbacks/{id}` 看详情（含全文 + 用户邮箱 + 截图）
6. **admin 打开自己邮件客户端**，用 `support@xxx` 或自己邮箱回用户
7. 后续来回都在邮箱里，DB 不记录
8. admin 处理完后，在后台手动改 `status=done` → 用户收通知「【留言反馈】您的反馈已处理完毕」

### 用户感知
- 提交即看到「将通过邮箱联系」
- admin 邮件回复到达用户邮箱
- 后续邮件往返用户在自己邮箱查
- 反馈完结时浮窗红点+，知道结束了

## 四、数据模型

### `feedbacks` 表
```python
class Feedback(Base):
    __tablename__ = "feedbacks"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    user_email = Column(String(255), nullable=False)  # 冗余快取，admin 后台直接显示
    type = Column(String(20), nullable=False)  # bug / idea
    content = Column(Text, nullable=False)  # 5~2000 字
    status = Column(String(20), default="received", nullable=False)
    # received → in_progress → done（admin 手动改）
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
```

### `feedback_attachments` 表（截图）
```python
class FeedbackAttachment(Base):
    __tablename__ = "feedback_attachments"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    feedback_id = Column(String(36), ForeignKey("feedbacks.id", ondelete="CASCADE"), nullable=True)  # 孤儿模式 NULL
    uploader_user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    oss_key = Column(String(255), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    content_type = Column(String(50), nullable=False)  # image/jpeg|png|webp
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
```

### `notifications` 表（通知，双向）
```python
class Notification(Base):
    __tablename__ = "notifications"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # 收件人可以是普通用户，也可以是 admin（每个 super_admin 各发一条）
    type = Column(String(30), nullable=False)
    # feedback_auto_ack / feedback_new / feedback_status_changed / announcement
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    read_at = Column(DateTime, nullable=True)  # NULL=未读
    related_feedback_id = Column(String(36), ForeignKey("feedbacks.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
```

### notification type 语义
| type | 收件人 | 触发时机 |
|---|---|---|
| `feedback_auto_ack` | 提交反馈的用户 | 用户提反馈时 |
| `feedback_new` | 每个 super_admin | 用户提反馈时 |
| `feedback_status_changed` | 提交反馈的用户 | admin 改 status 时 |
| `announcement` | 任意用户 | 未来扩展，本次不做入口 |

### 索引
- `feedbacks`: `(user_id, created_at DESC)`、`(status, updated_at DESC)`（admin 列表）
- `feedback_attachments`: `(feedback_id)`、`(uploader_user_id, created_at)`（孤儿清理）
- `notifications`: `(user_id, created_at DESC)`、`(user_id, read_at)`（未读查询）

## 五、文件存储（阿里云 OSS）

### 已就绪配置
- endpoint: `oss-cn-shanghai.aliyuncs.com`
- bucket: `soulhappy-hermes-agent`（私有）
- SDK: `oss2==2.19.1`（需加到 requirements.txt）
- AK 已配置（最小权限待收紧：当前是 AliyunOSSFullAccess，跑通后换自定义策略）

### 设计
- 统一 `core/storage/` 抽象层（BaseStorage 接口）
- 首期实现 OSS Provider
- 私有 Bucket + 签名 URL（1 小时有效期）
- 服务端中转上传（前端 POST 后端，后端校验后传 OSS）
- 选图即上传，孤儿文件 7 天清理

### 限制
- 单图 ≤ 2MB（前端+后端双校验）
- 每条反馈 ≤ 3 张图
- jpg/png/webp

## 六、API 接口契约

### 错误响应风格（沿用项目现有约定）
```json
{
  "code": 400,
  "message": "中文错误消息",
  "timestamp": "2026-07-16T10:30:00+00:00"
}
```
状态码：400(校验) / 401(未登录) / 403(权限不足) / 404(不存在) / 500(服务端)

### 用户侧接口（`(main)` 路由组）

#### `POST /api/v1/feedbacks` — 提交反馈
```json
// req
{ "type": "bug", "content": "...", "attachment_ids": ["uuid1"] }
// res 201
{ "id": "...", "type": "...", "status": "received", "created_at": "..." }
```
副作用：事务内插 feedback + 关联 attachments + 给用户发 auto_ack + 给每个 admin 发 feedback_new

#### `POST /api/v1/feedbacks/attachments` — 上传截图
```
multipart/form-data: file=<binary>
res 201: { "id": "...", "preview_url": "签名URL", "size_bytes": N, "content_type": "image/png" }
```
孤儿模式，feedback_id 暂为 NULL。

#### `DELETE /api/v1/feedbacks/attachments/{id}` — 删除截图
- 仅删自己的 + 未关联的
- 204 + OSS 同步删除

#### `GET /api/v1/notifications/unread_count` — 未读数
```json
{ "count": 5 }
```
页面刷新时调，决定红点。

#### `GET /api/v1/notifications?page=1&page_size=20&unread_only=false` — 通知列表
```json
{
  "items": [{
    "id": "...", "type": "feedback_auto_ack",
    "title": "【留言反馈】...", "content": "...",
    "read_at": null, "related_feedback_id": "...", "created_at": "..."
  }],
  "total": 42, "page": 1, "page_size": 20, "unread_count": 5
}
```

#### `POST /api/v1/notifications/{id}/read` — 标记已读（幂等）
#### `POST /api/v1/notifications/read_all` — 全部已读

### 管理员侧接口（`/admin` 前缀）

#### `GET /api/v1/admin/feedbacks?type=&status=&page=&page_size=` — 列表
```json
{
  "items": [{
    "id": "...", "user": {"username":"...", "email":"..."},
    "type": "bug", "content": "...",  // 全文返回，前端截断
    "status": "received", "attachments_count": 2,
    "created_at": "...", "updated_at": "..."
  }]
}
```

#### `GET /api/v1/admin/feedbacks/{id}` — 详情
```json
{
  "id": "...", "user": {...}, "user_email": "...",
  "type": "...", "content": "...",
  "status": "...", "attachments": [{"id":"...", "signed_url":"...", "size_bytes":N}],
  "created_at": "...", "updated_at": "..."
}
```

#### `PATCH /api/v1/admin/feedbacks/{id}/status` — 改状态
```json
{ "status": "in_progress" }  // received/in_progress/done
```
副作用：给用户发 `feedback_status_changed` 通知。

## 七、UI 细节（2026-07-16 确认）

### 用户侧浮窗
- **位置**：右下角
- **尺寸**：360 × 480 小窗（点开后）
- **内布局**：单栏切换（默认通知列表，点一条展开详情，返回回列表）
- **红点**：图标右上角红点 + 未读数字
- **动画**：淡入淡出 + scale
- **图标**：圆形 UI logo（v1 用一个圆形 placeholder，后续替换为 AI 机器人图标）
- **样式**：Tailwind + bd-* CSS 变量，跟主站风格一致

### admin 后台
- **路径**：`/admin/feedbacks`（列表）+ `/admin/feedbacks/[id]`（详情）
- **侧边栏**：在现有 `ADMIN_NAV_ITEMS` 加一项「用户反馈」（icon: MessageSquare 或 Mail）
- **样式**：**完全复用现有 admin 组件风格**（参考 `/admin/conversations`）
- 列表页：筛选（type/status）+ 分页表格
- 详情页：反馈全文 + 用户邮箱（可点击 mailto）+ 截图（签名 URL 加载）+ 状态切换按钮
- **不做回复输入框**（admin 用自己邮件客户端回）

## 八、邮件外发（2026-07-16 确认）

**仅在关键节点自动触发系统邮件，复用现有 notification_tasks 基础设施。**

| 触发场景 | 收件人 | 邮件标题 | 邮件内容 |
|---|---|---|---|
| 用户提反馈 | 用户注册邮箱 | 【留言反馈】我们已收到您的反馈 | 反馈摘要 + 「我们将在 3 天内通过邮箱与您联系」 |
| admin 改 status=done | 用户注册邮箱 | 【留言反馈】您的反馈已处理完毕 | 简短通知 + 反馈编号 |

**不发系统邮件的场景：**
- admin 平时的多轮邮件回复 → admin **手动**用邮件客户端发，与系统无关
- admin 改 status=in_progress → 只发站内信，不发邮件（避免邮件轰炸）

**外发实现：** 复用项目现有 `notification_tasks` + 邮件服务基础设施（不做新依赖）

---

# ✅ 实施完成总结（2026-07-16）

## 已交付文件清单

### 后端（Python / FastAPI）
| 文件 | 作用 |
|---|---|
| `src/backend/requirements.txt` | 新增 `oss2>=2.19.0` |
| `src/backend/app/config/settings.py` | 新增 OSS_*、FEEDBACK_ORPHAN_CLEANUP_* 配置项 |
| `src/backend/app/core/storage/__init__.py` | storage 抽象层入口 |
| `src/backend/app/core/storage/base.py` | BaseStorage 接口 + StorageObject |
| `src/backend/app/core/storage/oss_provider.py` | 阿里云 OSS 实现 + key 生成工具 |
| `src/backend/app/core/storage/factory.py` | get_storage() 单例工厂 |
| `src/backend/app/models/feedback.py` | Feedback / FeedbackAttachment / Notification 三张表 |
| `src/backend/app/models/__init__.py` | 导出新模型 |
| `src/backend/alembic/versions/010_feedback_and_notifications.py` | migration（已执行成功） |
| `src/backend/app/schemas/__init__.py` | schemas 包初始化 |
| `src/backend/app/schemas/feedback.py` | 请求/响应 Pydantic 模型 |
| `src/backend/app/services/feedback_service.py` | 反馈+通知业务逻辑 |
| `src/backend/app/services/feedback_orphan_cleanup.py` | 孤儿附件定时清理 |
| `src/backend/app/utils/super_admin.py` | 新增 `get_super_admin_user_ids()` |
| `src/backend/app/api/v1/feedbacks.py` | 用户侧：提反馈、传/删截图 |
| `src/backend/app/api/v1/notifications.py` | 用户侧：未读数、列表、标记已读 |
| `src/backend/app/api/v1/admin_feedbacks.py` | 管理员：列表、详情、改状态 |
| `src/backend/app/main.py` | 注册新 router + 加孤儿清理 scheduler |

### 前端（Next.js 14）
| 文件 | 作用 |
|---|---|
| `src/frontend/lib/api/feedback.ts` | 用户侧 API client |
| `src/frontend/lib/api/admin.ts` | 扩展：反馈管理 API（fetch/list/detail/update_status） |
| `src/frontend/lib/utils/timeAgo.ts` | 相对时间工具（"3 分钟前"） |
| `src/frontend/stores/notificationStore.ts` | Zustand 状态管理 |
| `src/frontend/components/feedback/FloatingFeedbackWidget.tsx` | 浮窗主组件（右下角 360x480） |
| `src/frontend/components/feedback/NotificationList.tsx` | 通知列表 |
| `src/frontend/components/feedback/FeedbackForm.tsx` | 提反馈表单（类型+内容+截图） |
| `src/frontend/components/feedback/AttachmentUploader.tsx` | 截图上传（选图即传 + 缩略图 + 删除） |
| `src/frontend/app/(main)/layout.tsx` | 挂载浮窗 |
| `src/frontend/app/(main)/admin/feedbacks/page.tsx` | admin 列表页（筛选+分页） |
| `src/frontend/app/(main)/admin/feedbacks/[id]/page.tsx` | admin 详情页（状态切换+mailto 回复） |
| `src/frontend/app/(main)/admin/layout.tsx` | 侧边栏加「用户反馈」菜单项 |

### 测试
| 文件 | 作用 |
|---|---|
| `test/backend/test_feedback_service.py` | 9 个 service 层测试（全过） |
| `test/backend/test_feedback_orphan_cleanup.py` | 孤儿清理测试（过） |

## 已验证

- ✅ Alembic migration 010 成功执行（三张表 + 6 个索引）
- ✅ OSS 实测连通（ListObjects / PutObject / GetObject / DeleteObject / 签名 URL 全通）
- ✅ 后端端到端测试：注册 → 提反馈 → 拉通知 → 标记已读 → 权限校验 → 字段校验
- ✅ 前端 `next build` 通过，`next lint` 无新增警告
- ✅ APScheduler 启动日志：`feedback orphan cleanup scheduler started, cron='0 4 * * *'`

## API 端点一览

### 用户侧
| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/api/v1/feedbacks` | 提反馈（type/content/attachment_ids） |
| POST | `/api/v1/feedbacks/attachments` | 上传截图（multipart） |
| DELETE | `/api/v1/feedbacks/attachments/{id}` | 删截图（仅自己的+未关联） |
| GET | `/api/v1/notifications/unread_count` | 未读数（页面刷新调） |
| GET | `/api/v1/notifications` | 通知列表（分页） |
| POST | `/api/v1/notifications/{id}/read` | 标记单条已读 |
| POST | `/api/v1/notifications/read_all` | 全部已读 |

### 管理员侧（需 is_super_admin）
| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/v1/admin/feedbacks` | 列表（type/status 筛选 + 分页） |
| GET | `/api/v1/admin/feedbacks/{id}` | 详情（含附件签名 URL） |
| PATCH | `/api/v1/admin/feedbacks/{id}/status` | 改状态（发通知给用户） |

## 上线检查清单

### 🔴 必做（用户）
- [ ] **RAM 权限收紧**：当前 RAM 子账号挂的是 `AliyunOSSFullAccess`，需换成自定义策略只给 `soulhappy-hermes-agent` Bucket 的 PutObject/GetObject/DeleteObject/ListObjects/ListParts/AbortMultipartUpload 权限。详见末尾「RAM 收紧步骤」。
- [ ] **前端手动测试浮窗**：登录后访问任意 `(main)` 页面，右下角应有圆形悬浮按钮
- [ ] **admin 后台手动测试**：访问 `/admin/feedbacks`，测试列表筛选 + 详情 + 状态切换

### 🟡 推荐
- [ ] **前端页面可见性变化时刷新未读数**：已实现 `visibilitychange` 监听，建议打开几个 tab 切换验证
- [ ] **多 admin 场景测试**：当前给所有 super_admin 各发一条 feedback_new 通知。若实际有多个 admin，确认都收到

### 🟢 已自动完成
- ✅ 数据库 migration 已执行
- ✅ OSS 连通性已验证
- ✅ 孤儿清理 cron（每日 04:00）已注册到 APScheduler

## 已知限制（设计阶段已确认接受）

1. **邮件往返不归档**：admin 用自己邮件客户端回用户后，邮件来回不入 DB。DB 里只有初次反馈 + 状态变更通知。
2. **管理员回复走邮件**：admin 后台没有回复输入框，详情页有 `mailto:` 链接直接打开邮件客户端。
3. **不做实时推送**：用户刷新页面或切换 tab 时拉取未读数，无 WebSocket / SSE / 轮询。
4. **错误响应格式**：项目中间件 `ErrorHandlerMiddleware` 实际未生效（项目老问题），HTTPException 直接返回 `{"detail": "..."}`，反馈接口跟项目一致。

## RAM 收紧步骤（用户操作）

1. 登录 https://ram.console.aliyun.com/
2. 「身份管理」→「用户」→ 点击你创建的 RAM 子用户
3. 「权限管理」→ 移除 `AliyunOSSFullAccess`
4. 「权限策略」→「创建权限策略」：
   - 策略名：`BeingDoingOSSMinimal`
   - 脚本：
   ```json
   {
     "Version": "1",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "oss:PutObject",
           "oss:GetObject",
           "oss:DeleteObject",
           "oss:ListObjects",
           "oss:ListParts",
           "oss:AbortMultipartUpload"
         ],
         "Resource": [
           "acs:oss:*:*:soulhappy-hermes-agent",
           "acs:oss:*:*:soulhappy-hermes-agent/*"
         ]
       }
     ]
   }
   ```
5. 回到 RAM 用户，「新增授权」→ 选 `BeingDoingOSSMinimal` → 确定
6. 完成后跑一次反馈提交冒烟测试，确认仍能上传截图
