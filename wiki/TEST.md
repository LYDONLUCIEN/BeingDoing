# TEST：测试脚本与用例说明

本页用于满足 `wiki/CURSOR.md` 中对 `TEST.md` 的要求，统一说明：

- 测试怎么跑（pytest 命令、脚本入口）
- 重点模块有哪些测试（尤其是智能体框架 / LangGraph）
- 常见问题排查入口

---

## 一、基础测试入口（全局）

### 1. 只跑配置相关的最小测试

用于验证环境是否正确：

```bash
# 从项目根目录
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

> 这些内容在 `wiki/START.md` / `docs/TESTING.md` 中也有更详细说明，这里只做统一索引。

### 2. 运行全部后端测试

```bash
pytest test/backend -v
```

查看覆盖率（参考 `docs/TESTING.md`）：

```bash
pytest test/backend --cov=src/backend/app --cov-report=html
```

---

## 二、智能体框架（LangGraph / Agent）测试

> 当前仓库里还 **没有专门的 `test_backend/core/agent` 测试文件**，  
> 但已经有完整的智能体实现入口，可以从下面几个方向开始测试：

### 1. 智能体代码入口位置

- 核心类型 & 入口：
  - `app/core/agent/state.py`：`AgentState`（LangGraph 状态数据结构）
  - `app/core/agent/graph.py`：
    - `create_agent_graph()`：构建 LangGraph 状态图（reasoning → action → observation → 循环 / 结束）
    - `create_initial_state(...)`：为一次对话创建初始 `AgentState`
  - `app/core/agent/__init__.py`：导出 `AgentState` 和 `create_agent_graph`
- 关键节点与上下文：
  - `app/core/agent/nodes/reasoning.py`：`reasoning_node`（用 LLM 决定下一步动作）
  - `app/core/agent/nodes/guide.py`：`guide_node`（给用户引导性回复）
  - `app/core/agent/context.py`：`ContextManager`（从 DB + 文件中拼接上下文和 LLM 消息）

> 简单理解：测试智能体框架，就是围绕 `create_agent_graph` + `create_initial_state` + 各个节点函数（reasoning/guide 等）写用例。

### 2. 建议新增的 pytest 用例位置

按现有测试结构，推荐创建：

```text
test/backend/core/agent/test_graph.py        # 测 graph + AgentState 流转
test/backend/core/agent/test_nodes.py        # 测 reasoning_node / guide_node 等单点行为
```

（目前 `test/backend/core/` 下已有 `knowledge`、`llmapi`、`tts`、`asr` 等子模块的测试，可以参考它们的组织方式。）

### 3. 示例：如何在测试里构建并运行智能体图

伪代码示例（建议写到 `test/backend/core/agent/test_graph.py`）：

```python
import pytest
from app.core.agent import create_agent_graph
from app.core.agent.graph import create_initial_state

@pytest.mark.asyncio
async def test_agent_graph_basic_flow(monkeypatch):
    # 1. 构建智能体图
    graph_app = create_agent_graph()

    # 2. 构建初始状态
    state = create_initial_state(user_input="我想探索自己的价值观", current_step="values_exploration")

    # 3. 这里可以 monkeypatch 掉真正的 LLM 调用，避免依赖外部 API
    #    例如：替换 get_default_llm_provider().chat 为一个假的实现
    #    以保证测试可重复、离线运行

    # 4. 运行一次或若干步图
    result = await graph_app.ainvoke(state)

    # 5. 断言：状态里至少有一条 assistant 消息 / 没有 error / should_continue 为 False 等
    assert result.get("error") is None
    assert len(result.get("messages", [])) > 0
```

> 重点：  
> - 用 `monkeypatch` 或自定义 Provider mock 掉真正的 OpenAI 调用；  
> - 只验证「状态流转和节点调用是否按预期工作」，不要求真实 LLM 的输出内容。

### 4. 单独测试节点（reasoning / guide）

可以对 `reasoning_node` / `guide_node` 分别写更细的用例，例如：

- 当 `user_input` 为空时，节点能否优雅地返回错误并停止循环；
- 当 LLM 返回非法 JSON 时，`reasoning_node` 是否会走到 `except` 分支里设置 `"action": "respond"`；  
- `guide_node` 在正常返回时，是否正确设置了 `final_response`、`messages`、`should_continue=False`。

这些用例同样需要 mock LLM，以保证运行稳定。

### 5. 运行智能体相关测试的命令

假设你按上面的建议新建了 `test/backend/core/agent/test_*.py` 文件：

```bash
# 仅运行智能体相关测试
pytest test/backend/core/agent -v

