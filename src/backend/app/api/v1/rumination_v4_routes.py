"""
Rumination v4 API 路由（2026-08-06 版，ADR-0015：用户主导结论卡 + 独立后台平衡点判定）

路由前缀: /api/v1/simple-chat/rumination-v4/...
(挂在 simple_chat.router 下,避免改动 main.py 注册)

端点:
- GET  /version                          v3/v4 分组判定
- GET  /state
- GET  /combos
- GET  /combos/{combo_id}
- POST /create-and-start
- POST /start-discussion
- POST /combo-chat                       (SSE 流式;纯对话,无任何隐藏协议)
- DELETE /combos/{combo_id}
- PATCH /combos/{combo_id}/conclusion-card           (用户手填/修改 hypothesis)
- POST /combos/{combo_id}/conclusion-card/confirm    (SSE:确认+平衡点判定,兼重试)
- POST /combos/{combo_id}/analysis/stream            (SSE:判定结果补拉/附着)
- POST /combos/{combo_id}/status         (跳过 abandoned / 再聊聊 discussing)
- POST /final-selection
- POST /final-selection/submit
- POST /active

数据模型与决策见 wiki/开发文档/0707-tag1.6.0.md + docs/adr/0015
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
    append_message,
    build_chat_messages,
    confirm_conclusion_card,
    create_and_start as svc_create_and_start,
    delete_combo as svc_delete_combo,
    find_combo,
    get_live_analysis_task,
    invalidate_balance_analysis,
    is_analyzing,
    list_combos,
    load_v4_state,
    mark_intro_shown,
    maybe_summarize_combo,
    patch_conclusion_card as svc_patch_card,
    register_analysis_task,
    run_balance_judge,
    save_v4_state,
    set_active_combo,
    set_combo_status,
    submit_final_selection,
    sweep_orphan_analysis,
    unregister_analysis_task,
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


def _sse(obj: Dict[str, Any]) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


# ── 请求/响应模型 ───────────────────────────────────────────────────────
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
    hypothesis: str  # 2026-08-06(ADR-0015):卡仅 hypothesis 一字段


class SetStatusReq(BaseModel):
    activation_code: str
    status: str  # abandoned | discussing(concluded 走 confirm 端点)


class FinalSelectionReq(BaseModel):
    activation_code: str
    selected_combo_ids: List[str]


class SubmitFinalReq(BaseModel):
    activation_code: str


class ConfirmReq(BaseModel):
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
    # ReportRegistry 的 base_dir 是 simple 根（内部再拼 /reports），不能传 reports_root
    registry = ReportRegistry(base_dir=str(reports_root.parent))
    record = registry.get_report_by_id(rid) or {}
    step = ((record.get("steps") or {}).get("rumination")) or {}
    if step.get("locked"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="最终选择已提交并锁定，报告已生成，不能再修改",
        )


def _assert_not_analyzing(combo: Dict[str, Any]) -> None:
    """分析中锁(ADR-0015):该 combo 的对话输入与结论卡编辑一并锁定。"""
    if is_analyzing(combo):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="正在分析中，请稍后",
        )


def _load_state_swept(reports_root: Path, rid: str) -> Dict[str, Any]:
    """载 state 并自愈孤儿判定(analyzing 但无存活任务 → failed,可重试)。"""
    state = load_v4_state(reports_root, rid)
    if sweep_orphan_analysis(state, rid):
        save_v4_state(reports_root, rid, state)
    return state


def _build_user_context(
    reports_root: Path, rid: str, rec, activation_code: str
) -> Tuple[str, Optional[List[str]]]:
    """装配 combo-chat 的用户上下文。

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

    state = _load_state_swept(reports_root, rid)
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
    state = _load_state_swept(reports_root, rid)
    return {"code": 200, "message": "success", "data": {"combos": list_combos(state), "active_combo_id": state.get("active_combo_id")}}


