# AI 客服浮窗（Feedback Widget）— 最终设计决策

> ✅ 设计已收敛，2026-07-16 grill-me 完成
> ✅ OSS 基础设施已验证可用

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

# ✅ 设计已完整收敛，可以进入实施阶段

## 实施大纲（待用户确认开始）

### 后端
1. 加 `oss2>=2.19.1` 到 `requirements.txt`
2. `app/core/storage/` 抽象层（BaseStorage + OSSStorage）
3. `app/models/` 新增 3 个 model（Feedback / FeedbackAttachment / Notification）
4. Alembic migration `010_feedback_and_notifications.py`
5. `app/api/v1/feedbacks.py`（用户侧）+ `app/api/v1/admin/feedbacks.py`（管理员侧）
6. `app/api/v1/notifications.py`（用户侧通知接口）
7. 复用现有邮件外发服务，在 feedback 提交/status 变更时触发

### 前端
1. `components/feedback/FloatingWidget.tsx`（浮窗主组件）
2. `components/feedback/FeedbackForm.tsx`（提反馈表单）
3. `components/feedback/NotificationList.tsx`（通知列表）
4. `components/feedback/AttachmentUploader.tsx`（截图上传组件）
5. `stores/notificationStore.ts`（Zustand 状态管理）
6. `lib/api/feedback.ts` + `lib/api/notification.ts`
7. 挂载到 `(main)/layout.tsx`
8. `/admin/feedbacks` 列表页 + `/admin/feedbacks/[id]` 详情页
9. admin 侧边栏加菜单项

### 收尾
10. OSS RAM 权限收紧（从 AliyunOSSFullAccess 换成单 Bucket 最小权限策略）
11. 孤儿附件定时清理任务（7 天未关联）
