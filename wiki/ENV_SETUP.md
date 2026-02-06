# 环境与依赖配置（ENV_SETUP）

本页是 **唯一权威** 的环境安装与配置文档，用来满足 `wiki/CURSOR.md` 里对 `ENV_SETUP.md` 的要求：
- 汇总系统要求、依赖、自动脚本、手动安装步骤
- 统一说明 `.env` 配置和基础测试
- 其他 wiki 文档（如 `DEPENDENCIES.md`、`QUICK_SETUP.md`、`MANUAL_SETUP.md`）只做补充或重定向，避免重复内容

---

## 一、系统要求（必读）

- **Python**: 3.10 及以上（推荐 3.11+）
- **Node.js**: 18 及以上（推荐 20 LTS）
- **包管理器**: `pip` + `npm`（或 `yarn`）
- **操作系统**: Windows / macOS / Linux 均可

> 详细依赖包清单请看：`wiki/DEPENDENCIES.md`（这里只讲“怎么装”，那边专门列“装什么”）。

---

## 二、推荐方式：一键脚本配置环境

### 1. Linux / macOS

```bash
chmod +x setup_env.sh
./setup_env.sh
```

脚本会自动完成：
- 检查 Python / Node.js 版本
- 在 `src/backend` 下创建并激活 `venv`
- 安装后端 `requirements.txt`
- 在 `src/frontend` 下安装前端依赖
- 在项目根目录创建 `.env`（如果不存在）

### 2. Windows（PowerShell）

```powershell
.\setup_env.ps1
```

首次如果遇到执行策略限制，可以临时放开当前会话：

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
.\setup_env.ps1
```

> 说明：`setup_env.sh` / `setup_env.ps1` 的详细逻辑见项目根目录同名脚本，本页只给使用方式。

---

## 三、手动配置环境（脚本失败时使用）

### 1. Python 后端环境

#### Windows PowerShell

```powershell
cd src/backend

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
.\venv\Scripts\Activate.ps1

# 升级 pip 并安装依赖
python -m pip install --upgrade pip
pip install -r requirements.txt
```

如遇“禁止运行脚本”报错，可先执行：

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
```

#### Linux / macOS

```bash
cd src/backend

# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 升级 pip 并安装依赖
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

### 2. Node.js 前端环境

```bash
cd src/frontend
npm install
```

如果安装缓慢，可使用国内镜像：

```bash
npm config set registry https://registry.npmmirror.com
npm install
```

---

## 四、环境变量与 `.env` 配置

### 1. `.env.example` 模板

- 位置：项目根目录
- 作用：列出所有支持的环境变量及示例值

#### 复制模板

**Windows PowerShell**：

```powershell
Copy-Item .env.example .env
```

**Linux / macOS**：

```bash
cp .env.example .env
```

如果没有 `.env.example`，可以参考下方“最小配置示例”手动创建 `.env`。

---

### 2. `.env` 文件说明

- **位置**：项目根目录（与 `.env.example` 同级）
- **作用**：存储实际的环境变量值（例如 `SECRET_KEY`、`OPENAI_API_KEY`）
- **安全**：已在 `.gitignore` 中忽略，不会提交到仓库

#### 最小配置（仅跑基础功能 / 测试）

```env
SECRET_KEY=test-secret-key-12345
```

#### 推荐开发配置（启用 LLM 功能）

```env
SECRET_KEY=your-secret-key-here-change-in-production
OPENAI_API_KEY=sk-your-actual-api-key-here

# 架构模式：simple = 简化架构（默认） | full = 预留完整架构
ARCHITECTURE_MODE=simple

# 语音功能开关
AUDIO_MODE=False

# 默认 SQLite 数据库（开发环境）
DATABASE_URL=sqlite+aiosqlite:///./app.db
```

> 说明：更完整的配置示例（包括 ASR/TTS、引导策略等）可以参考原来的 `MANUAL_SETUP.md` 内容，后续如有需要可迁移到本页的“高级配置”小节。

---

### 3. 关键环境变量一览

| 变量名 | 说明 | 是否必需 | 默认值 |
|--------|------|---------|--------|
| `SECRET_KEY` | 应用密钥，用于 JWT 等 | ✅ 必需 | - |
| `OPENAI_API_KEY` | OpenAI API 密钥（启用 LLM 功能） | ⚠️ LLM 功能需要 | - |
| `ARCHITECTURE_MODE` | 架构模式：`simple` / `full` | ❌ 可选 | `simple` |
| `AUDIO_MODE` | 是否启用语音（ASR/TTS） | ❌ 可选 | `False` |
| `DATABASE_URL` | 数据库连接 URL | ❌ 可选 | SQLite 默认 |

---

## 五、验证环境是否安装成功

### 1. 验证 Python 依赖

```bash
cd src/backend
source venv/bin/activate  # Windows 对应激活命令见上文

python -c "import fastapi; print('FastAPI installed')"
python -c "import langgraph; print('LangGraph installed')"
```

### 2. 验证 Node.js 依赖

```bash
cd src/frontend
npm list react
npm list vite
```

### 3. 运行最小测试用例

从项目根目录执行：

```bash
# Windows PowerShell
$env:PYTHONPATH="src/backend"
pytest test/backend/test_config.py -v

# Linux / macOS
export PYTHONPATH="src/backend"
pytest test/backend/test_config.py -v
```

如需使用封装好的脚本，也可以直接在根目录运行：

```powershell
.\run_tests.ps1    # Windows
```

```bash
chmod +x run_tests.sh
./run_tests.sh     # Linux / macOS
```

---

## 六、启动开发环境

> 更完整的开发流程和代码规范，请参考 `wiki/DEVELOPMENT.md`；这里只给“能跑起来”的最小命令。

### 1. 启动后端（FastAPI）

```bash
cd src/backend
source venv/bin/activate  # Windows 使用 venv\Scripts\activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. 启动前端（Next.js）

```bash
cd src/frontend
npm run dev
```

前端默认端口：`http://localhost:3000`  
后端默认端口：`http://localhost:8000`

---

## 七、常见问题（FAQ 精简版）

- **找不到 `.env.example`？**  
  直接在根目录创建 `.env`，参考上面的“最小配置示例”或“推荐开发配置”即可。

- **PowerShell 无法运行 `.ps1`？**  
  在当前会话执行：  
  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
  ```

- **pip / npm 很慢？**  
  - pip: 使用清华镜像：  
    ```bash
    pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    ```  
  - npm: 使用 npmmirror：  
    ```bash
    npm config set registry https://registry.npmmirror.com
    npm install
    ```

- **更细的依赖与问题排查？**  
  - 依赖列表：`wiki/DEPENDENCIES.md`  
  - 常见问题：`docs/FAQ.md`

---

## 八、下一步推荐阅读

- **想快速跑通项目**：请看 `wiki/START.md`
- **想了解项目结构和组件**：请看 `wiki/PROJECT.md`
- **想深入依赖细节与版本**：请看 `wiki/DEPENDENCIES.md`