# 或者运行所有 core 层测试（包含 knowledge / llmapi / tts / asr / agent）
pytest test/backend/core -v
```

---

## 三、现有核心模块测试分布（概览）

当前已存在的后端测试（部分）：

- 配置与基础：
  - `test/backend/test_config.py`
  - `test/backend/test_main.py`
  - `test/backend/test_middleware.py`
  - `test/backend/test_utils.py`
  - `test/backend/test_conversation_file_manager.py`
- 数据库与数据访问：
  - `test/backend/test_database.py`
  - `test/backend/test_database_operations.py`
- 知识库与向量：
  - `test/backend/core/knowledge/test_loader.py`
  - `test/backend/core/knowledge/test_search.py`
  - `test/backend/core/knowledge/vector/test_factory.py`
  - `test/backend/core/knowledge/vector/test_memory.py`
- LLM / ASR / TTS：
  - `test/backend/core/llmapi/test_base.py`
  - `test/backend/core/llmapi/test_factory.py`
  - `test/backend/core/llmapi/test_openai_provider.py`
  - `test/backend/core/asr/test_openai_whisper.py`
  - `test/backend/core/tts/test_openai_tts.py`

> 智能体（agent）相关测试目前是空位，推荐按第二节所述方式补齐。

---

## 四、常见测试问题排查

更全面的 FAQ 与排错见：`docs/TESTING.md` 和 `docs/FAQ.md`，这里只列与智能体相关的建议：

- **依赖缺失 / LangGraph 未安装**  
  - 错误提示中如出现 `LangGraph未安装，请运行: pip install langgraph`，请确认已在虚拟环境中安装正确版本。

- **测试运行时访问外部 API 失败**  
  - 优先通过 monkeypatch / fixture mock 掉真实 LLM 调用；  
  - 不建议在单元测试中依赖真实 OpenAI/DeepSeek 服务。

- **智能体测试覆盖率不足**  
  - 建议优先覆盖：
    - `create_agent_graph` 的构图与循环逻辑（`should_continue` / `max_iterations`）；  
    - `reasoning_node` 的正常路径与 JSON 解析失败路径；  
    - `guide_node` 的正常路径与异常路径。

---

## 五、与 Agent 实际对话，并记录调用/思考日志

你可以用两种方式和已经开发好的 Agent 对话，并观察它的调用与“思考”过程。

### 1. 通过 HTTP 接口对话，并查看对话日志

#### 1.1 启动后端服务

```bash
cd src/backend
source venv/bin/activate      # Windows 使用 venv\Scripts\activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### 1.2 创建会话（获取 session_id）

接口：`POST /api/v1/sessions`

示例请求（用 curl）：

```bash
curl -X POST http://localhost:8000/api/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "debug-client",
    "current_step": "values_exploration"
  }'
```

返回示例（节选）：

```json
{
  "code": 200,
  "data": {
    "session_id": "xxxx-xxxx-...",
    "current_step": "values_exploration"
  }
}
```

后面所有对话都复用这个 `session_id`。

#### 1.3 发送对话消息（通过 Agent）

接口：`POST /api/v1/chat/messages`

```bash
curl -X POST http://localhost:8000/api/v1/chat/messages \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "上一步返回的session_id",
    "message": "我最近对工作很迷茫，你可以帮我梳理一下吗？",
    "current_step": "values_exploration",
    "category": "main_flow"
  }'
```

返回示例（节选，自 `app/api/v1/chat.py::send_message`）：

```json
{
  "code": 200,
  "data": {
    "response": "... 助手的回复 ...",
    "session_id": "xxxx-xxxx-...",
    "tools_used": ["search_tool", "guide_tool"]
  }
}
```

- 这里的 `tools_used` 就是这轮对话里 Agent 实际调用过的工具列表，来自 `final_state["tools_used"]`。

#### 1.4 查看对话日志（文本层面）

对话日志由 `ConversationFileManager` 写入 JSON 文件（`app/utils/conversation_file_manager.py`）：

