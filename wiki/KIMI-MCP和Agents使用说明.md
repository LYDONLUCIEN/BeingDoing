# Kimi Code CLI - MCP 与 Agents 使用说明

本文档详细介绍 Kimi Code CLI 的 MCP (Model Context Protocol) 集成和自定义 Agents 功能。

---

## 目录

- [MCP (Model Context Protocol)](#mcp-model-context-protocol)
  - [什么是 MCP](#什么是-mcp)
  - [MCP 服务器管理命令](#mcp-服务器管理命令)
  - [MCP 配置文件](#mcp-配置文件)
  - [在会话中查看 MCP 状态](#在会话中查看-mcp-状态)
- [自定义 Agents](#自定义-agents)
  - [内置 Agent](#内置-agent)
  - [创建自定义 Agent](#创建自定义-agent)
  - [系统提示词](#系统提示词)
  - [子 Agent](#子-agent)
- [快速开始示例](#快速开始示例)
  - [添加 GitHub MCP 服务器](#添加-github-mcp-服务器)
  - [创建自定义 Agent](#创建自定义-agent-1)
- [安全性注意事项](#安全性注意事项)

---

## MCP (Model Context Protocol)

### 什么是 MCP

[MCP (Model Context Protocol)](https://modelcontextprotocol.io/) 是一个开放协议，让 AI 模型可以安全地与外部工具和数据源交互。通过 MCP，你可以为 Kimi Code CLI 添加更多功能：

- **访问特定 API 或数据库** - 如查询数据库、调用内部 API
- **控制浏览器或其他应用** - 如自动化浏览器操作
- **与第三方服务集成** - 如 GitHub、Linear、Notion 等

Kimi Code CLI 内置了一些基础工具（文件读写、Shell 命令、网页抓取等），通过 MCP 可以扩展更多能力。

### MCP 服务器管理命令

使用 `kimi mcp` 命令管理 MCP 服务器：

#### 添加服务器

**添加 HTTP 服务器：**
```bash
# 基本用法
kimi mcp add --transport http context7 https://mcp.context7.com/mcp

# 带 Header 认证
kimi mcp add --transport http context7 https://mcp.context7.com/mcp \
  --header "CONTEXT7_API_KEY: your-key"

# 使用 OAuth 认证
kimi mcp add --transport http --auth oauth linear https://mcp.linear.app/mcp
```

**添加本地进程服务器 (stdio)：**
```bash
kimi mcp add --transport stdio chrome-devtools -- npx chrome-devtools-mcp@latest
```

#### 其他管理命令

```bash
# 列出所有已配置的服务器
kimi mcp list

# 移除服务器
kimi mcp remove context7

# OAuth 授权（对于使用 OAuth 的服务器）
kimi mcp auth linear

# 测试服务器连接
kimi mcp test context7
```

### MCP 配置文件

MCP 服务器配置存储在 `~/.kimi/mcp.json`，格式与其他 MCP 客户端兼容：

```json
{
  "mcpServers": {
    "context7": {
      "url": "https://mcp.context7.com/mcp",
      "headers": {
        "CONTEXT7_API_KEY": "your-key"
      }
    },
    "chrome-devtools": {
      "command": "npx",
      "args": ["chrome-devtools-mcp@latest"],
      "env": {
        "SOME_VAR": "value"
      }
    }
  }
}
```

#### 临时加载其他配置

```bash
# 从文件加载
kimi --mcp-config-file /path/to/mcp.json

# 直接传入 JSON 配置
kimi --mcp-config '{"mcpServers": {"test": {"url": "https://..."}}}'
```

### 在会话中查看 MCP 状态

启动 Kimi Code CLI 后，输入 `/mcp` 可以查看：
- 已连接的服务器列表
- 每个服务器加载的工具
- 连接状态

MCP 服务器在 Shell UI 启动后**异步初始化**，不会阻塞界面。底部状态栏会显示连接进度，连接完成后自动切换为就绪状态。

---

## 自定义 Agents

Agent 定义了 AI 的行为方式，包括系统提示词、可用工具和子 Agent。

### 内置 Agent

Kimi Code CLI 提供两个内置 Agent：

| Agent | 说明 | 特点 |
|-------|------|------|
| `default` | 默认 Agent | 适合通常情况使用，包含常用工具 |
| `okabe` | 实验性 Agent | 在 default 基础上额外启用 `SendDMail` |

**切换 Agent：**
```bash
kimi --agent okabe
```

### 创建自定义 Agent

Agent 使用 **YAML 格式** 定义，通过 `--agent-file` 参数加载：

```bash
kimi --agent-file /path/to/my-agent.yaml
```

#### 基本结构

```yaml
version: 1
agent:
  name: my-agent
  system_prompt_path: ./system.md
  tools:
    - "kimi_cli.tools.shell:Shell"
    - "kimi_cli.tools.file:ReadFile"
    - "kimi_cli.tools.file:WriteFile"
```

#### 继承与覆盖

使用 `extend` 可以继承其他 Agent 的配置，只覆盖需要修改的部分：

```yaml
version: 1
agent:
  extend: default  # 继承默认 Agent
  system_prompt_path: ./my-prompt.md  # 覆盖系统提示词
  exclude_tools:  # 排除某些工具
    - "kimi_cli.tools.web:SearchWeb"
    - "kimi_cli.tools.web:FetchURL"
```

`extend: default` 会继承内置的默认 Agent。你也可以指定相对路径继承其他 Agent 文件。

#### 配置字段说明

| 字段 | 说明 | 是否必填 |
|------|------|----------|
| `extend` | 继承的 Agent，可以是 `default` 或相对路径 | 否 |
| `name` | Agent 名称 | 是（继承时可省略） |
| `system_prompt_path` | 系统提示词文件路径，相对于 Agent 文件 | 是（继承时可省略） |
| `system_prompt_args` | 传递给系统提示词的自定义参数，继承时会合并 | 否 |
| `tools` | 工具列表，格式为 `模块:类名` | 是（继承时可省略） |
| `exclude_tools` | 要排除的工具 | 否 |
| `subagents` | 子 Agent 定义 | 否 |

### 系统提示词

系统提示词是一个 Markdown 模板，可以使用 `${VAR}` 语法引用变量。

#### 内置变量

| 变量 | 说明 |
|------|------|
| `${KIMI_NOW}` | 当前时间（ISO 格式） |
| `${KIMI_WORK_DIR}` | 工作目录路径 |
| `${KIMI_WORK_DIR_LS}` | 工作目录文件列表 |
| `${KIMI_AGENTS_MD}` | AGENTS.md 文件内容（如果存在） |
| `${KIMI_SKILLS}` | 加载的 Skills 列表 |
| `${KIMI_ADDITIONAL_DIRS_INFO}` | 通过 `--add-dir` 或 `/add-dir` 添加的额外目录信息 |

#### 自定义变量

通过 `system_prompt_args` 定义自定义参数：

```yaml
agent:
  system_prompt_args:
    MY_VAR: "自定义值"
    ROLE: "代码审查专家"
```

然后在提示词中使用 `${MY_VAR}` 和 `${ROLE}`。

#### 系统提示词示例

```markdown
# 代码审查助手

你是一位专业的 ${ROLE}。

当前时间: ${KIMI_NOW}
工作目录: ${KIMI_WORK_DIR}

你的职责：
1. 检查代码质量和最佳实践
2. 发现潜在的 bug
3. 提供改进建议

${MY_VAR}
```

### 子 Agent

子 Agent 可以处理特定类型的任务。在 Agent 文件中定义子 Agent 后，主 Agent 可以通过 `Task` 工具启动它们。

#### 定义子 Agent

```yaml
version: 1
agent:
  extend: default
  subagents:
    coder:
      path: ./coder-sub.yaml
      description: "处理编码任务"
    reviewer:
      path: ./reviewer-sub.yaml
      description: "代码审查专家"
```

#### 子 Agent 文件示例

```yaml
# coder-sub.yaml
version: 1
agent:
  extend: ./agent.yaml  # 继承主 Agent
  system_prompt_args:
    ROLE_ADDITIONAL: |
      你现在作为子 Agent 运行，专注于编码任务...
  exclude_tools:
    - "kimi_cli.tools.multiagent:Task"  # 排除 Task 工具，避免嵌套
```

#### 子 Agent 的运行方式

通过 `Task` 工具启动的子 Agent 会在**独立的上下文中运行**，完成后将结果返回给主 Agent。这种方式的优势：

- **隔离上下文** - 避免污染主 Agent 的对话历史
- **并行处理** - 可以同时处理多个独立任务
- **针对性提示词** - 子 Agent 可以有专门的系统提示词

#### 动态创建子 Agent

`CreateSubagent` 工具允许 AI 在运行时动态定义新的子 Agent 类型（默认未启用）：

```yaml
agent:
  tools:
    - "kimi_cli.tools.multiagent:CreateSubagent"
```

动态创建的子 Agent 会随会话状态持久化，恢复会话时自动还原。

---

## 快速开始示例

### 添加 GitHub MCP 服务器

```bash
# 1. 添加 GitHub MCP 服务器
kimi mcp add --transport http --auth oauth github https://api.github.com/mcp

# 2. 完成 OAuth 授权
kimi mcp auth github

# 3. 测试连接
kimi mcp test github

# 4. 启动 Kimi Code CLI 使用
kimi
```

在会话中输入 `/mcp` 查看已加载的 GitHub 工具。

### 创建自定义 Agent

**1. 创建 Agent 配置文件 `my-agent.yaml`：**

```yaml
version: 1
agent:
  extend: default
  name: code-reviewer
  system_prompt_path: ./reviewer-prompt.md
  exclude_tools:
    - "kimi_cli.tools.web:SearchWeb"
  subagents:
    security:
      path: ./security-sub.yaml
      description: "安全审查专家"
```

**2. 创建系统提示词 `reviewer-prompt.md`：**

```markdown
# 代码审查助手

你是一位专业的代码审查专家。

当前时间: ${KIMI_NOW}
工作目录: ${KIMI_WORK_DIR}

## 你的职责

1. **代码质量** - 检查代码是否符合最佳实践
2. **Bug 检测** - 发现潜在的逻辑错误
3. **性能优化** - 提出性能改进建议
4. **安全审查** - 对于安全问题，调用 security 子 Agent 深入分析

## 审查原则

- 保持建设性，提供具体的改进建议
- 优先关注关键问题，不过度纠结细节
- 考虑代码的可读性和可维护性
```

**3. 创建子 Agent 配置 `security-sub.yaml`：**

```yaml
version: 1
agent:
  extend: ./my-agent.yaml
  system_prompt_path: ./security-prompt.md
  exclude_tools:
    - "kimi_cli.tools.multiagent:Task"
```

**4. 创建子 Agent 提示词 `security-prompt.md`：**

```markdown
# 安全审查专家

你是一位专注于安全的代码审查专家。

当前时间: ${KIMI_NOW}

## 关注领域

- SQL 注入风险
- XSS 漏洞
- 敏感信息泄露
- 不安全的依赖
- 权限控制问题

## 输出格式

对于每个发现的问题，请提供：
1. 问题描述
2. 风险等级（高/中/低）
3. 具体代码位置
4. 修复建议
```

**5. 启动使用：**

```bash
kimi --agent-file ./my-agent.yaml
```

---

## 安全性注意事项

### MCP 工具安全

MCP 工具可能会访问和操作外部系统，需要注意：

1. **审批机制** - 所有 MCP 工具调用都会弹出确认提示，需要用户批准
2. **提示词注入风险** - MCP 工具返回的内容可能包含恶意指令
3. **YOLO 模式警告** - 在 YOLO 模式下，MCP 工具的操作也会被自动批准

**建议：**
- 只使用可信来源的 MCP 服务器
- 检查 AI 提议的操作是否合理
- 对于高风险操作保持手动审批

### 工具安全边界

| 操作 | 审批要求 |
|------|---------|
| Shell 命令执行 | 每次执行 |
| 文件写入/编辑 | 每次操作 |
| MCP 工具调用 | 每次调用 |
| 停止后台任务 | 每次停止 |

**工作区范围：**
- 文件读写通常在工作目录（及通过 `--add-dir` 或 `/add-dir` 添加的额外目录）内进行
- 读取工作区外文件需使用绝对路径
- 写入和编辑操作都需要用户审批

---

## 参考资源

- [MCP 官方文档](https://modelcontextprotocol.io/)
- [Kimi Code CLI 文档](https://moonshotai.github.io/kimi-cli/)
- [Kimi Code CLI GitHub](https://github.com/MoonshotAI/kimi-cli)

---

*文档更新时间：2026-03-19*
