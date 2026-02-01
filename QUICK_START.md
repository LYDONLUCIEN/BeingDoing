# 快速开始 - 第一阶段测试

## 📋 已完成内容

✅ **Phase 0.1**: 项目结构搭建
- 完整的目录结构
- 配置文件（.gitignore, .env.example等）
- 代码规范配置

✅ **Phase 0.3**: 配置管理系统
- 应用配置 (`app/config/settings.py`)
- 架构配置 (`app/config/architecture.py`)
- 引导策略配置 (`app/config/guide_config.py`)
- 语音配置 (`app/config/audio_config.py`)

## 🚀 快速测试

### 方法1: 使用测试脚本（推荐）

**Windows (PowerShell):**
```powershell
.\run_tests.ps1
```

**Linux/Mac:**
```bash
chmod +x run_tests.sh
./run_tests.sh
```

### 方法2: 手动运行

**步骤1: 安装依赖**
```bash
cd src/backend
pip install -r requirements.txt
```

**步骤2: 设置环境变量（可选）**
```powershell
# Windows PowerShell
$env:PYTHONPATH="src/backend"

# Linux/Mac
export PYTHONPATH="src/backend"
```

**步骤3: 运行测试**
```bash
# 从项目根目录运行
pytest test/backend/test_config.py -v
```

## ✅ 预期测试结果

应该看到4个测试通过：

```
test/backend/test_config.py::test_settings PASSED
test/backend/test_config.py::test_architecture_config PASSED
test/backend/test_config.py::test_guide_config PASSED
test/backend/test_config.py::test_audio_config PASSED

============================= 4 passed in 0.20s ==============================
```

## 📁 项目结构

```
.
├── src/
│   ├── backend/          # 后端代码
│   │   └── app/
│   │       ├── config/   ✅ 配置模块（已测试）
│   │       ├── api/      # API路由（待开发）
│   │       ├── core/     # 核心功能（待开发）
│   │       └── ...
│   └── frontend/         # 前端代码（待开发）
├── test/
│   └── backend/
│       └── test_config.py  ✅ 配置测试
├── data/                 # 数据文件
└── planning/             # 设计文档
```

## 🔍 测试内容详情

### 1. 应用配置测试
- ✅ 配置读取功能
- ✅ 必要配置项存在性

### 2. 架构配置测试
- ✅ 架构配置获取
- ✅ 简化架构配置验证
- ✅ 架构模式判断

### 3. 引导配置测试
- ✅ 超时时间配置
- ✅ 不同偏好超时时间
- ✅ 配置值合理性

### 4. 语音配置测试
- ✅ 语音功能开关
- ✅ ASR/TTS提供商配置

## 📝 下一步

完成测试后，继续开发：
- **Phase 0.2**: 数据库设计与初始化
- **Phase 1**: 核心AI服务（LLM/ASR/TTS）

详细任务请参考：`planning/todolist.md`

## ❓ 遇到问题？

查看 `TESTING.md` 获取详细的测试指南和常见问题解决方案。
