"""
对话记录文件管理器
对话记录使用JSON文件存储，不存数据库表

并发：按 (report_id, category) 即按文件加锁，避免同一 thread 多请求并发写导致消息丢失。
"""
import asyncio
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime
from enum import Enum
import aiofiles
from filelock import FileLock

from app.utils.data_paths import get_conversation_dir


class ConversationCategory(str, Enum):
    """对话分类"""
    MAIN_FLOW = "main_flow"  # 主流程对话
    GUIDANCE = "guidance"  # 引导对话
    CLARIFICATION = "clarification"  # 澄清对话
    OTHER = "other"  # 其他对话


class ConversationFileManager:
    """对话记录文件管理器"""
    
    def __init__(self, base_dir: Optional[str] = None):
        """
        初始化文件管理器
        
        Args:
            base_dir: 对话记录存储根目录，None 则使用项目根 data/conversations
        """
        self.base_dir = Path(base_dir) if base_dir else get_conversation_dir()
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

    def _get_lock_path(self, file_path: Path) -> Path:
        """锁文件路径（与数据文件同目录）"""
        return file_path.with_suffix(file_path.suffix + ".lock")

    async def _with_file_lock(
        self,
        session_id: str,
        category: str,
        fn: Callable[[Path], Any],
    ) -> Any:
        """
        在文件锁保护下执行 fn(file_path)。
        锁粒度：按 (session_id, category) 即按文件，不同 report/thread 互不阻塞。
        """
        file_path = self._get_file_path(session_id, category)
        lock_path = self._get_lock_path(file_path)
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        def _do():
            file_lock = FileLock(str(lock_path), timeout=30)
            with file_lock:
                return fn(file_path)

        return await asyncio.to_thread(_do)

    async def append_message(
        self,
        session_id: str,
        category: str,
        message: Dict
    ) -> Dict:
        """
        添加消息到对话记录（异步）。使用文件锁保证同一 thread 并发写不丢失。
        """
        if "created_at" not in message:
            message["created_at"] = datetime.utcnow().isoformat() + "Z"

        def _do_append(fp: Path) -> Dict:
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except FileNotFoundError:
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
                data = {
                    "session_id": session_id,
                    "category": category,
                    "messages": [],
                    "metadata": {
                        "created_at": datetime.utcnow().isoformat() + "Z",
                        "updated_at": datetime.utcnow().isoformat() + "Z"
                    }
                }

            if "message_id" not in message:
                message["message_id"] = f"msg_{len(data.get('messages', [])) + 1}"
            if "id" not in message or not message.get("id"):
                message["id"] = message["message_id"]
            if "agent_id" not in message:
                message["agent_id"] = "coach" if message.get("role") == "assistant" else None
            if "event" not in message:
                message["event"] = "assistant_reply" if message.get("role") == "assistant" else "user_message"

            if "messages" not in data:
                data["messages"] = []
            data["messages"].append(message)
            data["metadata"]["updated_at"] = datetime.utcnow().isoformat() + "Z"
            data["metadata"]["total_messages"] = len(data["messages"])

            fp.parent.mkdir(parents=True, exist_ok=True)
            with open(fp, "w", encoding="utf-8") as f:
                f.write(json.dumps(data, indent=2, ensure_ascii=False))
            return message

        return await self._with_file_lock(session_id, category, _do_append)
    
    async def get_conversation_data(
        self,
        session_id: str,
        category: str,
    ) -> Dict:
        """
        获取对话完整数据（messages + metadata），用于读写元数据。
        """
        file_path = self._get_file_path(session_id, category)
        try:
            async with aiofiles.open(file_path, mode='r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content)
        except (FileNotFoundError, json.JSONDecodeError):
            return {
                "session_id": session_id,
                "category": category,
                "messages": [],
                "metadata": {
                    "created_at": datetime.utcnow().isoformat() + "Z",
                    "updated_at": datetime.utcnow().isoformat() + "Z",
                },
            }

    async def update_metadata(
        self,
        session_id: str,
        category: str,
        updates: Dict,
    ) -> None:
        """更新指定对话的 metadata，合并 updates 到现有 metadata。使用文件锁。"""

        def _do_update(fp: Path) -> None:
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                return
            meta = data.setdefault("metadata", {})
            meta.update(updates)
            meta["updated_at"] = datetime.utcnow().isoformat() + "Z"
            fp.parent.mkdir(parents=True, exist_ok=True)
            with open(fp, "w", encoding="utf-8") as f:
                f.write(json.dumps(data, indent=2, ensure_ascii=False))

        await self._with_file_lock(session_id, category, _do_update)

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
