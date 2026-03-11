"""
简单模式对话 API

特点：
- 不使用 LangGraph
- 通过一个较长的 system_prompt + 历史消息，分模块（values/strengths/interests）引导用户
- 会话由「激活码」标识，对话历史保存在 data/simple 下
"""

from typing import Optional, List, AsyncIterator
import asyncio
import json
import random

from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.core.llmapi import get_default_llm_provider, LLMMessage
from app.api.v1.auth import get_current_user_optional, _is_debug_admin
from app.config.settings import settings
from app.core.knowledge.loader import KnowledgeLoader
from app.utils.simple_activation_manager import SimpleActivationManager, ActivationStatus, get_simple_base_dir
from app.utils.conversation_file_manager import ConversationFileManager
from app.core.dimension_completion_checker import (
    check_dimension_complete,
    detect_explicit_completion,
    _should_run_completion_check,
)
from app.services.analytics_service import AnalyticsService
from app.utils.survey_storage import (
    save_basic_info,
    load_basic_info,
    format_basic_info_for_prompt,
    save_prior_context,
    load_prior_context,
)

# 每阶段随机抽取的题目数量
SIMPLE_QUESTION_SAMPLE_SIZE = 6
SIMPLE_BASE_DIR = str(get_simple_base_dir())

router = APIRouter(prefix="/simple-chat", tags=["简单模式对话"])


def _skip_expired_for_debug(rec, user: Optional[dict]) -> bool:
    """Debug 管理员可跳过过期检查"""
    return (
        getattr(settings, "DEBUG_MODE", False)
        and _is_debug_admin(user)
        and rec.status == ActivationStatus.EXPIRED
    )


def _storage_category(phase: str, thread_id: Optional[str] = None) -> str:
    """存储用 category：有 thread_id 则独立文件，实现多对话隔离"""
    if thread_id:
        return f"{phase}__{thread_id}"
    return phase


def _phase_to_loader_category(phase: str) -> str:
    """simple_chat 的 phase 映射到 KnowledgeLoader 的 category"""
    if phase == "values":
        return "values"
    if phase == "strengths":
        return "strengths"
    if phase == "interests":
        return "interests"
    if phase == "purpose":
        return "values"  # purpose 阶段复用 values 题库，或可后续单独建
    return "values"


