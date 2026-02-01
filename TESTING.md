# 测试指南

## 第一阶段测试内容

第一阶段（Phase 0）已完成的内容：
1. ✅ 项目结构搭建
2. ✅ 配置管理系统

## 测试环境准备

### 1. 安装Python依赖

```bash
# 进入后端目录
cd src/backend

# 创建虚拟环境（如果还没有）
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 设置环境变量

```bash
# 从项目根目录复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，至少设置以下内容：
# SECRET_KEY=your-secret-key-here
# OPENAI_API_KEY=your-openai-api-key (如果需要测试LLM功能)
```

## 运行测试

### 方法1：从项目根目录运行（推荐）

```bash
# 从项目根目录运行
cd "e:\个人\职业规划-找到喜欢的事"

# 设置PYTHONPATH
$env:PYTHONPATH="src/backend"

# 运行测试
python -m pytest test/backend/test_config.py -v
```

### 方法2：从后端目录运行

```bash
# 进入后端目录
cd src/backend

# 运行测试（需要指定测试文件路径）
python -m pytest ../../test/backend/test_config.py -v

# 或者设置PYTHONPATH后运行
$env:PYTHONPATH="."
python -m pytest ../../test/backend/test_config.py -v
```

### 方法3：使用pytest.ini配置

项目根目录已有 `pytest.ini` 配置文件，配置了 `pythonpath = src/backend`。

```bash
# 从项目根目录运行
pytest test/backend/test_config.py -v
```

## 测试内容说明

### 1. 配置模块测试 (`test/backend/test_config.py`)

测试以下内容：

#### 1.1 应用配置测试 (`test_settings`)
- ✅ 测试配置读取
- ✅ 验证必要配置项存在

#### 1.2 架构配置测试 (`test_architecture_config`)
- ✅ 测试架构配置获取
- ✅ 验证简化架构配置项
- ✅ 验证架构模式判断

#### 1.3 引导配置测试 (`test_guide_config`)
- ✅ 测试引导超时时间配置
- ✅ 测试不同偏好的超时时间
- ✅ 验证配置值合理性

#### 1.4 语音配置测试 (`test_audio_config`)
- ✅ 测试语音功能开关
- ✅ 测试ASR/TTS提供商配置

## 运行所有测试

```bash
# 从项目根目录运行所有后端测试
pytest test/backend -v

# 查看测试覆盖率
pytest test/backend --cov=src/backend/app --cov-report=html
```

## 测试输出示例

成功运行后应该看到类似输出：

```
============================= test session starts =============================
platform win32 -- Python 3.11.5, pytest-7.4.0
collected 4 items

test/backend/test_config.py::test_settings PASSED
test/backend/test_config.py::test_architecture_config PASSED
test/backend/test_config.py::test_guide_config PASSED
test/backend/test_config.py::test_audio_config PASSED

============================= 4 passed in 0.20s ==============================
```

## 常见问题

### 问题1: ModuleNotFoundError: No module named 'app'

**解决方案**：
确保设置了PYTHONPATH：
```bash
$env:PYTHONPATH="src/backend"
```

或者从 `src/backend` 目录运行测试。

### 问题2: 找不到pytest

**解决方案**：
```bash
pip install pytest pytest-asyncio
```

### 问题3: 导入错误

**解决方案**：
检查 `test/backend/test_config.py` 中的导入路径是否正确。
确保 `pytest.ini` 中的 `pythonpath` 设置正确。

## 下一步测试

完成Phase 0后，接下来需要测试：
- Phase 0.2: 数据库设计与初始化
- Phase 1: 核心AI服务（LLM/ASR/TTS）

## 测试最佳实践

1. **每次修改代码后运行测试**
2. **提交代码前确保所有测试通过**
3. **添加新功能时同时添加测试**
4. **保持测试代码简洁清晰**
