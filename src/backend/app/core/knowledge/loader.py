"""
知识库加载模块：支持从 domain 注入配置（文件路径、列名映射），解耦且知识集中。
"""
import csv
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class ValueItem:
    """价值观项目"""
    id: int
    name: str
    definition: str


@dataclass
class InterestItem:
    """兴趣项目"""
    id: int
    name: str


@dataclass
class StrengthItem:
    """才能项目"""
    id: int
    name: str
    strengths: str
    weaknesses: str


@dataclass
class QuestionItem:
    """问题项目"""
    id: int
    category: str  # values, strengths, interests
    question_number: int
    content: str
    is_starred: bool = False


def _default_config() -> Dict[str, Any]:
    """默认配置（与当前 CSV 表头一致），不依赖 domain。"""
    return {
        "base_dir": None,
        "files": {
            "values": "重要的事_价值观.csv",
            "interests": "喜欢的事_热情.csv",
            "strengths": "擅长的事_才能.csv",
            "questions": "question.md",
        },
        "columns": {
            "values": {"id": "序号", "name": "价值观", "definition": "定义"},
            "interests": {"id": "序号", "name": "领域"},
            "strengths": {"id": "序号", "name": "才能", "strengths": "成为长处", "weaknesses": "成为短处"},
        },
    }


class KnowledgeLoader:
    """知识库加载器：支持可选 config（来自 domain），用于路径与列名映射。"""

    def __init__(self, base_dir: Optional[str] = None, config: Optional[Dict[str, Any]] = None):
        """
        Args:
            base_dir: 知识库根目录，None 则用 config 或默认项目根
            config: 可选，来自 app.domain.knowledge_config.get_knowledge_config()；含 base_dir, files, columns
        """
        cfg = config or _default_config()
        self._config = cfg
        self._files = cfg.get("files", _default_config()["files"])
        self._columns = cfg.get("columns", _default_config()["columns"])

        if base_dir is not None:
            self.base_dir = Path(base_dir)
        elif cfg.get("base_dir") is not None:
            self.base_dir = Path(cfg["base_dir"])
        else:
            self.base_dir = Path(__file__).parent.parent.parent.parent.parent.parent

        self.values_file = self.base_dir / self._files.get("values", "重要的事_价值观.csv")
        self.interests_file = self.base_dir / self._files.get("interests", "喜欢的事_热情.csv")
        self.strengths_file = self.base_dir / self._files.get("strengths", "擅长的事_才能.csv")
        self.questions_file = self.base_dir / self._files.get("questions", "question.md")

        self._values_cache: Optional[List[ValueItem]] = None
        self._interests_cache: Optional[List[InterestItem]] = None
        self._strengths_cache: Optional[List[StrengthItem]] = None
        self._questions_cache: Optional[List[QuestionItem]] = None

    def load_values(self, force_reload: bool = False) -> List[ValueItem]:
        if self._values_cache is None or force_reload:
            col = self._columns.get("values", _default_config()["columns"]["values"])
            values = []
            if not self.values_file.exists():
                raise FileNotFoundError(f"价值观文件不存在: {self.values_file}")
            with open(self.values_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    values.append(ValueItem(
                        id=int(row.get(col["id"], 0) or 0),
                        name=(row.get(col["name"]) or "").strip(),
                        definition=(row.get(col["definition"]) or "").strip(),
                    ))
            self._values_cache = values
        return self._values_cache

    def load_interests(self, force_reload: bool = False) -> List[InterestItem]:
        if self._interests_cache is None or force_reload:
            col = self._columns.get("interests", _default_config()["columns"]["interests"])
            interests = []
            if not self.interests_file.exists():
                raise FileNotFoundError(f"兴趣文件不存在: {self.interests_file}")
            with open(self.interests_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    interests.append(InterestItem(
                        id=int(row.get(col["id"], 0) or 0),
                        name=(row.get(col["name"]) or "").strip(),
                    ))
            self._interests_cache = interests
        return self._interests_cache

    def load_strengths(self, force_reload: bool = False) -> List[StrengthItem]:
        if self._strengths_cache is None or force_reload:
            col = self._columns.get("strengths", _default_config()["columns"]["strengths"])
            strengths = []
            if not self.strengths_file.exists():
                raise FileNotFoundError(f"才能文件不存在: {self.strengths_file}")
            with open(self.strengths_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    strengths.append(StrengthItem(
                        id=int(row.get(col["id"], 0) or 0),
                        name=(row.get(col["name"]) or "").strip(),
                        strengths=(row.get(col["strengths"]) or "").strip(),
                        weaknesses=(row.get(col["weaknesses"]) or "").strip(),
                    ))
            self._strengths_cache = strengths
        return self._strengths_cache

    def load_questions(self, force_reload: bool = False) -> List[QuestionItem]:
        if self._questions_cache is None or force_reload:
            questions = []
            if not self.questions_file.exists():
                raise FileNotFoundError(f"问题文件不存在: {self.questions_file}")
            with open(self.questions_file, "r", encoding="utf-8") as f:
                content = f.read()
            current_category = None
            question_number = 0
            for line in content.split("\n"):
                line = line.strip()
                if line.startswith("## "):
                    category_text = line[3:].strip()
                    if "价值观" in category_text or "重要的事" in category_text:
                        current_category = "values"
                        question_number = 0
                    elif "才能" in category_text or "擅长的事" in category_text:
                        current_category = "strengths"
                        question_number = 0
                    elif "兴趣" in category_text or "喜欢的事" in category_text:
                        current_category = "interests"
                        question_number = 0
                elif line and current_category:
                    is_starred = "⭐" in line or "星号" in line
                    question_content = line
                    if question_content.startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.")):
                        parts = question_content.split(".", 1)
                        if len(parts) > 1:
                            question_content = parts[1].strip()
                    question_content = question_content.replace("⭐", "").replace("星号", "").strip()
                    if question_content:
                        question_number += 1
                        questions.append(QuestionItem(
                            id=len(questions) + 1,
                            category=current_category,
                            question_number=question_number,
                            content=question_content,
                            is_starred=is_starred
                        ))
            self._questions_cache = questions
        return self._questions_cache

    def load_all(self, force_reload: bool = False) -> Dict[str, Any]:
        return {
            "values": self.load_values(force_reload),
            "interests": self.load_interests(force_reload),
            "strengths": self.load_strengths(force_reload),
            "questions": self.load_questions(force_reload),
        }

    def clear_cache(self):
        self._values_cache = None
        self._interests_cache = None
        self._strengths_cache = None
        self._questions_cache = None
