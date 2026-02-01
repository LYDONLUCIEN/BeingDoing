# 手动环境配置指南

如果自动脚本无法运行，可以按照以下步骤手动配置环境。

## 📋 前置要求

- ✅ Python 3.10+ 已安装
- ✅ Node.js 18+ 已安装
- ✅ pip 和 npm 可用

## 🔧 步骤1: 配置 Python 后端环境

### Windows PowerShell

```powershell
# 1. 进入后端目录
cd src/backend

# 2. 创建虚拟环境
python -m venv venv

# 3. 激活虚拟环境
.\venv\Scripts\Activate.ps1

# 如果遇到执行策略错误，运行：
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process

# 4. 升级 pip
python -m pip install --upgrade pip

# 5. 安装依赖
pip install -r requirements.txt
```

### Linux/Mac

```bash
# 1. 进入后端目录
cd src/backend

# 2. 创建虚拟环境
python3 -m venv venv

# 3. 激活虚拟环境
source venv/bin/activate

# 4. 升级 pip
python -m pip install --upgrade pip

# 5. 安装依赖
pip install -r requirements.txt
```

## 🔧 步骤2: 配置 Node.js 前端环境

```bash
# 1. 进入前端目录
cd src/frontend

# 2. 安装依赖
npm install
```

## 🔧 步骤3: 创建环境变量文件

### 方法1: 复制模板文件

**Windows PowerShell:**
```powershell
# 从项目根目录执行
Copy-Item .env.example .env
```

**Linux/Mac:**
```bash
# 从项目根目录执行
cp .env.example .env
```

### 方法2: 手动创建 .env 文件

在项目根目录创建 `.env` 文件，内容如下：

```env
# 架构配置
ARCHITECTURE_MODE=simple

# 应用配置
APP_ENV=development
DEBUG=True
SECRET_KEY=your-secret-key-here-change-in-production

# 数据库
DATABASE_URL=sqlite+aiosqlite:///./app.db

# LLM配置
LLM_PROVIDER=openai
OPENAI_API_KEY=your-openai-api-key-here
LLM_MODEL=gpt-4

# ASR配置（可选）
ASR_PROVIDER=openai
OPENAI_WHISPER_API_KEY=your-openai-api-key-here

# TTS配置（可选）
TTS_PROVIDER=openai
OPENAI_TTS_API_KEY=your-openai-api-key-here

# 语音功能
AUDIO_MODE=False

# 引导策略
GUIDE_IDLE_TIMEOUT=600
GUIDE_QUIET_TIMEOUT=900
GUIDE_SHORT_ANSWER_THRESHOLD=20
```

### 方法3: 最小配置（仅测试用）

如果只是测试，可以只设置：

```env
SECRET_KEY=test-secret-key-12345
```

## 🔧 步骤4: 编辑 .env 文件

使用文本编辑器打开 `.env` 文件，至少修改：

1. **SECRET_KEY**: 改为一个随机字符串（用于JWT加密）
2. **OPENAI_API_KEY**: 如果需要测试LLM功能，填入您的OpenAI API密钥

## ✅ 验证安装

### 验证 Python 依赖

```bash
# 激活虚拟环境后
cd src/backend
python -c "import fastapi; print('FastAPI installed')"
python -c "import langgraph; print('LangGraph installed')"
```

### 验证 Node.js 依赖

```bash
cd src/frontend
npm list react
npm list vite
```

### 运行测试

```bash
# 从项目根目录
# Windows PowerShell
$env:PYTHONPATH="src/backend"
pytest test/backend/test_config.py -v

# Linux/Mac
export PYTHONPATH="src/backend"
pytest test/backend/test_config.py -v
```

## 🚀 启动服务

### 启动后端

```bash
# 激活虚拟环境后
cd src/backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 启动前端

```bash
# 新开一个终端
cd src/frontend
npm run dev
```

## 📝 完整命令清单（复制粘贴）

### Windows PowerShell（项目根目录）

```powershell
# 1. 配置后端
cd src/backend
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt

# 2. 配置前端（新终端）
cd src/frontend
npm install

# 3. 创建 .env 文件（项目根目录）
cd ..\..
Copy-Item .env.example .env
# 然后编辑 .env 文件

# 4. 测试
$env:PYTHONPATH="src/backend"
pytest test/backend/test_config.py -v
```

### Linux/Mac（项目根目录）

```bash
# 1. 配置后端
cd src/backend
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

# 2. 配置前端（新终端）
cd src/frontend
npm install

# 3. 创建 .env 文件（项目根目录）
cd ../..
cp .env.example .env
# 然后编辑 .env 文件

# 4. 测试
export PYTHONPATH="src/backend"
pytest test/backend/test_config.py -v
```

## ❓ 常见问题

### Q1: 虚拟环境激活失败（PowerShell）

**错误**: `无法加载文件，因为在此系统上禁止运行脚本`

**解决**:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
```

### Q2: pip 安装慢

**解决**: 使用国内镜像
```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### Q3: npm 安装慢

**解决**: 使用国内镜像
```bash
npm config set registry https://registry.npmmirror.com
npm install
```

### Q4: 找不到 .env.example

**解决**: 手动创建 `.env` 文件，内容参考上面的模板

## 📌 下一步

环境配置完成后：
1. ✅ 运行测试验证环境
2. ✅ 继续开发 Phase 0.2: 数据库设计与初始化
3. ✅ 开始 Phase 1: 核心AI服务开发