- 目录：`data/conversations/<session_id>/`
- 主流程对话文件：`main_flow.json`

结构大致如下：

```json
{
  "session_id": "xxxx-xxxx-...",
  "category": "main_flow",
  "messages": [
    {
      "id": "msg_1",
      "role": "user",
      "content": "我最近对工作很迷茫，你可以帮我梳理一下吗？",
      "created_at": "2026-02-04T12:34:56Z",
      "context": {"current_step": "values_exploration"}
    },
    {
      "id": "msg_2",
      "role": "assistant",
      "content": "... 助手的具体回答 ...",
      "created_at": "2026-02-04T12:34:58Z",
      "context": {"current_step": "values_exploration"}
    }
  ],
  "metadata": {
    "created_at": "...",
    "updated_at": "...",
    "total_messages": 2
  }
}
```

> 这一层日志主要用于回放对话内容，不包含完整的内部推理/工具调用细节，但能看到每轮 input/output 的时间线。

---

### 2. 在 Python 里直接跑 Agent，并记录内部“思考”流程

如果你想看到更细的内部状态（每一步的 `reasoning`、`tool_results`、`observation` 等），可以写一个专门的调试脚本或 pytest 用例，直接使用 `create_agent_graph` 和 `graph.astream`。

下面是一个**开发调试用**的示例（可以放在 `scripts/debug_agent.py` 或 notebook 里）：\n

```python
import asyncio
import json
from pathlib import Path

from app.core.agent.graph import create_agent_graph, create_initial_state


async def debug_agent_conversation():
    graph = create_agent_graph()

    # 构建初始状态（可以手动指定 session_id 方便和文件日志对齐）
    session_id = "debug-session-1"
    state = create_initial_state(
        user_input="我最近对工作很迷茫，你可以帮我梳理一下吗？",
        current_step="values_exploration",
        user_id=None,
        session_id=session_id,
    )

    debug_steps = []

    # 逐步遍历 LangGraph 的执行过程
    async for step in graph.astream(state):
        # step 一般是 {\"节点名\": AgentState} 或 AgentState 本身
        if isinstance(step, dict):
            node_name = list(step.keys())[-1]
            node_state = step[node_name]
        else:
            node_name = \"unknown\"
            node_state = step

        # 只保留适合序列化的字段，方便写入 JSON
        debug_steps.append(
            {
                \"node\": node_name,
                \"current_step\": node_state.get(\"current_step\"),\n
                \"tools_used\": node_state.get(\"tools_used\", []),
                \"tool_results\": node_state.get(\"tool_results\", []),
                \"reasoning\": node_state.get(\"context\", {}).get(\"reasoning\"),\n
                \"observation\": node_state.get(\"context\", {}).get(\"observation\"),\n
                \"final_response\": node_state.get(\"final_response\"),\n
                \"error\": node_state.get(\"error\"),\n
            }
        )

    # 将调试信息写入文件，便于之后分析
    out_dir = Path(\"data/agent_debug\")\n
    out_dir.mkdir(parents=True, exist_ok=True)\n
    out_path = out_dir / f\"{session_id}.json\"\n
    out_path.write_text(json.dumps(debug_steps, indent=2, ensure_ascii=False), encoding=\"utf-8\")\n

    print(f\"调试日志已写入: {out_path}\")\n

\nif __name__ == \"__main__\":\n
    asyncio.run(debug_agent_conversation())\n
```

运行方式（在虚拟环境里）：\n

```bash
cd src/backend
python scripts/debug_agent.py   # 如果你把上面的代码存成这个文件名\n
```

然后查看：`data/agent_debug/debug-session-1.json`，你就可以看到每一步：\n

- 哪个节点在执行（`node`）  
- 当前所在业务步骤（`current_step`）  
- 已经用了哪些工具（`tools_used` / `tool_results`）  
- LLM 决策 JSON（`reasoning`）  
- 工具结果二次分析（`observation`）  
- 最终回复与错误信息（`final_response` / `error`）  

> 注意：真实运行时，`reasoning_node` / `observation_node` 里会调用外部 LLM，如果只是做结构调试，建议在 pytest 用例里通过 monkeypatch mock 掉对真实 API 的调用，避免不可控因素影响测试稳定性。


