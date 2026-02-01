#!/bin/bash
# 环境配置脚本 (Bash)
# 使用方法: ./setup_env.sh

echo "========================================"
echo "环境配置脚本"
echo "========================================"

# 检查Python
echo ""
echo "检查Python环境..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    echo "✓ Python已安装: $PYTHON_VERSION"
else
    echo "✗ Python未安装，请先安装Python 3.10+"
    exit 1
fi

# 检查Node.js
echo ""
echo "检查Node.js环境..."
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    echo "✓ Node.js已安装: $NODE_VERSION"
else
    echo "✗ Node.js未安装，请先安装Node.js 18+"
    exit 1
fi

# 配置Python环境
echo ""
echo "配置Python环境..."
cd src/backend

if [ ! -d "venv" ]; then
    echo "创建Python虚拟环境..."
    python3 -m venv venv
fi

echo "激活虚拟环境..."
source venv/bin/activate

echo "升级pip..."
python -m pip install --upgrade pip

echo "安装Python依赖..."
pip install -r requirements.txt

if [ $? -eq 0 ]; then
    echo "✓ Python依赖安装完成"
else
    echo "✗ Python依赖安装失败"
    exit 1
fi

# 配置Node.js环境
echo ""
echo "配置Node.js环境..."
cd ../frontend

echo "安装Node.js依赖..."
npm install

if [ $? -eq 0 ]; then
    echo "✓ Node.js依赖安装完成"
else
    echo "✗ Node.js依赖安装失败"
    exit 1
fi

# 配置环境变量
echo ""
echo "配置环境变量..."
cd ../..
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "✓ 已创建.env文件，请编辑填入必要的配置"
        echo "  至少需要设置: SECRET_KEY 和 OPENAI_API_KEY"
    else
        echo "⚠ .env.example文件不存在，正在创建..."
        # 创建基本的.env文件
        cat > .env << 'EOF'
SECRET_KEY=your-secret-key-here-change-in-production
OPENAI_API_KEY=your-openai-api-key-here
ARCHITECTURE_MODE=simple
AUDIO_MODE=False
DATABASE_URL=sqlite+aiosqlite:///./app.db
EOF
        echo "✓ 已创建.env文件，请编辑填入必要的配置"
    fi
else
    echo "✓ .env文件已存在"
fi

echo ""
echo "========================================"
echo "环境配置完成！"
echo "========================================"
echo ""
echo "下一步："
echo "1. 编辑 .env 文件，填入必要的配置（如OPENAI_API_KEY）"
echo "2. 运行测试: pytest test/backend/test_config.py -v"
echo "3. 启动后端: cd src/backend; source venv/bin/activate; uvicorn app.main:app --reload"
echo "4. 启动前端: cd src/frontend; npm run dev"
