"""
优化的对话 API - 集成 Graph 缓存和完整上下文加载

优化特性：
1. Graph 缓存（15分钟 TTL，最多 20 个 session）
2. 完整上下文加载（all_flow + note + 压缩策略）
3. 三种对话文件分类：
   - all_flow.json: 完整对话（原文 + AI 思考过程）
   - main_flow.json: 用户可见的咨询对话
   - note.json: AI 总结的结论性内容

4. 自动保存 note.json（结论性内容）
"""
import asyncio
import json
import os
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Generator

from app.api.v1.auth import get_current_user
# ===== 使用优化的模块 =====
from app.core.agent.graph_optimized import (
    create_agent_graph,
    create_initial_state,
    save_context_after_agent,
)
from app.core.agent.graph_cache import get_graph_cache, get_or_create_graph
from app.utils.enhanced_conversation_manager import (
    EnhancedConversationFileManager,
    ConversationCategoryType,
)
# 保持向后兼容的导入（如果新模块有问题）
try:
    from app.core.agent.graph import (
        _load_question_progress,
        _save_question_progress,
        _extract_step_progress_info,
    )
except ImportError:
    # 降级方案
    from app.api.v1.chat import (
        _load_question_progress,
        _save_question_progress,
        _extract_step_progress_info,
    )

from app.core.database import HistoryDB
from app.models.database import AsyncSessionLocal
from app.config.settings import settings


router = APIRouter(prefix="/chat-optimized", tags=["对话（优化版）"])


# ========== 请求/响应模型 ==========

class SendMessageRequestOptimized(BaseModel):
    """发送消息请求（优化版）"""
    session_id: str
    message: str
    current_step: str
    category: str = "main_flow"  # main_flow, guidance, clarification, other
    force_regenerate_card: bool = False
    # ===== 新增参数 =====
    use_cache: bool = True  # 是否使用 Graph 缓存
    load_full_context: bool = True  # 是否加载完整上下文


class StandardResponse(BaseModel):
    """标准响应"""
    code: int = 200
    message: str = "success"
    data: dict


# ========== 辅助函数 ==========

def _get_enhanced_manager() -> EnhancedConversationFileManager:
    """获取增强的对话管理器"""
    return EnhancedConversationFileManager(
        base_dir=settings.CONVERSATION_DIR
    )


async def _save_note_conclusion(
    session_id: str,
    current_step: str,
    context: dict,
    manager: EnhancedConversationFileManager
):
    """
    保存 AI 总结的结论性内容到 note.json

    提取来源：
    - context.summaries: 每个步骤的摘要
    - context.profile: 用户画像和洞察
    - context.profile.notes: 最近的关键洞察
    """
    summaries = context.get("summaries", {})
    profile = context.get("profile", {})

    note_content_parts = []

    # 1. 步骤摘要
    if summaries:
        note_content_parts.append("## 步骤摘要\n")
        for step, summary in summaries.items():
            note_content_parts.append(f"### {step}\n{summary}\n")

    # 2. 用户画像和关键洞察
    if profile:
        note_content_parts.append("\n## 用户画像\n")

        # 基本信息
        if profile.get("user_info"):
            user_info = profile["user_info"]
            note_content_parts.append(f"- 性别: {user_info.get('gender', '未知')}")
            note_content_parts.append(f"- 年龄: {user_info.get('age', '未知')}")

        # 关键洞察（取最近 5 条）
        notes_list = profile.get("notes", [])
        if notes_list:
            note_content_parts.append("\n### 关键洞察\n")
            for note in notes_list[-5:]:  # 最近 5 条
                note_content_parts.append(f"- {note.get('analysis', '')}")

        # 矛盾点
        contradictions = profile.get("contradictions", [])
        if contradictions:
            note_content_parts.append("\n### 需要关注的矛盾点\n")
            for c in contradictions:
                note_content_parts.append(f"- {c.get('step', '')}: {c.get('keyword')} (冲突: {c.get('a')} vs {c.get('b')})")

    # 保存到 note.json
    if note_content_parts:
        await manager.save_note(
            session_id=session_id,
            note_content="\n".join(note_content_parts),
            note_type="summary",
            metadata={
                "current_step": current_step,
                "total_summaries": len(summaries),
                "generated_at": datetime.utcnow().isoformat() + "Z"
            }
        )


