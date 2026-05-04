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
from app.utils.id_codec import IDCodec


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
                result = fn(file_path)
            # 释放锁后清理 lock 文件，避免磁盘残留
            try:
                lock_path.unlink(missing_ok=True)
            except OSError:
                pass
            return result

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
                    **IDCodec.build_conversation_file_root_ids(session_id),
                    "category": category,
                    "messages": [],
                    "metadata": {
                        "created_at": datetime.utcnow().isoformat() + "Z",
                        "updated_at": datetime.utcnow().isoformat() + "Z"
                    }
                }
            except json.JSONDecodeError:
                data = {
                    **IDCodec.build_conversation_file_root_ids(session_id),
                    "category": category,
                    "messages": [],
                    "metadata": {
                        "created_at": datetime.utcnow().isoformat() + "Z",
                        "updated_at": datetime.utcnow().isoformat() + "Z"
                    }
                }
            else:
                data = IDCodec.normalize_conversation_data_on_read(data, session_id)

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
                raw = json.loads(content)
                return IDCodec.normalize_conversation_data_on_read(raw, session_id)
        except (FileNotFoundError, json.JSONDecodeError, OSError, IOError):
            return {
                **IDCodec.build_conversation_file_root_ids(session_id),
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

    async def update_last_conclusion_card_payload(
        self,
        session_id: str,
        category: str,
        card_payload: Dict[str, Any],
    ) -> bool:
        """将文件中最后一条 conclusion_card 的 content / card_payload 更新为最终结论。不存在则返回 False。"""

        def _do(fp: Path) -> bool:
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                return False
            msgs = data.get("messages") or []
            for i in range(len(msgs) - 1, -1, -1):
                if (msgs[i] or {}).get("role") != "conclusion_card":
                    continue
                js = json.dumps(card_payload, ensure_ascii=False)
                msgs[i]["content"] = js
                msgs[i]["card_payload"] = card_payload
                data["messages"] = msgs
                meta = data.setdefault("metadata", {})
                meta["updated_at"] = datetime.utcnow().isoformat() + "Z"
                meta["total_messages"] = len(msgs)
                with open(fp, "w", encoding="utf-8") as f:
                    f.write(json.dumps(data, indent=2, ensure_ascii=False))
                return True
            return False

        return bool(await self._with_file_lock(session_id, category, _do))

    async def remove_last_conclusion_card(self, session_id: str, category: str) -> bool:
        """删除文件中最后一条 conclusion_card（用户否定待确认结论时使用）。"""

        def _do(fp: Path) -> bool:
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                return False
            msgs = data.get("messages") or []
            for i in range(len(msgs) - 1, -1, -1):
                if (msgs[i] or {}).get("role") != "conclusion_card":
                    continue
                del msgs[i]
                data["messages"] = msgs
                meta = data.setdefault("metadata", {})
                meta["updated_at"] = datetime.utcnow().isoformat() + "Z"
                meta["total_messages"] = len(msgs)
                with open(fp, "w", encoding="utf-8") as f:
                    f.write(json.dumps(data, indent=2, ensure_ascii=False))
                return True
            return False

        return bool(await self._with_file_lock(session_id, category, _do))

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
                    data = IDCodec.normalize_conversation_data_on_read(json.loads(content), session_id)
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
                            data = IDCodec.normalize_conversation_data_on_read(json.loads(content), session_id)
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
                        data = IDCodec.normalize_conversation_data_on_read(json.loads(content), session_id)
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

    async def delete_messages_from_filter_step(
        self,
        session_id: str,
        category: str,
        from_step: int,
    ) -> int:
        """删除对话文件中 filter_step >= from_step 的消息及其之后的全部消息（含 filter_step=None 的引导文案）。

        保留 event=init_rumination_intro 的消息（开场白）。

        用于 rumination 阶段「重新填写」时从某子步起重置对话。

        Returns:
            删除的消息条数。
        """
        def _do(fp: Path) -> int:
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                return 0
            msgs = data.get("messages") or []
            before = len(msgs)

            # 找到第一条 filter_step >= from_step 的消息位置
            cut_idx = len(msgs)
            for i, m in enumerate(msgs):
                if not isinstance(m, dict):
                    continue
                fs = m.get("filter_step")
                if fs is not None and int(fs) >= from_step:
                    cut_idx = i
                    break

            # 从 cut_idx 开始删除，但保留 init_rumination_intro
            if cut_idx < len(msgs):
                kept = msgs[:cut_idx]
                for m in msgs[cut_idx:]:
                    if isinstance(m, dict) and m.get("event") == "init_rumination_intro":
                        kept.append(m)
                data["messages"] = kept
            else:
                # 没有找到 filter_step >= from_step 的消息，仅按旧逻辑过滤
                data["messages"] = [
                    m for m in msgs
                    if not isinstance(m, dict) or int(m.get("filter_step") or 0) < from_step
                ]

            deleted = before - len(data["messages"])
            # 清除 metadata 中 step_anchor_N 条目（N >= from_step）
            meta = data.setdefault("metadata", {})
            keys_to_remove = [k for k in meta if k.startswith("step_anchor_") and k[len("step_anchor_"):].isdigit() and int(k[len("step_anchor_"):]) >= from_step]
            for k in keys_to_remove:
                del meta[k]
            meta["updated_at"] = datetime.utcnow().isoformat() + "Z"
            meta["total_messages"] = len(data["messages"])
            fp.parent.mkdir(parents=True, exist_ok=True)
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return deleted

        return await self._with_file_lock(session_id, category, _do)
