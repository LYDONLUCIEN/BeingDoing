"""
导出服务
"""
from typing import Dict, List, Optional
from datetime import datetime
import json
from pathlib import Path
from app.core.database import UserDB, HistoryDB
from app.models.database import AsyncSessionLocal
from app.utils.conversation_file_manager import ConversationFileManager
from app.core.knowledge import KnowledgeLoader
from app.domain.knowledge_config import get_knowledge_config


class ExportService:
    """导出服务"""
    
    def __init__(self):
        """初始化导出服务"""
        self.conversation_manager = ConversationFileManager()
        self.knowledge_loader = KnowledgeLoader(config=get_knowledge_config())
    
    async def collect_export_data(
        self,
        user_id: str,
        session_id: str
    ) -> Dict:
        """
        收集导出数据
        
        Args:
            user_id: 用户ID
            session_id: 会话ID
        
        Returns:
            导出数据字典
        """
        async with AsyncSessionLocal() as db:
            user_db = UserDB(db)
            history_db = HistoryDB(db)
            
            # 获取用户信息
            user = await user_db.get_user_by_id(user_id)
            profile = await user_db.get_user_profile(user_id)
            work_histories = await user_db.get_user_work_histories(user_id)
            
            # 获取会话信息
            session = await history_db.get_session(session_id)
            
            # 获取回答
            answers = await history_db.get_session_answers(session_id)
            
            # 获取进度
            progresses = await history_db.get_session_progresses(session_id)
            
            # 获取用户选择
            from app.models.selection import UserSelection, ExplorationResult
            result = await db.execute(
                select(UserSelection).where(UserSelection.session_id == session_id)
            )
            selections = result.scalars().all()
            
            result = await db.execute(
                select(ExplorationResult).where(ExplorationResult.session_id == session_id)
            )
            exploration_result = result.scalar_one_or_none()
            
            # 获取对话历史
            conversation_history = await self.conversation_manager.get_all_conversations(session_id)
            
            # 构建导出数据
            export_data = {
                "export_time": datetime.utcnow().isoformat(),
                "user": {
                    "user_id": user.id if user else None,
                    "email": user.email if user else None,
                    "username": user.username if user else None,
                    "gender": profile.gender if profile else None,
                    "age": profile.age if profile else None
                },
                "session": {
                    "session_id": session.id if session else None,
                    "current_step": session.current_step if session else None,
                    "status": session.status if session else None,
                    "created_at": str(session.created_at) if session else None
                },
                "work_histories": [
                    {
                        "company": wh.company,
                        "position": wh.position,
                        "start_date": str(wh.start_date) if wh.start_date else None,
                        "end_date": str(wh.end_date) if wh.end_date else None,
                        "evaluation": wh.evaluation
                    }
                    for wh in work_histories
                ],
                "answers": [
                    {
                        "category": a.category,
                        "content": a.content,
                        "created_at": str(a.created_at)
                    }
                    for a in answers
                ],
                "progress": [
                    {
                        "step": p.step,
                        "completed_count": p.completed_count,
                        "total_count": p.total_count,
                        "percentage": int((p.completed_count / p.total_count * 100)) if p.total_count > 0 else 0
                    }
                    for p in progresses
                ],
                "selections": [
                    {
                        "category": s.category,
                        "selected_items": json.loads(s.selected_items) if s.selected_items else []
                    }
                    for s in selections
                ],
                "exploration_result": {
                    "values_selected": json.loads(exploration_result.values_selected) if exploration_result and exploration_result.values_selected else [],
                    "strengths_selected": json.loads(exploration_result.strengths_selected) if exploration_result and exploration_result.strengths_selected else [],
                    "interests_selected": json.loads(exploration_result.interests_selected) if exploration_result and exploration_result.interests_selected else [],
                    "wanted_thing": exploration_result.wanted_thing if exploration_result else None,
                    "true_wanted_thing": exploration_result.true_wanted_thing if exploration_result else None
                } if exploration_result else {},
                "conversation_history": conversation_history_dict
            }
            
            return export_data
    
    def export_to_json(self, data: Dict, output_path: str) -> str:
        """
        导出为JSON格式
        
        Args:
            data: 导出数据
            output_path: 输出文件路径
        
        Returns:
            输出文件路径
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return str(output_file)
    
    def export_to_markdown(self, data: Dict, output_path: str) -> str:
        """
        导出为Markdown格式
        
        Args:
            data: 导出数据
            output_path: 输出文件路径
        
        Returns:
            输出文件路径
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        md_content = f"""# 职业规划探索结果

导出时间：{data.get('export_time', '')}

## 用户信息

- 用户ID：{data.get('user', {}).get('user_id', '')}
- 邮箱：{data.get('user', {}).get('email', '')}
- 用户名：{data.get('user', {}).get('username', '')}
- 性别：{data.get('user', {}).get('gender', '')}
- 年龄：{data.get('user', {}).get('age', '')}

## 工作履历

"""
        
        for wh in data.get('work_histories', []):
            md_content += f"""### {wh.get('company', '')} - {wh.get('position', '')}

- 时间：{wh.get('start_date', '')} 至 {wh.get('end_date', '当前')}
- 评价：{wh.get('evaluation', '')}

"""
        
        md_content += """## 探索回答

"""
        
        for answer in data.get('answers', []):
            md_content += f"""### {answer.get('category', '')}

{answer.get('content', '')}

"""
        
        md_content += """## 探索结果

"""
        
        result = data.get('exploration_result', {})
        if result:
            md_content += f"""### 价值观选择

{', '.join(result.get('values_selected', []))}

### 才能选择

{', '.join(result.get('strengths_selected', []))}

### 兴趣选择

{', '.join(result.get('interests_selected', []))}

### 想做的事

{result.get('wanted_thing', '')}

### 真正想做的事

{result.get('true_wanted_thing', '')}

"""
        
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(md_content)
        
        return str(output_file)
    
    def export_to_pdf(self, data: Dict, output_path: str) -> str:
        """
        导出为PDF格式
        
        Args:
            data: 导出数据
            output_path: 输出文件路径
        
        Returns:
            输出文件路径
        
        Note:
            需要安装 reportlab 或 weasyprint
        """
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import inch
            
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            doc = SimpleDocTemplate(str(output_file), pagesize=A4)
            styles = getSampleStyleSheet()
            story = []
            
            # 标题
            story.append(Paragraph("职业规划探索结果", styles['Title']))
            story.append(Spacer(1, 0.2*inch))
            
            # 用户信息
            story.append(Paragraph("用户信息", styles['Heading1']))
            user = data.get('user', {})
            story.append(Paragraph(f"用户ID: {user.get('user_id', '')}", styles['Normal']))
            story.append(Paragraph(f"邮箱: {user.get('email', '')}", styles['Normal']))
            story.append(Spacer(1, 0.1*inch))
            
            # 探索结果
            story.append(Paragraph("探索结果", styles['Heading1']))
            result = data.get('exploration_result', {})
            if result:
                story.append(Paragraph(f"想做的事: {result.get('wanted_thing', '')}", styles['Normal']))
                story.append(Paragraph(f"真正想做的事: {result.get('true_wanted_thing', '')}", styles['Normal']))
            
            doc.build(story)
            return str(output_file)
        
        except ImportError:
            # 如果没有安装reportlab，先导出为Markdown，然后提示用户
            md_path = output_path.replace('.pdf', '.md')
            self.export_to_markdown(data, md_path)
            raise ImportError("PDF导出需要安装reportlab: pip install reportlab")
