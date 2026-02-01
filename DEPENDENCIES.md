# 依赖清单与环境配置

## 📦 系统要求

### Python环境
- **Python版本**: 3.10 或更高版本
- **推荐**: Python 3.11+

### Node.js环境
- **Node.js版本**: 18.0 或更高版本
- **推荐**: Node.js 20.x LTS
- **包管理器**: npm 或 yarn

## 🔧 Python依赖

### 后端核心依赖

#### Web框架
```
fastapi>=0.104.0          # FastAPI Web框架
uvicorn[standard]>=0.24.0 # ASGI服务器
python-multipart>=0.0.6   # 文件上传支持
```

#### 数据库
```
sqlalchemy>=2.0.0         # ORM框架
aiosqlite>=0.19.0         # SQLite异步驱动
```

#### 数据验证
```
pydantic>=2.0.0           # 数据验证
pydantic-settings>=2.0.0  # 配置管理
```

#### 认证与安全
```
python-jose[cryptography]>=3.3.0  # JWT Token
passlib[bcrypt]>=1.7.4            # 密码加密
```

#### 环境变量
```
python-dotenv>=1.0.0      # .env文件支持
```

### AI/智能体依赖

#### 智能体框架
```
langgraph>=0.0.20         # LangGraph智能体框架
langchain>=0.1.0          # LangChain基础
langchain-openai>=0.0.5   # OpenAI集成
```

#### LLM
```
openai>=1.0.0             # OpenAI API客户端
```

#### ASR/TTS（可选，AUDIO_MODE控制）
```
openai-whisper>=20231117  # 本地Whisper模型
pyttsx3>=2.90             # 本地TTS（离线）
gtts>=2.5.0               # Google TTS（在线）
```

### 开发依赖

#### 测试框架
```
pytest>=7.4.0             # 测试框架
pytest-asyncio>=0.21.0    # 异步测试支持
pytest-cov>=4.1.0         # 测试覆盖率
httpx>=0.25.0             # HTTP测试客户端
```

#### 代码质量
```
black>=23.0.0             # 代码格式化（可选）
flake8>=6.0.0             # 代码检查（可选）
mypy>=1.0.0               # 类型检查（可选）
```

## 📦 Node.js依赖

### 前端核心依赖

#### 框架与库
```json
{
  "react": "^18.2.0",
  "react-dom": "^18.2.0",
  "react-router-dom": "^6.20.0",
  "antd": "^5.11.0",
  "zustand": "^4.4.7",
  "axios": "^1.6.2"
}
```

### 开发依赖

#### 构建工具
```json
{
  "@vitejs/plugin-react": "^4.2.1",
  "vite": "^5.0.8",
  "typescript": "^5.2.2"
}
```

#### 代码质量
```json
{
  "@typescript-eslint/eslint-plugin": "^6.14.0",
  "@typescript-eslint/parser": "^6.14.0",
  "eslint": "^8.55.0",
  "eslint-plugin-react-hooks": "^4.6.0",
  "eslint-plugin-react-refresh": "^0.4.5",
  "prettier": "^3.1.1"
}
```

#### 类型定义
```json
{
  "@types/react": "^18.2.43",
  "@types/react-dom": "^18.2.17"
}
```

## 🚀 环境配置步骤

### 1. Python环境配置

#### Windows
```powershell
# 检查Python版本
python --version  # 应该 >= 3.10

# 创建虚拟环境
cd src/backend
python -m venv venv

# 激活虚拟环境
venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

#### Linux/Mac
```bash
# 检查Python版本
python3 --version  # 应该 >= 3.10

# 创建虚拟环境
cd src/backend
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 2. Node.js环境配置

```bash
# 检查Node.js版本
node --version  # 应该 >= 18.0
npm --version

# 进入前端目录
cd src/frontend

# 安装依赖
npm install
```

### 3. 环境变量配置

```bash
# 从项目根目录复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，至少设置以下内容：
# SECRET_KEY=your-secret-key-here
# OPENAI_API_KEY=your-openai-api-key (如果需要测试LLM功能)
```

### 4. 验证安装

#### 验证Python依赖
```bash
cd src/backend
python -c "import fastapi; print('FastAPI installed')"
python -c "import langgraph; print('LangGraph installed')"
```

#### 验证Node.js依赖
```bash
cd src/frontend
npm list react
npm list vite
```

## 📋 完整依赖安装命令

### Python后端
```bash
cd src/backend
pip install -r requirements.txt
```

### Node.js前端
```bash
cd src/frontend
npm install
```

## ⚠️ 注意事项

### 可选依赖说明

1. **ASR/TTS依赖** (`openai-whisper`, `pyttsx3`, `gtts`)
   - 仅在 `AUDIO_MODE=True` 时需要
   - 如果不需要语音功能，可以跳过安装
   - 安装 `openai-whisper` 需要较大磁盘空间（~3GB）

2. **代码质量工具** (`black`, `flake8`, `mypy`)
   - 开发时可选，但推荐安装
   - 用于代码格式化和检查

3. **测试覆盖率** (`pytest-cov`)
   - 用于生成测试覆盖率报告
   - 开发时推荐安装

### 依赖安装问题

#### 问题1: openai-whisper安装失败
**解决方案**：
```bash
# 如果不需要本地Whisper，可以从requirements.txt中移除
# 或使用conda安装
conda install -c conda-forge openai-whisper
```

#### 问题2: 某些包版本冲突
**解决方案**：
```bash
# 使用pip升级
pip install --upgrade pip
pip install -r requirements.txt --upgrade
```

#### 问题3: Node.js依赖安装慢
**解决方案**：
```bash
# 使用国内镜像
npm config set registry https://registry.npmmirror.com
npm install
```

## 🔍 依赖检查清单

安装完成后，检查以下内容：

- [ ] Python 3.10+ 已安装
- [ ] Node.js 18+ 已安装
- [ ] 虚拟环境已创建并激活
- [ ] 所有Python依赖已安装
- [ ] 所有Node.js依赖已安装
- [ ] .env文件已配置
- [ ] 可以运行 `pytest test/backend/test_config.py -v`
- [ ] 可以运行 `npm run dev` (前端)

## 📝 下一步

环境配置完成后，可以：
1. 运行第一阶段测试验证环境
2. 继续开发 Phase 0.2: 数据库设计与初始化
3. 开始 Phase 1: 核心AI服务开发
