"""
知识源配置：文件路径与 CSV 列名映射，单点维护。
Loader / Searcher 通过 config 注入使用，便于扩展新 CSV 且保持知识集中。
"""
from pathlib import Path
from typing import Dict, Any, Optional

# 知识库根目录，None 表示项目根目录（由调用方或 loader 解析）
KNOWLEDGE_BASE_DIR: Optional[Path] = None

# 知识库文件名（相对 base_dir）
KNOWLEDGE_FILES: Dict[str, str] = {
    "values": "重要的事_价值观.csv",
    "interests": "喜欢的事_热情.csv",
    "strengths": "擅长的事_才能.csv",
    "questions": "question.md",
}

# 各类型 CSV 的列名：内部字段名 -> 实际 CSV 表头
COLUMNS_VALUES: Dict[str, str] = {
    "id": "序号",
    "name": "价值观",
    "definition": "定义",
}
COLUMNS_INTERESTS: Dict[str, str] = {
    "id": "序号",
    "name": "领域",
}
COLUMNS_STRENGTHS: Dict[str, str] = {
    "id": "序号",
    "name": "才能",
    "strengths": "成为长处",
    "weaknesses": "成为短处",
}


def get_knowledge_config(base_dir: Optional[Path] = None) -> Dict[str, Any]:
    """
    返回供 KnowledgeLoader 使用的配置。
    base_dir 若为 None，loader 内部使用项目根目录。
    """
    return {
        "base_dir": base_dir,
        "files": KNOWLEDGE_FILES,
        "columns": {
            "values": COLUMNS_VALUES,
            "interests": COLUMNS_INTERESTS,
            "strengths": COLUMNS_STRENGTHS,
        },
    }
