# DEBUG 记录

## 2026-02-04 后端启动 & 认证 & 数据库初始化

### 1. 启动后端服务

```bash
cd src/backend
uvicorn app.main:app --reload
```

### 2. 直接 curl 会报「未提供认证Token」的原因

`/api/v1/sessions` 的接口签名：

```python
@router.post("", response_model=StandardResponse)
async def create_session(
    request: CreateSessionRequest,
    current_user: Optional[dict] = Depends(get_current_user)
):
    ...
```

`get_current_user` 内部逻辑：

```python
if not token:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="未提供认证Token"
    )
```

所以：**任何调用 `POST /api/v1/sessions` 的请求都必须带上 `Authorization: Bearer <JWT>`，否则会返回 401。**

### 3. 本地调试时获取 JWT 的固定流程

```bash
# 1）先注册一个用户
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "test-password"
  }'

# 2）再登录拿到 token
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "test-password"
  }'

# 返回的 data 里有 token（JWT），拷贝出来，30 天内都可复用

# 3）创建会话时带上 Authorization 头
curl -X POST http://localhost:8000/api/v1/sessions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <你的token>" \
  -d '{
    "device_id": "debug-client",
    "current_step": "values_exploration"
  }'
```

JWT 相关信息（见 `AuthService`）：
- Token 有效期：`ACCESS_TOKEN_EXPIRE_MINUTES = 30 * 24 * 60`（30 天）
- 同一个 token 在未过期前可以反复使用，不需要每次测试都重新登录。

### 4. 数据库初始化与 Alembic 迁移（解决 no such table / MissingGreenlet）

**问题现象：**
- 注册时报错：`no such table: users`
- 执行 `alembic upgrade head` 报错：`sqlalchemy.exc.MissingGreenlet`

**原因简化解释：**
- 应用运行时用的是异步数据库 URL（例如 `sqlite+aiosqlite:///./app.db`），方便 FastAPI 用 async/await。
- Alembic 迁移工具默认使用“同步方式”连接数据库，不支持直接用 `sqlite+aiosqlite` 这类异步驱动。
- 结果在 Alembic 的同步环境里尝试执行异步连接 → 抛出 `MissingGreenlet`。

**修复方式（已经在 `alembic/env.py` 中完成）：**
- 从 `app.models.database.get_database_url()` 拿到 async URL（如 `sqlite+aiosqlite:///./app.db`）。
- 在 Alembic 里做一个小转换：
  - `sqlite+aiosqlite` → `sqlite`
  - `postgresql+asyncpg` → `postgresql`
- 这样：
  - **应用** 仍然使用异步 URL 运行；
  - **Alembic** 使用同步 URL 安全地建表，不再触发 `MissingGreenlet`。

**本地初始化数据库的一次性命令：**

```bash
cd src/backend
source venv/bin/activate        # Windows 用 venv\Scripts\activate

# 1）运行 Alembic 迁移，创建所有表结构
alembic upgrade head

# 2）运行初始化脚本，导入问题等基础数据
python scripts/init_db.py
```

之后再走“注册 → 登录 → 带 token 调用 /sessions”的流程，就不会再出现 `no such table` 之类的问题。
