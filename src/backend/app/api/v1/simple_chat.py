"""
简单模式对话 API

特点：
- 不使用 LangGraph
- 通过一个较长的 system_prompt + 历史消息，分模块（values/strengths/interests_goals）引导用户
- 会话由「激活码」标识，对话历史保存在 data/simple 下
"""

from typing import Optional, List, AsyncIterator
import json
import random

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.llmapi import get_default_llm_provider, LLMMessage
from app.core.knowledge.loader import KnowledgeLoader
from app.utils.simple_activation_manager import SimpleActivationManager, ActivationStatus
from app.utils.conversation_file_manager import ConversationFileManager
from app.utils.survey_storage import (
    save_basic_info,
    load_basic_info,
    format_basic_info_for_prompt,
    save_prior_context,
    load_prior_context,
)

# 每阶段随机抽取的题目数量
SIMPLE_QUESTION_SAMPLE_SIZE = 6
SIMPLE_BASE_DIR = "data/simple"

router = APIRouter(prefix="/simple-chat", tags=["简单模式对话"])


def _phase_to_loader_category(phase: str) -> str:
    """simple_chat 的 phase 映射到 KnowledgeLoader 的 category"""
    if phase == "values":
        return "values"
    if phase == "strengths":
        return "strengths"
    if phase in ("interests", "interests_goals", "goals"):
        return "interests"
    if phase == "purpose":
        return "values"  # purpose 阶段复用 values 题库，或可后续单独建
    return "values"


def _get_random_questions_for_phase(phase: str, n: int = SIMPLE_QUESTION_SAMPLE_SIZE) -> str:
    """
    从 question.md 中按阶段加载问题，随机抽取 n 个，格式化为字符串。
     phase: values | strengths | interests_goals
    """
    try:
        loader = KnowledgeLoader()
        all_questions = loader.load_questions()
        category = _phase_to_loader_category(phase)
        phase_questions = [q for q in all_questions if q.category == category]
        if not phase_questions:
            return "（暂无该阶段题库）"
        sampled = random.sample(phase_questions, min(n, len(phase_questions)))
        lines = [f"{i+1}. {q.content}" for i, q in enumerate(sampled)]
        return "\n".join(lines)
    except Exception:
        return "（题库加载失败）"


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


class SurveySaveRequest(BaseModel):
    activation_code: str
    survey_data: dict


class PriorContextSaveRequest(BaseModel):
    activation_code: str
    phase: str       # 目标阶段，如 "strengths" / "interests_goals"
    context_text: str


def _load_basic_info_from_activation(activation_code: str) -> str:
    """根据激活码加载 basic_info，格式化为提示词用文本"""
    manager = SimpleActivationManager()
    rec = manager.get_activation(activation_code)
    if not rec:
        return "暂无"
    data = load_basic_info(rec.session_id, SIMPLE_BASE_DIR)
    return format_basic_info_for_prompt(data)


def _load_prior_context_from_activation(activation_code: str, phase: str) -> str:
    """根据激活码和阶段加载上一轮咨询结果文本"""
    manager = SimpleActivationManager()
    rec = manager.get_activation(activation_code)
    if not rec:
        return ""
    return load_prior_context(rec.session_id, phase, SIMPLE_BASE_DIR)


@router.get("/survey")
def get_survey(activation_code: str):
    """获取指定激活码下的调研问卷数据"""
    manager = SimpleActivationManager()
    rec = manager.get_activation(activation_code)
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="激活码不存在",
        )
    data = load_basic_info(rec.session_id, SIMPLE_BASE_DIR)
    return SimpleChatResponse(
        code=200,
        message="success",
        data={"survey_data": data or {}},
    )


@router.get("/prior-context")
def get_prior_context(activation_code: str, phase: str):
    """获取指定阶段的上一轮咨询结果文本"""
    manager = SimpleActivationManager()
    rec = manager.get_activation(activation_code)
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="激活码不存在")
    text = load_prior_context(rec.session_id, phase, SIMPLE_BASE_DIR)
    return SimpleChatResponse(code=200, message="success", data={"context_text": text})


@router.post("/prior-context", response_model=SimpleChatResponse)
def save_prior_context_endpoint(request: PriorContextSaveRequest):
    """保存（上传）指定阶段的上一轮咨询结果文本"""
    manager = SimpleActivationManager()
    rec = manager.get_activation(request.activation_code)
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="激活码不存在")
    if rec.status == ActivationStatus.EXPIRED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="激活码已过期")
    save_prior_context(rec.session_id, request.phase, request.context_text or "", SIMPLE_BASE_DIR)
    return SimpleChatResponse(code=200, message="success", data={})


@router.post("/survey", response_model=SimpleChatResponse)
def save_survey(request: SurveySaveRequest):
    """保存调研问卷数据到指定激活码的会话下"""
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
            detail="激活码已过期",
        )
    save_basic_info(rec.session_id, request.survey_data or {}, SIMPLE_BASE_DIR)
    return SimpleChatResponse(code=200, message="success", data={})