def _get_random_questions_for_phase(phase: str, n: int = SIMPLE_QUESTION_SAMPLE_SIZE) -> str:
    """
    从 question.md 中按阶段加载问题，随机抽取 n 个，格式化为字符串。
     phase: values | strengths | interests
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
    # 阶段：values / strengths / interests
    phase: Optional[str] = "values"


class SimpleChatResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: dict


class SimpleInitRequest(BaseModel):
    activation_code: str
    phase: Optional[str] = "values"
    thread_id: Optional[str] = None  # 新建对话时传入，后端按 thread_id 创建独立存储


class SimpleHistoryResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: dict


class SimpleChatStreamRequest(BaseModel):
    activation_code: str
    message: str
    phase: Optional[str] = "values"
    thread_id: Optional[str] = None  # 当前对话 id，用于加载/保存到对应记录


class SurveySaveRequest(BaseModel):
    activation_code: str
    survey_data: dict


class PriorContextSaveRequest(BaseModel):
    activation_code: str
    phase: str       # 目标阶段，如 "strengths" / "interests"
    context_text: str


class ThreadCompleteRequest(BaseModel):
    activation_code: str
    phase: str
    thread_id: str


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
async def save_prior_context_endpoint(
    request: PriorContextSaveRequest,
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
    """保存（上传）指定阶段的上一轮咨询结果文本"""
    manager = SimpleActivationManager()
    rec = manager.get_activation(request.activation_code)
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="激活码不存在")
    if rec.status == ActivationStatus.EXPIRED and not _skip_expired_for_debug(rec, current_user):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="激活码已过期")
    save_prior_context(rec.session_id, request.phase, request.context_text or "", SIMPLE_BASE_DIR)
    return SimpleChatResponse(code=200, message="success", data={})


@router.post("/survey", response_model=SimpleChatResponse)
async def save_survey(
    request: SurveySaveRequest,
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
    """保存调研问卷数据到指定激活码的会话下"""
    manager = SimpleActivationManager()
    rec = manager.get_activation(request.activation_code)
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="激活码不存在",
        )
    if rec.status == ActivationStatus.EXPIRED and not _skip_expired_for_debug(rec, current_user):
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
    phase: values | strengths | interests
    question_bank: 从 question.md 随机抽取的题目文本
    basic_info: 来访者基本信息（调研问卷）
    prior_context: 上一阶段咨询结果（values → 空；strengths → values 结果；interests → strengths+values 结果）
    """
    prior_block = f"\n\n以下是该来访者在上一轮咨询中的谈话结果，供你参考：\n{prior_context}" if prior_context.strip() else ""

    if phase == "values":
        return f"""你是一名专业的职业规划咨询师，正在进行第一轮咨询。本轮咨询的目标是：**帮助用户发现并确认对其职业发展最重要的5个价值观关键词**。

请严格遵循以下咨询流程和方法。

### 咨询流程

1. **开场提问**：直接询问用户："你能否直接告诉我，在你心中对你最重要的5个价值观关键词是什么？"（例如：成就感、稳定、创新、人际关系等）
2. **记录初始答案**：
   - 如果用户给出了任何关键词（无论数量多少），请全部记录下来，并标记为"用户自述"。
   - 如果用户无法给出任何关键词，或给出的不足5个，请记录下来，并继续下一步。
3. **深度提问探索**：进入正式的问题探索环节。
   - **提问原则**：每次只向用户提出**一个**问题。问题可以不局限于工作，可以涉及生活、过往经历、未来畅想等，目的是从用户的回答中挖掘潜在的价值观。
   - **追问技巧**：根据用户的回答进行追问，引导用户深入思考，直到用户自己能清晰地总结出："这对我来说，意味着[价值观关键词]很重要。"
   - **记录关键词**：每从一个问题中提炼出关键词，就记录下来，并标记为"探索发现"。
4. **整合与确认**：
   - **对比初始答案**：将"探索发现"的关键词与第一步中用户"用户自述"的关键词进行对比。
   - 如果重复出现，则在该关键词旁记录"权重+1"。
   - 如果出现全新的关键词，向用户确认："通过刚才的讨论，我们发现了[新关键词]这个价值观，你觉得它对你来说重要吗？可以加入你的价值观列表吗？"
5. **收敛判断**：持续进行提问探索，直到满足以下任一条件：
   - **收敛条件**：无论再提出什么新问题，都无法从用户的回答中提炼出任何新的价值观关键词。
   - **数量上限**：提出的独立新问题（不包括追问）累计达到10个。
   - **注意**：达到5个关键词并不代表收敛，必须确认无法再发现新的关键词才算收敛。
6. **排序与整合**：
   - **引导排序**：当关键词收敛后，请用户对所有已确认的关键词（包括用户自述和探索发现的）进行优先级排序。
   - **合并与删减**：如果关键词过多（超过5个），引导用户合并含义相近的词，或删减相对不重要的词，并请用户给出自己对每个关键词的理解和解释。如果合并后数量**少于5个**，则需继续重复步骤3-5的提问探索。
   - **核对差异**：在用户给出排序后，将其排序结果与你记录过程中的"权重"进行对比。如果存在明显差异，向用户提问以澄清原因；如果无差异，则直接采用用户的排序。
7. **最终确认**：向用户呈现最终结果："我们最终确定了对你最重要的5个价值观关键词，按优先级排序是：1. [关键词]（你的解释），2. [关键词]（你的解释）…… 你确认这个结果吗？"
8. **结束对话**：用户确认后，本轮咨询结束。告知用户："恭喜你完成了第一轮价值观探索。下一轮我们将进入优势探索，帮助你发现你的核心能力。我们下次见。"

### 重要准则

- **引导而非灌输**：始终给用户思考和回答的空间，不要直接替用户下结论。
- **一次一问**：严格遵守每轮对话只提一个问题。
- **完整收敛**：务必确认无论问什么都无法再提取新词，才算收敛，不能因为凑够5个就停止。
- 【对话续写】若对话已有历史，必须在已有探索基础上继续深挖，禁止重复开场式提问（如「你的价值观是什么」）或泛泛寒暄，应基于用户已有回答进行追问和深化。

### 题库参考

以下题库可供选择，你也可以根据对话情境灵活提问：
{question_bank}

来访者基本信息：{basic_info}{prior_block}

请直接用中文和用户继续这一轮对话。"""

    if phase == "strengths":
        return f"""你是一名专业的职业规划咨询师，正在进行第二轮咨询。本轮咨询的目标是：**帮助用户发现并确认其最突出的10个优势**。

请先以友好、专业的态度与用户打招呼，然后按照以下流程和方法开展咨询。

### 咨询流程

1. **开场提问**：直接询问用户："你自己认为你的优势有哪些？请尽量列举。"
   - 如果用户给出了任何答案，请全部记录下来，标记为"用户自述"。
   - 如果用户无法给出任何答案，或给出的数量不足，请记录下来，并继续下一步。
2. **深度提问探索**：进入正式的问题探索环节。
   - **提问原则**：每次只向用户提出**一个**问题。问题可以不局限于工作，可以涉及生活、过往经历、未来畅想等，目的是从用户的回答中挖掘潜在的优势。
   - **追问技巧**：根据用户的回答进行追问，引导用户深入思考，直到用户自己能清晰地总结出："这对我来说，意味着[某项优势]是我的一个优势。"
3. **记录与确认**：
   - 每从一个问题中提炼出一个优势，就记录下来，并标记为"探索发现"。
   - **对比初始答案**：将"探索发现"的优势与第一步中用户"用户自述"的优势进行对比。
   - 如果重复出现，则在该优势旁记录"权重+1"。
   - 如果出现全新的优势，向用户确认："通过刚才的讨论，我们发现[新优势]可能是你的一个优势，你认可吗？可以加入你的优势列表吗？"
4. **重复提问直至达成10个**：持续进行提问探索，直到用户确认的优势累计达到**10个**。提取出的优势之间不能有重复。
5. **标记优势**：当用户确认了10个优势后，向用户解释标记体系的含义，并引导用户对每个优势进行标记。
   - **a. 有充实感，与成功有关**：你不仅做这件事时感到充实、有活力，而且它通常能带来好的结果或成就。
   - **b. 有充实感**：你做这件事时感到充实、充满能量，但并不一定每次都带来成功。
   - **c. 目前还不确定**：你对自己是否具备这个优势，或者使用时是否有充实感，还不太确定。
6. **确认标记结果**：当所有10个优势都标记完毕后，向用户呈现最终列表及对应的标记，询问用户是否确认。
7. **结束对话**：用户确认后，告知用户："恭喜你完成了第二轮优势探索。下一轮我们将进入热爱探索，帮助你发现你的激情所在。我们下次见！"

### 重要准则

- **引导而非灌输**：始终给用户思考和回答的空间，不要直接替用户下结论。
- **一次一问**：严格遵守每轮对话只提一个问题。
- **确保10个优势**：必须通过提问挖掘，直到用户认可并确认了10个不重复的优势。
- **提问差异化**：避免重复问类似问题，要变换角度，防止用户思维僵化或"钻牛角尖"。
- 【对话续写】若对话已有历史，必须在已有探索基础上继续深挖，禁止重复开场式提问（如「你的优势有哪些」）或泛泛寒暄，应基于用户已有回答进行追问和深化。

### 题库参考

以下题库可供选择，你也可以根据对话情境灵活提问：
{question_bank}

来访者基本信息：{basic_info}{prior_block}

请直接用中文和用户继续这一轮对话。"""

    if phase == "interests":
        return f"""你是一名专业的职业规划咨询师，正在进行第三轮咨询。本轮咨询的目标是：**帮助用户发现3个"热爱"——即用户真正感兴趣、充满好奇的领域（以名词形式呈现，例如：自然环境、自我认知、足球、艺术创作等）**。

请先以亲切、专业的语气向用户介绍本次咨询的主题，然后严格遵循以下流程和方法开展咨询。

### 咨询流程

1. **开场提问**：直接询问用户："你自己认为，你有哪些热爱的事情或领域？请列举一些你真正感兴趣、充满好奇的方向。"
   - 如果用户给出了答案，请分析是否符合"热爱"的定义（感兴趣、好奇的领域，名词形式）。如果符合，记录下来，标记为"用户自述"。
   - 如果用户无法给出任何答案，或给出的答案不符合定义，则记录下来，并继续下一步。
2. **深度提问探索**：进入正式的问题探索环节。
   - **提问原则**：每次只向用户提出**一个**问题。问题可以不局限于工作，可以涉及生活、过往经历、未来畅想等，目的是从用户的回答中挖掘潜在的热爱领域。
   - **追问技巧**：根据用户的回答进行追问，引导用户深入思考，直到用户自己能清晰地总结出："我发现自己对[某个领域]真的很感兴趣/充满好奇。"
3. **记录与确认**：
   - 每从一个问题中提炼出一个热爱领域，就记录下来，并标记为"探索发现"。
   - **对比初始答案**：将"探索发现"的热爱与第一步中用户"用户自述"的热爱进行对比。
   - 如果重复出现，则在该热爱旁记录"权重+1"。
   - 如果出现全新的热爱，向用户确认："通过刚才的讨论，我们发现你对[新领域]似乎很有热情，你觉得可以把它列入你的热爱清单吗？"
4. **收集候选热爱清单**：
   - 持续进行提问探索，直到收集到的热爱领域（包括用户自述和探索发现的）达到**至少6个**。
   - 询问用户："目前我们列出了X个你热爱的领域（列出清单），你觉得这些是否全面表达了你所有的热爱？有没有什么重要的领域被遗漏了？"
   - 如果用户认为有遗漏，继续提问帮助用户补充，直到用户觉得清单已基本全面（或总数量达到12个左右，作为上限参考）。
   - **注意**：提取出的热爱领域不能重复，确保每个都是独特的。
5. **引导用户选出TOP 3**：
   - 当候选清单确定后（N≥6），请用户从中选出最重要的3个，作为"核心热爱"。
   - 你可以这样引导："在这些热爱的领域中，哪三个是你最想深入探索、最不愿意放弃的？为什么？"
   - 如果用户对选择感到困难，可以通过追问帮助其厘清优先级。
   - 如果用户不认可某一项热爱，需要重新确认该热爱是否应保留在候选清单中，必要时通过提问重新挖掘替代项。
6. **确认最终结果**：当用户明确选出TOP 3后，向用户呈现最终结果："你最终确认的3个核心热爱是：1. [热爱A]，2. [热爱B]，3. [热爱C]。你确认这个结果吗？"
7. **结束对话**：用户确认后，告知用户："恭喜你完成了第三轮热爱探索。下一轮我们将进入使命探索，帮助你找到你的人生召唤。我们下次见！"

### 重要准则

- **引导而非灌输**：始终给用户思考和回答的空间，不要直接替用户下结论。
- **一次一问**：严格遵守每轮对话只提一个问题。
- **提问差异化**：避免重复问类似问题，要变换角度，防止用户思维僵化或"钻牛角尖"。
- **热爱的形式**：确保提炼出的热爱是名词形式的领域，例如"人工智能"、"心理学"、"户外运动"等，而不是形容词或抽象感受。
- 【对话续写】若对话已有历史，必须在已有探索基础上继续深挖，禁止重复开场式提问（如「你的热爱有哪些」）或泛泛寒暄，应基于用户已有回答进行追问和深化。

### 题库参考

以下题库可供选择，你也可以根据对话情境灵活提问：
{question_bank}

来访者基本信息：{basic_info}{prior_block}

请直接用中文和用户继续这一轮对话。"""

    if phase == "purpose":
        return f"""你是一名专业的职业规划咨询师，正在进行第四轮咨询。本轮咨询的目标是：**帮助用户发现其工作使命——即用户最希望为他人提供的核心价值**。

请先以祝贺和鼓励的语气开启对话，告知用户即将完成整个探索旅程，然后按照以下流程和方法开展咨询。

### 咨询流程

1. **开场与回顾**：
   - 亲切地向用户表示恭喜："恭喜你即将完成整个职业探索旅程！本轮我们将一起发现你的工作使命——你内心深处最希望为他人提供的价值。"
   - 帮助用户回忆第一轮咨询中确认的5个价值观关键词。参考下方"来访者上一轮咨询结果"中的价值观相关内容，向用户复述："还记得我们在第一轮一起探索出的对你最重要的5个价值观吗？它们是：[从上一轮结果中提取的5个价值观关键词]。在接下来的讨论中，我们会用到它们。"
2. **梳理价值经历**：
   - 引导用户梳理出**10个曾经为他人提供价值的经历**。这些经历可以来自工作、学习、志愿活动、日常生活等任何方面。
   - 提问示例："请你回想一下，在过去的生活或工作中，有哪些你曾经为他人提供帮助、解决问题或带来积极影响的经历？可以列出10个，每个用一两句话简单描述。"
   - 如果用户一时想不出10个，可以通过提问引导，但避免替用户决定。
3. **匹配价值观（逐个经历进行）**：
   - 针对每一段经历，与用户一起分析：在这段经历中，你提供或试图提供的价值，对应着第一轮中的哪个（或哪些）价值观关键词？
   - 向用户确认匹配是否准确，如果用户认可则记录；如果不认可，继续引导用户思考更匹配的价值观，直到用户确认。
   - 处理完一段经历后，继续下一段，直到10段经历全部匹配完成。（若用户实在想不出10段，可适当放宽至8-9段。）
4. **统计与总结**：
   - 完成经历分析后，统计每个价值观关键词出现的次数。
   - 根据统计结果，为用户整理一份使命总结，内容包括：
     - **（1）经历-价值观对应表格**：第一列是每段经历的简要概括，第二列是该经历对应的价值观关键词。
     - **（2）核心使命陈述**：用一句话概括你最希望传递的核心价值观；对这句话进行展开说明；用一句话概括你希望通过工作传递的最终目的。
5. **确认总结**：向用户展示上述总结，询问是否认可，有没有需要调整的地方。根据用户反馈调整，直到用户完全认可。
6. **结束对话**：用户确认后，告知用户："太棒了！你已经完成了使命探索。接下来我们将进行最后一轮对话——帮助你整合所有发现，找到具体的职业发展方向。我们下次见！"

### 重要准则

- **引导而非灌输**：始终给用户思考和回答的空间，不要替用户下结论。
- **一次一问**：严格遵守每轮对话只提一个问题。
- **提问差异化**：在引导用户回忆经历时，变换提问角度，避免重复。
- **经历数量**：尽量引导至10段经历，若用户实在想不出可适当放宽到8-9段。
- **匹配准确**：在匹配价值观时，一定要得到用户的明确认可。
- 【对话续写】若对话已有历史，必须在已有探索基础上继续深挖，禁止重复开场式提问（如「你为什么而工作」）或泛泛寒暄，应基于用户已有回答进行追问和深化。

### 题库参考

以下题库可供选择，你也可以根据对话情境灵活提问：
{question_bank}

来访者基本信息：{basic_info}{prior_block}

请直接用中文和用户继续这一轮对话。"""

    return _build_system_prompt("values", question_bank, basic_info, prior_context)


