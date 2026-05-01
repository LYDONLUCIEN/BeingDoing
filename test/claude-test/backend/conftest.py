"""claude-test 后端 conftest — 确保能导入 app 模块"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

# 让 src/backend 在 sys.path 中，使 `import app.xxx` 生效
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_BACKEND_DIR = _PROJECT_ROOT / "src" / "backend"
_BACKEND_STR = str(_BACKEND_DIR)
if _BACKEND_STR not in sys.path:
    sys.path.insert(0, _BACKEND_STR)


@pytest.fixture
def sample_table_rows() -> List[Dict[str, Any]]:
    """通用测试表格数据（3 行）。"""
    return [
        {
            "id": "1",
            "热爱": "教育",
            "优势": "沟通",
            "优势标记": "有充实感",
            "匹配性": "匹配",
            "用户确认的假设": "",
            "假设1": "",
            "假设2": "",
        },
        {
            "id": "2",
            "热爱": "写作",
            "优势": "分析",
            "优势标记": "有充实感",
            "匹配性": "不匹配",
            "用户确认的假设": "",
            "假设1": "",
            "假设2": "",
        },
        {
            "id": "3",
            "热爱": "公益",
            "优势": "组织",
            "优势标记": "不确定",
            "匹配性": "匹配",
            "用户确认的假设": "",
            "假设1": "",
            "假设2": "",
        },
    ]


@pytest.fixture
def fake_dimension_conclusion() -> Dict[str, Dict[str, Any]]:
    """模拟已确认结论卡数据。"""
    return {
        "values": {"keywords": ["诚信", "成长", "自由"]},
        "strengths": {"keywords": ["写作", "沟通", "分析"]},
        "interests": {"keywords": ["教育", "公益", "心理学"]},
        "purpose": {"keywords": ["帮助他人成长"]},
    }


@pytest.fixture
def fake_report_record() -> Dict[str, Any]:
    """模拟 report record.json 数据。"""
    return {
        "steps": {
            "values": {"anchor_summary": {"goals": "包括诚信、责任感等，强调个人成长"}},
            "strengths": {"anchor_summary": {"goals": "写作、沟通能力、分析能力"}},
            "interests": {"anchor_summary": {"goals": "教育、公益"}},
            "purpose": {"anchor_summary": {"goals": "「帮助他人成长」"}},
        }
    }


@pytest.fixture
def fake_prior_context() -> str:
    """模拟 prior_context_values.txt 内容。"""
    return (
        "【信念 阶段结果】\n"
        "1. 诚信\n2. 责任\n3. 成长\n\n"
        "【禀赋 阶段结果】\n"
        "写作、沟通、分析\n\n"
        "【热忱 阶段结果】\n"
        "教育、公益\n\n"
        "【使命 阶段结果】\n"
        "帮助他人\n"
    )
