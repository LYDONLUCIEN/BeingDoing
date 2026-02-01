# 环境变量配置说明

## 📝 .env.example 文件说明

`.env.example` 是环境变量配置模板文件，位于项目根目录。

### 作用
- 提供环境变量配置模板
- 说明需要配置哪些环境变量
- 作为 `.env` 文件的参考模板

### 使用方法

#### Windows PowerShell
```powershell
# 复制模板文件
Copy-Item .env.example .env

# 或使用脚本自动创建
.\setup_env.ps1
```

#### Linux/Mac
```bash
# 复制模板文件
cp .env.example .env

# 或使用脚本自动创建
./setup_env.sh
```

#### 手动创建
如果 `.env.example` 不存在，可以手动创建 `.env` 文件，内容参考上面的模板。

## 🔒 .env 文件说明

`.env` 文件是实际的环境变量配置文件：
- **位置**: 项目根目录
- **作用**: 存储实际的环境变量值（如API密钥等敏感信息）
- **安全**: 已被 `.gitignore` 忽略，不会提交到Git仓库

### 必须配置的变量

#### 最小配置（可以运行基础功能）
```env
SECRET_KEY=your-secret-key-here-change-in-production
```

#### 完整配置（需要LLM功能）
```env
SECRET_KEY=your-secret-key-here-change-in-production
OPENAI_API_KEY=sk-your-actual-api-key-here
```

### 配置说明

| 变量名 | 说明 | 是否必需 | 默认值 |
|--------|------|---------|--------|
| `SECRET_KEY` | 应用密钥，用于JWT等 | ✅ 必需 | - |
| `OPENAI_API_KEY` | OpenAI API密钥 | ⚠️ LLM功能需要 | - |
| `ARCHITECTURE_MODE` | 架构模式 | ❌ 可选 | `simple` |
| `AUDIO_MODE` | 语音功能开关 | ❌ 可选 | `False` |
| `DATABASE_URL` | 数据库连接URL | ❌ 可选 | SQLite默认 |

## 📋 .ps1 文件说明

### 什么是 .ps1 文件？

`.ps1` 是 **PowerShell 脚本文件**的扩展名。

- **PowerShell**: Windows 系统的命令行工具和脚本语言
- **作用**: 自动化执行一系列命令
- **类似**: Linux/Mac 的 `.sh` (Bash脚本)

### 项目中的 .ps1 文件

#### 1. `setup_env.ps1` - 环境配置脚本
**作用**: 自动配置开发环境
- 检查 Python 和 Node.js 是否安装
- 创建 Python 虚拟环境
- 安装 Python 依赖
- 安装 Node.js 依赖
- 创建 `.env` 文件

**使用方法**:
```powershell
# 在PowerShell中运行
.\setup_env.ps1
```

#### 2. `run_tests.ps1` - 测试运行脚本
**作用**: 自动运行测试
- 设置 PYTHONPATH
- 运行 pytest 测试

**使用方法**:
```powershell
.\run_tests.ps1
```

### 如何运行 .ps1 文件？

#### 方法1: 直接运行（推荐）
```powershell
# 在PowerShell中
.\setup_env.ps1
```

#### 方法2: 如果遇到执行策略限制
```powershell
# 临时允许执行脚本（当前会话）
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process

# 然后运行脚本
.\setup_env.ps1
```

#### 方法3: 使用 PowerShell ISE
- 打开 PowerShell ISE
- 打开 `.ps1` 文件
- 点击运行按钮

### 如果不想使用 .ps1 文件

可以手动执行脚本中的命令，或使用对应的 `.sh` 文件（Linux/Mac）。

## 🚀 快速开始

### 步骤1: 创建 .env 文件

**Windows**:
```powershell
Copy-Item .env.example .env
```

**Linux/Mac**:
```bash
cp .env.example .env
```

### 步骤2: 编辑 .env 文件

使用文本编辑器打开 `.env` 文件，至少修改：

```env
SECRET_KEY=your-actual-secret-key-here
OPENAI_API_KEY=sk-your-actual-api-key-here  # 如果需要LLM功能
```

### 步骤3: 验证配置

运行测试验证环境配置：
```powershell
# Windows
.\run_tests.ps1

# Linux/Mac
./run_tests.sh
```

## ❓ 常见问题

### Q1: 找不到 .env.example 文件？
**A**: 我已经创建了 `.env.example` 文件在项目根目录。如果还是找不到，可以手动创建 `.env` 文件。

### Q2: .ps1 文件无法运行？
**A**: 可能是PowerShell执行策略限制。运行：
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
```

### Q3: 不想使用 .ps1 文件？
**A**: 可以：
1. 使用对应的 `.sh` 文件（Linux/Mac）
2. 手动执行脚本中的命令
3. 参考 `DEPENDENCIES.md` 手动配置

### Q4: .env 文件应该放在哪里？
**A**: 项目根目录（与 `.env.example` 同级）
