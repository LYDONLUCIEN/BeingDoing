"""
简单模式对话 API

特点：
- 不使用 LangGraph
- 通过一个较长的 system_prompt + 历史消息，分模块（values/strengths/interests_goals）引导用户
- 会话由「激活码」标识，对话历史保存在 data/simple 下
"""

from typing import Optional, List, AsyncIterator
import json

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.llmapi import get_default_llm_provider, LLMMessage
from app.utils.simple_activation_manager import SimpleActivationManager, ActivationStatus
from app.utils.conversation_file_manager import ConversationFileManager


router = APIRouter(prefix="/simple-chat", tags=["简单模式对话"])


class SimpleChatRequest(BaseModel):
    activation_code: str
    message: str
    # 阶段：values / strengths / interests_goals
    phase: Optional[str] = "values"


class SimpleChatResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: dict


class SimpleInitRequest(BaseModel):
    activation_code: str
    phase: Optional[str] = "values"


class SimpleHistoryResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: dict


class SimpleChatStreamRequest(BaseModel):
    activation_code: str
    message: str
    phase: Optional[str] = "values"


def _build_system_prompt(phase: str) -> str:
    """
    根据阶段构建简单版 system prompt。
    phase: values | strengths | interests_goals
    """
    if phase == "strengths":
        module_text = "你的主要才能、天赋和可以反复利用的优势"
    elif phase in ("interests", "interests_goals", "goals"):
        module_text = "你真正感兴趣、愿意长期投入并希望达成的目标"
    else:
        # 默认按价值观模块处理
        module_text = "真正对你重要的价值观，以及你想怎样生活"

    return f"""你是一名职业生涯与人生规划向导，擅长用非常温柔、细致的方式陪用户对话。

当前任务模块：{module_text}

目标：
1. 通过多轮对话，帮助用户把模糊的感觉、故事和想法说清楚
2. 不要急着下结论，而是一步步澄清、追问、总结
3. 在合适的时机，用自己的话帮用户总结出 3~7 条「核心结论」，包括关键词 + 简短解释

对话原则：
- 每次只问 1~2 个问题，问题要具体、有画面感
- 多用例子帮助用户理解问题含义
- 允许用户停顿、混乱，你要帮他整理
- 不要给标准答案，而是引导用户自己说出答案

输出格式：
- 正常和用户对话时，用自然中文就好
- 当你觉得阶段性总结的时机到了，请在回答结尾用一段清晰的「当前阶段性总结」，例如：
  【阶段性总结】
  1. 价值观A：……
  2. 价值观B：……
  3. 暂时还不确定/存在矛盾的点：……

请直接用中文和用户继续这一轮对话。
"""


@router.post("/message", response_model=SimpleChatResponse)
async def simple_chat(request: SimpleChatRequest):
    """
    简单模式的单轮对话：
    - 使用 activation_code 找到对应的会话与模式
    - 读取历史消息
    - 构造 system_prompt + 历史 + 当前用户消息
    - 调用 LLM 得到回复
    - 将本轮 user / assistant 消息写入 data/simple 下
    """
    manager = SimpleActivationManager()
    rec = manager.get_activation(request.activation_code)
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="激活码不存在",
        )

    if rec.status == ActivationStatus.EXPIRED:
        # 按你的需求：历史数据仍保留，但不再允许继续交互
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="激活码已过期（历史记录已保留，可以用于回放或导出）",
        )

    # 更新最后活跃时间
    manager.touch_activity(rec.code)

    # 使用 data/simple 作为根目录保存对话
    conv_manager = ConversationFileManager(base_dir="data/simple")
    phase = (request.phase or "values").strip() or "values"
    category = phase  # 按阶段区分文件
    session_id = rec.session_id

    # 读取历史消息（只取当前分类）
    history_messages: List[dict] = await conv_manager.get_messages(
        session_id=session_id,
        category=category,
    )

    llm = get_default_llm_provider()

    # 构造 messages：system + 历史 + 当前用户
    system_prompt = _build_system_prompt(phase)
    llm_messages = [LLMMessage(role="system", content=system_prompt)]

    # 把历史文件中的 role/content 转成 LLMMessage
    for m in history_messages:
        role = m.get("role") or "user"
        content = m.get("content") or ""
        if not content:
            continue
        llm_messages.append(LLMMessage(role=role, content=content))

    # 当前用户输入
    llm_messages.append(LLMMessage(role="user", content=request.message))

    # 调用大模型
    response = await llm.chat(llm_messages, temperature=0.7)
    reply_text = response.content or ""

    # 把当前轮 user / assistant 消息写入文件
    await conv_manager.append_message(
        session_id=session_id,
        category=category,
        message={
            "role": "user",
            "content": request.message,
        },
    )