@router.post("/message", response_model=SimpleChatResponse)
async def simple_chat(
    request: SimpleChatRequest,
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
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

    if rec.status == ActivationStatus.EXPIRED and not _skip_expired_for_debug(rec, current_user):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="激活码已过期（历史记录已保留，可以用于回放或导出）",
        )

    # 更新最后活跃时间（过期时不更新）
    if rec.status == ActivationStatus.ACTIVE:
        manager.touch_activity(rec.code)

    # 使用 data/simple 作为根目录保存对话
    conv_manager = ConversationFileManager(base_dir=SIMPLE_BASE_DIR)
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
async def simple_init(
    request: SimpleInitRequest,
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
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
    if rec.status == ActivationStatus.EXPIRED and not _skip_expired_for_debug(rec, current_user):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="激活码已过期（历史记录已保留，可以用于回放或导出）",
        )

    conv_manager = ConversationFileManager(base_dir=SIMPLE_BASE_DIR)
    phase = (request.phase or "values").strip() or "values"
    category = _storage_category(phase, request.thread_id)
    session_id = rec.session_id

    # 如果已有历史，就直接返回历史（新建 thread_id 时文件不存在，返回空）
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


class ThreadReopenRequest(BaseModel):
    activation_code: str
    phase: str
    thread_id: str


