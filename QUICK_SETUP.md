# 快速手动配置指南

如果自动脚本无法运行，按照以下步骤手动配置（5分钟完成）。

## ⚡ 快速步骤

### 1. Python 后端（2分钟）

```powershell
# Windows PowerShell
cd src/backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

```bash
# Linux/Mac
cd src/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Node.js 前端（1分钟）

```bash
cd src/frontend
npm install
```

### 3. 创建 .env 文件（1分钟）

在项目根目录创建 `.env` 文件：

```env
SECRET_KEY=test-secret-key-12345
OPENAI_API_KEY=your-key-here
ARCHITECTURE_MODE=simple
AUDIO_MODE=False
DATABASE_URL=sqlite+aiosqlite:///./app.db
```

### 4. 测试（1分钟）

```powershell
# Windows
$env:PYTHONPATH="src/backend"
pytest test/backend/test_config.py -v
```

```bash
# Linux/Mac
export PYTHONPATH="src/backend"
pytest test/backend/test_config.py -v
```

## ✅ 完成！

如果测试通过，环境配置成功！

详细说明请参考：`MANUAL_SETUP.md`
