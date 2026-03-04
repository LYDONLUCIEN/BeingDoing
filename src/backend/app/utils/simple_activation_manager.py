"""
简单激活码管理器（不依赖数据库，使用文件持久化）

用于「简单对话模式」：
- 通过激活码识别一个简单会话
- 每个激活码对应一个 session_id，用于对话文件管理
- 记录创建时间 / 过期时间 / 模式（values / strengths / interests_goals / combined）

注意：
- 激活码过期后，历史文件仍然保留在 data/simple 下
- activations.json 只作为索引，方便通过 code 找到 session_id 等元信息
"""

import json
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, Optional


class ActivationStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


@dataclass
class ActivationRecord:
    code: str
    session_id: str
    mode: str
    created_at: str
    expires_at: str
    last_activity_at: str
    status: str = ActivationStatus.ACTIVE


def get_simple_base_dir() -> Path:
    """使用项目根目录下的 data/simple，避免依赖当前工作目录。供激活码、对话、调研等统一使用。"""
    project_root = Path(__file__).resolve().parents[4]
    return project_root / "data" / "simple"


def _default_base_dir() -> Path:
    return get_simple_base_dir()


class SimpleActivationManager:
    """简单激活码会话管理器（文件存储实现）"""

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir) if base_dir else _default_base_dir()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._activations_file = self.base_dir / "activations.json"

    def _load_all(self) -> Dict[str, ActivationRecord]:
        if not self._activations_file.exists():
            return {}
        try:
            content = self._activations_file.read_text(encoding="utf-8")
            raw = json.loads(content or "{}")
        except (json.JSONDecodeError, OSError):
            raw = {}
        records: Dict[str, ActivationRecord] = {}
        for code, data in raw.items():
            try:
                records[code] = ActivationRecord(**data)
            except TypeError:
                continue
        return records

    def _save_all(self, records: Dict[str, ActivationRecord]) -> None:
        serializable = {code: asdict(rec) for code, rec in records.items()}
        self._activations_file.write_text(
            json.dumps(serializable, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def create_activation(
        self,
        mode: str,
        ttl_minutes: int = 60,
    ) -> ActivationRecord:
        """
        创建一个新的激活会话

        Returns:
            ActivationRecord
        """
        records = self._load_all()

        # 简单生成一个 10 位激活码（大写字母+数字）
        import random
        import string

        alphabet = string.ascii_uppercase + string.digits
        while True:
            code = "".join(random.choices(alphabet, k=10))
            if code not in records:
                break

        session_id = str(uuid.uuid4())
        now = datetime.utcnow()
        expires_at = now + timedelta(minutes=ttl_minutes)

        record = ActivationRecord(
            code=code,
            session_id=session_id,
            mode=mode,
            created_at=now.isoformat() + "Z",
            expires_at=expires_at.isoformat() + "Z",
            last_activity_at=now.isoformat() + "Z",
            status=ActivationStatus.ACTIVE,
        )
        records[code] = record
        self._save_all(records)
        return record

    def get_activation(self, code: str) -> Optional[ActivationRecord]:
        """根据激活码获取记录（不会自动删除过期记录）。
        查找时自动 trim 并转为大写（生成的码为大写），方便用户输入。"""
        if not code or not isinstance(code, str):
            return None
        raw = code.strip()
        if not raw:
            return None
        # 激活码生成时为大写+数字，查找时统一转大写
        normalized = raw.upper()
        records = self._load_all()
        rec = records.get(normalized) or records.get(raw)
        if not rec:
            return None

        # 自动标记状态为 expired（但不删除）
        try:
            expires_dt = datetime.fromisoformat(rec.expires_at.replace("Z", ""))
        except ValueError:
            return rec
        if rec.status == ActivationStatus.ACTIVE and datetime.utcnow() > expires_dt:
            rec.status = ActivationStatus.EXPIRED
            records[code] = rec
            self._save_all(records)
        return rec

    def touch_activity(self, code: str) -> None:
        """更新最后活跃时间（仅在 ACTIVE 时更新）"""
        records = self._load_all()
        rec = records.get(code)
        if not rec:
            return
        if rec.status != ActivationStatus.ACTIVE:
            return
        now = datetime.utcnow().isoformat() + "Z"
        rec.last_activity_at = now
        records[code] = rec
        self._save_all(records)

