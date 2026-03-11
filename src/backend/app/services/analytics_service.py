"""
数据分析服务：埋点记录与 Admin 统计聚合
"""
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, Set

from sqlalchemy import select, func, distinct
from app.models.database import AsyncSessionLocal
from app.models.analytics import AnalyticsChatTurn, AnalyticsReport, AnalyticsLike
from app.models.user import User
from app.models.session import Session
from app.utils.data_paths import get_debug_logs_dir, get_logs_dir
from app.utils.simple_activation_manager import get_simple_base_dir

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

    @staticmethod
    def _collect_run_entries() -> List[Tuple[str, int, Dict[str, Any]]]:
        """扫描 data/debug_logs 和 logs/ 下的 runs.jsonl，返回 [(session_id, log_index, entry), ...]。同 session 优先用 debug_logs。"""
        session_to_entries: Dict[str, List[Tuple[int, Dict[str, Any]]]] = {}

        def load_file(path: Path, session_id: str) -> None:
            if not path.is_file():
                return
            if session_id in session_to_entries:
                return  # 已从 debug_logs 加载，不再用 logs 覆盖
            lines: List[Tuple[int, Dict[str, Any]]] = []
            with open(path, "r", encoding="utf-8") as f:
                for idx, line in enumerate(f):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    lines.append((idx, entry))
            if lines:
                session_to_entries[session_id] = lines

        # 1. data/debug_logs/{session_id}.jsonl（主源）
        debug_dir = get_debug_logs_dir()
        if debug_dir.is_dir():
            for f in debug_dir.iterdir():
                if f.suffix == ".jsonl":
                    load_file(f, f.stem)

        # 2. logs/{user_id}/{session_id}/runs.jsonl（补充 debug_logs 没有的 session）
        logs_base = get_logs_dir()
        if logs_base.is_dir():
            for user_dir in logs_base.iterdir():
                if not user_dir.is_dir():
                    continue
                for session_dir in user_dir.iterdir():
                    if not session_dir.is_dir():
                        continue
                    sid = session_dir.name
                    runs_file = session_dir / "runs.jsonl"
                    load_file(runs_file, sid)

        entries: List[Tuple[str, int, Dict[str, Any]]] = []
        for sid, items in session_to_entries.items():
            for idx, entry in items:
                entries.append((sid, idx, entry))
        return entries

    @staticmethod
    def _extract_dimension_from_entry(entry: Dict[str, Any]) -> Optional[str]:
        """从 runs.jsonl 条目中提取维度（从 logs 的 meta.step 或 context）"""
        logs = entry.get("logs") or []
        for log in reversed(logs):
            meta = log if isinstance(log, dict) else {}
            step = meta.get("step") or meta.get("current_step")
            if step:
                return step
        # context_keys 可能包含 current_step
        ctx_keys = entry.get("context_keys") or []
        for k in ctx_keys:
            if "step" in k.lower() or k in (
                "values_exploration", "strengths_exploration", "interests_exploration",
                "combination", "refinement", "values", "strengths", "interests", "purpose",
            ):
                return k
        return None

    @staticmethod
    def _extract_token_usage_from_entry(entry: Dict[str, Any]) -> Tuple[int, int]:
        """从 runs.jsonl 提取 token：优先 token_usage 根字段，其次从 logs 的 meta.token_usage 累加"""
        usage = entry.get("token_usage")
        if isinstance(usage, dict):
            pt = usage.get("prompt_tokens", 0) or 0
            ct = usage.get("completion_tokens", 0) or 0
            if pt or ct:
                return (pt, ct)
        # 从 logs 的 meta.token_usage 累加（reasoning 节点会写入）
        pt_total, ct_total = 0, 0
        for log in entry.get("logs") or []:
            meta = log if isinstance(log, dict) else {}
            tu = meta.get("token_usage")
            if isinstance(tu, dict):
                pt_total += tu.get("prompt_tokens", 0) or 0
                ct_total += tu.get("completion_tokens", 0) or 0
        return (pt_total, ct_total)

    @staticmethod
    async def sync_from_history() -> Dict[str, Any]:
        """
        从 history（runs.jsonl）同步到 analytics 表。
        读取 data/debug_logs 和 logs/ 下的所有运行记录，将缺失的对话轮次写入 AnalyticsChatTurn。
        """
        entries = AnalyticsService._collect_run_entries()

        # 收集已有 (session_id, dimension, log_index)，log_index 可为负（simple 用 -1,-2... 表示轮次）
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AnalyticsChatTurn.session_id, AnalyticsChatTurn.dimension, AnalyticsChatTurn.log_index)
            )
            existing: Set[Tuple[str, str, int]] = set()
            for r in result.all():
                sid, dim, lidx = r[0], r[1] or "", r[2]
                if lidx is not None:
                    existing.add((sid, dim, lidx))

        to_insert: List[AnalyticsChatTurn] = []
        runs_synced = 0
        for session_id, log_index, entry in entries:
            user_input = entry.get("user_input") or ""
            llm_in, llm_out = AnalyticsService._extract_token_usage_from_entry(entry)
            dim = AnalyticsService._extract_dimension_from_entry(entry) or "unknown"
            if (session_id, dim, log_index) in existing:
                continue
            turn = AnalyticsChatTurn(
                session_id=session_id,
                dimension=dim,
                user_input_chars=len(user_input),
                llm_input_tokens=llm_in,
                llm_output_tokens=llm_out,
                log_index=log_index,
            )
            to_insert.append(turn)
            existing.add((session_id, dim, log_index))
            runs_synced += 1

        # 2. 从 data/simple 补充：扫描会话对话文件，按轮次写入（simple 无 token，至少记录轮次）
        simple_dir = get_simple_base_dir()
        simple_synced = 0
        if simple_dir.is_dir():
            for session_dir in simple_dir.iterdir():
                if not session_dir.is_dir():
                    continue
                sid = session_dir.name
                for conv_file in session_dir.glob("*.json"):
                    category = conv_file.stem
                    if "__" in category:
                        dim = category.split("__")[0]
                    else:
                        dim = category
                    if dim not in ("values", "strengths", "interests", "purpose", "combination", "refinement"):
                        continue
                    try:
                        data = json.loads(conv_file.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError):
                        continue
                    messages = data.get("messages") or []
                    turn_idx = 0
                    for i, m in enumerate(messages):
                        if m.get("role") != "user":
                            continue
                        content = m.get("content") or ""
                        log_idx = -(turn_idx + 1)
                        if (sid, dim, log_idx) in existing:
                            turn_idx += 1
                            continue
                        turn = AnalyticsChatTurn(
                            session_id=sid,
                            dimension=dim,
                            user_input_chars=len(content),
                            llm_input_tokens=0,
                            llm_output_tokens=0,
                            log_index=log_idx,
                        )
                        to_insert.append(turn)
                        existing.add((sid, dim, log_idx))
                        simple_synced += 1
                        turn_idx += 1

        if not to_insert:
            return {"synced": 0, "skipped": len(entries), "total_entries": len(entries), "from_simple": simple_synced}

        async with AsyncSessionLocal() as db:
            for turn in to_insert:
                db.add(turn)
            await db.commit()

        logger.info("sync_from_history: runs %d, simple %d", runs_synced, simple_synced)
        return {
            "synced": len(to_insert),
            "skipped": len(entries) - runs_synced,
            "total_entries": len(entries),
            "from_simple": simple_synced,
        }

    @staticmethod
    async def _get_session_metadata_map(session_ids: List[str]) -> Dict[str, Dict[str, Optional[str]]]:
        """为 session_ids 解析 user_id、username、activation_code"""
        result: Dict[str, Dict[str, Optional[str]]] = {sid: {"user_id": None, "username": None, "activation_code": None} for sid in session_ids}
        if not session_ids:
            return result

        # 1. Session 表：session_id -> user_id，User 表 -> username
        try:
            from app.models.session import Session
            from app.models.user import User
            async with AsyncSessionLocal() as db:
                sess_result = await db.execute(
                    select(Session.id, Session.user_id).where(Session.id.in_(session_ids))
                )
                session_to_user: Dict[str, str] = {r[0]: r[1] for r in sess_result.all() if r[1]}
                user_ids = list(set(session_to_user.values()))
                if user_ids:
                    user_result = await db.execute(
                        select(User.id, User.username, User.email).where(User.id.in_(user_ids))
                    )
                    user_info = {r[0]: (r[1] or r[2] or r[0][:8]) for r in user_result.all()}
                    for sid, uid in session_to_user.items():
                        if sid in result:
                            result[sid]["user_id"] = uid
                            result[sid]["username"] = user_info.get(uid)
        except Exception:
            pass

        # 2. activations.json 反向查 session_id -> activation_code
        try:
            act_file = get_simple_base_dir() / "activations.json"
            if act_file.is_file():
                raw = json.loads(act_file.read_text(encoding="utf-8"))
                for code, rec in (raw or {}).items():
                    sid = rec.get("session_id") if isinstance(rec, dict) else getattr(rec, "session_id", None)
                    if sid and sid in result:
                        result[sid]["activation_code"] = code
        except Exception:
            pass

        # 3. logs/{user_id}/{session_id}/ 目录结构
        logs_base = get_logs_dir()
        if logs_base.is_dir():
            for sid in session_ids:
                if result[sid]["user_id"]:
                    continue
                for uid_dir in logs_base.iterdir():
                    if not uid_dir.is_dir() or uid_dir.name == "anonymous":
                        continue
                    if (uid_dir / sid / "runs.jsonl").is_file():
                        result[sid]["user_id"] = uid_dir.name
                        break

        return result

    @staticmethod
    async def get_chat_records_paginated(
        page: int = 1,
        page_size: int = 50,
        dimension: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """分页获取对话轮次明细。session_id 可为 session_id 或 activation_code（自动解析）"""
        # 若传入的可能是激活码，解析出 session_id
        resolved_session_id = session_id
        if session_id and len(session_id) <= 16 and session_id.replace(" ", "").isalnum():
            try:
                act_file = get_simple_base_dir() / "activations.json"
                if act_file.is_file():
                    raw = json.loads(act_file.read_text(encoding="utf-8"))
                    code = session_id.strip().upper()
                    for c, rec in (raw or {}).items():
                        if (c or "").upper() == code:
                            sid = rec.get("session_id") if isinstance(rec, dict) else getattr(rec, "session_id", None)
                            if sid:
                                resolved_session_id = sid
                                break
            except Exception:
                pass

        async with AsyncSessionLocal() as db:
            count_q = select(func.count(AnalyticsChatTurn.id))
            if dimension:
                count_q = count_q.where(AnalyticsChatTurn.dimension == dimension)
            if resolved_session_id:
                count_q = count_q.where(AnalyticsChatTurn.session_id == resolved_session_id)
            total = (await db.scalar(count_q)) or 0
            q = select(AnalyticsChatTurn).order_by(AnalyticsChatTurn.created_at.desc())
            if dimension:
                q = q.where(AnalyticsChatTurn.dimension == dimension)
            if resolved_session_id:
                q = q.where(AnalyticsChatTurn.session_id == resolved_session_id)
            q = q.offset((page - 1) * page_size).limit(page_size)
            result = await db.execute(q)
            rows = result.scalars().all()
        session_ids = list({r.session_id for r in rows})
        meta_map = await AnalyticsService._get_session_metadata_map(session_ids)
        records = [
            {
                "id": r.id,
                "session_id": r.session_id,
                "dimension": r.dimension,
                "user_input_chars": r.user_input_chars,
                "llm_input_tokens": r.llm_input_tokens,
                "llm_output_tokens": r.llm_output_tokens,
                "log_index": r.log_index,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "user_id": meta_map.get(r.session_id, {}).get("user_id"),
                "username": meta_map.get(r.session_id, {}).get("username"),
                "activation_code": meta_map.get(r.session_id, {}).get("activation_code"),
            }
            for r in rows
        ]
        return {"records": records, "total": total, "page": page, "page_size": page_size}

    @staticmethod
    async def get_session_conversation_detail(session_id: str) -> Optional[Dict[str, Any]]:
        """获取 session 完整对话：优先 runs.jsonl，否则从 data/simple 读取"""
        # 1. 尝试 data/debug_logs/{session_id}.jsonl
        debug_path = get_debug_logs_dir() / f"{session_id}.jsonl"
        if debug_path.is_file():
            entries = []
            with open(debug_path, "r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append({"log_index": i, "entry": json.loads(line)})
                    except json.JSONDecodeError:
                        entries.append({"log_index": i, "entry": {"raw": line[:500]}})
            return {"source": "runs", "session_id": session_id, "turns": entries}

        # 2. 尝试 logs/{user_id}/{session_id}/runs.jsonl
        logs_root = get_logs_dir()
        if logs_root.is_dir():
            for user_dir in logs_root.iterdir():
                if not user_dir.is_dir():
                    continue
                runs_file = user_dir / session_id / "runs.jsonl"
                if runs_file.is_file():
                    entries = []
                    with open(runs_file, "r", encoding="utf-8") as f:
                        for i, line in enumerate(f):
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                entries.append({"log_index": i, "entry": json.loads(line)})
                            except json.JSONDecodeError:
                                entries.append({"log_index": i, "entry": {"raw": line[:500]}})
                    return {"source": "runs", "session_id": session_id, "turns": entries}

        # 3. 尝试 data/simple/{session_id}/
        simple_dir = get_simple_base_dir() / session_id
        if simple_dir.is_dir():
            conversations: Dict[str, List[Dict]] = {}
            for conv_file in simple_dir.glob("*.json"):
                try:
                    data = json.loads(conv_file.read_text(encoding="utf-8"))
                    conversations[conv_file.stem] = data.get("messages", [])
                except (json.JSONDecodeError, OSError):
                    conversations[conv_file.stem] = []
            if conversations:
                return {"source": "simple", "session_id": session_id, "conversations": conversations}

        return None
