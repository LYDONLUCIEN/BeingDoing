import os
from typing import Tuple, List

from langchain_core.runnables import RunnableConfig

from new_agent.graph.state import AgentState


DEFAULT_KNOWLEDGE_DIR_ENV = "KNOWLEDGE_DIR"
SUPPORTED_EXTS = (".txt", ".md", ".csv")


def _resolve_knowledge_dir() -> str:
    """
    知识库根目录：
    - 优先使用环境变量 KNOWLEDGE_DIR；
    - 否则使用当前工作目录下的 knowledge/。
    """
    base = os.getenv(DEFAULT_KNOWLEDGE_DIR_ENV)
    if not base:
        base = os.path.join(os.getcwd(), "knowledge")
    os.makedirs(base, exist_ok=True)
    return base


def _iter_knowledge_files(base_dir: str) -> List[str]:
    paths: List[str] = []
    for root, _, files in os.walk(base_dir):
        for f in files:
            if f.lower().endswith(SUPPORTED_EXTS):
                paths.append(os.path.join(root, f))
    return paths


async def query_knowledge(
    state: AgentState,
    config: RunnableConfig,
    question: str,
) -> Tuple[AgentState, str]:
    """
    极简知识库查询工具：

    - 在指定知识库目录下遍历 .txt/.md/.csv 文件；
    - 做最简单的关键字匹配（不做向量检索）；
    - 返回若干条命中的片段，供上层 LLM 使用。

    注意：
    - 这是一个「占位实现」，重心在接口形态：
      (state, config, question) -> (state, summary_text)。
    - 将来可以在内部替换为向量检索 / 专业 RAG，而不改上层节点。
    """
    base_dir = _resolve_knowledge_dir()
    files = _iter_knowledge_files(base_dir)

    if not files:
        return state, "知识库目录中尚无可用的文本文件。"

    # 非严格分词，简单按空格和常见分隔符拆成一组关键字
    import re

    tokens = [t for t in re.split(r"[\s,;，。！？!?.]+", question) if t]
    tokens = [t.lower() for t in tokens]

    hits: List[str] = []
    max_hits = 5

    for path in files:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except Exception:
            continue

        lowered = text.lower()
        score = sum(1 for t in tokens if t and t in lowered)
        if score <= 0:
            continue

        snippet = text[:800]
        hits.append(f"=== 文件: {os.path.relpath(path, base_dir)} （命中 {score} 次） ===\n{snippet}\n")
        if len(hits) >= max_hits:
            break

    if not hits:
        return state, "在知识库中未找到明显相关内容，请尝试换一种问法或补充更多上下文。"

    result_text = "以下是从知识库中检索到的参考内容（供模型使用，不必逐字复述）：\n\n" + "\n".join(hits)
    return state, result_text