@router.post("/messages/stream")
async def send_message_stream_optimized(
    request: SendMessageRequestOptimized,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    优化的流式对话端点

    主要优化：
    1. 使用 Graph 缓存（避免每次编译）
    2. 加载完整上下文（all_flow + note）
    3. 自动保存结论性 note
    """
    async def event_stream():
        try:
            # 1. 发送 started 事件
            yield f"data: {json.dumps({'started': True}, ensure_ascii=False)}\n\n"

            enhanced_manager = _get_enhanced_manager()
            user_id = current_user["user_id"] if current_user else None

            # 2. 保存用户消息到 main_flow（用户可见对话）
            if request.message.strip():
                await enhanced_manager.append_main_flow_message(
                    session_id=request.session_id,
                    role="user",
                    content=request.message,
                    metadata={"current_step": request.current_step}
                )

            # 3. 创建或获取缓存的 Graph（核心优化）
            from app.core.agent.config import AgentRunConfig
            config = AgentRunConfig(use_user_agent_node=True, max_iterations=10)

            if request.use_cache:
                # 使用缓存优先
                graph = get_or_create_graph(
                    session_id=request.session_id,
                    graph_factory=create_agent_graph,
                    config=config
                )
            else:
                # 每次创建新的
                graph = create_agent_graph(config)

            # 4. 创建初始状态（加载完整上下文）
            saved_qp = _load_question_progress(request.session_id)

            initial_state = await create_initial_state(
                user_input=request.message,
                current_step=request.current_step,
                user_id=user_id,
                session_id=request.session_id,
                stream_queue=asyncio.Queue(),
                question_progress=saved_qp,
                force_regenerate_card=request.force_regenerate_card,
                load_full_context=request.load_full_context,
                enhanced_manager=enhanced_manager,
            )

            final_holder = {}
            stream_queue = initial_state["stream_queue"]

            async def run_graph():
                last = None
                try:
                    async for state in graph.astream(initial_state):
                        if isinstance(state, dict):
                            node_name = list(state.keys())[-1] if state else None
                            last = state[node_name] if node_name else state
                        else:
                            last = state
                finally:
                    final_holder["state"] = last
                    await stream_queue.put(None)  # Signal completion

            task = asyncio.create_task(run_graph())

            # 5. 流式输出
            while True:
                chunk = await stream_queue.get()
                if chunk is None:
                    break
                yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"

            await task

            # 6. 处理最终状态
            final_state = final_holder.get("state")
            if not final_state:
                yield f"data: {json.dumps({'error': 'No final state'}, ensure_ascii=False)}\n\n"
                return

            # 7. 保存完整上下文（all_flow + note）
            await save_context_after_agent(
                session_id=request.session_id,
                state=final_state,
                enhanced_manager=enhanced_manager,
            )

            # 8. 构造响应
            messages = final_state.get("messages") or []
            if messages:
                last_msg = messages[-1]
                response = getattr(last_msg, "content", None) or (
                    last_msg.get("content") if isinstance(last_msg, dict) else None
                )
            else:
                response = final_state.get("final_response") or "抱歉，我无法处理您的请求。"

            err = final_state.get("error")
            if err:
                yield f"data: {json.dumps({'error': err}, ensure_ascii=False)}\n\n"
                return

            logs = final_state.get("logs") or []
            if not logs:
                logs = [{"message": "no internal logs captured", "done": True}]

            # 9. 保存调试日志
            _save_debug_logs(request.session_id, request.message, response, logs, final_state)

            # 10. 持久化 question_progress
            question_progress_data = final_state.get("question_progress", {})
            _save_question_progress(request.session_id, question_progress_data)
            step_progress_info = _extract_step_progress_info(question_progress_data, request.current_step)

            # 11. 构造 answer_card
            answer_card = final_state.get("answer_card")
            answer_card_info = None
            if answer_card and answer_card.get("should_show"):
                answer_card_info = {
                    "question_id": answer_card.get("question_id"),
                    "question_content": answer_card.get("question_content"),
                    "user_answer": answer_card.get("user_answer"),
                    "ai_summary": answer_card.get("ai_summary", ""),
                    "ai_analysis": answer_card.get("ai_analysis", ""),
                    "key_insights": answer_card.get("key_insights", []),
                }

            # 12. 获取 note 内容（新增）
            note_content = None
            notes = await enhanced_manager.get_notes(request.session_id)
            if notes:
                # 获取最新的总结类型笔记
                summary_notes = [n for n in notes if n.get("type") == "summary"]
                if summary_notes:
                    latest_note = summary_notes[-1]
                    note_content = latest_note.get("content", "")

            suggestions = final_state.get("suggestions", [])

            yield f"data: {json.dumps({'done': True, 'response': response, 'answer_card': answer_card_info, 'question_progress': step_progress_info, 'suggestions': suggestions, 'note_content': note_content}, ensure_ascii=False)}\n\n"

            # 13. 保存 assistant 消息到 main_flow
            await enhanced_manager.append_main_flow_message(
                session_id=request.session_id,
                role="assistant",
                content=response,
                metadata={"current_step": request.current_step}
            )

            # 14. 更新会话最后活动时间
            async with AsyncSessionLocal() as db:
                history_db = HistoryDB(db)
                await history_db.update_session(
                    request.session_id,
                    current_step=request.current_step,
                )

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/cache/stats")
async def get_cache_stats():
    """获取缓存统计信息"""
    cache = get_graph_cache()
    stats = cache.get_stats()

    # 获取文件系统统计
    conv_dir = settings.CONVERSATION_DIR
    session_count = 0
    total_files = 0

    if os.path.exists(conv_dir):
        for session_id in os.listdir(conv_dir):
            session_path = os.path.join(conv_dir, session_id)
            if os.path.isdir(session_path):
                session_count += 1
                for filename in os.listdir(session_path):
                    file_path = os.path.join(session_path, filename)
                    if os.path.isfile(file_path):
                        total_files += 1

    return StandardResponse(
        code=200,
        message="success",
        data={
            "graph_cache": stats,
            "conversation_storage": {
                "session_count": session_count,
                "total_files": total_files,
                "base_dir": conv_dir,
            },
            "config": {
                "graph_cache_enabled": settings.GRAPH_CACHE_ENABLED,
                "graph_cache_ttl_minutes": settings.GRAPH_CACHE_TTL_MINUTES,
                "graph_cache_max_size": settings.GRAPH_CACHE_MAX_SIZE,
                "full_context_enabled": settings.FULL_CONTEXT_ENABLED,
                "context_compress_after_rounds": settings.CONTEXT_COMPRESS_AFTER_ROUNDS,
                "context_keep_latest_messages": settings.CONTEXT_KEEP_LATEST_MESSAGES,
            }
        }
    )


@router.post("/cache/clear")
async def clear_cache(session_id: Optional[str] = None):
    """手动清除缓存"""
    cache = get_graph_cache()
    if session_id:
        cache.remove(session_id)
        return StandardResponse(
            code=200,
            message="Cleared",
            data={"session_id": session_id}
        )
    else:
        # 清除所有缓存
        from app.core.agent.graph_cache import _graph_cache
        if _graph_cache:
            _graph_cache._cache.clear()
            _graph_cache._stats = {
                "hits": 0,
                "misses": 0,
                "evictions": 0,
                "expirations": 0,
            }
        return StandardResponse(
            code=200,
            message="All caches cleared",
            data={"cache_size": 0}
        )


# ========== 向后兼容的导入 ==========

# 保持原有函数可访问
from app.utils.enhanced_conversation_manager import ConversationFileManager as OldConversationFileManager

_old_manager = OldConversationFileManager()


def _load_question_progress(session_id: str) -> Dict:
    """向后兼容的题目进度加载"""
    path = os.path.join("data", "question_progress", f"{session_id}.json")
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_question_progress(session_id: str, question_progress: Dict) -> None:
    """向后兼容的题目进度保存"""
    os.makedirs("data/question_progress", exist_ok=True)
    path = os.path.join("data", "question_progress", f"{session_id}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(question_progress, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _extract_step_progress_info(question_progress_data: Dict, current_step: str) -> Optional[Dict]:
    """向后兼容的步骤进度提取"""
    if current_step not in question_progress_data:
        return None
    step_data = question_progress_data[current_step]
    current_index = step_data.get("current_question_index", 0)
    questions = step_data.get("questions", [])
    return {
        "current_question_id": questions[current_index]["question_id"] if current_index < len(questions) else None,
        "current_index": current_index,
        "total_questions": len(questions),
        "completed_count": sum(1 for q in questions if q.get("status") == "completed"),
        "current_question_content": questions[current_index]["question_content"] if current_index < len(questions) else None,
        "is_intro_shown": step_data.get("is_intro_shown", False),
    }


def _save_debug_logs(
    session_id: str,
    user_input: str,
    response: str,
    logs: list,
    final_state: Optional[dict],
) -> None:
    """向后兼容的调试日志保存"""
    log_dir = "logs"
    user_id = final_state.get("user_id") if final_state else None

    if user_id:
        log_dir = os.path.join(log_dir, str(user_id), str(session_id))
    else:
        log_dir = os.path.join(log_dir, "anonymous", str(session_id))

    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "runs.jsonl")

    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "user_id": user_id,
        "session_id": session_id,
        "user_input": user_input,
        "response_preview": (response or "")[:500],
        "logs": logs,
        "tools_used": final_state.get("tools_used", []) if final_state else [],
        "context_keys": list((final_state.get("context") or {}).keys()) if final_state else [],
    }

    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ========== 新增：获取历史 Answer Cards API ==========

@router.get("/answer-cards", response_model=StandardResponse)
async def get_answer_cards(
    session_id: str,
    current_user: Optional[dict] = Depends(get_current_user)
):
    """
    获取会话的所有历史 Answer Cards

    用于前端页面加载时恢复已完成的题目列表
    """
    try:
        manager = _get_enhanced_manager()
        answer_cards = await manager.get_answer_cards(session_id)

        return StandardResponse(
            code=200,
            message="success",
            data={
                "answer_cards": answer_cards,
                "count": len(answer_cards)
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@router.get("/notes", response_model=StandardResponse)
async def get_notes(
    session_id: str,
    current_user: Optional[dict] = Depends(get_current_user)
):
    """
    获取会话的所有笔记（包括 summary 和 answer_cards）

    返回完整的 note.json 内容
    """
    try:
        manager = _get_enhanced_manager()
        notes = await manager.get_notes(session_id)

        # 分类整理
        summaries = [n for n in notes if n.get("type") == "summary"]
        answer_cards_raw = [n for n in notes if n.get("type") == "answer_card"]

        # 解析 answer_cards 的 JSON content
        answer_cards = []
        for ac in answer_cards_raw:
            try:
                content = json.loads(ac.get("content", "{}"))
                answer_cards.append({
                    **content,
                    "created_at": ac.get("created_at"),
                    "note_id": ac.get("id")
                })
            except json.JSONDecodeError:
                continue

        return StandardResponse(
            code=200,
            message="success",
            data={
                "notes": notes,
                "summaries": summaries,
                "answer_cards": answer_cards,
                "summary_count": len(summaries),
                "answer_card_count": len(answer_cards)
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
