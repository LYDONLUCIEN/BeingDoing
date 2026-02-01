# 开发指南

## 🛠️ 开发环境设置

### 1. 克隆项目

```bash
git clone <repository-url>
cd 职业规划-找到喜欢的事
```

### 2. 后端环境

```bash
cd src/backend

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp ../../.env.example ../../.env
# 编辑 .env 文件

# 初始化数据库
alembic upgrade head
python scripts/init_db.py
```

### 3. 前端环境

```bash
cd src/frontend

# 安装依赖
npm install

# 配置环境变量（可选）
# 默认使用 .env 中的 NEXT_PUBLIC_API_URL
```

## 📝 代码规范

### Python代码规范

- 遵循 **PEP 8**
- 使用 **Black** 格式化（可选）
- 类型提示：使用 `typing` 模块
- 文档字符串：使用 Google 风格

**示例**:
```python
from typing import Optional, List, Dict

async def get_user(user_id: str) -> Optional[Dict]:
    """
    获取用户信息
    
    Args:
        user_id: 用户ID
    
    Returns:
        用户信息字典，如果不存在则返回None
    """
    pass
```

### TypeScript代码规范

- 使用 **ESLint** 配置
- 使用 **Prettier** 格式化（可选）
- 类型定义：使用 TypeScript 接口
- 组件文档：使用 JSDoc

**示例**:
```typescript
interface User {
  user_id: string;
  email?: string;
}

/**
 * 获取用户信息
 * @param userId 用户ID
 * @returns 用户信息
 */
async function getUser(userId: string): Promise<User | null> {
  // ...
}
```

## 🏗️ 项目结构

### 后端结构

```
src/backend/
├── app/
│   ├── api/           # API路由
│   │   └── v1/        # API v1版本
│   ├── core/          # 核心服务
│   │   ├── agent/     # 智能体框架
│   │   ├── llmapi/    # LLM API
│   │   ├── asr/       # ASR API
│   │   ├── tts/       # TTS API
│   │   └── knowledge/ # 知识库
│   ├── models/        # 数据模型
│   ├── services/      # 业务逻辑
│   ├── utils/         # 工具函数
│   └── config/        # 配置
├── alembic/           # 数据库迁移
├── scripts/           # 脚本
└── requirements.txt   # 依赖
```

### 前端结构

```
src/frontend/
├── app/               # Next.js App Router
│   ├── auth/          # 认证页面
│   ├── profile/       # 用户信息页面
│   └── explore/       # 探索页面
├── components/        # React组件
│   └── explore/       # 探索相关组件
├── lib/               # 工具库
│   └── api/           # API客户端
├── stores/            # Zustand状态
└── package.json       # 依赖
```

## 🔄 开发流程

### 1. 创建新功能

1. **设计**: 在 `planning/` 目录下设计
2. **实现**: 按照模块化原则实现
3. **测试**: 编写测试用例
4. **文档**: 更新相关文档

### 2. 添加新API

1. 在 `src/backend/app/api/v1/` 创建路由文件
2. 在 `src/backend/app/services/` 实现业务逻辑
3. 在 `src/backend/app/main.py` 注册路由
4. 更新 `docs/API_DOCUMENTATION.md`

### 3. 添加新组件

1. 在 `src/frontend/components/` 创建组件
2. 在 `src/frontend/lib/api/` 添加API调用（如需要）
3. 在页面中使用组件
4. 添加类型定义

## 🧪 测试开发

### 编写测试

**位置**: `test/backend/` 或 `test/frontend/`

**命名**: `test_*.py` 或 `*.test.ts`

**示例**:
```python
import pytest
from app.services.auth_service import AuthService

@pytest.mark.asyncio
async def test_user_register():
    """测试用户注册"""
    result = await AuthService.register(
        email="test@example.com",
        password="password123"
    )
    assert result["user_id"] is not None
    assert result["token"] is not None
```

### 运行测试

```bash
# 后端
cd src/backend
pytest

# 前端（待实现）
cd src/frontend
npm test
```

## 🐛 调试技巧

### 后端调试

1. **使用日志**:
```python
import logging
logger = logging.getLogger(__name__)
logger.debug("调试信息")
```

2. **使用断点**:
```python
import pdb; pdb.set_trace()
```

3. **FastAPI调试**: 使用 `--reload` 自动重载

### 前端调试

1. **浏览器控制台**: 查看错误和日志
2. **React DevTools**: 调试组件状态
3. **Next.js调试**: 使用 `npm run dev` 开发模式

## 📦 依赖管理

### 添加Python依赖

```bash
# 安装依赖
pip install package_name

# 更新requirements.txt
pip freeze > requirements.txt
```

### 添加Node.js依赖

```bash
# 安装依赖
npm install package_name

# 安装开发依赖
npm install -D package_name
```

## 🔍 代码审查清单

- [ ] 代码符合规范
- [ ] 有适当的注释和文档
- [ ] 有测试用例
- [ ] 错误处理完善
- [ ] 性能考虑
- [ ] 安全性考虑

## 🔗 相关文档

- 测试说明: 查看 `docs/TESTING.md`
- API文档: 查看 `docs/API_DOCUMENTATION.md`
- 架构设计: 查看 `docs/ARCHITECTURE.md`
