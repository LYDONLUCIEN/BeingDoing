"""
对话记录文件管理器
对话记录使用JSON文件存储，不存数据库表
"""
import json
import os
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from enum import Enum
import aiofiles


class ConversationCategory(str, Enum):
    """对话分类"""
    MAIN_FLOW = "main_flow"  # 主流程对话
    GUIDANCE = "guidance"  # 引导对话
    CLARIFICATION = "clarification"  # 澄清对话
    OTHER = "other"  # 其他对话


class ConversationFileManager:
    """对话记录文件管理器"""
    
    def __init__(self, base_dir: str = "data/conversations"):
        """
        初始化文件管理器
        
        Args:
            base_dir: 对话记录存储根目录
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_session_dir(self, session_id: str) -> Path:
        """获取会话目录"""
        session_dir = self.base_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir
    
    def _get_file_path(self, session_id: str, category: str) -> Path:
        """获取文件路径"""
        session_dir = self._get_session_dir(session_id)
        return session_dir / f"{category}.json"
    
    async def append_message(
        self,
        session_id: str,
        category: str,
        message: Dict
    ) -> Dict:
        """
        添加消息到对话记录（异步）
        
        Args:
            session_id: 会话ID
            category: 对话分类（字符串）
            message: 消息字典（必须包含role, content, created_at）
        
        Returns:
            添加的消息字典
        """
        file_path = self._get_file_path(session_id, category)
        
        # 确保消息包含created_at
        if "created_at" not in message:
            message["created_at"] = datetime.utcnow().isoformat() + "Z"
        
        try:
            # 读取现有文件
            async with aiofiles.open(file_path, mode='r', encoding='utf-8') as f:
                content = await f.read()
                data = json.loads(content)
        except FileNotFoundError:
            # 文件不存在，创建新文件
            data = {
                "session_id": session_id,
                "category": category,
                "messages": [],
                "metadata": {
                    "created_at": datetime.utcnow().isoformat() + "Z",
                    "updated_at": datetime.utcnow().isoformat() + "Z"
                }
            }
        except json.JSONDecodeError:
            # 文件损坏，重新创建
            data = {
                "session_id": session_id,
                "category": category,
                "messages": [],
                "metadata": {
                    "created_at": datetime.utcnow().isoformat() + "Z",
                    "updated_at": datetime.utcnow().isoformat() + "Z"
                }
            }
        
        # 添加消息ID（如果不存在）
        if "id" not in message:
            message["id"] = f"msg_{len(data.get('messages', [])) + 1}"
        
        # 添加消息
        if "messages" not in data:
            data["messages"] = []
        data["messages"].append(message)
        
        # 更新元数据
        data["metadata"]["updated_at"] = datetime.utcnow().isoformat() + "Z"
        data["metadata"]["total_messages"] = len(data["messages"])
        
        # 保存文件
        async with aiofiles.open(file_path, mode='w', encoding='utf-8') as f:
            await f.write(json.dumps(data, indent=2, ensure_ascii=False))
        
        return message
    
    async def get_messages(
        self,
        session_id: str,
        category: Optional[str] = None
    ) -> List[Dict]:
        """
        获取对话消息（异步）
        
        Args:
            session_id: 会话ID
            category: 对话分类，None表示获取所有分类
        
        Returns:
            消息列表
        """
        if category:
            file_path = self._get_file_path(session_id, category)
            try:
                async with aiofiles.open(file_path, mode='r', encoding='utf-8') as f:
                    content = await f.read()
                    data = json.loads(content)
                    return data.get("messages", [])
            except (FileNotFoundError, json.JSONDecodeError):
                return []
        else:
            # 获取所有分类的消息
            messages = []
            session_dir = self._get_session_dir(session_id)
            if session_dir.exists():
                for file_path in session_dir.glob("*.json"):
                    try:
                        async with aiofiles.open(file_path, mode='r', encoding='utf-8') as f:
                            content = await f.read()
                            data = json.loads(content)
                            messages.extend(data.get("messages", []))
                    except (FileNotFoundError, json.JSONDecodeError):
                        continue
            
            # 按时间排序
            messages.sort(key=lambda x: x.get("created_at", ""))
            return messages
    
    async def get_all_conversations(
        self,
        session_id: str
    ) -> Dict[str, List[Dict]]:
        """
        获取所有分类的对话（异步）
        
        Args:
            session_id: 会话ID
        
        Returns:
            按分类组织的对话字典
        """
        result = {}
        session_dir = self._get_session_dir(session_id)
        
        if session_dir.exists():
            for file_path in session_dir.glob("*.json"):
                category = file_path.stem  # 文件名（不含扩展名）
                try:
                    async with aiofiles.open(file_path, mode='r', encoding='utf-8') as f:
                        content = await f.read()
                        data = json.loads(content)
                        result[category] = data.get("messages", [])
                except (FileNotFoundError, json.JSONDecodeError):
                    result[category] = []
        
        return result
    
    async def delete_session(self, session_id: str):
        """删除会话的所有对话记录（异步）"""
        session_dir = self._get_session_dir(session_id)
        if session_dir.exists():
            import shutil
            shutil.rmtree(session_dir)
