# 寻录 (xunlu) — 领域术语

> 面向产品、运营与开发共用的语言。不含实现细节。

## 探索流程

**阶段 (Phase)**  
用户探索路径上的五个主阶段：`values`（价值观）、`strengths`（优势）、`interests`（兴趣）、`purpose`（使命）、`rumination`（沉淀）。

**沉淀子步 (Filter Step)**  
沉淀阶段内的 7 个筛选步骤（编号 1–7），用于表格筛选、假设生成、方向点选等。每子步可有独立的引导语与对话追加提示词。

## 提示词分类

**阶段引导语**  
进入或离开某阶段时展示给用户的弹窗文案（intro / outro），不直接作为 LLM system prompt。

**主对话提示词**  
该阶段 LLM 对话使用的 system prompt 主体，按阶段分支。

**子步对话追加 (Chat Addon)**  
沉淀子步 1–7 各自追加到主对话 system prompt 的片段。

**子步引导语 (Step Opening)**  
进入沉淀某子步时的开场白。分两种模式：**固定文案**（直接展示）或 **LLM 生成**（由 system + user 模板驱动）。

**兜底 (Fallback)**  
主路径失败或未命中时的备用文案，例如首轮开场失败、零结果闸门、探索阶段 init 兜底等。

**运行时追加**  
对话过程中动态拼接到 system prompt 的内容（如状态协议块、使命进度、结论卡待确认摘要），非静态配置文件中的完整段落。

**Canonical 配置**  
Git 中的 YAML 与 Python 常量，生产环境默认使用的提示词来源。

**Prompt Lab 覆盖**  
仅在调试沙箱激活码下生效的提示词改写（当前限于主对话模板与 extra_goal_hint），不改变 canonical 配置。

**Effective 提示词**  
某次沙箱对话实际生效的拼装结果：canonical Layer Stack + 可选 Prompt Lab 覆盖 + 运行时注入。

**注入点 (Injection Point)**  
运行时内容拼接到 system prompt 的位置；在提示词总览中以分层堆叠视图标注顺序与触发条件。

**变量占位符 / 示例上下文**  
模板中的 `{{ variable }}`；悬停可查看固定 mock 示例，不展示真实用户数据。

## 提示词总览（Prompt Lab 扩展）

合并进 Prompt Lab，不单独开页。按五阶段浏览；沉淀阶段内按子步 1–7 展开。v1 不含 LangGraph 节点提示词。双语项（如 step_copy、chat_addon）通过页顶 **中/英切换** 展示。

## 调试与隔离

**调试沙箱 (Sandbox Fork)**  
从正式激活码 fork 出的隔离环境（`SBX*` 激活码），用于测试，不影响生产用户。

**Savepoint**  
沙箱会话在某一刻的状态快照；载入后可从该点继续手动测试，不修改 canonical 提示词文件。沉淀/子步调试时优先使用。

**试跑**  
在沙箱中验证提示词效果的两条路径：**从 Savepoint 续测**（默认/主路径）与 **Fork 从头试跑**（整阶段流程）。
