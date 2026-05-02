# 测试说明文档

## 📋 测试概述

本项目采用测试驱动开发（TDD）方法，所有可独立测试的模块都包含测试用例。

## 🧪 测试结构

```
test/
├── backend/              # 后端测试
│   ├── core/            # 核心服务测试
│   │   ├── llmapi/      # LLM API测试
│   │   ├── asr/         # ASR测试
│   │   ├── tts/         # TTS测试
│   │   ├── agent/       # 智能体测试
│   │   └── knowledge/   # 知识库测试
│   ├── api/             # API接口测试
│   ├── services/        # 业务逻辑测试
│   └── models/          # 数据模型测试
├── frontend/            # 前端测试（待实现）
└── integration/         # 集成测试（待实现）
```

## 🚀 运行测试

### 后端测试

```bash
cd src/backend

# 运行所有测试
pytest

# 运行特定测试文件
pytest test/backend/test_config.py

# 运行特定测试类
pytest test/backend/test_config.py::TestSettings

# 运行特定测试方法
pytest test/backend/test_config.py::TestSettings::test_settings_loading

# 显示覆盖率
pytest --cov=app --cov-report=html

# 详细输出
pytest -v

# 只运行失败的测试
pytest --lf
```

### 前端测试（待实现）

```bash
cd src/frontend

# 运行测试
npm test

# 运行测试并显示覆盖率
npm test -- --coverage

# 运行E2E测试
npm run test:e2e
```

## 📝 测试分类

### 1. 单元测试

测试单个函数或类的功能。

**示例**: `test/backend/test_config.py`

```python
def test_settings_loading():
    """测试配置加载"""
    settings = Settings()
    assert settings.DEBUG is not None
```

### 2. 集成测试

测试多个模块的协作。

**示例**: `test/backend/test_database_operations.py`

```python
async def test_user_crud():
    """测试用户CRUD操作"""
    # 创建用户
    user = await user_db.create_user(...)
    # 查询用户
    found = await user_db.get_user_by_id(user.id)
    assert found is not None
```

### 3. E2E测试

测试完整的用户流程。

**示例**: 用户注册 → 登录 → 完善信息 → 开始探索

## 🔍 测试覆盖范围

### 已实现测试

- ✅ 配置模块测试
- ✅ 数据库模型测试
- ✅ 数据库操作测试
- ✅ LLM API测试（需要API密钥）
- ✅ ASR/TTS测试（需要API密钥）
- ✅ 知识库加载测试
- ✅ 对话文件管理测试

### 待实现测试

- ⏳ 智能体框架测试（需要LLM API）
- ⏳ API接口E2E测试
- ⏳ 前端组件测试
- ⏳ 前端页面测试
- ⏳ 完整用户流程测试

## 🎯 测试要求

### 代码覆盖率目标

- **单元测试**: ≥80%
- **集成测试**: ≥60%
- **E2E测试**: 核心流程100%

### 测试原则

1. **独立性**: 每个测试应该独立运行
2. **可重复**: 测试结果应该一致
3. **快速**: 单元测试应该快速执行
4. **清晰**: 测试名称应该描述测试内容

## 📊 测试数据

### Mock数据

对于需要外部API的测试，使用Mock：

```python
from unittest.mock import Mock, patch

@patch('app.core.llmapi.openai_provider.OpenAI')
def test_llm_provider(mock_openai):
    # Mock OpenAI响应
    mock_openai.return_value.chat.completions.create.return_value = Mock(...)
    # 运行测试
```

### 测试数据库

使用独立的测试数据库：

```python
# conftest.py
@pytest.fixture
async def test_db():
    # 使用内存数据库或临时文件
    test_url = "sqlite+aiosqlite:///:memory:"
    # ...
```

## 🐛 调试测试

### 查看详细输出

```bash
pytest -v -s  # -s 显示print输出
```

### 使用调试器

```python
import pdb; pdb.set_trace()  # 在测试中设置断点
```

### 只运行失败的测试

```bash
pytest --lf  # last failed
pytest --ff  # failed first
```

## 📈 持续集成

### GitHub Actions（待实现）

```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: |
          pip install -r src/backend/requirements.txt
      - name: Run tests
        run: |
          cd src/backend
          pytest
```

## 🔗 相关文档

- 测试策略: 查看 `planning/todolist.md` 中的测试要求
- API测试: 查看 `docs/API_DOCUMENTATION.md`
- 开发指南: 查看 `docs/DEVELOPMENT.md`