@router.post("/thread/reopen", response_model=SimpleChatResponse)
async def reopen_thread(
    request: ThreadReopenRequest,
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
    """用户选择「再聊聊」完善答案时，清除完成状态以便继续对话"""
    manager = SimpleActivationManager()
    rec = manager.get_activation(request.activation_code)
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="激活码不存在")
    conv_manager = ConversationFileManager(base_dir=SIMPLE_BASE_DIR)
    phase_val = (request.phase or "values").strip() or "values"
    category = _storage_category(phase_val, request.thread_id)
    await conv_manager.update_metadata(
        rec.session_id, category,
        {
            "thread_completed": False,
            "pending_conclusion": None,
        },
    )
    return SimpleChatResponse(code=200, message="success", data={})


@router.post("/thread/complete", response_model=SimpleChatResponse)
async def mark_thread_complete(
    request: ThreadCompleteRequest,
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
    """标记某对话为已完成（用户点击「确认没有问题」后调用）"""
    manager = SimpleActivationManager()
    rec = manager.get_activation(request.activation_code)
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="激活码不存在")
    conv_manager = ConversationFileManager(base_dir=SIMPLE_BASE_DIR)
    phase_val = (request.phase or "values").strip() or "values"
    category = _storage_category(phase_val, request.thread_id)
    await conv_manager.update_metadata(rec.session_id, category, {"thread_completed": True})
    return SimpleChatResponse(code=200, message="success", data={})


