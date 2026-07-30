"""
报告 PDF 生成服务。

流程：
1. 收集5个phase的结论数据（4维 dimension_conclusions + rumination_v4 最终结论卡）
2. 收集五个阶段的完整对话全文（与 admin 批量导出的 report_<id>.md 同源口径）
3. 解析用户昵称（basic_info nickname → User.username → 探索者）+ 可选拼接用户 profile
4. Jinja2 渲染提示词（202607 版八章框架）→ LLM 生成 markdown 报告
5. 缓存 markdown 到文件系统（record.json 存时间戳）
6. WeasyPrint: markdown → HTML → PDF（含水印）

缓存策略：
- record.json 增加 report_markdown_generated_at 字段
- markdown 存 data/simple/reports/{report_id}/report_markdown.md
- 比对结论卡 updated_at 判断是否过期
- force=True 跳过缓存强制重新生成
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import markdown as md_lib

from app.core.llmapi import LLMMessage, get_default_llm_provider
from app.domain.prompts.loader import _get_loader
from app.utils.report_registry import STEP_IDS, ReportRegistry
from app.utils.simple_activation_manager import get_simple_base_dir
from app.utils.survey_storage import load_dimension_conclusions

logger = logging.getLogger(__name__)

# 静态资源路径
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
_WATERMARK_LOGO = _STATIC_DIR / "assets" / "watermark_logo.png"
_PAGE_LOGO_HEADER = _STATIC_DIR / "assets" / "openlifelogo_header.png"  # 页眉右上角小 logo
_PAGE_LOGO_FOOTER = _STATIC_DIR / "assets" / "openlifelogo_footer.png"  # 页脚正中心 logo
_REPORT_CSS = _STATIC_DIR / "styles" / "report_pdf.css"

# 报告落款签名（ADR-0012 品牌更名后新增）：首次生成随机分配，持久化到 record.json 的
# report_signature 字段，保证同一报告再生成时签名不变
_SIGNATURE_CHOICES = ("signature_1", "signature_2", "signature_3")
_SIGNATURE_SUFFIX = ".png"

# 缓存文件名
_REPORT_MARKDOWN_FILENAME = "report_markdown.md"

# 对话全文注入配置（conversation_block）：与批量导出 md 同口径，只保留 user/assistant
_CONVERSATION_ROLES_KEEP = {"user", "assistant"}
_CONVERSATION_ROLE_CN = {"user": "用户", "assistant": "助手"}
_PHASE_LABEL_CN = {
    "values": "价值观",
    "strengths": "优势",
    "interests": "热爱",
    "purpose": "使命",
    "rumination": "沉淀",
}
# 单阶段对话注入上限（字符）；超出时保留开头 + 结尾，中间省略，防止 prompt 超长
_CONVERSATION_PHASE_CHAR_LIMIT = 20000
_CONVERSATION_PHASE_HEAD_CHARS = 6000
# 昵称兜底
_DEFAULT_NICKNAME = "探索者"


def _image_data_uri(path: Path) -> str:
    """读取图片并返回 data URI（用于 CSS @page 边距盒 content: url(...)）；文件缺失时返回空串。"""
    import base64

    if not path.is_file():
        logger.warning("报告页眉页脚 logo 缺失: %s", path)
        return ""
    return f"data:image/png;base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


class ReportPdfService:
    """报告 PDF 生成服务。"""

    def __init__(self, base_dir: Optional[str] = None):
        self.simple_base_dir = Path(base_dir) if base_dir else get_simple_base_dir()
        self.reports_root = self.simple_base_dir / "reports"

    # ── 公开接口 ──────────────────────────────────────────────

    async def generate_pdf(
        self,
        report_id: str,
        *,
        user_id: Optional[str] = None,
        force: bool = False,
        vip_level: int = 1,
    ) -> bytes:
        """
        生成 PDF 报告，返回 bytes。

        Args:
            report_id: 报告 ID
            user_id: 用户 ID（用于查 profile，可选）
            force: 是否强制重新生成（跳过缓存）
            vip_level: LLM VIP 级别
        Returns:
            PDF bytes
        """
        reports_root = str(self.reports_root)

        # 1. 尝试读缓存
        if not force:
            cached = self._load_cached_markdown(report_id)
            if cached is not None:
                logger.info("report_pdf 缓存命中: report_id=%s", report_id)
                return self._markdown_to_pdf(cached, report_id=report_id)

        # 2. 收集数据
        report_md = await self._generate_report_markdown(
            report_id, user_id=user_id, vip_level=vip_level
        )

        # 3. 写缓存
        self._save_cached_markdown(report_id, report_md)

        # 4. 转 PDF
        return self._markdown_to_pdf(report_md, report_id=report_id)

    # ── 异步生成支持（拆分为 markdown 生成 + PDF 转换）─────────

    async def generate_markdown_only(
        self,
        report_id: str,
        *,
        user_id: Optional[str] = None,
        force: bool = False,
        vip_level: int = 1,
    ) -> str:
        """
        只生成并缓存 markdown（不含 PDF 转换）。
        供异步后台任务调用。
        """
        # 缓存命中
        if not force:
            cached = self._load_cached_markdown(report_id)
            if cached is not None:
                logger.info("report_pdf markdown 缓存命中: report_id=%s", report_id)
                return cached

        # LLM 生成
        report_md = await self._generate_report_markdown(
            report_id, user_id=user_id, vip_level=vip_level
        )
        # 写缓存
        self._save_cached_markdown(report_id, report_md)
        return report_md

    def has_cached_markdown(self, report_id: str) -> bool:
        """检查是否有有效的缓存 markdown。"""
        return self._load_cached_markdown(report_id) is not None

    def load_cached_markdown(self, report_id: str) -> Optional[str]:
        """读取缓存的 markdown（公开接口）。"""
        return self._load_cached_markdown(report_id)

    def markdown_to_pdf_bytes(self, markdown_text: str, report_id: Optional[str] = None) -> bytes:
        """将 markdown 转为 PDF bytes（公开接口）。report_id 用于读取/分配落款签名。"""
        return self._markdown_to_pdf(markdown_text, report_id=report_id)

    def get_report_filename(self, record: dict) -> str:
        """根据 record 生成 PDF 文件名。"""
        user_id = (record.get("user_id") or "user").strip()
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        return f"寻路·OpenLife报告_{user_id}_{date_str}.pdf"

    # ── 数据收集 ──────────────────────────────────────────────

    def _collect_phase_data(self, report_id: str) -> Dict[str, str]:
        """
        收集5个phase的结论，渲染成文本块。

        Returns:
            {
                "values_block": "...",
                "strengths_block": "...",
                "interests_block": "...",
                "purpose_block": "...",
                "rumination_block": "..."
            }
        """
        reports_root = str(self.reports_root)

        # 4维结论
        dim = load_dimension_conclusions(report_id, reports_root)
        result: Dict[str, str] = {}
        for phase in ("values", "strengths", "interests", "purpose"):
            result[f"{phase}_block"] = self._format_dimension_block(phase, dim.get(phase))

        # rumination 最终结论
        result["rumination_block"] = self._collect_rumination_block(report_id)
        return result

    def _format_dimension_block(self, phase: str, data: Optional[Dict[str, Any]]) -> str:
        """格式化单个维度的结论块。"""
        if not data:
            return f"（{phase} 阶段暂无结论数据）"

        lines: List[str] = []
        summary = (data.get("summary") or data.get("ai_summary") or "").strip()
        keywords = data.get("keywords") or []
        final_answer = (data.get("final_answer") or "").strip()

        if final_answer:
            lines.append(f"确认结论：{final_answer}")
        if keywords:
            lines.append(f"关键词：{'、'.join(str(k) for k in keywords)}")
        if summary:
            lines.append(f"详细总结：\n{summary}")

        # purpose 特有字段
        if phase == "purpose":
            mission_core = data.get("mission_core")
            if mission_core:
                lines.append(f"使命核心：{mission_core}")
            mission_detail = data.get("mission_detail")
            if mission_detail:
                lines.append(f"使命详述：{mission_detail}")

        return "\n".join(lines) if lines else f"（{phase} 阶段暂无有效结论）"

    def _collect_rumination_block(self, report_id: str) -> str:
        """收集 rumination V4 最终选定的结论卡。"""
        try:
            from app.services.rumination_v4_service import load_v4_state

            state = load_v4_state(self.reports_root, report_id)
        except Exception as e:
            logger.warning("加载 rumination_v4_state 失败: %s", e)
            return "（rumination 阶段暂无数据）"

        final_selection = state.get("final_selection") or {}
        selected_ids = set(final_selection.get("selected_combo_ids") or [])

        combo_sessions = state.get("combo_sessions") or []
        selected_combos = [
            c for c in combo_sessions if c.get("combo_id") in selected_ids
        ]

        if not selected_combos:
            return "（用户尚未完成最终选择）"

        lines: List[str] = []
        for combo in selected_combos:
            passion = combo.get("passion") or ""
            strengths = combo.get("strengths") or []
            card = combo.get("conclusion_card")

            lines.append(f"### 探索方向：{passion} × {'、'.join(strengths)}")

            if not card:
                lines.append("（该方向暂无结论卡）\n")
                continue

            hypothesis = card.get("hypothesis")
            if isinstance(hypothesis, dict):
                for k, v in hypothesis.items():
                    lines.append(f"- 假设（{k}）：{v}")
            elif isinstance(hypothesis, str) and hypothesis:
                lines.append(f"- 核心假设：{hypothesis}")

            motivation = card.get("motivation")
            if motivation:
                lines.append(f"- 动机：{motivation}")

            work_purposes = card.get("work_purposes")
            if work_purposes:
                lines.append(f"- 工作目的：{'；'.join(work_purposes)}")

            passion_mark = card.get("passion_mark")
            if passion_mark:
                lines.append(f"- 激情标记：{passion_mark}")

            timing_mark = card.get("timing_mark")
            if timing_mark:
                lines.append(f"- 时机标记：{timing_mark}")

            lines.append("")  # 空行分隔

        return "\n".join(lines)

    # ── 昵称与对话全文收集 ──────────────────────────────────

    async def _collect_nickname(
        self, report_id: str, user_id: Optional[str] = None
    ) -> str:
        """解析用户昵称：basic_info nickname → User.username → 探索者。"""
        uid = (user_id or "").strip()
        if not uid:
            try:
                registry = ReportRegistry(base_dir=str(self.simple_base_dir))
                record = registry.get_report_by_id(report_id) or {}
                uid = (record.get("user_id") or "").strip()
            except Exception:
                uid = ""
        if not uid:
            return _DEFAULT_NICKNAME

        # 1. basic_info 问卷昵称（对话中 AI 称呼用户用的就是它）
        try:
            from app.utils.survey_storage import load_basic_info_by_user

            info = load_basic_info_by_user(uid) or {}
            nickname = (info.get("nickname") or "").strip()
            if nickname:
                return nickname
        except Exception as e:
            logger.warning("读取 basic_info 昵称失败: user_id=%s err=%s", uid, e)

        # 2. 注册用户名
        try:
            from app.models.database import AsyncSessionLocal
            from app.models.user import User
            from sqlalchemy import select

            async with AsyncSessionLocal() as session:
                result = await session.execute(select(User).where(User.id == uid))
                user = result.scalar_one_or_none()
                if user and user.username:
                    return str(user.username).strip()
        except Exception as e:
            logger.warning("读取用户 username 失败: user_id=%s err=%s", uid, e)

        return _DEFAULT_NICKNAME

    def _collect_conversation_block(self, report_id: str) -> str:
        """收集五个阶段的完整对话全文，渲染成文本块（conversation_block）。

        口径与 admin 批量导出的 report_<id>.md 一致：
        - 遍历 STEP_IDS，每阶段选会话优先级 selected_session_id > session_ids 最后一个
        - 只保留 user/assistant 消息，过滤 system/tool/conclusion_card 等噪音
        - 单阶段超长时保留开头 + 结尾，中间省略
        """
        try:
            registry = ReportRegistry(base_dir=str(self.simple_base_dir))
            record = registry.get_report_by_id(report_id)
        except Exception as e:
            logger.warning("加载 report record 失败: report_id=%s err=%s", report_id, e)
            return "（暂无对话记录）"
        if not record:
            return "（暂无对话记录）"

        blocks: List[str] = []
        for step_id in STEP_IDS:
            step = (record.get("steps") or {}).get(step_id) or {}
            session_ids = step.get("session_ids") or []
            chosen = step.get("selected_session_id") or (session_ids[-1] if session_ids else None)
            if not chosen:
                continue

            label = _PHASE_LABEL_CN.get(step_id, step_id)
            file_path = registry.get_step_session_file(report_id, step_id, chosen)
            if not file_path.is_file():
                blocks.append(f"### {label}阶段\n\n> （该阶段对话源文件缺失）")
                continue
            try:
                raw = json.loads(file_path.read_text(encoding="utf-8") or "{}")
            except (OSError, json.JSONDecodeError) as e:
                logger.warning("对话源文件解析失败: %s err=%s", file_path, e)
                blocks.append(f"### {label}阶段\n\n> （该阶段对话源文件解析失败）")
                continue

            dialogue = self._render_dialogue_text(raw.get("messages") or [])
            if not dialogue:
                dialogue = "（本阶段无对话记录）"
            blocks.append(f"### {label}阶段\n\n{dialogue}")

        if not blocks:
            return "（暂无对话记录）"
        return "\n\n".join(blocks)

    def _render_dialogue_text(self, messages: list) -> str:
        """把消息列表渲染为「**用户**：xxx」对话文本，超长时头尾保留、中间省略。"""
        lines: List[str] = []
        for m in messages:
            if not isinstance(m, dict):
                continue
            role = m.get("role") or ""
            if role not in _CONVERSATION_ROLES_KEEP:
                continue
            content = m.get("content")
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False) if content else ""
            text = content.strip()
            if not text:
                continue
            speaker = _CONVERSATION_ROLE_CN.get(role, role)
            lines.append(f"**{speaker}**：{text}")

        dialogue = "\n\n".join(lines)
        if len(dialogue) <= _CONVERSATION_PHASE_CHAR_LIMIT:
            return dialogue
        head = dialogue[:_CONVERSATION_PHASE_HEAD_CHARS]
        tail = dialogue[_CONVERSATION_PHASE_HEAD_CHARS - _CONVERSATION_PHASE_CHAR_LIMIT:]
        return f"{head}\n\n> ……（中间对话省略）……\n\n{tail}"

    # ── LLM 生成 ─────────────────────────────────────────────

    async def _generate_report_markdown(
        self, report_id: str, *, user_id: Optional[str] = None, vip_level: int = 1
    ) -> str:
        """调用 LLM 生成 markdown 报告。"""
        # 1. 收集数据
        phase_data = self._collect_phase_data(report_id)
        profile_block = ""
        if user_id:
            profile_block = await self._collect_profile_async(user_id)
        nickname = await self._collect_nickname(report_id, user_id)
        conversation_block = self._collect_conversation_block(report_id)

        # 2. 渲染提示词
        context = {
            **phase_data,
            "profile_block": profile_block,
            "user_nickname": nickname,
            "conversation_block": conversation_block,
        }
        system_prompt = _get_loader().render("report_system", context)

        # 3. 调 LLM
        llm = get_default_llm_provider(vip_level=vip_level)
        messages = [
            LLMMessage(
                role="system",
                content=system_prompt,
            ),
            LLMMessage(
                role="user",
                content="请开始撰写报告。",
            ),
        ]

        response = await llm.chat(
            messages=messages,
            temperature=0.7,
            max_tokens=8000,
        )
        return response.content.strip()

    async def _collect_profile_async(self, user_id: str) -> str:
        """异步获取用户 profile 文本块。"""
        if not user_id:
            return ""
        try:
            from app.models.database import AsyncSessionLocal
            from app.models.user import User, UserProfile, WorkHistory
            from sqlalchemy import select

            lines: List[str] = []
            async with AsyncSessionLocal() as session:
                user_result = await session.execute(
                    select(User, UserProfile)
                    .join(UserProfile, UserProfile.user_id == User.id)
                    .where(User.id == user_id)
                )
                row = user_result.first()
                if not row:
                    return ""
                user, profile = row

                if user.username:
                    lines.append(f"姓名：{user.username}")
                if profile:
                    if profile.gender:
                        gender_cn = {
                            "male": "男",
                            "female": "女",
                            "other": "其他",
                        }.get(profile.gender, profile.gender)
                        lines.append(f"性别：{gender_cn}")
                    if profile.age:
                        lines.append(f"年龄：{profile.age}")

                wh_result = await session.execute(
                    select(WorkHistory)
                    .where(WorkHistory.user_id == user_id)
                    .order_by(WorkHistory.start_date.desc())
                )
                work_histories = wh_result.scalars().all()
                if work_histories:
                    lines.append("工作经历：")
                    for wh in work_histories:
                        company = wh.company or ""
                        position = wh.position or ""
                        end = "至今" if wh.end_date is None else str(wh.end_date)
                        start = str(wh.start_date or "")
                        lines.append(f"  - {company} {position}（{start} ~ {end}）")

            return "\n".join(lines) if lines else ""
        except Exception as e:
            logger.warning("读取用户 profile 失败: %s", e)
            return ""

    # ── 缓存读写 ──────────────────────────────────────────────

    def _load_cached_markdown(self, report_id: str) -> Optional[str]:
        """
        读缓存的 markdown。
        比对结论卡 updated_at 判断是否过期。
        过期或不存在返回 None。
        """
        registry = ReportRegistry(base_dir=str(self.simple_base_dir))
        record = registry.get_report_by_id(report_id)
        if not record:
            return None

        generated_at = record.get("report_markdown_generated_at")
        if not generated_at:
            return None

        # 检查缓存文件存在
        md_path = self._markdown_path(report_id)
        if not md_path.is_file():
            return None

        # 比对结论卡更新时间
        if self._is_cache_expired(report_id, generated_at):
            return None

        try:
            return md_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def _is_cache_expired(self, report_id: str, generated_at: str) -> bool:
        """比对结论卡 updated_at 与缓存生成时间。"""
        try:
            gen_dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return True

        latest_conclusion_ts = self._get_latest_conclusion_ts(report_id)
        if latest_conclusion_ts is None:
            return False  # 没有结论卡数据，不算过期

        try:
            latest_dt = datetime.fromisoformat(
                latest_conclusion_ts.replace("Z", "+00:00")
            )
        except (ValueError, AttributeError):
            return False

        return latest_dt > gen_dt

    def _get_latest_conclusion_ts(self, report_id: str) -> Optional[str]:
        """获取所有结论卡中最大的 updated_at。"""
        latest: Optional[str] = None

        # rumination 结论卡
        try:
            from app.services.rumination_v4_service import load_v4_state

            state = load_v4_state(self.reports_root, report_id)
            for combo in state.get("combo_sessions") or []:
                card = combo.get("conclusion_card")
                if card and isinstance(card, dict):
                    ts = card.get("updated_at") or card.get("created_at")
                    if ts and (latest is None or ts > latest):
                        latest = ts
        except Exception:
            pass

        # dimension_conclusions.json 的文件修改时间作为参考
        dim_path = self.reports_root / report_id / "dimension_conclusions.json"
        if dim_path.is_file():
            try:
                mtime = datetime.fromtimestamp(
                    dim_path.stat().st_mtime, tz=timezone.utc
                ).isoformat()
                if latest is None or mtime > latest:
                    latest = mtime
            except OSError:
                pass

        return latest

    def _save_cached_markdown(self, report_id: str, markdown_text: str) -> None:
        """保存 markdown 到文件 + 更新 record.json 时间戳。"""
        md_path = self._markdown_path(report_id)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(markdown_text, encoding="utf-8")

        # 更新 record.json
        registry = ReportRegistry(base_dir=str(self.simple_base_dir))
        record = registry.get_report_by_id(report_id)
        if record:
            record["report_markdown_generated_at"] = datetime.now(timezone.utc).isoformat()
            registry._save_record(record)

    def _markdown_path(self, report_id: str) -> Path:
        return self.reports_root / report_id / _REPORT_MARKDOWN_FILENAME

    # ── 落款签名 ─────────────────────────────────────────────

    def _get_or_assign_signature(self, report_id: str) -> Optional[str]:
        """读取 record.json 的 report_signature；缺失/非法时随机分配并持久化。

        保证同一报告多次生成 PDF 使用同一签名。异常时返回 None（不阻塞出报告）。
        """
        try:
            registry = ReportRegistry(base_dir=str(self.simple_base_dir))
            record = registry.get_report_by_id(report_id)
            if not record:
                return None
            sig = record.get("report_signature")
            if sig not in _SIGNATURE_CHOICES:
                sig = random.choice(_SIGNATURE_CHOICES)
                record["report_signature"] = sig
                registry.save_record(record)
                logger.info("报告落款签名分配: report_id=%s signature=%s", report_id, sig)
            return sig
        except Exception:
            logger.exception("报告落款签名读取/分配失败: report_id=%s", report_id)
            return None

    def _signature_block_html(self, report_id: Optional[str]) -> str:
        """报告末尾的落款签名区块；无 report_id 或签名图缺失时返回空串。"""
        if not report_id:
            return ""
        sig = self._get_or_assign_signature(report_id)
        if not sig:
            return ""
        sig_path = _STATIC_DIR / "assets" / f"{sig}{_SIGNATURE_SUFFIX}"
        data_uri = _image_data_uri(sig_path)
        if not data_uri:
            return ""
        return (
            '<div class="report-signature">'
            '<div class="signature-label">—— 你的寻路·OpenLife 探索引导师</div>'
            f'<img class="signature-img" src="{data_uri}" alt="引导师签名" />'
            "</div>"
        )

    # ── PDF 生成 ─────────────────────────────────────────────

    def _markdown_to_pdf(self, markdown_text: str, report_id: Optional[str] = None) -> bytes:
        """markdown → HTML → PDF（含水印），返回 bytes。"""
        from weasyprint import HTML

        # 1. markdown → HTML
        extensions = ["extra", "nl2br"]
        html_body = md_lib.markdown(markdown_text, extensions=extensions)

        # 2. 读 CSS，注入页眉/页脚 logo（data URI 替换占位符）
        css_content = _REPORT_CSS.read_text(encoding="utf-8")
        css_content = css_content.replace(
            "__PAGE_LOGO_HEADER_URL__", _image_data_uri(_PAGE_LOGO_HEADER)
        ).replace(
            "__PAGE_LOGO_FOOTER_URL__", _image_data_uri(_PAGE_LOGO_FOOTER)
        )

        # 3. 水印 logo base64 编码（嵌入 HTML）
        logo_b64 = ""
        if _WATERMARK_LOGO.is_file():
            import base64

            logo_bytes = _WATERMARK_LOGO.read_bytes()
            logo_b64 = base64.b64encode(logo_bytes).decode("ascii")

        # 4. 构建水印 HTML（上中下 3 条斜 45 度水印带，覆盖整页）
        #    水印图本身含品牌文字；图缺失时退化为纯文字水印
        strip_content = (
            f'<img src="data:image/png;base64,{logo_b64}" alt="logo" />'
            if logo_b64
            else '<div class="watermark-text">寻路·OpenLife</div>'
        )
        watermark_strips = "".join(
            f'<div class="watermark-strip strip-{i}">{strip_content}</div>' for i in (1, 2, 3)
        )
        watermark_html = f'<div class="watermark-layer">{watermark_strips}</div>'

        # 5. 拼装完整 HTML
        full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<style>
{css_content}
</style>
</head>
<body>
{watermark_html}

<!-- 封面 -->
<div class="cover">
  <div class="cover-title">寻路·OpenLife 报告</div>
  <div class="cover-divider"></div>
  <div class="cover-subtitle">OPENLIFE</div>
  <div class="cover-info">
    不是找到方向，而是认出自己<br/>
    <br/>
    {datetime.now(timezone.utc).strftime("%Y 年 %m 月 %d 日")}
  </div>
</div>

<!-- 正文 -->
<div class="content">
{html_body}
{self._signature_block_html(report_id)}
</div>
</body>
</html>"""

        # 6. WeasyPrint 渲染
        pdf_bytes = HTML(string=full_html).write_pdf()
        return pdf_bytes
