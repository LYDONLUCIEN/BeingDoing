# START：如何开始使用这个项目

本页是 wiki 的统一「起步指南」，用于满足 `wiki/CURSOR.md` 中对 `START.md` 的要求：
- 面向**新用户 / 体验者**：怎样最快跑起来体验功能
- 面向**开发者**：怎样搭建开发环境、跑测试、启动前后端
- 所有环境安装细节统一收敛到：`wiki/ENV_SETUP.md`

---

## 一、面向“只想先用用”的用户

### 1. 前置条件

- 已安装 Python 3.10+、Node.js 18+
- 能在终端里使用 `git`、`python` / `python3`、`node`、`npm`

### 2. 一键配置环境（推荐）

在项目根目录执行：

```bash
# Linux / macOS
chmod +x setup_env.sh
./setup_env.sh
```

```powershell
# Windows PowerShell
.\setup_env.ps1
```

> 说明：脚本会自动安装后端/前端依赖并创建 `.env`，如失败再参考 `wiki/ENV_SETUP.md` 里的「手动配置」章节。

### 3. 启动后端与前端

后端（FastAPI）：

```bash
cd src/backend
source venv/bin/activate      # Windows 使用 venv\Scripts\activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

前端（Next.js）：

```bash
cd src/frontend
npm run dev
```

打开浏览器访问：
- 前端：`http://localhost:3000`
- 后端 API 文档：`http://localhost:8000/docs`

---

## 二、面向开发者：完整快速上手流程

### 步骤 0：克隆仓库

```bash
git clone <repository-url>
cd BeingDoing
```

### 步骤 1：配置环境

优先使用一键脚本（见上一节）。如果脚本无法使用，请参考：
- 环境与依赖安装：`wiki/ENV_SETUP.md`

确保已完成：
- Python 虚拟环境创建并激活
- `src/backend/requirements.txt` 安装完成
- `src/frontend` 依赖安装完成
- 根目录存在 `.env` 文件并配置了至少 `SECRET_KEY`（以及需要时的 `OPENAI_API_KEY`）

### 步骤 2：运行基础测试（验证环境）

从项目根目录：

```bash
# Windows PowerShell
$env:PYTHONPATH="src/backend"
pytest test/backend/test_config.py -v

# Linux / macOS
export PYTHONPATH="src/backend"
pytest test/backend/test_config.py -v
```

或使用脚本：

```powershell
.\run_tests.ps1    # Windows
```

```bash
chmod +x run_tests.sh
./run_tests.sh     # Linux / macOS
```

预期看到 4 个配置相关测试全部通过。

> 更完整的测试说明（覆盖率、全部用例等）请参考：`docs/TESTING.md`。

### 步骤 3：进入开发模式

后端开发：

```bash
cd src/backend
source venv/bin/activate      # Windows 使用 venv\Scripts\activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

前端开发：

```bash
cd src/frontend
npm run dev
```

开发规范、目录说明和推荐流程请参见：`wiki/DEVELOPMENT.md`。

---

## 三、不同角色的“最少必读”建议

- **只想体验功能的用户**  
  1）阅读本页到「一、面向‘只想先用用’的用户」；  
  2）如果环境不工作，再补看 `wiki/ENV_SETUP.md`。

- **日常开发者**  
  1）完整阅读本页；  
  2）补充阅读：`wiki/ENV_SETUP.md`、`wiki/DEVELOPMENT.md`；  
  3）想了解当前进度/缺陷时看：`wiki/PROJECT_STATUS.md`。

- **需要部署到服务器的同学**  
  1）先按本页完成本地启动；  
  2）再阅读：`wiki/DEPLOYMENT.md`（包含 Docker / 阿里云 等）。

---

## 四、和其他 wiki 文档的关系

- `ENV_SETUP.md`：**唯一** 的环境安装与依赖配置说明，本页只给“步骤串联”和“起步路径”。
- `PROJECT.md`：描述项目目录结构、后端/前端模块、数据与知识库等关系。
- `DEPENDENCIES.md`：依赖列表的**参考手册**，不再重复任何安装步骤。

