"""
统一的项目数据目录，供复杂版 explore 使用。

所有日志、对话、题目进度等数据存储在项目根 ./data/ 下，
不依赖当前工作目录，避免数据落在 src/backend/ 内。
"""
from pathlib import Path


def get_project_root() -> Path:
    """项目根目录 (BeingDoing/)"""
    # app/utils/data_paths.py -> .../src/backend/app/utils -> parents[4] = 项目根
    return Path(__file__).resolve().parents[4]


def get_project_data_dir() -> Path:
    """项目根目录下的 data/"""
    return get_project_root() / "data"


def get_conversation_dir() -> Path:
    """data/conversations/ - 对话记录"""
    return get_project_data_dir() / "conversations"


def get_question_progress_dir() -> Path:
    """data/question_progress/ - 题目进度"""
    return get_project_data_dir() / "question_progress"


def get_debug_logs_dir() -> Path:
    """data/debug_logs/ - 按 session 维度的调试日志"""
    return get_project_data_dir() / "debug_logs"


def get_logs_dir() -> Path:
    """data/logs/ - 按 user/session 维度的运行日志"""
    return get_project_data_dir() / "logs"