# ── 端点 3:GET /combos/{combo_id} ──────────────────────────────────────
@router.get("/combos/{combo_id}")
async def get_combo_detail(combo_id: str, activation_code: str, current_user: dict = Depends(get_current_user)):
    """获取单个 combo_session 详情(含 messages)。"""
    reports_root, rid = _resolve_v4_ctx(activation_code, current_user)
    state = _load_state_swept(reports_root, rid)
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
    opening_text = (
        f"好的,我们就来聊聊「{combo.get('passion')}」+「{'、'.join(combo.get('strengths') or [])}」这个组合。\n\n"
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
    """主对话端点(SSE 流式)。

    2026-08-06(ADR-0015):纯对话,无任何隐藏协议(chips/tool/双信号已删除);
    分析中的 combo 拒绝新消息(锁输入);新对话作废旧判定(聊即作废)。
    """
    reports_root, rid, rec = _resolve_v4_ctx_with_rec(req.activation_code, current_user)
    _assert_rumination_editable(reports_root, rid, current_user, rec)
    state = load_v4_state(reports_root, rid)
    combo = find_combo(state, req.combo_id)
    if not combo:
        raise HTTPException(status_code=404, detail="combo_id 不存在")
    if combo.get("status") in ("concluded", "abandoned"):
        raise HTTPException(status_code=400, detail=f"该组合已 {combo.get('status')},不可继续对话")
    _assert_not_analyzing(combo)

    user_msg = (req.message or "").strip()
    if not user_msg:
        raise HTTPException(status_code=400, detail="message 不可为空")

    # 新对话作废旧判定(ADR-0015:聊即作废,灯灭,需重新确认)
    invalidate_balance_analysis(combo)

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

        full_reply = ""
        async for piece in llm.chat_stream(llm_messages, temperature=0.7, max_tokens=800):
            if isinstance(piece, dict):
                # 项目内 think_chunk 等特殊信号,透传
                t = piece.get("_t")
                if t == "think_start":
                    yield _sse({"think_start": True})
                elif t == "think_chunk":
                    yield _sse({"think_chunk": piece.get("content") or ""})
                elif t == "think_end":
                    yield _sse({"think_end": piece.get("content")})
                continue
            if piece:
                full_reply += piece
                yield _sse({"chunk": piece})

        visible_text = full_reply.strip()

        # 空可见回复兜底:避免「空气泡」
        if not visible_text:
            logger.warning("combo-chat 空可见回复 combo_id=%s", req.combo_id)
            visible_text = "嗯,我记下了。这个想法里,最吸引你的是哪一点?可以多跟我说说。"
            yield _sse({"chunk": visible_text})

        # 把 LLM 的可见回复追加到 messages
        append_message(latest_state, req.combo_id, "assistant", visible_text)

        # 后台摘要(异步,不阻塞流)
        try:
            await maybe_summarize_combo(latest_state, req.combo_id, llm)
        except Exception as e:
            logger.warning("maybe_summarize_combo 异常: %s", e)

        # 持久化
        save_v4_state(reports_root, rid, latest_state)

        yield _sse({"done": True})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── 端点 7:DELETE /combos/{combo_id} ───────────────────────────────────
@router.delete("/combos/{combo_id}")
async def delete_combo_endpoint(combo_id: str, activation_code: str, current_user: dict = Depends(get_current_user)):
    """硬删除 combo_session(含 messages),仅审计日志保留。
    分析中删除:允许;判定任务写盘前发现 combo 不存在会丢弃结果。"""
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
    """用户手填/修改结论卡 hypothesis(不绕道 LLM)。

    2026-08-06(ADR-0015):hypothesis 变更即作废旧判定;已确认卡被修改后退回
    discussing(未确认态),需重新点「确认」触发重判。分析中拒绝编辑(409)。
    """
    reports_root, rid, rec = _resolve_v4_ctx_with_rec(req.activation_code, current_user)
    _assert_rumination_editable(reports_root, rid, current_user, rec)
    state = load_v4_state(reports_root, rid)
    combo = find_combo(state, combo_id)
    if not combo:
        raise HTTPException(status_code=404, detail="combo_id 不存在")
    _assert_not_analyzing(combo)
    try:
        state, card = svc_patch_card(reports_root, rid, combo_id, req.hypothesis)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _audit_log("rumination_v4_card_patched", current_user, req.activation_code, {"combo_id": combo_id})
    return {"code": 200, "message": "success", "data": {"conclusion_card": card, "combo": find_combo(state, combo_id)}}


# ── 端点 9:POST /combos/{combo_id}/conclusion-card/confirm(SSE)────────
@router.post("/combos/{combo_id}/conclusion-card/confirm")
async def confirm_conclusion_card_endpoint(
    combo_id: str, req: ConfirmReq, current_user: dict = Depends(get_current_user)
):
    """用户点「确认」(ADR-0015):置 concluded + analyzing,流内执行平衡点判定。

    SSE 事件:
    - {analysis_status: 'analyzing'}        —— 已进入判定
    - {analysis_done: {balance_found, balance_fail_reason}} —— 判定完成
    - {analysis_failed: {error}}            —— 判定失败(可重新调本端点重试)
    - {done: true}                          —— 流结束
    """
    reports_root, rid, rec = _resolve_v4_ctx_with_rec(req.activation_code, current_user)
    _assert_rumination_editable(reports_root, rid, current_user, rec)
    try:
        _state, combo, started_at = confirm_conclusion_card(reports_root, rid, combo_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _audit_log(
        "rumination_v4_card_confirmed",
        current_user,
        req.activation_code,
        {"combo_id": combo_id},
    )
    llm = _get_dialogue_llm_provider(vip_level=1)

    async def event_stream() -> AsyncIterator[str]:
        yield _sse({"analysis_status": "analyzing"})
        task = asyncio.create_task(run_balance_judge(reports_root, rid, combo_id, llm, started_at))
        register_analysis_task(rid, combo_id, task)
        try:
            analysis = await task
        except asyncio.CancelledError:
            # 客户端断连:任务一并取消,analyzing 态由 sweep 自愈为 failed
            task.cancel()
            raise
        finally:
            unregister_analysis_task(rid, combo_id, task)
        if analysis.get("status") == "done":
            yield _sse(
                {
                    "analysis_done": {
                        "balance_found": analysis.get("balance_found"),
                        "balance_fail_reason": analysis.get("balance_fail_reason"),
                    }
                }
            )
        else:
            yield _sse({"analysis_failed": {"error": analysis.get("error") or "判定失败"}})
        yield _sse({"done": True})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── 端点 10:POST /combos/{combo_id}/analysis/stream(SSE 补拉)───────────
@router.post("/combos/{combo_id}/analysis/stream")
async def analysis_stream_endpoint(
    combo_id: str, req: ConfirmReq, current_user: dict = Depends(get_current_user)
):
    """判定结果补拉/附着(ADR-0015:刷新/重进页面时前端自动调本端点)。

    - done/failed           → 直接回放当前结果
    - analyzing 且任务存活  → 附着(await 存活任务后推结果)
    - analyzing 但任务孤儿  → 视同重试,本流内重跑判定
    - 无判定记录            → 推 {analysis_status: 'none'}(前端应回到草稿态)
    """
    reports_root, rid, rec = _resolve_v4_ctx_with_rec(req.activation_code, current_user)
    _assert_rumination_editable(reports_root, rid, current_user, rec)
    state = _load_state_swept(reports_root, rid)
    combo = find_combo(state, combo_id)
    if not combo:
        raise HTTPException(status_code=404, detail="combo_id 不存在")
    llm = _get_dialogue_llm_provider(vip_level=1)

    def _result_events(analysis: Dict[str, Any]) -> List[str]:
        if analysis.get("status") == "done":
            return [
                _sse(
                    {
                        "analysis_done": {
                            "balance_found": analysis.get("balance_found"),
                            "balance_fail_reason": analysis.get("balance_fail_reason"),
                        }
                    }
                )
            ]
        if analysis.get("status") == "failed":
            return [_sse({"analysis_failed": {"error": analysis.get("error") or "判定失败"}})]
        return [_sse({"analysis_status": analysis.get("status") or "none"})]

    async def event_stream() -> AsyncIterator[str]:
        # 读取最新状态(可能在 sweep 后已变 failed)
        cur_state = load_v4_state(reports_root, rid)
        cur_combo = find_combo(cur_state, combo_id)
        analysis = (cur_combo or {}).get("balance_analysis") or {}
        status_now = analysis.get("status")

        if status_now in ("done", "failed"):
            for e in _result_events(analysis):
                yield e
            yield _sse({"done": True})
            return

        if status_now == "analyzing":
            live = get_live_analysis_task(rid, combo_id)
            if live is not None and not live.done():
                # 附着存活任务
                yield _sse({"analysis_status": "analyzing"})
                try:
                    result = await asyncio.shield(live)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    yield _sse({"analysis_failed": {"error": str(e)}})
                    yield _sse({"done": True})
                    return
                for e in _result_events(result or {}):
                    yield e
                yield _sse({"done": True})
                return
            # 孤儿 analyzing(sweep 未及时介入的竞态):本流内重跑
            try:
                _s, _c, started_at = confirm_conclusion_card(reports_root, rid, combo_id)
            except ValueError as e:
                yield _sse({"analysis_failed": {"error": str(e)}})
                yield _sse({"done": True})
                return
            yield _sse({"analysis_status": "analyzing"})
            task = asyncio.create_task(run_balance_judge(reports_root, rid, combo_id, llm, started_at))
            register_analysis_task(rid, combo_id, task)
            try:
                result = await task
            except asyncio.CancelledError:
                task.cancel()
                raise
            finally:
                unregister_analysis_task(rid, combo_id, task)
            for e in _result_events(result or {}):
                yield e
            yield _sse({"done": True})
            return

        # 无判定记录
        yield _sse({"analysis_status": "none"})
        yield _sse({"done": True})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── 端点 11:POST /combos/{combo_id}/status(跳过/再聊聊)─────────────────
@router.post("/combos/{combo_id}/status")
async def set_combo_status_endpoint(
    combo_id: str, req: SetStatusReq, current_user: dict = Depends(get_current_user)
):
    """跳过(abandoned)/再聊聊(discussing)。

    2026-08-06(ADR-0015):确认(concluded)统一走 conclusion-card/confirm 端点(含判定),
    本端点的 concluded 请求会被 service 层拒绝(双保险)。
    """
    reports_root, rid, rec = _resolve_v4_ctx_with_rec(req.activation_code, current_user)
    _assert_rumination_editable(reports_root, rid, current_user, rec)
    try:
        state = set_combo_status(reports_root, rid, combo_id, req.status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _audit_log("rumination_v4_combo_status", current_user, req.activation_code, {"combo_id": combo_id, "status": req.status})
    return {"code": 200, "message": "success", "data": {"combo": find_combo(state, combo_id)}}


# ── 端点 12:POST /final-selection ─────────────────────────────────────
@router.post("/final-selection")
async def final_selection_endpoint(req: FinalSelectionReq, current_user: dict = Depends(get_current_user)):
    """第 8 步:更新选定的 1-3 个 combo_id。
    ADR-0015 门槛:所有已确认卡必须判定完成,否则 400「有结论卡正在分析中,请稍后」。"""
    reports_root, rid, rec = _resolve_v4_ctx_with_rec(req.activation_code, current_user)
    _assert_rumination_editable(reports_root, rid, current_user, rec)
    try:
        state = update_final_selection(reports_root, rid, req.selected_combo_ids)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"code": 200, "message": "success", "data": {"final_selection": state.get("final_selection")}}


# ── 端点 13:POST /final-selection/submit ──────────────────────────────
@router.post("/final-selection/submit")
async def submit_final_selection_endpoint(req: SubmitFinalReq, current_user: dict = Depends(get_current_user)):
    """第 8 步最终提交(锁定)。ADR-0015:所有已确认卡必须判定完成。"""
    reports_root, rid, rec = _resolve_v4_ctx_with_rec(req.activation_code, current_user)
    _assert_rumination_editable(reports_root, rid, current_user, rec)
    try:
        state = submit_final_selection(reports_root, rid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # 终选提交即锁定 rumination（与其它四阶段「进入下一阶段锁上一阶段」口径对称；
    # rumination 是最后一步，无后续阶段触发锁定，需在此显式锁定）
    ReportRegistry(base_dir=str(reports_root.parent)).lock_step(rid, "rumination")
    _audit_log("rumination_v4_final_submitted", current_user, req.activation_code, {"selected": state.get("final_selection", {}).get("selected_combo_ids")})
    return {"code": 200, "message": "success", "data": {"final_selection": state.get("final_selection"), "main_section": state.get("main_section")}}


# ── 端点 14:POST /active(切换 active combo)──────────────────────────
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


# ── 端点 15:POST /intro-shown(开场弹窗已读标记)────────────────────────
class IntroShownReq(BaseModel):
    activation_code: str


@router.post("/intro-shown")
async def intro_shown_endpoint(req: IntroShownReq, current_user: dict = Depends(get_current_user)):
    """标记 v4 开场弹窗已展示（每个激活码的 rumination report 首次进入 v4 页面弹一次）。

    纯 UI 标记，不做 editable 锁检查（报告定稿后回看页面也允许落标记）。
    """
    reports_root, rid = _resolve_v4_ctx(req.activation_code, current_user)
    state = mark_intro_shown(reports_root, rid)
    return {"code": 200, "message": "success", "data": {"intro_shown": state.get("intro_shown")}}
