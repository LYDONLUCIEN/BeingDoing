"""
数据分析服务：埋点记录与 Admin 统计聚合
"""
import logging
from typing import Optional, Dict, Any, List
from sqlalchemy import select, func, distinct
from app.models.database import AsyncSessionLocal
from app.models.analytics import AnalyticsChatTurn, AnalyticsReport, AnalyticsLike
from app.models.user import User
from app.models.session import Session

logger = logging.getLogger(__name__)


class AnalyticsService:
    """埋点记录与统计"""

    @staticmethod
    async def record_chat_turn(
        session_id: str,
        dimension: str,
        user_input_chars: int,
        llm_input_tokens: int,
        llm_output_tokens: int,
        log_index: Optional[int] = None,
    ) -> None:
        """记录一次对话轮次"""
        try:
            async with AsyncSessionLocal() as db:
                turn = AnalyticsChatTurn(
                    session_id=session_id,
                    dimension=dimension,
                    user_input_chars=user_input_chars,
                    llm_input_tokens=llm_input_tokens,
                    llm_output_tokens=llm_output_tokens,
                    log_index=log_index,
                )
                db.add(turn)
                await db.commit()
        except Exception:
            await db.rollback()
            raise

    @staticmethod
    async def record_report(session_id: str, activation_code: Optional[str] = None) -> None:
        """记录报告生成"""
        try:
            async with AsyncSessionLocal() as db:
                r = AnalyticsReport(session_id=session_id, activation_code=activation_code)
                db.add(r)
                await db.commit()
        except Exception:
            await db.rollback()
            raise

    @staticmethod
    async def record_like(
        session_id: str,
        log_index: int,
        content_preview: Optional[str] = None,
        dimension: Optional[str] = None,
    ) -> None:
        """记录用户点赞"""
        try:
            async with AsyncSessionLocal() as db:
                like = AnalyticsLike(
                    session_id=session_id,
                    log_index=log_index,
                    content_preview=(content_preview or "")[:500],
                    dimension=dimension,
                )
                db.add(like)
                await db.commit()
        except Exception:
            await db.rollback()
            raise

    @staticmethod
    def _empty_dashboard() -> Dict[str, Any]:
        """无数据时的安全默认结构"""
        return {
            "user_count": 0,
            "visit_count": 0,
            "dialogs_by_dimension": {},
            "user_input_total_chars": 0,
            "llm_input_tokens": 0,
            "llm_output_tokens": 0,
            "report_count": 0,
            "last_stop_by_dimension": {},
            "like_count": 0,
            "like_records": [],
        }

    @staticmethod
    async def get_admin_dashboard() -> Dict[str, Any]:
        """获取 Admin 仪表盘数据（需 super_admin 校验）"""
        try:
            async with AsyncSessionLocal() as db:
                # 用户数量（scalar 可能为 None，用 or 0 兜底）
                user_count = (await db.scalar(select(func.count(User.id)))) or 0

                # 访问次数：Session 数量 + simple 模式下去重 session（chat_turns 中有但 Session 中无）
                session_count = (await db.scalar(select(func.count(Session.id)))) or 0
                distinct_turn_sessions = (
                    await db.scalar(select(func.count(distinct(AnalyticsChatTurn.session_id))))
                ) or 0
                visit_count = max(session_count, distinct_turn_sessions)

                # 每个维度的总对话轮次
                dim_counts = await db.execute(
                    select(AnalyticsChatTurn.dimension, func.count(AnalyticsChatTurn.id))
                    .where(AnalyticsChatTurn.dimension.isnot(None))
                    .group_by(AnalyticsChatTurn.dimension)
                )
                dialogs_by_dimension = {row[0]: row[1] for row in dim_counts.all()}

                # 用户输入总字数
                user_input_total = (
                    await db.scalar(select(func.sum(AnalyticsChatTurn.user_input_chars)))
                ) or 0

                # LLM token 汇总
                llm_input_total = (
                    await db.scalar(select(func.sum(AnalyticsChatTurn.llm_input_tokens)))
                ) or 0
                llm_output_total = (
                    await db.scalar(select(func.sum(AnalyticsChatTurn.llm_output_tokens)))
                ) or 0

                # 报告生成数
                report_count = (await db.scalar(select(func.count(AnalyticsReport.id)))) or 0

                # 最后访问停留维度（按 Session.current_step 统计）
                last_step_counts = await db.execute(
                    select(Session.current_step, func.count(Session.id))
                    .where(Session.current_step.isnot(None))
                    .group_by(Session.current_step)
                )
                last_stop_by_dimension = {row[0]: row[1] for row in last_step_counts.all()}

                # Simple 模式：session 不在 Session 表时，从 chat_turns 按 session 取最后一条的 dimension
                all_turns = await db.execute(
                    select(
                        AnalyticsChatTurn.session_id,
                        AnalyticsChatTurn.dimension,
                        AnalyticsChatTurn.created_at,
                    )
                    .order_by(AnalyticsChatTurn.created_at.desc())
                )
                session_last_dim: Dict[str, str] = {}
                for row in all_turns.all():
                    sid, dim, _ = row
                    if sid and dim and sid not in session_last_dim:
                        session_last_dim[sid] = dim
                session_ids_result = await db.execute(select(Session.id))
                db_sessions = {r[0] for r in session_ids_result.all()}
                for sid, dim in session_last_dim.items():
                    if sid not in db_sessions:
                        last_stop_by_dimension[dim] = last_stop_by_dimension.get(dim, 0) + 1

                # 点赞统计与记录列表
                like_count = (await db.scalar(select(func.count(AnalyticsLike.id)))) or 0
                like_result = await db.execute(
                    select(AnalyticsLike)
                    .order_by(AnalyticsLike.created_at.desc())
                    .limit(200)
                )
                likes = []
                for like in like_result.scalars().all():
                    likes.append({
                        "id": like.id,
                        "session_id": like.session_id,
                        "log_index": like.log_index,
                        "content_preview": like.content_preview,
                        "dimension": like.dimension,
                        "created_at": like.created_at.isoformat() if like.created_at else None,
                    })

            return {
                "user_count": user_count,
                "visit_count": visit_count,
                "dialogs_by_dimension": dialogs_by_dimension,
                "user_input_total_chars": user_input_total,
                "llm_input_tokens": llm_input_total,
                "llm_output_tokens": llm_output_total,
                "report_count": report_count,
                "last_stop_by_dimension": last_stop_by_dimension,
                "like_count": like_count,
                "like_records": likes,
            }
        except Exception as e:
            logger.exception("get_admin_dashboard 失败: %s", e)
            return AnalyticsService._empty_dashboard()