@router.post("/init", response_model=SimpleChatResponse)
async def simple_init(request: SimpleInitRequest):
    """
    初始化某个阶段的对话：
    - 如果该阶段已经有历史消息，则直接返回（不再重复生成）
    - 如果没有历史，则生成一条「首轮引导问题」的 assistant 消息
    """
    manager = SimpleActivationManager()
    rec = manager.get_activation(request.activation_code)
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="激活码不存在",
        )
    if rec.status == ActivationStatus.EXPIRED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="激活码已过期（历史记录已保留，可以用于回放或导出）",
        )

    conv_manager = ConversationFileManager(base_dir="data/simple")
    phase = (request.phase or "values").strip() or "values"
    category = phase
    session_id = rec.session_id

    # 如果已有历史，就直接返回历史
    history_messages: List[dict] = await conv_manager.get_messages(
        session_id=session_id,
        category=category,
    )
    if history_messages:
        return SimpleChatResponse(
            code=200,
            message="success",
            data={
                "messages": history_messages,
                "activation": {
                    "activation_code": rec.code,
                    "session_id": rec.session_id,
                    "mode": rec.mode,
                    "created_at": rec.created_at,
                    "expires_at": rec.expires_at,
                    "status": rec.status,
                },
            },
        )

    # 没有历史：生成一条首轮引导问题
    llm = get_default_llm_provider()
    system_prompt = _build_system_prompt(phase)
    llm_messages = [
        LLMMessage(role="system", content=system_prompt),
        LLMMessage(role="user", content="请给出第一轮温柔而具体的引导问题，让我开始思考。"),
    ]
    response = await llm.chat(llm_messages, temperature=0.7)
    reply_text = response.content or ""

    # 只写入 assistant 消息，作为起始问题
    await conv_manager.append_message(
        session_id=session_id,
        category=category,
        message={
            "role": "assistant",
            "content": reply_text,
        },
    )

    return SimpleChatResponse(
        code=200,
        message="success",
        data={
            "messages": [
                {
                    "role": "assistant",
                    "content": reply_text,
                }
            ],
            "activation": {
                "activation_code": rec.code,
                "session_id": rec.session_id,
                "mode": rec.mode,
                "created_at": rec.created_at,
                "expires_at": rec.expires_at,
                "status": rec.status,
            },
        },
    )


@router.get("/history", response_model=SimpleHistoryResponse)
async def simple_history(activation_code: str, phase: Optional[str] = "values"):
    """
    获取某个激活码 + 阶段下的全部历史消息
    """
    manager = SimpleActivationManager()
    rec = manager.get_activation(activation_code)
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="激活码不存在",
        )

    conv_manager = ConversationFileManager(base_dir="data/simple")
    category = (phase or "values").strip() or "values"
    session_id = rec.session_id

    history_messages: List[dict] = await conv_manager.get_messages(
        session_id=session_id,
        category=category,
    )

    return SimpleHistoryResponse(
        code=200,
        message="success",
        data={
            "messages": history_messages,
            "activation": {
                "activation_code": rec.code,
                "session_id": rec.session_id,
                "mode": rec.mode,
                "created_at": rec.created_at,
                "expires_at": rec.expires_at,
                "status": rec.status,
            },
        },
    )


@router.post("/message/stream")
async def simple_chat_stream(request: SimpleChatStreamRequest):
    """
    简单模式流式对话：
    - 使用 activation_code + phase 区分会话与阶段
    - 保存用户消息
    - 使用 chat_stream 按块返回助手回复
    - 结束时保存完整助手回复
    """
    manager = SimpleActivationManager()
    rec = manager.get_activation(request.activation_code)
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="激活码不存在",
        )
    if rec.status == ActivationStatus.EXPIRED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="激活码已过期（历史记录已保留，可以用于回放或导出）",
        )

    phase = (request.phase or "values").strip() or "values"
    category = phase
    conv_manager = ConversationFileManager(base_dir="data/simple")
    session_id = rec.session_id

    async def event_stream() -> AsyncIterator[str]:
        llm = get_default_llm_provider()

        # 读取历史
        history_messages: List[dict] = await conv_manager.get_messages(
            session_id=session_id,
            category=category,
        )

        system_prompt = _build_system_prompt(phase)
        llm_messages = [LLMMessage(role="system", content=system_prompt)]

        for m in history_messages:
            role = m.get("role") or "user"
            content = m.get("content") or ""
            if not content:
                continue
            llm_messages.append(LLMMessage(role=role, content=content))

        # 当前用户输入
        user_content = (request.message or "").strip()
        if user_content:
            llm_messages.append(LLMMessage(role="user", content=user_content))
            # 先保存用户消息
            await conv_manager.append_message(
                session_id=session_id,
                category=category,
                message={
                    "role": "user",
                    "content": user_content,
                },
            )

        full_reply = ""

        # 发送 started 事件
        yield f"data: {{\"started\": true}}\n\n"

        try:
            async for chunk in llm.chat_stream(llm_messages, temperature=0.7):
                if not chunk:
                    continue
                full_reply += chunk
                yield f"data: {{\"chunk\": {json.dumps(chunk, ensure_ascii=False)} }}\n\n"
        except Exception as e:
            err = str(e)
            yield f"data: {{\"error\": {json.dumps(err, ensure_ascii=False)} }}\n\n"
            return

        # 保存完整助手回复
        if full_reply:
            await conv_manager.append_message(
                session_id=session_id,
                category=category,
                message={
                    "role": "assistant",
                    "content": full_reply,
                },
            )

        yield f"data: {{\"done\": true, \"response\": {json.dumps(full_reply, ensure_ascii=False)} }}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

    await conv_manager.append_message(
        session_id=session_id,
        category=category,
        message={
            "role": "assistant",
            "content": reply_text,
        },
    )

    return SimpleChatResponse(
        code=200,
        message="success",
        data={
            "reply": reply_text,
            "activation": {
                "activation_code": rec.code,
                "session_id": rec.session_id,
                "mode": rec.mode,
                "created_at": rec.created_at,
                "expires_at": rec.expires_at,
                "status": rec.status,
            },
        },
    )

