"""
对话API
"""
from fastapi import APIRouter, HTTPException, Depends, status, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict
from app.api.v1.auth import get_current_user
from app.core.agent.graph import create_agent_graph, create_initial_state
from app.core.database import HistoryDB
from app.models.database import AsyncSessionLocal
from app.utils.conversation_file_manager import ConversationFileManager, ConversationCategory
from datetime import datetime

router = APIRouter(prefix="/chat", tags=["对话"])


class SendMessageRequest(BaseModel):
    """发送消息请求"""
    session_id: str
    message: str
    current_step: str = "values_exploration"
    category: str = "main_flow"  # main_flow, guidance, clarification, other


class GuideRequest(BaseModel):
    """主动引导请求"""
    session_id: str
    current_step: str


class GuidePreferenceRequest(BaseModel):
    """引导偏好请求"""
    session_id: str
    preference: str  # normal, quiet


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
    """发送消息"""
    try:
        user_id = current_user["user_id"] if current_user else None
        
        # 创建智能体图
        graph = create_agent_graph()
        
        # 创建初始状态
        initial_state = create_initial_state(
            user_input=request.message,
            current_step=request.current_step,
            user_id=user_id,
            session_id=request.session_id
        )
        
        # 运行智能体
        final_state = None
        try:
            # LangGraph的astream返回状态字典
            async for state in graph.astream(initial_state):
                # state是一个字典，包含所有节点的输出
                # 获取最后一个节点的状态
                if isinstance(state, dict):
                    # 如果有多个节点，取最后一个
                    node_name = list(state.keys())[-1] if state else None
                    if node_name:
                        final_state = state[node_name]
                    else:
                        final_state = state
                else:
                    final_state = state
        except Exception as e:
            # 如果智能体运行失败，返回错误
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"智能体运行失败: {str(e)}"
            )
        
        # 获取最终响应
        response = final_state.get("final_response") if final_state else "抱歉，我无法处理您的请求。"
        error = final_state.get("error") if final_state else None
        
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
        
        # 添加用户消息
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
        
        return StandardResponse(
            code=200,
            message="success",
            data={
                "response": response,
                "session_id": request.session_id,
                "tools_used": final_state.get("tools_used", []) if final_state else []
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
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
