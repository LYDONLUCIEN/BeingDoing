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
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.v1.auth import get_current_user
from app.api.v1.simple_chat.context_resolver import (
    resolve_report_context as _resolve_report_context,
)
from app.api.v1.simple_chat.llm_providers import (
    get_dialogue_llm_provider as _get_dialogue_llm_provider,
)
from app.utils.simple_activation_manager import (
    get_activation_manager_for_code,
    get_effective_simple_root,
)
from app.utils.rumination_ops import extract_dimension_lists_for_rumination_table
from app.services.rumination_v4_service import (
    CONCLUSION_READY_MARKER,
    apply_tool_call,
    append_message,
    build_chat_messages,
    create_and_start as svc_create_and_start,
    delete_combo as svc_delete_combo,
    detect_conclusion_signals,
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


def _get_values_list() -> List[str]:
    """从价值观 CSV 读取可选价值观列表(供 LLM prompt 参考)。
    简化:返回固定列表(可后续接 CSV 加载)。"""
    return ["发现", "冒险", "达成", "贡献", "自由", "成长", "连接", "掌控"]


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
    reports_root, rid = _resolve_v4_ctx(req.activation_code, current_user)
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
    reports_root, rid = _resolve_v4_ctx(req.activation_code, current_user)
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
    """主对话端点(SSE 流式)。LLM 自主调 tool,后端解析隐藏 JSON 块 + 双信号兜底。"""
    reports_root, rid = _resolve_v4_ctx(req.activation_code, current_user)
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

    values_list = _get_values_list()
    vip_level = 1

    async def event_stream() -> AsyncIterator[str]:
        # 重新加载最新 state(用户消息已落盘)
        latest_state = load_v4_state(reports_root, rid)
        combo_obj = find_combo(latest_state, req.combo_id)
        # 拼装 LLM 消息
        llm_messages, _sys_prompt = build_chat_messages(combo_obj, user_msg, values_list)
        llm = _get_dialogue_llm_provider(vip_level=vip_level)

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
                # 过滤掉 <<CONCLUSION_READY>> 标记后再流给前端
                safe = piece.replace(CONCLUSION_READY_MARKER, "")
                if safe:
                    yield f"data: {json.dumps({'chunk': safe}, ensure_ascii=False)}\n\n"

        # 流式结束,解析完整回复
        visible_text, tool_calls = _parse_and_clean(full_reply)
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
            card = await fallback_generate_conclusion(combo_obj, llm, values_list)
            if card:
                # 直接写 conclusion_card
                apply_tc = {"tool": "save_conclusion_card", "fields": {
                    "hypothesis": card.get("hypothesis"),
                    "motivation": card.get("motivation"),
                    "work_purposes": card.get("work_purposes"),
                    "passion_mark": card.get("passion_mark"),
                    "timing_mark": card.get("timing_mark"),
                }}
                c2, _e = apply_tool_call(latest_state, req.combo_id, apply_tc)
                if c2:
                    conclusion_card_event = c2

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
    reports_root, rid = _resolve_v4_ctx(activation_code, current_user)
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
    reports_root, rid = _resolve_v4_ctx(req.activation_code, current_user)
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
    reports_root, rid = _resolve_v4_ctx(req.activation_code, current_user)
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
    reports_root, rid = _resolve_v4_ctx(req.activation_code, current_user)
    try:
        state = update_final_selection(reports_root, rid, req.selected_combo_ids)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"code": 200, "message": "success", "data": {"final_selection": state.get("final_selection")}}


# ── 端点 11:POST /final-selection/submit ──────────────────────────────
@router.post("/final-selection/submit")
async def submit_final_selection_endpoint(req: SubmitFinalReq, current_user: dict = Depends(get_current_user)):
    """第 8 步最终提交(锁定)。"""
    reports_root, rid = _resolve_v4_ctx(req.activation_code, current_user)
    try:
        state = submit_final_selection(reports_root, rid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
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