def _build_system_prompt(
    phase: str,
    question_bank: str = "",
    basic_info: str = "暂无",
    prior_context: str = "",
) -> str:
    """
    根据阶段构建 system prompt。
    phase: values | strengths | interests_goals
    question_bank: 从 question.md 随机抽取的题目文本
    basic_info: 来访者基本信息（调研问卷）
    prior_context: 上一阶段咨询结果（values → 空；strengths → values 结果；interests_goals → strengths+values 结果）
    """
    prior_block = f"\n\n以下是该来访者在上一轮咨询中的谈话结果，供你参考：\n{prior_context}" if prior_context.strip() else ""

    if phase == "values":
        return f"""你是一名专业的职业规划咨询师，你需要帮助用户一起探索其职业发展的可能性。目前你正在进行第一轮咨询，主题是帮助用户发现其经过收敛的5个价值观关键词，即在职业规划中对其最重要的5件事。以下是你的咨询方法：
1、先向用户提问：你能否直接告诉我你的5个价值观关键词？
2、若用户给出关键词，无论多少，先记录下来。若用户给不出关键词，则直接进行下一步。
3、进入正式问题提问环节。对于提出的每一个问题，帮助用户从该问题的答案中发现价值观关键词。根据用户的回答进行追问，直到用户可以清晰地说出其答案反映出来的价值观关键词。
4、提的问题不一定针对工作，也可以是生活中发生的事情或者对未来的畅想等等。以下是可供选择的题库：
{question_bank}
5、根据你和用户沟通的答案，对应第一个问题中用户自己给出的价值观关键词。如果有重复的，记录其权重+1；对于新出现的，向用户确认是否可以加入关键词序列。
6、重复该提问过程，直到：1）关键词收敛，即发现无论再问什么问题都提取不出新的关键词才算关键词收敛；或 2）提出的独立问题（新提出的问题，不包括追问）数目超过10个。
7、当关键词收敛后，提出问题，引导用户针对优先级给关键词排序。若关键词过多，则需要引导用户对关键词进行合并或删减且给出自己对关键词的解释。若合并之后数量少于5个，则需要继续进行提问，帮助用户发现更多未发现的关键词。若用户对如何排序不确定，则需要继续提问引导用户明确。
8、向用户确认排序结果。

你需要做到：
1. 给用户回答问题的空间，而不是直接给出答案。如果用户实在回答不出来，可以做一些引导。
2. 每一次轮对话只能向用户提出一个问题。
3. 关键词收敛后，需要对比答案记录过程中的权重和用户最终自己排序结果的优先级，如果有区别，进一步向用户提问明确这样差异存在的原因；如果无区别，则按照排序结果。
4. 最终的结果返回5个收敛的关键词及其解释。注意，并不是关键词到达5个后就算收敛，而是发现无论再问什么问题都提取不出新的关键词才算关键词收敛。
5. 如果在过程中出现了关键词不足5个的情况，需要再重复步骤3-8，直到最后用户确认5个关键词为止。

来访者基本信息：{basic_info}{prior_block}

请直接用中文和用户继续这一轮对话。"""

    if phase == "strengths":
        return f"""你是一名专业的职业规划咨询师，你需要帮助用户一起探索其职业发展的可能性。目前你正在进行第二轮咨询，主题是帮助用户发现其10件擅长的事。以下是你的咨询方法：
1、先向用户提问：你自己认为你的优势有哪些？
2、若用户给出答案，无论多少，先记录下来。若用户给不出答案，则直接进行下一步。
3、进入正式问题提问环节。对于提出的每一个问题，帮助用户从该问题的答案中发现其擅长的事。根据用户的回答进行追问，直到用户可以清晰地说出其答案反映出来的擅长的事。
4、提的问题不一定针对工作，也可以是生活中发生的事情或者对未来的畅想等等。以下是可供选择的题库：
{question_bank}
5、根据你和用户沟通的答案，对应第一个问题中用户自己给出的答案。如果有重复的，记录其权重+1；对于新出现的，向用户确认是否可以加入序列。
6、重复该提问过程，直到提取出10个擅长的事。
7、当用户确认后，引导用户针对擅长的事进行标记，同时解释标签体系的含义。标记体系：a. 有充实感，与成功有关；b. 有充实感；c. 目前还不确定。
8、向用户确认标记结果。告知用户需要进行下一轮咨询：探索"喜欢的事"。

你需要做到：
1. 给用户回答问题的空间，而不是直接给出答案。如果用户实在回答不出来，可以做一些引导。
2. 每一次轮对话只能向用户提出一个问题。
3. 如果在过程中出现了关键词不足10个的情况，或者用户不认可某一项擅长的事，需要再重复提问，直到最后用户确认10件擅长的事为止。
4. 提问需要有差异化，防止钻牛角尖。
5. 提取出的擅长的事之间不能有重复。

来访者基本信息：{basic_info}{prior_block}

请直接用中文和用户继续这一轮对话。"""

    if phase in ("interests", "interests_goals", "goals"):
        return f"""你是一名专业的职业规划咨询师，你需要帮助用户一起探索其职业发展的可能性。目前你正在进行第三轮咨询，主题是帮助用户发现其喜欢的事（热情）与目标。以下是你的咨询方法：
1、先向用户提问：你喜欢做哪些事情？哪些事情让你感到充满热情和意义？
2、若用户给出答案，无论多少，先记录下来。若用户给不出答案，则直接进行下一步。
3、进入正式问题提问环节。对于提出的每一个问题，帮助用户从该问题的答案中发现其喜欢的事。根据用户的回答进行追问，直到用户可以清晰地说出其答案反映出来的热情所在。
4、提的问题不一定针对工作，也可以是生活中发生的事情或者对未来的畅想等等。以下是可供选择的题库：
{question_bank}
5、根据你和用户沟通的答案，梳理出用户的热情领域。如果有重复的，记录其权重+1；对于新出现的，向用户确认是否可以加入序列。
6、重复该提问过程，直到热情领域收敛。
7、引导用户结合上一轮探索出的价值观和擅长的事，思考其热情与它们的交集，找到最有意义的方向。
8、向用户确认最终的热情领域列表。

你需要做到：
1. 给用户回答问题的空间，而不是直接给出答案。如果用户实在回答不出来，可以做一些引导。
2. 每一次轮对话只能向用户提出一个问题。
3. 充分利用来访者上一轮的咨询结果（价值观和擅长的事）来帮助用户发现热情与它们之间的联系。

来访者基本信息：{basic_info}{prior_block}

请直接用中文和用户继续这一轮对话。"""

    if phase == "purpose":
        return f"""你是一名专业的职业规划咨询师，你需要帮助用户一起探索其职业发展的可能性。目前你正在进行第四轮咨询，主题是帮助用户探索其「使命感」——即工作对于他们来说更深层的目的与意义。以下是你的咨询方法：
1、先向用户提问：你觉得你为什么而工作？仅仅是为了生存、还是有更深的意义？
2、若用户给出答案，先记录下来，进行追问，帮助用户深化对"目的"的认识。
3、进入正式问题提问环节。对于提出的每一个问题，帮助用户从该问题的答案中发现其工作的深层目的。根据用户的回答进行追问。
4、提的问题可以是：如果金钱不是问题，你会做什么？你希望在这个世界留下什么？你最不愿意看到的未来是什么？以下是可供选择的题库：
{question_bank}
5、帮助用户整合已经探索的信念（价值观）、禀赋（擅长的事）、热忱（喜欢的事），引导他们思考：这些维度汇聚之处，指向了怎样的使命？
6、引导用户用一句话或一个短语表达自己的使命宣言，例如"帮助普通人做出更好的决策"。
7、向用户确认使命宣言，并做简短的总结。

你需要做到：
1. 给用户回答问题的空间，而不是直接给出答案。如果用户实在回答不出来，可以做一些引导。
2. 每一次轮对话只能向用户提出一个问题。
3. 使命宣言应该是真实的、具体的，避免过于宏大或空洞。
4. 结合前三轮的探索结果，帮助用户发现各维度之间的内在联系。

来访者基本信息：{basic_info}{prior_block}

请直接用中文和用户继续这一轮对话。"""

    return _build_system_prompt("values", question_bank, basic_info, prior_context)


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

    # 从 question.md 按阶段随机抽取题目，动态注入提示词
    question_bank = _get_random_questions_for_phase(phase)
    basic_info = _load_basic_info_from_activation(request.activation_code)
    prior_context = _load_prior_context_from_activation(request.activation_code, phase)
    system_prompt = _build_system_prompt(phase, question_bank=question_bank, basic_info=basic_info, prior_context=prior_context)
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
    question_bank = _get_random_questions_for_phase(phase)
    basic_info = _load_basic_info_from_activation(request.activation_code)
    prior_context = _load_prior_context_from_activation(request.activation_code, phase)
    system_prompt = _build_system_prompt(phase, question_bank=question_bank, basic_info=basic_info, prior_context=prior_context)
    llm_messages = [
        LLMMessage(role="system", content=system_prompt),
        LLMMessage(role="user", content="我是来访者，你需要向我提问。以下是我的基本信息：暂无。请给出第一轮温柔而具体的引导问题，让我开始思考。"),
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

        question_bank = _get_random_questions_for_phase(phase)
        basic_info = _load_basic_info_from_activation(request.activation_code)
        prior_context = _load_prior_context_from_activation(request.activation_code, phase)
        system_prompt = _build_system_prompt(phase, question_bank=question_bank, basic_info=basic_info, prior_context=prior_context)
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

