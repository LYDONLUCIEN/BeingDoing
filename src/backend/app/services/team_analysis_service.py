"""
团队分析服务（P-E，ADR-0008/0010）

规则口径：
- 候选报告 = 自己名下码的报告 + 自己购买订单交付且被激活人一键授权的码的报告
- 激活人只授权「报告」，对话过程记录永不分享
- 分析内容：团队匹配度分析 + 团队角色投射（LLM 生成，markdown 存 team_analyses）
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select

from app.models.database import AsyncSessionLocal
from app.models.payment import TeamAnalysis
from app.utils.simple_activation_manager import (
    SimpleActivationManager,
    get_activation_with_manager,
)

logger = logging.getLogger(__name__)

# 单次分析的码数量范围
MIN_CODES = 2
MAX_CODES = 10


class AnalysisNotFoundError(Exception):
    """分析记录不存在（路由转 404）"""


def _activation_manager() -> SimpleActivationManager:
    """生产激活码管理器（独立成函数便于测试替换 base_dir）"""
    return SimpleActivationManager()


def _report_registry():
    from app.utils.report_registry import ReportRegistry

    return ReportRegistry()


def _pdf_service():
    from app.services.report_pdf_service import ReportPdfService

    return ReportPdfService()


def _mask_email(email: Optional[str]) -> Optional[str]:
    """邮箱脱敏：a***@domain.com"""
    if not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    return f"{local[:1]}***@{domain}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TeamAnalysisService:
    """团队分析服务"""

    # ─── 候选报告 ──────────────────────────────────────────────

    @classmethod
    def list_candidates(cls, user_id: str) -> List[Dict[str, Any]]:
        """团队分析候选报告列表

        - 自己名下码（激活人=我）的报告：直接可选
        - 我购买的码（所属人=我）被他人激活：报告已授权且审核通过才可选；
          未授权/未就绪的也返回（selectable=False 供前端展示状态）
        """
        mgr = _activation_manager()
        registry = _report_registry()
        # report 索引：activation_code → record（仅审核通过/存量豁免）
        approved_by_code: Dict[str, dict] = {}
        for record in registry.list_reports():
            review_status = record.get("review_status") or "approved"
            if review_status == "approved":
                approved_by_code[record.get("activation_code")] = record

        candidates: List[Dict[str, Any]] = []
        for code, rec in mgr.list_activations().items():
            is_activator = rec.owner_user_id == user_id
            is_purchaser = getattr(rec, "purchaser_user_id", None) == user_id
            if not (is_activator or is_purchaser):
                continue

            report = approved_by_code.get(code)
            authorized = bool(getattr(rec, "report_authorized", False))

            if is_activator:
                # 自己的码：报告就绪即可选（授权开关是给所属人看的，自己不受限）
                candidates.append(
                    {
                        "activation_code": code,
                        "role": "self",
                        "owner_label": "我",
                        "has_report": report is not None,
                        "report_id": report.get("report_id") if report else None,
                        "report_authorized": authorized,
                        "selectable": report is not None,
                    }
                )
            else:
                # 我购买的、别人激活的码：须激活人授权 + 报告就绪
                candidates.append(
                    {
                        "activation_code": code,
                        "role": "purchased",
                        "owner_label": _mask_email(rec.owner_email) or "未激活",
                        "activated": bool(rec.owner_user_id),
                        "has_report": report is not None,
                        "report_id": report.get("report_id") if report else None,
                        "report_authorized": authorized,
                        "selectable": authorized and report is not None,
                    }
                )

        candidates.sort(key=lambda c: (c["role"] != "self", c["activation_code"]))
        return candidates

    # ─── 创建与生成 ────────────────────────────────────────────

    @classmethod
    async def create_analysis(
        cls, user_id: str, code_list: List[str], title: Optional[str] = None
    ) -> TeamAnalysis:
        """创建团队分析（状态 generating，由路由层 BackgroundTasks 调 run_generation）

        Raises:
            ValueError: 码数量/可选性校验失败
        """
        codes = sorted({(c or "").strip().upper() for c in (code_list or []) if (c or "").strip()})
        if not MIN_CODES <= len(codes) <= MAX_CODES:
            raise ValueError(f"请选择 {MIN_CODES}-{MAX_CODES} 份报告")

        selectable = {
            c["activation_code"]: c for c in cls.list_candidates(user_id) if c["selectable"]
        }
        for code in codes:
            if code not in selectable:
                raise ValueError(f"激活码 {code} 的报告不可用于团队分析（未就绪或未授权）")

        report_ids = [selectable[c]["report_id"] for c in codes]
        import json

        async with AsyncSessionLocal() as db:
            analysis = TeamAnalysis(
                user_id=user_id,
                title=(title or "").strip() or f"团队分析 {datetime.now(timezone.utc):%Y-%m-%d}",
                code_list=json.dumps(codes, ensure_ascii=False),
                report_ids=json.dumps(report_ids, ensure_ascii=False),
                status="generating",
            )
            db.add(analysis)
            await db.commit()
            await db.refresh(analysis)
            logger.info("团队分析已创建：id=%s user=%s codes=%s", analysis.id, user_id, codes)
            return analysis

    @classmethod
    async def run_generation(cls, analysis_id: str) -> None:
        """后台生成：汇总报告 markdown → LLM → 存结果（done/failed）"""
        import json

        async with AsyncSessionLocal() as db:
            analysis = (
                await db.execute(select(TeamAnalysis).where(TeamAnalysis.id == analysis_id))
            ).scalar_one_or_none()
            if not analysis:
                logger.error("团队分析不存在：%s", analysis_id)
                return
            report_ids = json.loads(analysis.report_ids or "[]")
            codes = json.loads(analysis.code_list or "[]")

        try:
            markdown = await cls._generate_markdown(report_ids, codes)
        except Exception as e:
            logger.exception("团队分析生成失败：id=%s err=%s", analysis_id, e)
            async with AsyncSessionLocal() as db:
                row = (
                    await db.execute(select(TeamAnalysis).where(TeamAnalysis.id == analysis_id))
                ).scalar_one_or_none()
                if row:
                    row.status = "failed"
                    row.error = str(e)[:500]
                    await db.commit()
            return

        async with AsyncSessionLocal() as db:
            row = (
                await db.execute(select(TeamAnalysis).where(TeamAnalysis.id == analysis_id))
            ).scalar_one_or_none()
            if row:
                row.status = "done"
                row.result_markdown = markdown
                await db.commit()
                logger.info("团队分析生成完成：id=%s", analysis_id)

    @classmethod
    async def _generate_markdown(cls, report_ids: List[str], codes: List[str]) -> str:
        """加载各报告 markdown（缓存优先，缺失则生成）→ LLM 汇总分析"""
        from app.core.llmapi.base import LLMMessage
        from app.core.llmapi.factory import get_llm_provider_for_vip

        pdf = _pdf_service()
        sections: List[str] = []
        for code, report_id in zip(codes, report_ids):
            content = pdf.load_cached_markdown(report_id)
            if content is None:
                content = await pdf.generate_markdown_only(report_id, vip_level=2)
            sections.append(f"## 成员报告（激活码 {code}）\n\n{content}")

        joined = "\n\n---\n\n".join(sections)
        system_prompt = (
            "你是一位资深的职业规划与团队建设顾问。用户会提供多位团队成员的个人探索报告"
            "（每份报告包含价值观、优势、兴趣、使命、沉淀五个维度的分析）。"
            "请基于这些报告输出一份团队分析，使用中文、Markdown 格式，包含两个部分：\n"
            "1. **团队匹配度分析**：成员间的互补点、潜在协同方向、可能的冲突点与化解建议；\n"
            "2. **团队角色投射**：每位成员在团队中的倾向性定位（如推动者/协调者/思考者等），"
            "并给出依据。分析须具体引用报告内容，避免泛泛而谈。"
        )
        provider = get_llm_provider_for_vip(2)
        response = await provider.chat(
            [
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=joined),
            ],
            temperature=0.7,
            max_tokens=4000,
        )
        return response.content

    # ─── 查询 ──────────────────────────────────────────────────

    @classmethod
    async def list_my_analyses(
        cls, user_id: str, page: int = 1, page_size: int = 20
    ) -> Tuple[List[Dict[str, Any]], int]:
        """我的团队分析列表（不含结果正文）"""
        async with AsyncSessionLocal() as db:
            base = select(TeamAnalysis).where(TeamAnalysis.user_id == user_id)
            total = (
                await db.execute(
                    select(func.count())
                    .select_from(TeamAnalysis)
                    .where(TeamAnalysis.user_id == user_id)
                )
            ).scalar() or 0
            rows = (
                (
                    await db.execute(
                        base.order_by(TeamAnalysis.created_at.desc())
                        .offset((page - 1) * page_size)
                        .limit(page_size)
                    )
                )
                .scalars()
                .all()
            )
            return [cls._to_dict(a, with_result=False) for a in rows], total

    @classmethod
    async def get_my_analysis(cls, user_id: str, analysis_id: str) -> Dict[str, Any]:
        """我的团队分析详情（含结果正文）"""
        async with AsyncSessionLocal() as db:
            analysis = (
                await db.execute(select(TeamAnalysis).where(TeamAnalysis.id == analysis_id))
            ).scalar_one_or_none()
            if not analysis or analysis.user_id != user_id:
                raise AnalysisNotFoundError("团队分析不存在")
            return cls._to_dict(analysis, with_result=True)

    # ─── 内部 ──────────────────────────────────────────────────

    @staticmethod
    def _to_dict(analysis: TeamAnalysis, with_result: bool) -> Dict[str, Any]:
        import json

        item: Dict[str, Any] = {
            "id": analysis.id,
            "title": analysis.title,
            "code_list": json.loads(analysis.code_list or "[]"),
            "status": analysis.status,
            "error": analysis.error,
            "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
        }
        if with_result:
            item["result_markdown"] = analysis.result_markdown
        return item
