"""
增强的对话文件管理器 - 支持三种对话分类

1. all_flow.json - 完整对话（原文 + AI 思考过程）
2. main_flow.json - 用户可见的咨询对话
3. note.json - AI 总结的结论性内容

存储结构：
data/conversations/
    {session_id}/
        ├── all_flow.json      # 完整对话（原文 + AI 思考）
        ├── main_flow.json    # 用户可见的咨询对话（现有 main_flow）
        └── note.json        # AI 总结的结论性内容
"""
import json
import os
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime
from enum import Enum
import aiofiles


class ConversationCategoryType(str, Enum):
    """对话分类类型"""
    ALL_FLOW = "all_flow"      # 完整对话（原文 + AI 思考过程）
    MAIN_FLOW = "main_flow"    # 用户可见的咨询对话
    NOTE = "note"              # AI 总结的结论性内容


class EnhancedConversationFileManager:
    """增强的对话文件管理器"""

    def __init__(self, base_dir: str = "data/conversations"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_session_dir(self, session_id: str) -> Path:
        """获取会话目录"""
        session_dir = self.base_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir

    def _get_file_path(self, session_id: str, category: ConversationCategoryType) -> Path:
        """获取文件路径"""
        session_dir = self._get_session_dir(session_id)
        return session_dir / category.value

    async def append_to_flow(
        self,
        session_id: str,
        message: Dict,
        category: ConversationCategoryType = ConversationCategoryType.ALL_FLOW
    ) -> Dict:
        """
        添加消息到指定流程

        Args:
            session_id: 会话 ID
            message: 消息字典（必须包含 role, content）
            category: 对话分类

        Returns:
            添加的消息字典
        """
        file_path = self._get_file_path(session_id, category)

        # 确保消息包含必要字段
        if "id" not in message:
            message["id"] = f"msg_{datetime.utcnow().timestamp()}"
        if "created_at" not in message:
            message["created_at"] = datetime.utcnow().isoformat() + "Z"

        try:
            # 读取现有文件
            if file_path.exists():
                async with aiofiles.open(file_path, mode='r', encoding='utf-8') as f:
                    content = await f.read()
                data = json.loads(content)
            else:
                # 创建新文件结构
                data = {
                    "session_id": session_id,
                    "category": category.value,
                    "messages": [],
                    "metadata": {
                        "created_at": message["created_at"],
                        "updated_at": message["created_at"],
                        "total_messages": 0
                    }
                }
        except (FileNotFoundError, json.JSONDecodeError):
            # 文件不存在或损坏，创建新结构
            data = {
                "session_id": session_id,
                "category": category.value,
                "messages": [],
                "metadata": {
                    "created_at": message["created_at"],
                    "updated_at": message["created_at"],
                    "total_messages": 0
                }
            }

        # 添加消息
        data["messages"].append(message)
        data["metadata"]["updated_at"] = message["created_at"]
        data["metadata"]["total_messages"] = len(data["messages"])

        # 保存文件
        async with aiofiles.open(file_path, mode='w', encoding='utf-8') as f:
            await f.write(json.dumps(data, indent=2, ensure_ascii=False))

        return message

    async def append_all_flow_message(
        self,
        session_id: str,
        role: str,
        content: str,
        message_type: str,  # "user_input", "ai_thinking", "ai_response"
        metadata: Optional[Dict] = None
    ) -> Dict:
        """
        添加完整流程消息（原文 + AI 思考）

        Args:
            session_id: 会话 ID
            role: 角色（user/assistant/system）
            content: 内容
            message_type: 消息类型（user_input/ai_thinking/ai_response）
            metadata: 额外元数据

        Returns:
            添加的消息字典
        """
        message = {
            "role": role,
            "content": content,
            "type": message_type,
            "created_at": datetime.utcnow().isoformat() + "Z"
        }

        if metadata:
            message["metadata"] = metadata

        return await self.append_to_flow(
            session_id=session_id,
            message=message,
            category=ConversationCategoryType.ALL_FLOW
        )

    async def append_main_flow_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict] = None
    ) -> Dict:
        """
        添加主流程消息（用户可见的咨询对话）

        这是用户在界面上看到的对话，是经过处理的"友好版本"
        """
        message = {
            "role": role,
            "content": content,
            "created_at": datetime.utcnow().isoformat() + "Z"
        }

        if metadata:
            message["metadata"] = metadata

        return await self.append_to_flow(
            session_id=session_id,
            message=message,
            category=ConversationCategoryType.MAIN_FLOW
        )

    async def save_note(
        self,
        session_id: str,
        note_content: str,
        note_type: str = "summary",  # summary, conclusion, insight
        metadata: Optional[Dict] = None
    ):
        """
        保存或追加到 note.json（AI 总结的结论性内容）

        Args:
            session_id: 会话 ID
            note_content: 笔记内容
            note_type: 笔记类型
            metadata: 额外元数据
        """
        file_path = self._get_file_path(session_id, ConversationCategoryType.NOTE)

        # 读取现有笔记
        existing_notes = []
        if file_path.exists():
            async with aiofiles.open(file_path, mode='r', encoding='utf-8') as f:
                content = await f.read()
                data = json.loads(content)
                existing_notes = data.get("notes", [])
        else:
            # 创建新笔记文件
            data = {
                "session_id": session_id,
                "created_at": datetime.utcnow().isoformat() + "Z",
                "updated_at": datetime.utcnow().isoformat() + "Z",
                "notes": []
            }

        # 添加新笔记
        note_entry = {
            "id": f"note_{len(existing_notes) + 1}",
            "type": note_type,
            "content": note_content,
            "created_at": datetime.utcnow().isoformat() + "Z"
        }

        if metadata:
            note_entry["metadata"] = metadata

        existing_notes.append(note_entry)
        data["notes"] = existing_notes
        data["updated_at"] = datetime.utcnow().isoformat() + "Z"

        # 保存
        async with aiofiles.open(file_path, mode='w', encoding='utf-8') as f:
            await f.write(json.dumps(data, indent=2, ensure_ascii=False))

    async def get_all_flow_messages(
        self,
        session_id: str,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """获取完整流程消息（原文 + AI 思考）"""
        file_path = self._get_file_path(session_id, ConversationCategoryType.ALL_FLOW)
        try:
            async with aiofiles.open(file_path, mode='r', encoding='utf-8') as f:
                content = await f.read()
                data = json.loads(content)
                messages = data.get("messages", [])
                if limit:
                    return messages[-limit:]
                return messages
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    async def get_main_flow_messages(
        self,
        session_id: str,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """获取主流程消息（用户可见的咨询对话）"""
        file_path = self._get_file_path(session_id, ConversationCategoryType.MAIN_FLOW)
        try:
            async with aiofiles.open(file_path, mode='r', encoding='utf-8') as f:
                content = await f.read()
                data = json.loads(content)
                messages = data.get("messages", [])
                if limit:
                    return messages[-limit:]
                return messages
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    async def get_notes(
        self,
        session_id: str
    ) -> List[Dict]:
        """获取笔记内容"""
        file_path = self._get_file_path(session_id, ConversationCategoryType.NOTE)
        try:
            async with aiofiles.open(file_path, mode='r', encoding='utf-8') as f:
                content = await f.read()
                data = json.loads(content)
                return data.get("notes", [])
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    async def save_answer_card(
        self,
        session_id: str,
        answer_card: Dict,
    ):
        """
        保存 Answer Card 到 note.json

        Args:
            session_id: 会话 ID
            answer_card: Answer Card 数据，包含：
                - question_id: 题目 ID
                - question_content: 题目内容
                - user_answer: 用户回答
                - ai_summary: AI 总结
                - ai_analysis: AI 分析
                - key_insights: 关键洞察
                - current_step: 当前步骤
        """
        file_path = self._get_file_path(session_id, ConversationCategoryType.NOTE)

        # 读取现有笔记
        existing_notes = []
        if file_path.exists():
            async with aiofiles.open(file_path, mode='r', encoding='utf-8') as f:
                content = await f.read()
                data = json.loads(content)
                existing_notes = data.get("notes", [])
        else:
            # 创建新笔记文件
            data = {
                "session_id": session_id,
                "created_at": datetime.utcnow().isoformat() + "Z",
                "updated_at": datetime.utcnow().isoformat() + "Z",
                "notes": []
            }

        # 查找是否已存在该题目的 answer_card，存在则更新
        question_id = answer_card.get("question_id")
        answer_card_note = {
            "id": f"answer_card_{question_id}",
            "type": "answer_card",
            "content": json.dumps(answer_card, ensure_ascii=False),
            "created_at": datetime.utcnow().isoformat() + "Z",
            "metadata": {
                "question_id": question_id,
                "current_step": answer_card.get("current_step"),
            }
        }

        # 移除旧的同一题目 answer_card（如果有）
        existing_notes = [n for n in existing_notes if not (
            n.get("type") == "answer_card" and
            n.get("metadata", {}).get("question_id") == question_id
        )]

        # 添加新的 answer_card
        existing_notes.append(answer_card_note)
        data["notes"] = existing_notes
        data["updated_at"] = datetime.utcnow().isoformat() + "Z"

        # 保存
        async with aiofiles.open(file_path, mode='w', encoding='utf-8') as f:
            await f.write(json.dumps(data, indent=2, ensure_ascii=False))

    async def get_answer_cards(
        self,
        session_id: str,
    ) -> List[Dict]:
        """
        获取所有 Answer Cards

        Returns:
            Answer Card 列表，按创建时间排序
        """
        notes = await self.get_notes(session_id)
        answer_cards = []

        for note in notes:
            if note.get("type") == "answer_card":
                try:
                    content = json.loads(note.get("content", "{}"))
                    answer_cards.append({
                        **content,
                        "created_at": note.get("created_at"),
                        "note_id": note.get("id")
                    })
                except json.JSONDecodeError:
                    continue

        # 按题目 ID 排序
        answer_cards.sort(key=lambda x: x.get("question_id", 0))
        return answer_cards

    async def get_compressed_context(
        self,
        session_id: str,
        max_rounds: int = 5,
        keep_latest: int = 3,
        include_all_flow: bool = True
    ) -> Dict[str, Any]:
        """
        获取压缩后的上下文（用于 LLM）

        压缩策略：
        1. 如果对话轮数 <= max_rounds，返回全部
        2. 如果超过，保留最近 keep_latest 轮的对话 + 更早的摘要

        Args:
            session_id: 会话 ID
            max_rounds: 最大轮数阈值
            keep_latest: 超过阈值后保留的最新轮数
            include_all_flow: 是否包含 all_flow（AI 思考过程）

        Returns:
            压缩后的上下文字典
        """
        # 获取主流程消息
        main_messages = await self.get_main_flow_messages(session_id)

        # 计算对话轮数（用户消息数）
        user_messages = [m for m in main_messages if m.get("role") == "user"]
        round_count = len(user_messages)

        if round_count <= max_rounds:
            # 未超过阈值，返回全部
            context_messages = main_messages
            was_compressed = False
        else:
            # 超过阈值，需要压缩
            was_compressed = True

            # 保留最新的 keep_latest 轮对话
            # 计算需要保留的消息数
            if round_count > keep_latest:
                # 找到第 (round_count - keep_latest) 条用户消息的位置
                cutoff_index = round_count - keep_latest
                cutoff_user_msg = user_messages[cutoff_index]
                # 找到这条消息在原数组中的位置
                cutoff_idx = main_messages.index(cutoff_user_msg)
                context_messages = main_messages[cutoff_idx + 1:]
            else:
                context_messages = main_messages[-keep_latest * 2:]  # 保留最近几轮

        # 构建 LLM 消息列表
        llm_messages = []
        for msg in context_messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ["user", "assistant"] and content:
                llm_messages.append({
                    "role": role,
                    "content": content
                })

        # 可选：包含 all_flow（AI 思考过程）
        all_flow_messages = []
        if include_all_flow:
            all_flow_raw = await self.get_all_flow_messages(session_id)
            # 将 all_flow 转换为思考过程格式
            for msg in all_flow_raw:
                if msg.get("type") == "ai_thinking":
                    all_flow_messages.append({
                        "role": "system",
                        "content": f"[AI 思考过程] {msg.get('content', '')}"
                    })

        return {
            "session_id": session_id,
            "round_count": round_count,
            "was_compressed": was_compressed,
            "messages": llm_messages,
            "all_flow_messages": all_flow_messages if include_all_flow else [],
            "context_summary": f"当前对话共 {round_count} 轮，" + (
                f"已压缩，保留最近 {keep_latest} 轮" if was_compressed else "未压缩"
            )
        }


# 保持向后兼容的旧接口
class ConversationCategory(str, Enum):
    """旧的对话分类（保持兼容）"""
    MAIN_FLOW = "main_flow"
    GUIDANCE = "guidance"
    CLARIFICATION = "clarification"
    OTHER = "other"


class ConversationFileManager:
    """旧的文件管理器（保持向后兼容）"""

    def __init__(self, base_dir: str = "data/conversations"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._enhanced = EnhancedConversationFileManager(base_dir)

    def _get_session_dir(self, session_id: str) -> Path:
        session_dir = self.base_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir

    def _get_file_path(self, session_id: str, category: str) -> Path:
        session_dir = self._get_session_dir(session_id)
        return session_dir / f"{category}.json"

    async def append_message(
        self,
        session_id: str,
        category: str,
        message: Dict
    ) -> Dict:
        """添加消息（向后兼容接口，路由到 main_flow）"""
        # 如果使用旧接口，默认写入 main_flow
        return await self._enhanced.append_to_flow(
            session_id=session_id,
            message=message,
            category=ConversationCategoryType.MAIN_FLOW
        )

    async def get_messages(
        self,
        session_id: str,
        category: Optional[str] = None
    ) -> List[Dict]:
        """获取消息（向后兼容接口）"""
        if category is None or category == "main_flow":
            return await self._enhanced.get_main_flow_messages(session_id)
        else:
            # 其他类别暂不支持，返回空
            return []

    async def get_all_conversations(
        self,
        session_id: str
    ) -> Dict[str, List[Dict]]:
        """获取所有分类的对话（向后兼容接口）"""
        result = {
            "main_flow": await self._enhanced.get_main_flow_messages(session_id),
            "all_flow": await self._enhanced.get_all_flow_messages(session_id),
            "note": [],  # 需要从 note.json 读取
        }

        # 读取笔记
        note_path = self._enhanced._get_file_path(session_id, ConversationCategoryType.NOTE)
        if note_path.exists():
            async with aiofiles.open(note_path, mode='r', encoding='utf-8') as f:
                content = await f.read()
                data = json.loads(content)
                result["note"] = data.get("notes", [])

        return result
