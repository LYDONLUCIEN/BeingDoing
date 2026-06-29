"""
批量导出服务（admin 按报告维度，聚合 5 个 phase 的会话为 md/txt 单文件）

==========================================================================
【导出格式规范（冻结）】 —— T3 正则解析以此为准，修改需同步通知 T3。
==========================================================================
1. 文件头（每个 report 文件的第一块）：
   - 首行标题：`# 寻录探索报告 - <report_id>`（md）或 `寻录探索报告 - <report_id>`（txt）
   - 紧跟一行由 `=` 组成的分隔线（长度 >= 20）
   - 元信息块（每行 `key: value`，key 为中文，冒号后一个空格）：
     - `用户ID: <user_id>`
     - `邮箱: <email 或 "未提供">`
     - `用户名: <username 或 "未提供">`
     - `激活码: <activation_code>`
     - `导出时间: <YYYY-MM-DD HH:MM:SS>`（本地时区，datetime.now().strftime("%Y-%m-%d %H:%M:%S")）
     - `报告ID: <report_id>`
   - 元信息块后一空行，再一行由 `-` 组成的分隔线（长度 >= 20）

2. Phase 章节标题（按 STEP_IDS 顺序：values, strengths, interests, purpose, rumination）：
   - md 格式：`## <序号>. <中文阶段名>（<step_id>）`
     示例：`## 1. 价值观（values）`
   - txt 格式：`<序号>. <中文阶段名>（<step_id>）`，下一行由 `-` 组成（长度 >= 10）
   - 中文阶段名映射（冻结，勿改）：
     values=价值观, strengths=优势, interests=热爱, purpose=使命, rumination=沉淀
   - 序号从 1 开始连续递增（仅含已完成的 phase，跳过未完成的 phase 不编号、不输出）

3. Phase 章节内会话信息（标题后第一块）：
   - 每行一个字段，格式 `  - <字段名>: <值>`（md 用 `-`，txt 也用 `-`，统一缩进两空格）
   - 字段顺序：
     - `会话ID: <session_id>`
     - `会话状态: <status 或 "未知">`
     - `创建时间: <created_at 或 "未知">`
   - 空行分隔会话信息块和消息块

4. 消息块（每个 phase 章节内）：
   - 每条消息两行：
     - 角色行：md 用 `**[<角色>]** <时间戳>`，txt 用 `[<角色>] <时间戳>`
       角色取值：user（用户）、assistant（助手）、system（系统）、tool（工具）
       时间戳格式：消息原 created_at 字段（若无则留空，冒号后无内容）
     - 内容行：消息正文原样输出
   - 消息之间用一个空行分隔

5. Phase 章节之间用一个空行分隔；文件末尾不留多余空行。

6. 文件扩展名：md 格式 `.md`，txt 格式 `.txt`。
   zip 内每个 report 一个文件，文件名：`report_<report_id>.<ext>`。

7. 跳过规则：若某个 phase 的 selected_session_id 为 None/空，该 phase 整章不输出（不占序号）。
   若全部 phase 均未完成，文件仅含文件头 + 提示行 `（本报告暂无已完成的探索阶段）`。
==========================================================================
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from app.services.export_service import ExportService
from app.utils.report_registry import STEP_IDS, ReportRegistry

logger = logging.getLogger(__name__)

# 中文阶段名映射（与格式规范冻结一致）
PHASE_LABEL_CN: Dict[str, str] = {
    "values": "价值观",
    "strengths": "优势",
    "interests": "热爱",
    "purpose": "使命",
    "rumination": "沉淀",
}

# 单次批量导出硬上限
MAX_BATCH_REPORTS = 50


class BatchExportService:
    """批量导出服务：按 report 聚合 5 phase 会话为 md/txt 文件。"""

    def __init__(self) -> None:
        """初始化，复用 ExportService 收集单会话数据。"""
        self.export_service = ExportService()
        self.registry = ReportRegistry()

    async def collect_report_export(
        self,
        report_id: str,
        fmt: str,
    ) -> Optional[Tuple[str, str]]:
        """
        收集单个 report 的导出内容。

        Args:
            report_id: 报告 ID
            fmt: 导出格式，``md`` 或 ``txt``

        Returns:
            ``(filename, content)`` 元组；report 不存在或无数据时返回 None。
        """
        record = self.registry.get_report_by_id(report_id)
        if not record:
            logger.warning("批量导出：report 不存在，跳过: %s", report_id)
            return None

        user_id = record.get("user_id") or ""
        activation_code = record.get("activation_code") or ""

        # 收集各 phase 的会话数据
        phase_blocks: List[str] = []
        phase_seq = 0
        for step_id in STEP_IDS:
            session_id = self.registry.get_selected_session(report_id, step_id)
            if not session_id:
                # 未完成 phase，跳过
                continue
            phase_seq += 1
            block = await self._build_phase_block(
                step_id=step_id,
                seq=phase_seq,
                session_id=session_id,
                user_id=user_id,
                fmt=fmt,
            )
            phase_blocks.append(block)

        # 组装文件
        ext = "md" if fmt == "md" else "txt"
        filename = f"report_{report_id}.{ext}"
        content = self._assemble_file(
            report_id=report_id,
            user_id=user_id,
            activation_code=activation_code,
            phase_blocks=phase_blocks,
            fmt=fmt,
        )
        return filename, content

    async def _build_phase_block(
        self,
        step_id: str,
        seq: int,
        session_id: str,
        user_id: str,
        fmt: str,
    ) -> str:
        """
        构建单个 phase 章节文本块。

        Args:
            step_id: 阶段 ID（values/strengths/...）
            seq: 章节序号（从 1 起，仅含已完成 phase）
            session_id: 该 phase 选中的会话 ID
            user_id: 用户 ID（复用 ExportService 收集数据）
            fmt: 导出格式

        Returns:
            章节文本块
        """
        label_cn = PHASE_LABEL_CN.get(step_id, step_id)
        sep_md = "=" * 30
        sep_dash = "-" * 20

        # 章节标题
        if fmt == "md":
            title = f"## {seq}. {label_cn}（{step_id}）"
        else:
            title = f"{seq}. {label_cn}（{step_id}）\n" + "-" * 12

        # 收集会话数据（复用 ExportService）
        session_info_lines: List[str] = []
        message_lines: List[str] = []
        try:
            data = await self.export_service.collect_export_data(
                user_id=user_id,
                session_id=session_id,
            )
            session_data = data.get("session") or {}
            session_status = session_data.get("status") or "未知"
            session_created = session_data.get("created_at") or "未知"
            session_info_lines.append(f"  - 会话ID: {session_id}")
            session_info_lines.append(f"  - 会话状态: {session_status}")
            session_info_lines.append(f"  - 创建时间: {session_created}")

            # 提取对话历史
            conv_history = data.get("conversation_history")
            # ExportService 内部可能因 bug 返回 dict 属性名不一致，这里兼容处理
            if not isinstance(conv_history, dict):
                conv_history = {}
            message_lines = self._format_messages(conv_history, fmt)
        except Exception as e:
            logger.exception(
                "批量导出：收集 phase 会话数据失败: report_id=%s step=%s err=%s",
                user_id,
                step_id,
                e,
            )
            session_info_lines.append(f"  - 会话ID: {session_id}")
            session_info_lines.append(f"  - 会话状态: 收集失败")
            session_info_lines.append(f"  - 创建时间: 未知")
            message_lines.append(f"（数据收集失败：{e}）")

        # 组装章节
        parts: List[str] = [title, ""]
        parts.extend(session_info_lines)
        parts.append("")
        if message_lines:
            parts.extend(message_lines)
        else:
            parts.append("（本阶段无对话记录）")
        return "\n".join(parts)

    def _format_messages(
        self,
        conv_history: Dict[str, List[Dict]],
        fmt: str,
    ) -> List[str]:
        """
        将对话历史字典格式化为消息行列表。

        Args:
            conv_history: ``{category: [message_dict, ...]}``
            fmt: 导出格式

        Returns:
            格式化后的消息行列表（每条消息含角色行+内容行，空行分隔）
        """
        # 角色中文映射
        role_map = {
            "user": "用户",
            "assistant": "助手",
            "system": "系统",
            "tool": "工具",
        }

        lines: List[str] = []
        # 按 category 排序，保证输出稳定
        for category in sorted(conv_history.keys()):
            messages = conv_history.get(category) or []
            for msg in messages:
                role = msg.get("role") or "unknown"
                role_cn = role_map.get(role, role)
                timestamp = msg.get("created_at") or msg.get("timestamp") or ""
                content = msg.get("content") or ""
                if isinstance(content, list):
                    # 某些 provider 返回 content 为片段列表
                    content = "".join(
                        (c.get("text") or "") if isinstance(c, dict) else str(c) for c in content
                    )
                if fmt == "md":
                    role_line = f"**[{role_cn}]** {timestamp}"
                else:
                    role_line = f"[{role_cn}] {timestamp}"
                lines.append(role_line)
                lines.append(str(content))
                lines.append("")  # 消息间空行
        # 去掉末尾多余空行
        while lines and lines[-1] == "":
            lines.pop()
        return lines

    def _assemble_file(
        self,
        report_id: str,
        user_id: str,
        activation_code: str,
        phase_blocks: List[str],
        fmt: str,
    ) -> str:
        """
        组装完整文件内容（文件头 + phase 章节）。

        Args:
            report_id: 报告 ID
            user_id: 用户 ID
            activation_code: 激活码
            phase_blocks: 已构建的 phase 章节文本块列表
            fmt: 导出格式

        Returns:
            完整文件文本
        """
        sep_eq = "=" * 30
        sep_dash = "-" * 20
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S") + " UTC"

        # 尝试取用户邮箱/用户名（ExportService.collect_export_data 内部查 DB，
        # 此处不重复查询，仅用 report_id/activation_code 兜底）
        email = "未提供"
        username = "未提供"

        parts: List[str] = []
        # 文件头标题
        if fmt == "md":
            parts.append(f"# 寻录探索报告 - {report_id}")
        else:
            parts.append(f"寻录探索报告 - {report_id}")
        parts.append(sep_eq)
        # 元信息块
        parts.append(f"用户ID: {user_id}")
        parts.append(f"邮箱: {email}")
        parts.append(f"用户名: {username}")
        parts.append(f"激活码: {activation_code}")
        parts.append(f"导出时间: {now_str}")
        parts.append(f"报告ID: {report_id}")
        parts.append("")
        parts.append(sep_dash)
        parts.append("")

        # Phase 章节
        if phase_blocks:
            for i, block in enumerate(phase_blocks):
                if i > 0:
                    parts.append("")  # 章节间空行
                parts.append(block)
        else:
            parts.append("（本报告暂无已完成的探索阶段）")

        return "\n".join(parts)
