"""
题目进度管理：跟踪每个步骤中的题目完成情况
"""
from typing import Dict, List, Optional
from pydantic import BaseModel


class QuestionProgress(BaseModel):
    """单个题目的进度"""
    question_id: int
    question_content: str
    status: str  # 'not_started', 'in_progress', 'completed'
    turn_count: int = 0  # 当前题目的对话轮数
    user_answer: Optional[str] = None  # 用户的最终答案（AI判断充分后提取）


class StepProgress(BaseModel):
    """单个步骤的进度"""
    step_id: str
    category: str  # values/strengths/interests
    questions: List[QuestionProgress]
    current_question_index: int = 0  # 当前正在回答的题目索引
    is_intro_shown: bool = False  # 是否已展示步骤介绍


    @property
    def current_question(self) -> Optional[QuestionProgress]:
        """获取当前题目"""
        if 0 <= self.current_question_index < len(self.questions):
            return self.questions[self.current_question_index]
        return None

    @property
    def is_completed(self) -> bool:
        """判断步骤是否完成"""
        return all(q.status == 'completed' for q in self.questions)

    def move_to_next_question(self) -> bool:
        """移动到下一题，返回是否成功"""
        if self.current_question_index < len(self.questions) - 1:
            self.current_question_index += 1
            return True
        return False


class ProgressManager:
    """
    进度管理器：管理session的题目进度
    存储在session的metadata中，格式：
    {
        "question_progress": {
            "values_exploration": StepProgress.model_dump(),
            "strengths_exploration": StepProgress.model_dump(),
            ...
        }
    }
    """

    @staticmethod
    def initialize_step_progress(step_id: str, category: str, questions: List[Dict]) -> StepProgress:
        """初始化步骤进度"""
        question_progresses = [
            QuestionProgress(
                question_id=q['id'],
                question_content=q['content'],
                status='not_started'
            )
            for q in questions
        ]

        return StepProgress(
            step_id=step_id,
            category=category,
            questions=question_progresses,
            current_question_index=0,
            is_intro_shown=False
        )

    @staticmethod
    def load_from_metadata(metadata: Dict, step_id: str) -> Optional[StepProgress]:
        """从session metadata加载进度"""
        if not metadata or 'question_progress' not in metadata:
            return None

        step_data = metadata['question_progress'].get(step_id)
        if not step_data:
            return None

        return StepProgress(**step_data)

    @staticmethod
    def save_to_metadata(metadata: Dict, step_progress: StepProgress) -> Dict:
        """保存进度到metadata"""
        if 'question_progress' not in metadata:
            metadata['question_progress'] = {}

        metadata['question_progress'][step_progress.step_id] = step_progress.model_dump()
        return metadata