@router.get("/history", response_model=SimpleHistoryResponse)
async def simple_history(activation_code: str, phase: Optional[str] = "values", thread_id: Optional[str] = None):
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

    conv_manager = ConversationFileManager(base_dir=SIMPLE_BASE_DIR)
    phase_val = (phase or "values").strip() or "values"
    category = _storage_category(phase_val, thread_id)
    session_id = rec.session_id

    conv_data = await conv_manager.get_conversation_data(session_id, category)
    history_messages = conv_data.get("messages", [])
    metadata = conv_data.get("metadata", {})

    return SimpleHistoryResponse(
        code=200,
        message="success",
        data={
            "messages": history_messages,
            "metadata": {
                "thread_completed": metadata.get("thread_completed", False),
                "dimension_conclusion": metadata.get("dimension_conclusion"),
            },
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
async def simple_chat_stream(
    request: SimpleChatStreamRequest,
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
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
    if rec.status == ActivationStatus.EXPIRED and not _skip_expired_for_debug(rec, current_user):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="激活码已过期（历史记录已保留，可以用于回放或导出）",
        )

    phase = (request.phase or "values").strip() or "values"
    category = _storage_category(phase, request.thread_id)
    conv_manager = ConversationFileManager(base_dir=SIMPLE_BASE_DIR)
    session_id = rec.session_id

    async def event_stream() -> AsyncIterator[str]:
        llm = get_default_llm_provider()

        # 读取当前 thread 的历史（独立存储，全新上下文）
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

        # 1) 若有上一轮后台检测的 pending_conclusion，综合本轮输入重新生成并展示
        conv_data = await conv_manager.get_conversation_data(session_id, category)
        meta = conv_data.get("metadata", {})
        pending_conclusion = meta.get("pending_conclusion")
        conv_history = [
            {"role": m.get("role", "user"), "content": m.get("content", "")}
            for m in conv_data.get("messages", [])
        ]
        user_count = sum(1 for m in conv_data.get("messages", []) if m.get("role") == "user")
        conclusion_shown_at = meta.get("conclusion_shown_at_turn")

        if pending_conclusion and not meta.get("thread_completed"):
            # 综合本轮用户输入 + 上一轮结论，重新生成确定性结论
            dimension_conclusion = await check_dimension_complete(
                phase, conv_history, prior_conclusion=pending_conclusion
            )
            if dimension_conclusion:
                await conv_manager.update_metadata(
                    session_id, category,
                    {
                        "conclusion_shown_at_turn": user_count,
                        "dimension_conclusion": dimension_conclusion,
                        "pending_conclusion": None,
                    },
                )
                transition_msg = "好的，根据我们的对话，我为你整理出本维度的探索结论，请确认下方摘要是否准确。"
                yield f"data: {{\"chunk\": {json.dumps(transition_msg, ensure_ascii=False)} }}\n\n"
                full_reply = transition_msg
                await conv_manager.append_message(
                    session_id=session_id,
                    category=category,
                    message={"role": "assistant", "content": full_reply},
                )
                yield f"data: {{\"dimension_conclusion\": {json.dumps(dimension_conclusion, ensure_ascii=False)} }}\n\n"
                try:
                    await AnalyticsService.record_chat_turn(session_id=session_id, dimension=phase, user_input_chars=len(user_content or ""), llm_input_tokens=0, llm_output_tokens=0, log_index=None)
                except Exception:
                    pass
                yield f"data: {{\"done\": true, \"response\": {json.dumps(full_reply, ensure_ascii=False)} }}\n\n"
                return
            # 若 regenerate 返回 None，清除 pending 并继续正常流程
            await conv_manager.update_metadata(session_id, category, {"pending_conclusion": None})

        # 2) 无 pending 时：显式完成 或 轮数条件 → 同步检测
        dimension_conclusion = None
        if not meta.get("thread_completed"):
            explicit_result = bool(
                user_content and await detect_explicit_completion(phase, user_content, conv_history)
            )
            should_check = _should_run_completion_check(
                user_count, conclusion_shown_at,
                include_explicit=True, explicit_result=explicit_result,
            )
            if should_check:
                dimension_conclusion = await check_dimension_complete(phase, conv_history)
                if dimension_conclusion:
                    await conv_manager.update_metadata(
                        session_id, category,
                        {"conclusion_shown_at_turn": user_count, "dimension_conclusion": dimension_conclusion},
                    )

        if dimension_conclusion:
            transition_msg = "好的，根据我们的对话，我为你整理出本维度的探索结论，请确认下方摘要是否准确。"
            yield f"data: {{\"chunk\": {json.dumps(transition_msg, ensure_ascii=False)} }}\n\n"
            full_reply = transition_msg
            await conv_manager.append_message(
                session_id=session_id,
                category=category,
                message={"role": "assistant", "content": full_reply},
            )
            yield f"data: {{\"dimension_conclusion\": {json.dumps(dimension_conclusion, ensure_ascii=False)} }}\n\n"
            try:
                await AnalyticsService.record_chat_turn(session_id=session_id, dimension=phase, user_input_chars=len(user_content or ""), llm_input_tokens=0, llm_output_tokens=0, log_index=None)
            except Exception:
                pass
            yield f"data: {{\"done\": true, \"response\": {json.dumps(full_reply, ensure_ascii=False)} }}\n\n"
            return

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

        # 3) 后台异步检测：不阻塞响应，不展示，仅更新 pending_conclusion 判定
        async def _background_completion_check() -> None:
            try:
                conv_data = await conv_manager.get_conversation_data(session_id, category)
                meta = conv_data.get("metadata", {})
                if meta.get("thread_completed"):
                    return
                user_count = sum(1 for m in conv_data.get("messages", []) if m.get("role") == "user")
                conclusion_shown_at = meta.get("conclusion_shown_at_turn")
                if not _should_run_completion_check(user_count, conclusion_shown_at):
                    return
                conv_history = [
                    {"role": m.get("role", "user"), "content": m.get("content", "")}
                    for m in conv_data.get("messages", [])
                ]
                conclusion = await check_dimension_complete(phase, conv_history)
                if conclusion:
                    await conv_manager.update_metadata(
                        session_id, category, {"pending_conclusion": conclusion}
                    )
                else:
                    await conv_manager.update_metadata(
                        session_id, category, {"pending_conclusion": None}
                    )
            except Exception:
                pass

        asyncio.create_task(_background_completion_check())

        # 埋点：记录对话轮次（simple 模式无 token 统计）
        try:
            await AnalyticsService.record_chat_turn(
                session_id=session_id,
                dimension=phase,
                user_input_chars=len(user_content or ""),
                llm_input_tokens=0,
                llm_output_tokens=0,
                log_index=None,
            )
        except Exception:
            pass

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

