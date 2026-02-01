"""
知识库加载模块
"""
import csv
import json
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from app.config.settings import settings


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


class KnowledgeLoader:
    """知识库加载器"""
    
    def __init__(self, base_dir: Optional[str] = None):
        """
        初始化知识库加载器
        
        Args:
            base_dir: 知识库文件根目录，None则使用项目根目录
        """
        if base_dir is None:
            # 默认从项目根目录查找
            self.base_dir = Path(__file__).parent.parent.parent.parent.parent
        else:
            self.base_dir = Path(base_dir)
        
        # 知识库文件路径
        self.values_file = self.base_dir / "重要的事_价值观.csv"
        self.interests_file = self.base_dir / "喜欢的事_热情.csv"
        self.strengths_file = self.base_dir / "擅长的事_才能.csv"
        self.questions_file = self.base_dir / "question.md"
        
        # 缓存
        self._values_cache: Optional[List[ValueItem]] = None
        self._interests_cache: Optional[List[InterestItem]] = None
        self._strengths_cache: Optional[List[StrengthItem]] = None
        self._questions_cache: Optional[List[QuestionItem]] = None
    
    def load_values(self, force_reload: bool = False) -> List[ValueItem]:
        """
        加载价值观数据
        
        Args:
            force_reload: 强制重新加载
        
        Returns:
            价值观列表
        """
        if self._values_cache is None or force_reload:
            values = []
            if not self.values_file.exists():
                raise FileNotFoundError(f"价值观文件不存在: {self.values_file}")
            
            with open(self.values_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    values.append(ValueItem(
                        id=int(row.get("id", 0)),
                        name=row.get("名称", "").strip(),
                        definition=row.get("定义", "").strip()
                    ))
            
            self._values_cache = values
        
        return self._values_cache
    
    def load_interests(self, force_reload: bool = False) -> List[InterestItem]:
        """
        加载兴趣数据
        
        Args:
            force_reload: 强制重新加载
        
        Returns:
            兴趣列表
        """
        if self._interests_cache is None or force_reload:
            interests = []
            if not self.interests_file.exists():
                raise FileNotFoundError(f"兴趣文件不存在: {self.interests_file}")
            
            with open(self.interests_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    interests.append(InterestItem(
                        id=int(row.get("id", 0)),
                        name=row.get("名称", "").strip()
                    ))
            
            self._interests_cache = interests
        
        return self._interests_cache
    
    def load_strengths(self, force_reload: bool = False) -> List[StrengthItem]:
        """
        加载才能数据
        
        Args:
            force_reload: 强制重新加载
        
        Returns:
            才能列表
        """
        if self._strengths_cache is None or force_reload:
            strengths = []
            if not self.strengths_file.exists():
                raise FileNotFoundError(f"才能文件不存在: {self.strengths_file}")
            
            with open(self.strengths_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    strengths.append(StrengthItem(
                        id=int(row.get("id", 0)),
                        name=row.get("名称", "").strip(),
                        strengths=row.get("优势", "").strip(),
                        weaknesses=row.get("劣势", "").strip()
                    ))
            
            self._strengths_cache = strengths
        
        return self._strengths_cache
    
    def load_questions(self, force_reload: bool = False) -> List[QuestionItem]:
        """
        加载问题数据（从question.md解析）
        
        Args:
            force_reload: 强制重新加载
        
        Returns:
            问题列表
        """
        if self._questions_cache is None or force_reload:
            questions = []
            if not self.questions_file.exists():
                raise FileNotFoundError(f"问题文件不存在: {self.questions_file}")
            
            with open(self.questions_file, "r", encoding="utf-8") as f:
                content = f.read()
            
            # 解析Markdown格式的问题
            current_category = None
            question_number = 0
            
            for line in content.split("\n"):
                line = line.strip()
                
                # 检测分类标题
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
                
                # 检测问题（以数字开头或包含⭐）
                elif line and current_category:
                    is_starred = "⭐" in line or "星号" in line
                    
                    # 移除星号和数字前缀
                    question_content = line
                    if question_content.startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.")):
                        parts = question_content.split(".", 1)
                        if len(parts) > 1:
                            question_content = parts[1].strip()
                    
                    # 移除星号标记
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
    
    def load_all(self, force_reload: bool = False) -> Dict[str, any]:
        """
        加载所有知识库数据
        
        Args:
            force_reload: 强制重新加载
        
        Returns:
            包含所有数据的字典
        """
        return {
            "values": self.load_values(force_reload),
            "interests": self.load_interests(force_reload),
            "strengths": self.load_strengths(force_reload),
            "questions": self.load_questions(force_reload)
        }
    
    def clear_cache(self):
        """清除缓存"""
        self._values_cache = None
        self._interests_cache = None
        self._strengths_cache = None
        self._questions_cache = None
