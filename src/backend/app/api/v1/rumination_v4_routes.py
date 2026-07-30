"""
Rumination v4 API 路由

路由前缀: /api/v1/simple-chat/rumination-v4/...
(挂在 simple_chat.router 下,避免改动 main.py 注册)

端点(见 wiki/开发文档/0707-tag1.6.0.md 第六节):
- POST /create-combo
- POST /start-discussion
- POST /combo-chat            (SSE 流式)
- GET  /combos
- GET  /combos/{combo_id}
- DELETE /combos/{combo_id}
- PATCH /combos/{combo_id}/conclusion-card
- POST /final-selection
- GET  /state

数据模型与决策见 wiki/开发文档/0707-tag1.6.0.md
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.v1.auth import get_current_user
from app.api.v1.simple_chat.context_resolver import (
    load_basic_info_from_activation as _load_basic_info_from_activation,
)
from app.api.v1.simple_chat.context_resolver import (
    resolve_report_context as _resolve_report_context,
)
from app.api.v1.simple_chat.llm_providers import (
    get_dialogue_llm_provider as _get_dialogue_llm_provider,
)
from app.api.v1.simple_chat.stream_utils import (
    build_stream_hidden_block_filter as _build_stream_hidden_block_filter,
)
from app.utils.simple_activation_manager import (
    get_activation_manager_for_code,
    get_effective_simple_root,
)
from app.utils.report_registry import ReportRegistry
from app.utils.rumination_ops import extract_dimension_lists_for_rumination_table
from app.utils.survey_storage import (
    format_conclusion_prior_block,
    load_dimension_conclusions,
)
from app.services.rumination_v4_service import (
    CONCLUSION_READY_MARKER,
    apply_tool_call,
    append_message,
    build_chat_messages,
    create_and_start as svc_create_and_start,
    delete_combo as svc_delete_combo,
    detect_conclusion_signals,
    extract_hyp_candidates,
    HYP_JSON_END,
    HYP_JSON_START,
    fallback_generate_conclusion,
    find_combo,
    list_combos,
    load_v4_state,
    maybe_summarize_combo,
    patch_conclusion_card as svc_patch_card,
    save_v4_state,
    set_active_combo,
    set_combo_status,
    submit_final_selection,
    STREAM_HIDDEN_BLOCK_MARKERS,
    update_final_selection,
)
from app.utils.activation_audit import append_activation_audit  # 复用项目审计日志

# v3/v4 分组判定
from app.models.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.rumination_ab_service import resolve_rumination_version

logger = logging.getLogger(__name__)

# 挂在 simple_chat.router 之下(父 router 已有 /simple-chat prefix)
router = APIRouter(prefix="/rumination-v4", tags=["Rumination v4"])


# ── 请求/响应模型 ───────────────────────────────────────────────────────
class _ActivationReq(BaseModel):
    activation_code: str


class CreateComboReq(BaseModel):
    activation_code: str
    passion: str
    strengths: List[str]


class StartDiscussionReq(BaseModel):
    activation_code: str
    combo_id: str


class ComboChatReq(BaseModel):
    activation_code: str
    combo_id: str
    message: str


class PatchConclusionReq(BaseModel):
    activation_code: str
    hypothesis: Optional[Any] = None
    motivation: Optional[str] = None
    work_purposes: Optional[List[str]] = None
    passion_mark: Optional[str] = None
    timing_mark: Optional[str] = None


class SetStatusReq(BaseModel):
    activation_code: str
    status: str  # concluded | abandoned


class FinalSelectionReq(BaseModel):
    activation_code: str
    selected_combo_ids: List[str]


class SubmitFinalReq(BaseModel):
    activation_code: str


# ── 辅助:解析 reports_root + report_id ──────────────────────────────────
def _resolve_v4_ctx(activation_code: str, current_user: dict):
    manager = get_activation_manager_for_code(activation_code)
    rec, report, _phase_step, _sid, _cat, _conv = _resolve_report_context(
        manager=manager,
        activation_code=activation_code,
        current_user=current_user,
        phase="rumination",
    )
    storage_root = str(get_effective_simple_root(rec))
    reports_root = Path(storage_root) / "reports"
    rid = report["report_id"]
    return reports_root, rid


def _resolve_v4_ctx_with_rec(activation_code: str, current_user: dict):
    """同 _resolve_v4_ctx,但额外返回激活记录 rec(装配用户上下文需要 record_dict)。"""
    manager = get_activation_manager_for_code(activation_code)
    rec, report, _phase_step, _sid, _cat, _conv = _resolve_report_context(
        manager=manager,
        activation_code=activation_code,
        current_user=current_user,
        phase="rumination",
    )
    storage_root = str(get_effective_simple_root(rec))
    reports_root = Path(storage_root) / "reports"
    rid = report["report_id"]
    return reports_root, rid, rec


# 前四阶段结论卡按此顺序注入用户背景
_DIMENSION_PHASE_ORDER = ("values", "strengths", "interests", "purpose")


def _assert_rumination_editable(reports_root: Path, rid: str, current_user: dict, rec) -> None:
    """报告定稿（终选提交）后 rumination 锁定：v4 写端点统一拦截。

    豁免口径与 simple_chat 一致：管理员调试工作区（fork/resident）可绕过。
    锁定时机：final-selection/submit（V4）或 step7 定稿（V3）时 lock_step("rumination")。
    """
    from app.api.v1.simple_chat_routes import _can_bypass_flow_limits  # 延迟导入避免循环依赖

    if _can_bypass_flow_limits(current_user, rec):
        return
    registry = ReportRegistry(base_dir=str(reports_root))
    record = registry.get_report_by_id(rid) or {}
    step = ((record.get("steps") or {}).get("rumination")) or {}
    if step.get("locked"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="最终选择已提交并锁定，报告已生成，不能再修改",
        )


def _build_user_context(
    reports_root: Path, rid: str, rec, activation_code: str
) -> Tuple[str, Optional[List[str]]]:
    """装配 combo-chat 的用户上下文(实施口径 §1-Q5 / §2.3)。

    - basic_info: 复用 simple_chat 的激活码维度拼装(format_basic_info_for_prompt)
    - 前四阶段结论卡: load_dimension_conclusions,逐阶段 keywords + summary 全量不截断
    - values 关键词: extract_dimension_lists_for_rumination_table 的 values 结果,
      为空则返回 None(prompt 整块省略,禁固定 8 词兜底)

    Returns:
        (user_context 文本, values_keywords 或 None)
    """
    parts: List[str] = []
    try:
        basic = (_load_basic_info_from_activation(activation_code) or "").strip()
        if basic and basic != "暂无":
            parts.append(f"【基本资料】\n{basic}")
    except Exception as e:
        logger.warning("v4 user_context basic_info 装配失败 report=%s: %s", rid, e)
    try:
        conclusions = load_dimension_conclusions(rid, str(reports_root))
        for phase in _DIMENSION_PHASE_ORDER:
            conclusion = conclusions.get(phase)
            if not conclusion:
                continue
            block = format_conclusion_prior_block(phase, conclusion)
            if block:
                parts.append(block)
    except Exception as e:
        logger.warning("v4 user_context 结论卡装配失败 report=%s: %s", rid, e)
    values_keywords: Optional[List[str]] = None
    try:
        record_obj = rec.record_dict if hasattr(rec, "record_dict") else None
        values_list, _s, _i, _p, _src = extract_dimension_lists_for_rumination_table(
            str(reports_root), rid, record_obj
        )
        if values_list:
            values_keywords = list(values_list)
    except Exception as e:
        logger.warning("v4 values 关键词装配失败 report=%s: %s", rid, e)
    return "\n\n".join(parts), values_keywords


def _audit_log(event: str, user: Optional[dict], activation_code: str, detail: Dict[str, Any]):
    """审计日志写入(复用项目 activation_audit)。失败时降级到 logger。"""
    try:
        append_activation_audit(
            event,
            activation_code,
            actor_user_id=(user or {}).get("user_id"),
            actor_email=(user or {}).get("email"),
            detail=detail,
        )
    except Exception:
        logger.info("AUDIT %s user=%s code=%s detail=%s", event, (user or {}).get("user_id"), activation_code, detail)


# ── 端点 0:GET /version（v3/v4 分组判定，前端进 rumination 时首调）────────
@router.get("/version")
async def get_rumination_version(
    activation_code: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """返回该 report 应走的 rumination 版本。

    首次进入时按配置（强制 v3/v4 或 AB 随机）分配并落库，后续直接返回已分配结果。
    返回 {version: 'v3'|'v4', source: 'forced'|'ab', assigned_at, ratio_at_assignment}。
    """
    reports_root, rid = _resolve_v4_ctx(activation_code, current_user)
    result = await resolve_rumination_version(db, rid, (current_user or {}).get("user_id"))
    _audit_log("version_assigned", current_user, activation_code, result)
    return {"code": 200, "message": "success", "data": result}


# ── 端点 1:GET /state ──────────────────────────────────────────────────
@router.get("/state")
async def get_state(activation_code: str, current_user: dict = Depends(get_current_user)):
    """获取全局 v4 rumination_state。

    若 matrix_snapshot 的 passions/strengths 为空（首次进入），
    从前置阶段（values/strengths/interests 结论）提取并填充。
    """
    manager = get_activation_manager_for_code(activation_code)
    rec, report, _phase_step, _sid, _cat, _conv = _resolve_report_context(
        manager=manager,
        activation_code=activation_code,
        current_user=current_user,
        phase="rumination",
    )
    storage_root = str(get_effective_simple_root(rec))
    reports_root = Path(storage_root) / "reports"
    rid = report["report_id"]

    state = load_v4_state(reports_root, rid)
    snap = state.get("matrix_snapshot") or {}
    needs_fill = not snap.get("passions") or not snap.get("strengths")
    if needs_fill:
        try:
            record_obj = rec.record_dict if hasattr(rec, "record_dict") else None
            _, strengths_list, interests_list, _, _ = extract_dimension_lists_for_rumination_table(
                str(reports_root), rid, record_obj
            )
            passions = (interests_list or [])[:3]
            strengths = (strengths_list or [])[:5]
            state["matrix_snapshot"] = {"passions": passions, "strengths": strengths}
            save_v4_state(reports_root, rid, state)
            logger.info(
                "v4 matrix_snapshot filled report=%s passions=%d strengths=%d",
                rid, len(passions), len(strengths),
            )
        except Exception as e:
            logger.warning("v4 matrix_snapshot fill failed report=%s: %s", rid, e)

    return {"code": 200, "message": "success", "data": {"state": state, "combos": list_combos(state)}}


# ── 端点 2:GET /combos ─────────────────────────────────────────────────
@router.get("/combos")
async def get_combos(activation_code: str, current_user: dict = Depends(get_current_user)):
    """列出所有 combo_session 元信息(tag 条用)。"""
    reports_root, rid = _resolve_v4_ctx(activation_code, current_user)
    state = load_v4_state(reports_root, rid)
    return {"code": 200, "message": "success", "data": {"combos": list_combos(state), "active_combo_id": state.get("active_combo_id")}}


# ── 端点 3:GET /combos/{combo_id} ──────────────────────────────────────
@router.get("/combos/{combo_id}")
async def get_combo_detail(combo_id: str, activation_code: str, current_user: dict = Depends(get_current_user)):
    """获取单个 combo_session 详情(含 messages)。"""
    reports_root, rid = _resolve_v4_ctx(activation_code, current_user)
    state = load_v4_state(reports_root, rid)
    combo = find_combo(state, combo_id)
    if not combo:
        raise HTTPException(status_code=404, detail="combo_id 不存在")
    return {"code": 200, "message": "success", "data": {"combo": combo}}


# ── 端点 4:POST /create-and-start(原子:建 combo + 唤起引导语)────────
@router.post("/create-and-start")
async def create_and_start_endpoint(req: CreateComboReq, current_user: dict = Depends(get_current_user)):
    """原子操作:创建 combo + 生成引导语开场,一次调用完成。
    校验:10 上限 + 严格集合判重。返回 {combo_id, combo, opening}。"""
    if not req.passion.strip():
        raise HTTPException(status_code=400, detail="passion 不可为空")
    if not req.strengths or not all(isinstance(s, str) and s.strip() for s in req.strengths):
        raise HTTPException(status_code=400, detail="strengths 不可为空")
    reports_root, rid, rec = _resolve_v4_ctx_with_rec(req.activation_code, current_user)
    _assert_rumination_editable(reports_root, rid, current_user, rec)
    try:
        state, combo, opening = svc_create_and_start(
            reports_root, rid, req.passion.strip(), [s.strip() for s in req.strengths]
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _audit_log(
        "rumination_v4_combo_created_and_started",
        current_user,
        req.activation_code,
        {"combo_id": combo["combo_id"]},
    )
    return {
        "code": 200,
        "message": "success",
        "data": {"combo_id": combo["combo_id"], "combo": combo, "opening": opening},
    }


# ── 端点 5:POST /start-discussion ─────────────────────────────────────
@router.post("/start-discussion")
async def start_discussion_endpoint(req: StartDiscussionReq, current_user: dict = Depends(get_current_user)):
    """标记开始讨论(组合固定),返回初始 AI 开场消息(同步,非流式)。"""
    reports_root, rid, rec = _resolve_v4_ctx_with_rec(req.activation_code, current_user)
    _assert_rumination_editable(reports_root, rid, current_user, rec)
    state = load_v4_state(reports_root, rid)
    combo = find_combo(state, req.combo_id)
    if not combo:
        raise HTTPException(status_code=404, detail="combo_id 不存在")
    # 若已有开场 assistant 消息,直接返回(idempotent)
    existing_opening = None
    for m in combo.get("messages") or []:
        if m.get("role") == "assistant":
            existing_opening = m
            break
    if existing_opening:
        return {"code": 200, "message": "success", "data": {"opening": existing_opening}}
    # 生成开场(非 LLM,固定话术 + 引导问)
    passion = combo.get("passion")
    strengths = combo.get("strengths") or []
    strengths_str = "、".join(strengths)
    opening_text = (
        f"好的,我们就来聊聊「{passion}」+「{strengths_str}」这个组合。\n\n"
        f"在正式展开之前,我想先听听你 —— 是什么吸引你把这个热爱和这几个优势放在一起?"
        f"可以告诉我一个具体的场景,或者一个让你心动的瞬间吗?"
    )
    append_message(state, req.combo_id, "assistant", opening_text)
    save_v4_state(reports_root, rid, state)
    state = load_v4_state(reports_root, rid)
    combo = find_combo(state, req.combo_id)
    opening_msg = combo["messages"][-1] if combo.get("messages") else None
    return {"code": 200, "message": "success", "data": {"opening": opening_msg}}


# ── 端点 6:POST /combo-chat(SSE 流式)─────────────────────────────────
@router.post("/combo-chat")
async def combo_chat_endpoint(req: ComboChatReq, current_user: dict = Depends(get_current_user)):
    """主对话端点(SSE 流式)。LLM 自主调 tool,后端解析隐藏 JSON 块 + 双信号兜底。
    实施口径 §2.3:回复完成后解析 chips 隐藏块并推 hyp_candidates 事件;
    <<CONCLUSION_READY>> / tool 块 / [STEP3_HYP_JSON] 块均剥离后再入库/推送。"""
    reports_root, rid, rec = _resolve_v4_ctx_with_rec(req.activation_code, current_user)
    _assert_rumination_editable(reports_root, rid, current_user, rec)
    state = load_v4_state(reports_root, rid)
    combo = find_combo(state, req.combo_id)
    if not combo:
        raise HTTPException(status_code=404, detail="combo_id 不存在")
    if combo.get("status") in ("concluded", "abandoned"):
        raise HTTPException(status_code=400, detail=f"该组合已 {combo.get('status')},不可继续对话")

    user_msg = (req.message or "").strip()
    if not user_msg:
        raise HTTPException(status_code=400, detail="message 不可为空")

    # 先把用户消息落盘(事务性:消息进来就存,即使流式中断也不丢用户输入)
    append_message(state, req.combo_id, "user", user_msg)
    save_v4_state(reports_root, rid, state)

    # 装配用户上下文(basic_info + 前四阶段结论卡全量 + values 真实关键词,空则 None)
    user_context, values_keywords = _build_user_context(
        reports_root, rid, rec, req.activation_code
    )
    vip_level = 1

    async def event_stream() -> AsyncIterator[str]:
        # 重新加载最新 state(用户消息已落盘)
        latest_state = load_v4_state(reports_root, rid)
        combo_obj = find_combo(latest_state, req.combo_id)
        # 拼装 LLM 消息
        llm_messages, _sys_prompt = build_chat_messages(
            combo_obj, user_msg, user_context, values_keywords
        )
        llm = _get_dialogue_llm_provider(vip_level=vip_level)

        # 流式隐藏块过滤(跨 chunk 安全,复用 v3 同款):
        # ```tool 块 / [STEP3_HYP_JSON] 块 / <<CONCLUSION_READY>> 标记均不推给前端,
        # 避免标记被切块拆开或 tool JSON 原样泄漏到聊天气泡。
        stream_hidden_filter = _build_stream_hidden_block_filter(
            block_markers=STREAM_HIDDEN_BLOCK_MARKERS
        )

        full_reply = ""
        async for piece in llm.chat_stream(llm_messages, temperature=0.7, max_tokens=800):
            if isinstance(piece, dict):
                # 项目内 think_chunk 等特殊信号,透传
                t = piece.get("_t")
                if t == "think_start":
                    yield f"data: {json.dumps({'think_start': True}, ensure_ascii=False)}\n\n"
                elif t == "think_chunk":
                    yield f"data: {json.dumps({'think_chunk': piece.get('content') or ''}, ensure_ascii=False)}\n\n"
                elif t == "think_end":
                    yield f"data: {json.dumps({'think_end': piece.get('content')}, ensure_ascii=False)}\n\n"
                continue
            if piece:
                full_reply += piece
                # 基于累计文本计算可见增量,隐藏块跨 chunk 也不会泄漏
                safe = stream_hidden_filter(full_reply)
                if safe:
                    yield f"data: {json.dumps({'chunk': safe}, ensure_ascii=False)}\n\n"

        # 流式结束,解析完整回复:剥离 tool 块 → chips 隐藏块 → 隐藏标记
        visible_text, tool_calls = _parse_and_clean(full_reply)
        visible_text, hyp_candidates = extract_hyp_candidates(visible_text)
        visible_text = visible_text.replace(CONCLUSION_READY_MARKER, "").strip()
        signals = detect_conclusion_signals(full_reply)

        # 执行所有 tool call(透明 + 校验)
        conclusion_card_event: Optional[Dict[str, Any]] = None
        tool_errors: List[str] = []
        for tc in tool_calls:
            card, err = apply_tool_call(latest_state, req.combo_id, tc)
            if err:
                tool_errors.append(err)
            if card:
                conclusion_card_event = card

        # 兜底机制:有 visible 信号但无 hidden 标记 → 重新生成结论
        if signals.get("visible") and not signals.get("hidden") and not conclusion_card_event:
            yield f"data: {json.dumps({'fallback': True}, ensure_ascii=False)}\n\n"
            card = await fallback_generate_conclusion(combo_obj, llm, values_keywords)
            if card:
                # 直接写 conclusion_card(含 balance 两字段)
                apply_tc = {"tool": "save_conclusion_card", "fields": {
                    "hypothesis": card.get("hypothesis"),
                    "motivation": card.get("motivation"),
                    "work_purposes": card.get("work_purposes"),
                    "passion_mark": card.get("passion_mark"),
                    "timing_mark": card.get("timing_mark"),
                    "balance_found": card.get("balance_found"),
                    "balance_fail_reason": card.get("balance_fail_reason"),
                }}
                c2, _e = apply_tool_call(latest_state, req.combo_id, apply_tc)
                if c2:
                    conclusion_card_event = c2

        # 空可见回复兜底:LLM 整轮只输出隐藏块(或 tool 校验失败)时 visible_text 为空,
        # 直接落库/渲染会出现「空气泡」。补一句与情境相符的兜底话术并记日志。
        if not visible_text.strip():
            logger.warning(
                "combo-chat 空可见回复 combo_id=%s tool_errors=%s raw=%.300s",
                req.combo_id, tool_errors, full_reply,
            )
            if conclusion_card_event:
                visible_text = "我已经把最新的共识更新到结论卡了,你看看这版是否更贴合?有想调整的随时告诉我。"
            elif hyp_candidates:
                visible_text = "基于你的想法,我整理了两条候选方向,点一条我们继续细聊。"
            else:
                visible_text = "嗯,我记下了。这个想法里,最吸引你的是哪一点?可以多跟我说说。"
            # 流式阶段一个 chunk 都没推过,补推兜底话术让前端即时可见
            yield f"data: {json.dumps({'chunk': visible_text}, ensure_ascii=False)}\n\n"

        # 把 LLM 的可见回复追加到 messages(注意:存的是过滤后的可见文本)
        append_message(latest_state, req.combo_id, "assistant", visible_text)

        # 后台摘要(异步,不阻塞流)
        try:
            new_summary = await maybe_summarize_combo(latest_state, req.combo_id, llm)
        except Exception as e:
            logger.warning("maybe_summarize_combo 异常: %s", e)

        # 持久化
        save_v4_state(reports_root, rid, latest_state)

        # 推送结论卡事件(若有)
        if conclusion_card_event:
            yield f"data: {json.dumps({'conclusion_card': conclusion_card_event}, ensure_ascii=False)}\n\n"

        # 推送 chips 候选事件(无候选不推;前端收到即替换选择器)
        if hyp_candidates:
            yield f"data: {json.dumps({'type': 'hyp_candidates', 'hyp_candidates': hyp_candidates}, ensure_ascii=False)}\n\n"

        # 推送 tool 错误(若有,仅调试用)
        if tool_errors:
            yield f"data: {json.dumps({'tool_errors': tool_errors}, ensure_ascii=False)}\n\n"

        yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _parse_and_clean(text: str):
    """复用 service 的 parse_tool_blocks(返回 visible, tools)。"""
    from app.services.rumination_v4_service import parse_tool_blocks
    return parse_tool_blocks(text)


# ── 端点 7:DELETE /combos/{combo_id} ───────────────────────────────────
@router.delete("/combos/{combo_id}")
async def delete_combo_endpoint(combo_id: str, activation_code: str, current_user: dict = Depends(get_current_user)):
    """硬删除 combo_session(含 messages),仅审计日志保留。"""
    reports_root, rid, rec = _resolve_v4_ctx_with_rec(activation_code, current_user)
    _assert_rumination_editable(reports_root, rid, current_user, rec)
    try:
        state = svc_delete_combo(reports_root, rid, combo_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    _audit_log("rumination_v4_combo_deleted", current_user, activation_code, {"combo_id": combo_id})
    return {"code": 200, "message": "success", "data": {"combos": list_combos(state), "active_combo_id": state.get("active_combo_id")}}


# ── 端点 8:PATCH /combos/{combo_id}/conclusion-card ────────────────────
@router.patch("/combos/{combo_id}/conclusion-card")
async def patch_conclusion_card_endpoint(
    combo_id: str, req: PatchConclusionReq, current_user: dict = Depends(get_current_user)
):
    """用户直接编辑结论卡文本(不绕道 LLM)。"""
    reports_root, rid, rec = _resolve_v4_ctx_with_rec(req.activation_code, current_user)
    _assert_rumination_editable(reports_root, rid, current_user, rec)
    fields = {k: v for k, v in req.model_dump().items() if k != "activation_code" and v is not None}
    try:
        state, card = svc_patch_card(reports_root, rid, combo_id, fields)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _audit_log("rumination_v4_card_patched", current_user, req.activation_code, {"combo_id": combo_id})
    return {"code": 200, "message": "success", "data": {"conclusion_card": card}}


# ── 端点 9:POST /combos/{combo_id}/status(确认/放弃)──────────────────
@router.post("/combos/{combo_id}/status")
async def set_combo_status_endpoint(
    combo_id: str, req: SetStatusReq, current_user: dict = Depends(get_current_user)
):
    """用户确认或放弃 combo_session。"""
    reports_root, rid, rec = _resolve_v4_ctx_with_rec(req.activation_code, current_user)
    _assert_rumination_editable(reports_root, rid, current_user, rec)
    try:
        state = set_combo_status(reports_root, rid, combo_id, req.status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _audit_log("rumination_v4_combo_status", current_user, req.activation_code, {"combo_id": combo_id, "status": req.status})
    return {"code": 200, "message": "success", "data": {"combo": find_combo(state, combo_id)}}


# ── 端点 10:POST /final-selection ─────────────────────────────────────
@router.post("/final-selection")
async def final_selection_endpoint(req: FinalSelectionReq, current_user: dict = Depends(get_current_user)):
    """第 8 步:更新选定的 1-3 个 combo_id。"""
    reports_root, rid, rec = _resolve_v4_ctx_with_rec(req.activation_code, current_user)
    _assert_rumination_editable(reports_root, rid, current_user, rec)
    try:
        state = update_final_selection(reports_root, rid, req.selected_combo_ids)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"code": 200, "message": "success", "data": {"final_selection": state.get("final_selection")}}


# ── 端点 11:POST /final-selection/submit ──────────────────────────────
@router.post("/final-selection/submit")
async def submit_final_selection_endpoint(req: SubmitFinalReq, current_user: dict = Depends(get_current_user)):
    """第 8 步最终提交(锁定)。"""
    reports_root, rid, rec = _resolve_v4_ctx_with_rec(req.activation_code, current_user)
    _assert_rumination_editable(reports_root, rid, current_user, rec)
    try:
        state = submit_final_selection(reports_root, rid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # 终选提交即锁定 rumination（与其它四阶段「进入下一阶段锁上一阶段」口径对称；
    # rumination 是最后一步，无后续阶段触发锁定，需在此显式锁定）
    ReportRegistry(base_dir=str(reports_root)).lock_step(rid, "rumination")
    _audit_log("rumination_v4_final_submitted", current_user, req.activation_code, {"selected": state.get("final_selection", {}).get("selected_combo_ids")})
    return {"code": 200, "message": "success", "data": {"final_selection": state.get("final_selection"), "main_section": state.get("main_section")}}


# ── 端点 12:POST /active(切换 active combo)──────────────────────────
class SetActiveReq(BaseModel):
    activation_code: str
    combo_id: str


@router.post("/active")
async def set_active_endpoint(req: SetActiveReq, current_user: dict = Depends(get_current_user)):
    """切换 active combo(tag 条点击)。"""
    reports_root, rid = _resolve_v4_ctx(req.activation_code, current_user)
    try:
        state = set_active_combo(reports_root, rid, req.combo_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"code": 200, "message": "success", "data": {"active_combo_id": state.get("active_combo_id")}}
