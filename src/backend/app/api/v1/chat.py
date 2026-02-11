"""
对话API
"""
import asyncio
import json
import os
import re
from fastapi import APIRouter, HTTPException, Depends, status, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Generator
from app.api.v1.auth import get_current_user
from app.core.agent.graph import create_agent_graph, create_initial_state
from app.core.agent.config import AgentRunConfig
from app.domain import DEFAULT_CURRENT_STEP
from app.core.database import HistoryDB
from app.models.database import AsyncSessionLocal
from app.utils.conversation_file_manager import ConversationFileManager, ConversationCategory
from datetime import datetime
from app.config.settings import settings

router = APIRouter(prefix="/chat", tags=["对话"])

# ---------- question_progress 持久化 ----------

_QP_DIR = os.path.join("data", "question_progress")


def _load_question_progress(session_id: str) -> Dict:
    """从文件加载 session 的 question_progress"""
    path = os.path.join(_QP_DIR, f"{session_id}.json")
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_question_progress(session_id: str, question_progress: Dict) -> None:
    """将 question_progress 持久化到文件"""
    if not question_progress:
        return
    os.makedirs(_QP_DIR, exist_ok=True)
    path = os.path.join(_QP_DIR, f"{session_id}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(question_progress, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _extract_step_progress_info(question_progress_data: Dict, current_step: str) -> Optional[Dict]:
    """从 question_progress_data 中提取当前步骤的进度摘要（返回给前端）"""
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


# ---------- 请求/响应模型 ----------


class SendMessageRequest(BaseModel):
    """发送消息请求（current_step 默认从 domain 读取）"""
    session_id: str
    message: str
    current_step: str = DEFAULT_CURRENT_STEP
    category: str = "main_flow"  # main_flow, guidance, clarification, other


class GuideRequest(BaseModel):
    """主动引导请求"""
    session_id: str
    current_step: str


class GuidePreferenceRequest(BaseModel):
    """引导偏好请求"""
    session_id: str
    preference: str  # normal, quiet


class ResummarizeRequest(BaseModel):
    """用户修改回答后触发重新梳理总结"""
    session_id: str
    current_step: Optional[str] = None


class RecordInterruptRequest(BaseModel):
    """用户点击终止时记录打断与截至内容"""
    session_id: str
    partial_content: str
    current_step: Optional[str] = None


class StandardResponse(BaseModel):
    """标准响应"""
    code: int = 200
    message: str = "success"
    data: dict


@router.post("/messages", response_model=StandardResponse)
async def send_message(
    request: SendMessageRequest,
    current_user: Optional[dict] = Depends(get_current_user),
    background_tasks: BackgroundTasks = None
):
    """发送消息（思考链 + 用户侧输出：用户可见内容来自 user_agent 节点）"""
    try:
        user_id = current_user["user_id"] if current_user else None

        # 加载已有的 question_progress
        saved_qp = _load_question_progress(request.session_id)

        run_config = AgentRunConfig(use_user_agent_node=True)
        graph = create_agent_graph(run_config)

        initial_state = create_initial_state(
            user_input=request.message,
            current_step=request.current_step,
            user_id=user_id,
            session_id=request.session_id,
            question_progress=saved_qp,
        )

        final_state = None
        try:
            async for state in graph.astream(initial_state):
                if isinstance(state, dict):
                    node_name = list(state.keys())[-1] if state else None
                    final_state = state[node_name] if node_name else state
                else:
                    final_state = state
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"智能体运行失败: {str(e)}"
            )

        # 用户可见回复：优先从 messages（user_agent 写入）取最后一条，否则 fallback 到 final_response
        messages = (final_state.get("messages") or []) if final_state else []
        if messages:
            last_msg = messages[-1]
            response = getattr(last_msg, "content", None) or (last_msg.get("content") if isinstance(last_msg, dict) else None)
        else:
            response = None
        if not response and final_state:
            response = final_state.get("final_response")
        if not response:
            response = "抱歉，我无法处理您的请求。"
        error = final_state.get("error") if final_state else None
        logs = final_state.get("logs") or [] if final_state else []

        if error:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error
            )
        
        # 保存对话记录（后台任务）
        conversation_manager = ConversationFileManager()
        category_map = {
            "main_flow": ConversationCategory.MAIN_FLOW,
            "guidance": ConversationCategory.GUIDANCE,
            "clarification": ConversationCategory.CLARIFICATION,
            "other": ConversationCategory.OTHER
        }
        category = category_map.get(request.category, ConversationCategory.MAIN_FLOW)

        # 只保存非空用户消息（空消息用于触发AI引导）
        if request.message.strip():
            await conversation_manager.append_message(
                session_id=request.session_id,
                category=category.value if hasattr(category, 'value') else category,
                message={
                    "role": "user",
                    "content": request.message,
                    "context": {"current_step": request.current_step},
                    "created_at": datetime.utcnow().isoformat() + "Z"
                }
            )
        
        # 添加助手回复
        await conversation_manager.append_message(
            session_id=request.session_id,
            category=category.value if hasattr(category, 'value') else category,
            message={
                "role": "assistant",
                "content": response,
                "context": {"current_step": request.current_step},
                "created_at": datetime.utcnow().isoformat() + "Z"
            }
        )
        
        # 更新会话最后活动时间
        async with AsyncSessionLocal() as db:
            history_db = HistoryDB(db)
            await history_db.update_session(
                request.session_id,
                current_step=request.current_step
            )
        
        # v2.4: 持久化 question_progress 并提取返回信息
        question_progress_data = final_state.get("question_progress", {}) if final_state else {}
        _save_question_progress(request.session_id, question_progress_data)

        step_progress_info = _extract_step_progress_info(question_progress_data, request.current_step)

        # 构造answer_card信息
        answer_card_data = final_state.get("answer_card", {}) if final_state else {}
        answer_card_info = None
        if answer_card_data.get("should_show"):
            answer_card_info = {
                "question_id": answer_card_data.get("question_id"),
                "question_content": answer_card_data.get("question_content"),
                "user_answer": answer_card_data.get("user_answer"),
            }

        return StandardResponse(
            code=200,
            message="success",
            data={
                "response": response,
                "session_id": request.session_id,
                "tools_used": final_state.get("tools_used", []) if final_state else [],
                "logs": logs,
                "question_progress": step_progress_info,  # v2.4: 新增
                "answer_card": answer_card_info,  # v2.4: 新增
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


def _chunk_response_for_stream(text: str, chunk_size: int = 20) -> Generator[str, None, None]:
    """将完整回复按句或按长度切分为小块，便于前端流式展示。chunk_size 较小以更快呈现。"""
    if not (text or "").strip():
        return
    # 先按句号、问号、换行切分，再按长度
    parts = re.split(r"(?<=[。！？\n])", text)
    buf = ""
    for p in parts:
        buf += p
        if len(buf) >= chunk_size or buf.endswith(("\n", "。", "！", "？")):
            if buf.strip():
                yield buf
            buf = ""
    if buf.strip():
        yield buf


def _is_super_admin(user: Optional[dict]) -> bool:
    """是否超级管理员（仅超级管理员可看 debug 日志）"""
    if not user:
        return False
    ids_str = (getattr(settings, "SUPER_ADMIN_USER_IDS", None) or "").strip()
    emails_str = (getattr(settings, "SUPER_ADMIN_EMAILS", None) or "").strip()
    if ids_str and user.get("user_id") in [x.strip() for x in ids_str.split(",") if x.strip()]:
        return True
    if emails_str and user.get("email") in [x.strip() for x in emails_str.split(",") if x.strip()]:
        return True
    return False


def _save_debug_logs(
    session_id: str,
    user_input: str,
    response: str,
    logs: list,
    final_state: Optional[dict],
) -> None:
    """将本次运行的日志追加到 data/debug_logs/{session_id}.jsonl 以及 logs/{user_id}/{session_id}/runs.jsonl"""
    try:
        user_id = (final_state or {}).get("user_id") or None

        # 旧路径：按 session 维度集中存储，便于历史兼容
        debug_dir = os.path.join("data", "debug_logs")
        os.makedirs(debug_dir, exist_ok=True)
        path = os.path.join(debug_dir, f"{session_id}.jsonl")
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "user_id": user_id,
            "session_id": session_id,
            "user_input": user_input,
            "response_preview": (response or "")[:500],
            "logs": logs,
            "tools_used": (final_state or {}).get("tools_used", []),
            "context_keys": list((final_state or {}).get("context") or {}).keys(),
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        # 新路径：按用户 / 会话分目录存储，便于后台人工排查
        if user_id:
            user_log_dir = os.path.join("logs", str(user_id), str(session_id))
        else:
            user_log_dir = os.path.join("logs", "anonymous", str(session_id))
        os.makedirs(user_log_dir, exist_ok=True)
        user_log_path = os.path.join(user_log_dir, "runs.jsonl")
        with open(user_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


@router.post("/messages/stream")
async def send_message_stream(
    request: SendMessageRequest,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """发送消息并流式返回助手回复（SSE）。先发 started，再跑智能体；reasoning 节点使用 chat_stream 边生成边推块，真流式输出。"""
    async def event_stream():
        try:
            yield f"data: {json.dumps({'started': True}, ensure_ascii=False)}\n\n"
            conversation_manager = ConversationFileManager()
            category = "main_flow"
            # 只保存非空用户消息（空消息用于触发AI引导）
            if request.message.strip():
                await conversation_manager.append_message(
                    session_id=request.session_id,
                    category=category,
                    message={
                        "role": "user",
                        "content": request.message,
                        "context": {"current_step": request.current_step},
                        "created_at": datetime.utcnow().isoformat() + "Z",
                    },
                )
            user_id = current_user["user_id"] if current_user else None
            run_config = AgentRunConfig(use_user_agent_node=True)
            graph = create_agent_graph(run_config)
            queue = asyncio.Queue()

            # 加载已有的 question_progress
            saved_qp = _load_question_progress(request.session_id)

            initial_state = create_initial_state(
                user_input=request.message,
                current_step=request.current_step,
                user_id=user_id,
                session_id=request.session_id,
                stream_queue=queue,
                question_progress=saved_qp,
            )
            final_holder = {}

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
                    await queue.put(None)

            task = asyncio.create_task(run_graph())
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"
            await task

            final_state = final_holder.get("state")
            messages = (final_state.get("messages") or []) if final_state else []
            if messages:
                last_msg = messages[-1]
                response = getattr(last_msg, "content", None) or (
                    last_msg.get("content") if isinstance(last_msg, dict) else None
                )
            else:
                response = final_state.get("final_response") if final_state else None
            if not response:
                response = "抱歉，我无法处理您的请求。"
            err = final_state.get("error") if final_state else None
            if err:
                yield f"data: {json.dumps({'error': err}, ensure_ascii=False)}\n\n"
                return

            logs = final_state.get("logs") or [] if final_state else []
            if not logs:
                # 确保至少有一条基础日志，避免 debug-logs 返回完全空数组
                logs = [{"message": "no internal logs captured", "done": True}]
            _save_debug_logs(request.session_id, request.message, response, logs, final_state)

            answer_card = (final_state or {}).get("answer_card")

            # v2.4: 持久化 question_progress 并提取返回信息
            question_progress_data = (final_state or {}).get("question_progress", {})
            _save_question_progress(request.session_id, question_progress_data)
            step_progress_info = _extract_step_progress_info(question_progress_data, request.current_step)

            # 构造 answer_card（只传 should_show=True 的）
            answer_card_info = None
            if answer_card and answer_card.get("should_show"):
                answer_card_info = {
                    "question_id": answer_card.get("question_id"),
                    "question_content": answer_card.get("question_content"),
                    "user_answer": answer_card.get("user_answer"),
                }

            yield f"data: {json.dumps({'done': True, 'response': response, 'answer_card': answer_card_info, 'question_progress': step_progress_info}, ensure_ascii=False)}\n\n"

            await conversation_manager.append_message(
                session_id=request.session_id,
                category=category,
                message={
                    "role": "assistant",
                    "content": response,
                    "context": {"current_step": request.current_step},
                    "created_at": datetime.utcnow().isoformat() + "Z",
                },
            )
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


@router.post("/record-interrupt", response_model=StandardResponse)
async def record_interrupt(
    request: RecordInterruptRequest,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """用户点击终止时记录打断动作与截至之前的助手内容"""
    try:
        conversation_manager = ConversationFileManager()
        category = "main_flow"
        await conversation_manager.append_message(
            session_id=request.session_id,
            category=category,
            message={
                "role": "assistant",
                "content": request.partial_content or "(用户终止)",
                "context": {
                    "current_step": request.current_step,
                    "interrupted": True,
                },
                "created_at": datetime.utcnow().isoformat() + "Z",
            },
        )
        return StandardResponse(code=200, message="success", data={"recorded": True})
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/debug-logs", response_model=StandardResponse)
async def get_debug_logs(
    session_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """获取某会话的智能体调试日志（仅超级管理员）。含思考链、工具调用、logs 等。"""
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅超级管理员可查看调试日志")
    try:
        path = os.path.join("data", "debug_logs", f"{session_id}.jsonl")
        entries = []
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return StandardResponse(code=200, message="success", data={"entries": entries})
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/history", response_model=StandardResponse)
async def get_conversation_history(
    session_id: str,
    category: Optional[str] = None,
    limit: Optional[int] = None,
    current_user: Optional[dict] = Depends(get_current_user)
):
    """获取对话历史"""
    try:
        conversation_manager = ConversationFileManager()
        
        category_map = {
            "main_flow": "main_flow",
            "guidance": "guidance",
            "clarification": "clarification",
            "other": "other"
        }
        
        conv_category = None
        if category:
            conv_category = category_map.get(category)
        
        if conv_category:
            messages = await conversation_manager.get_messages(
                session_id=session_id,
                category=conv_category
            )
        else:
            all_conversations = await conversation_manager.get_all_conversations(session_id)
            messages = []
            for cat_messages in all_conversations.values():
                messages.extend(cat_messages)
        
        # 限制数量
        if limit:
            messages = messages[-limit:]
        
        return StandardResponse(
            code=200,
            message="success",
            data={"messages": messages, "count": len(messages)}
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/guide", response_model=StandardResponse)
async def trigger_guide(
    request: GuideRequest,
    current_user: Optional[dict] = Depends(get_current_user)
):
    """触发主动引导"""
    try:
        from app.services.guide_service import GuideService
        
        service = GuideService()
        guide_message = await service.generate_active_guide_message(
            session_id=request.session_id,
            current_step=request.current_step
        )
        
        # 保存引导消息到对话记录
        conversation_manager = ConversationFileManager()
        await conversation_manager.append_message(
            session_id=request.session_id,
            category="guidance",
            message={
                "role": "assistant",
                "content": guide_message,
                "context": {"current_step": request.current_step},
                "created_at": datetime.utcnow().isoformat() + "Z"
            }
        )
        
        return StandardResponse(
            code=200,
            message="success",
            data={"message": guide_message}
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/guide-preference", response_model=StandardResponse)
async def set_guide_preference(
    request: GuidePreferenceRequest,
    current_user: Optional[dict] = Depends(get_current_user)
):
    """设置引导偏好"""
    try:
        from app.services.guide_service import GuideService
        
        service = GuideService()
        result = await service.set_guide_preference(
            session_id=request.session_id,
            preference=request.preference
        )
        
        return StandardResponse(
            code=200,
            message="设置成功",
            data=result
        )
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/resummarize", response_model=StandardResponse)
async def resummarize_after_edit(
    request: ResummarizeRequest,
    current_user: Optional[dict] = Depends(get_current_user)
):
    """用户修改回答后触发后台思考智能体重新梳理和总结（当前返回成功，后续可接入智能体重算 step_summary）"""
    # TODO: 接入 agent 根据该步骤最新回答重新生成 step_summary 并持久化
    return StandardResponse(
        code=200,
        message="success",
        data={"triggered": True, "session_id": request.session_id, "current_step": request.current_step}
    )
