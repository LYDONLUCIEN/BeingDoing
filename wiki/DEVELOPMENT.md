# 开发指南

## 环境设置

### 后端环境

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
cd src/backend
pip install -r requirements.txt

# 设置环境变量
cp ../../../.env.example ../../../.env
# 编辑 .env 文件，填入必要的配置（如OpenAI API Key）

# 运行开发服务器
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 前端环境

```bash
# 安装依赖
cd src/frontend
npm install

# 运行开发服务器
npm run dev
```

## 运行测试

### 后端测试

```bash
# 从项目根目录运行
cd src/backend
pytest ../../test/backend -v

# 或从项目根目录
pytest test/backend -v
```

### 前端测试

```bash
cd src/frontend
npm test
```

## 代码规范

### Python

```bash
# 格式化代码
black src/backend

# 检查代码风格
flake8 src/backend

# 类型检查
mypy src/backend
```

### TypeScript

```bash
cd src/frontend

# 格式化代码
npm run format

# 检查代码风格
npm run lint
```

## 项目结构

```
.
├── src/
│   ├── backend/          # 后端代码
│   │   ├── app/          # 应用主目录
│   │   │   ├── api/      # API路由
│   │   │   ├── core/     # 核心功能
│   │   │   ├── models/   # 数据模型
│   │   │   ├── services/ # 业务逻辑
│   │   │   └── config/   # 配置
│   │   └── requirements.txt
│   └── frontend/         # 前端代码
├── test/                 # 测试代码
├── data/                 # 数据文件
└── planning/             # 设计文档
```

## 开发流程

1. 从 `planning/todolist.md` 中选择任务
2. 创建功能分支
3. 实现功能
4. 编写测试
5. 运行测试确保通过
6. 提交代码

## 注意事项

- 所有可测试的模块都要有测试用例
- 保持代码风格一致
- 及时更新文档
- 遵循设计文档中的架构设计
