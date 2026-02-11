import os
from typing import Tuple

from langchain_core.runnables import RunnableConfig

from new_agent.graph.state import AgentState


DEFAULT_BASE_DIR_ENV = "NOTE_BASE_DIR"


def _resolve_base_dir() -> str:
    """
    解析笔记根目录：
    - 优先使用环境变量 NOTE_BASE_DIR
    - 否则使用当前工作目录下的 notes/
    """
    base = os.getenv(DEFAULT_BASE_DIR_ENV)
    if not base:
        base = os.path.join(os.getcwd(), "notes")
    os.makedirs(base, exist_ok=True)
    return base


async def write_note(
    state: AgentState,
    config: RunnableConfig,
    path: str,
    content: str,
) -> Tuple[AgentState, str]:
    """
    将笔记内容写入指定相对路径。

    - 实际写入位置 = base_dir / path
      其中 base_dir 由环境变量 NOTE_BASE_DIR 或默认的 ./notes 决定。
    - 如有必要，可在上层对 path 做更严格的校验（防止越权路径）。
    """
    base_dir = _resolve_base_dir()
    # 简单防御：禁止绝对路径，禁止向上跳目录
    safe_path = os.path.normpath(path).lstrip(os.sep)
    full_path = os.path.join(base_dir, safe_path)

    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)

    notes = state.get("notes", [])
    notes.append({"path": path, "content": content})
    state["notes"] = notes

    return state, f"笔记已写入: {full_path}"

