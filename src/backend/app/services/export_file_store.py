"""临时会话导出文件：随机标识、用户隔离，外部输入不能成为文件路径。"""

import hashlib
import re
import tempfile
import uuid
from pathlib import Path


class ExportFileStore:
    """只在当前用户的临时目录创建和查找导出文件。"""

    def __init__(self, user_id: str):
        if not user_id:
            raise ValueError("导出文件必须绑定用户")
        namespace = hashlib.sha256(user_id.encode("utf-8")).hexdigest()
        self.root = Path(tempfile.gettempdir()) / "beingdoing-exports" / namespace

    def create(self, suffix: str) -> tuple[str, Path]:
        """生成服务器控制的随机导出标识和目标文件名。"""
        if suffix not in {".json", ".md", ".pdf"}:
            raise ValueError("不支持的导出格式")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        export_id = f"export_{uuid.uuid4().hex}"
        return export_id, self.root / f"{export_id}{suffix}"

    def find(self, export_id: str) -> Path | None:
        """标识非法时拒绝；不存在或属于其他用户时返回 None。"""
        if not re.fullmatch(r"export_[0-9a-f]{32}", export_id):
            raise ValueError("无效的导出标识，请重新生成导出文件")
        for suffix in (".json", ".md", ".pdf"):
            candidate = self.root / f"{export_id}{suffix}"
            if not candidate.is_symlink() and candidate.is_file():
                return candidate
        return None
