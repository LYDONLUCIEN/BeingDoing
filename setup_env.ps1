# 环境配置脚本 (PowerShell)
# 使用方法: .\setup_env.ps1

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "环境配置脚本" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 检查Python
Write-Host ""
Write-Host "检查Python环境..." -ForegroundColor Yellow
$pythonVersion = python --version 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "Python已安装: $pythonVersion" -ForegroundColor Green
} else {
    Write-Host "Python未安装，请先安装Python 3.10+" -ForegroundColor Red
    exit 1
}

# 检查Node.js
Write-Host ""
Write-Host "检查Node.js环境..." -ForegroundColor Yellow
$nodeVersion = node --version 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "Node.js已安装: $nodeVersion" -ForegroundColor Green
} else {
    Write-Host "Node.js未安装，请先安装Node.js 18+" -ForegroundColor Red
    exit 1
}

# 配置Python环境
Write-Host ""
Write-Host "配置Python环境..." -ForegroundColor Yellow
Set-Location src\backend

if (-not (Test-Path "venv")) {
    Write-Host "创建Python虚拟环境..." -ForegroundColor Cyan
    python -m venv venv
}

Write-Host "激活虚拟环境..." -ForegroundColor Cyan
& .\venv\Scripts\Activate.ps1

Write-Host "升级pip..." -ForegroundColor Cyan
python -m pip install --upgrade pip

Write-Host "安装Python依赖..." -ForegroundColor Cyan
pip install -r requirements.txt

if ($LASTEXITCODE -eq 0) {
    Write-Host "Python依赖安装完成" -ForegroundColor Green
} else {
    Write-Host "Python依赖安装失败" -ForegroundColor Red
    exit 1
}

# 配置Node.js环境
Write-Host ""
Write-Host "配置Node.js环境..." -ForegroundColor Yellow
Set-Location ..\frontend

Write-Host "安装Node.js依赖..." -ForegroundColor Cyan
npm install

if ($LASTEXITCODE -eq 0) {
    Write-Host "Node.js依赖安装完成" -ForegroundColor Green
} else {
    Write-Host "Node.js依赖安装失败" -ForegroundColor Red
    exit 1
}

# 配置环境变量
Write-Host ""
Write-Host "配置环境变量..." -ForegroundColor Yellow
Set-Location ..\..\..
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item .env.example .env
        Write-Host "已创建.env文件，请编辑填入必要的配置" -ForegroundColor Green
        Write-Host "至少需要设置: SECRET_KEY 和 OPENAI_API_KEY" -ForegroundColor Yellow
    } else {
        Write-Host ".env.example文件不存在，正在创建基本.env文件..." -ForegroundColor Yellow
        $envContent = @"
SECRET_KEY=your-secret-key-here-change-in-production
OPENAI_API_KEY=your-openai-api-key-here
ARCHITECTURE_MODE=simple
AUDIO_MODE=False
DATABASE_URL=sqlite+aiosqlite:///./app.db
"@
        $envContent | Out-File -FilePath ".env" -Encoding utf8
        Write-Host "已创建.env文件，请编辑填入必要的配置" -ForegroundColor Green
    }
} else {
    Write-Host ".env文件已存在" -ForegroundColor Green
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "环境配置完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "下一步：" -ForegroundColor Yellow
Write-Host "1. 编辑 .env 文件，填入必要的配置（如OPENAI_API_KEY）" -ForegroundColor White
Write-Host "2. 运行测试: pytest test/backend/test_config.py -v" -ForegroundColor White
Write-Host "3. 启动后端: cd src/backend; uvicorn app.main:app --reload" -ForegroundColor White
Write-Host "4. 启动前端: cd src/frontend; npm run dev" -ForegroundColor White
