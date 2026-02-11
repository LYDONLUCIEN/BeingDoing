# 本地完整跑起来指南

按下面步骤可在本机完整跑通「找到想做的事」前后端，并体验智能引导与对话。

---

## 一、环境要求

- **Python 3.10+**
- **Node.js 18+**
- 已安装 **pip**、**npm**

---

## 二、一键配置环境（推荐）

在**项目根目录**（`BeingDoing/`）执行：

```bash
chmod +x setup_env.sh
./setup_env.sh
```

脚本会：

- 检查 Python / Node.js
- 在 `src/backend` 下创建并激活虚拟环境、安装 Python 依赖
- 在 `src/frontend` 下执行 `npm install`
- 若没有 `.env`，会从模板创建；若没有 `.env.example`，会生成一份基础 `.env`

**注意**：脚本执行完后，当前 shell 的虚拟环境会随终端关闭而失效；后面「启动后端」时需要在对应终端里再次激活 venv。

---

## 三、配置 .env（必做）

1. 在**项目根目录**确认有 `.env` 文件（没有则复制 `.env.example` 或由 `setup_env.sh` 生成）。
2. 用编辑器打开 `.env`，至少配置：

**方式 A：使用 OpenAI**

```env
OPENAI_API_KEY=sk-你的OpenAI密钥
SECRET_KEY=随便写一串随机字符串（生产环境务必换掉）
```

**方式 B：使用 DeepSeek（兼容 OpenAI 接口）**

```env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-你的DeepSeek密钥
LLM_MODEL=deepseek-chat
SECRET_KEY=随便写一串随机字符串
```

其他项可先保持默认，例如：

- `DATABASE_URL=sqlite+aiosqlite:///./app.db`（SQLite，库文件会生成在 `src/backend/` 下）
- `ARCHITECTURE_MODE=simple`
- `AUDIO_MODE=False`

3. 保存 `.env`。  
   **说明**：后端会从**项目根目录**的 `.env` 读配置（由 `app/config/settings.py` 的 `base_dir` 决定），与你在哪个目录执行命令无关。

---

## 四、初始化数据库

在**项目根目录**执行：

```bash
cd src/backend
source venv/bin/activate   # Windows: venv\Scripts\activate
python scripts/init_db.py
```

看到「数据库表结构创建完成」即表示 SQLite 库和表已就绪（库文件为 `src/backend/app.db`）。

---

## 五、启动后端

保持当前在 `src/backend` 且虚拟环境已激活：

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- 后端地址：**http://localhost:8000**
- 健康检查：浏览器打开 http://localhost:8000/health 应返回 `{"status":"healthy"}`
- API 文档：http://localhost:8000/docs

**不要关闭此终端**，后端需常驻。

---

## 六、启动前端

**新开一个终端**，在**项目根目录**执行：

```bash
cd src/frontend
npm install   # 若已跑过 setup_env.sh 可省略
npm run dev
```

- 前端地址：**http://localhost:3000**
- 默认会请求后端：`http://localhost:8000`（见 `next.config.js` / `lib/api/client.ts`）

浏览器访问 **http://localhost:3000** 即可使用应用。

---

## 七、体验流程建议

1. **注册 / 登录**  
   使用前端「注册」或「登录」，完成认证。

2. **完善资料（可选）**  
   在「个人资料」里填基本信息、工作履历等，便于后续引导更贴合。

3. **探索流程**  
   - 进入「探索」或对应引导页，按步骤选择当前阶段（如价值观 / 才能 / 兴趣）。
   - 在对话里输入问题，例如：
     - 「有哪些价值观？」（会触发知识库预填 + 检索）
     - 「我不太确定自己适合什么」（由 Agent 自判是否查知识并引导）
   - 后端会按 domain 的步骤与知识规则做推理、检索（search_tool / 预填 knowledge_snippets）并回复。

4. **查看对话与进度**  
   前端会展示当前步骤、对话历史和进度；后端会写 SQLite 与对话记录（若已接好）。

---

## 八、知识库文件位置（可选）

以下 CSV 放在**项目根目录**时，会被默认加载（参见 `app/domain/knowledge_config.py` 与 `app/core/knowledge/loader.py`）：

- `重要的事_价值观.csv`
- `喜欢的事_热情.csv`
- `擅长的事_才能.csv`
- `question.md`（若存在）

若缺文件，仅对应知识检索无数据，不影响后端与对话整体运行；列名需与 `app/domain/knowledge_config.py` 中的 `COLUMNS_*` 一致。

---

## 九、常见问题

| 现象 | 处理 |
|------|------|
| 后端启动报错 `ModuleNotFoundError: app` | 必须在 `src/backend` 下执行 `uvicorn`，且先 `source venv/bin/activate`。 |
| 后端读不到 `.env` / LLM 未配置 | 确认 `.env` 在**项目根目录**（与 `src/` 同级），且 `OPENAI_API_KEY` 或 `DEEPSEEK_API_KEY` 已填。 |
| 前端请求 404 或跨域 | 确认后端已启动在 8000 端口，且前端 `NEXT_PUBLIC_API_URL` 为 `http://localhost:8000`（或未设置用默认）。 |
| 对话无回复或报 500 | 查看后端终端日志；多为 LLM 密钥错误或网络问题。 |
| 数据库/表不存在 | 在 `src/backend` 下执行 `python scripts/init_db.py`。 |

---

## 十、命令速查（项目根目录为 `BeingDoing/`）

```bash
# 1. 配置环境（首次）
./setup_env.sh

# 2. 编辑 .env，填 OPENAI_API_KEY 或 DEEPSEEK_API_KEY 和 SECRET_KEY

# 3. 初始化数据库
cd src/backend && source venv/bin/activate && python scripts/init_db.py

# 4. 启动后端（终端 1）
cd src/backend && source venv/bin/activate && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 5. 启动前端（终端 2）
cd src/frontend && npm run dev

# 6. 浏览器打开
#    http://localhost:3000
```

按上述顺序执行即可在本地完整跑起来并体验整个项目。
