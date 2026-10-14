"""AI 用例的固定上下文、受限断言和运行预算定义。此模块不发起模型请求。"""

import json
import re
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.services.test_center import digest, encode


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Message(Strict):
    role: Literal["user", "assistant", "system"]
    content: str = Field(max_length=16000)


class Card(Strict):
    hypothesis: str = Field(default="", max_length=8000)


class Combo(Strict):
    combo_id: str = Field(min_length=1, max_length=100)
    passion: str = Field(min_length=1, max_length=1000)
    strengths: list[str] = Field(min_length=1, max_length=30)
    status: Literal["discussing"] = "discussing"
    messages: list[Message] = Field(default_factory=list, max_length=200)
    summary: str = Field(default="", max_length=16000)
    summary_last_round: int = Field(default=0, ge=0)
    conclusion_card: Card = Field(default_factory=Card)
    reopen_feedback: str = Field(default="", max_length=4000)


class ContextSpec(Strict):
    name: str = Field(min_length=1, max_length=160)
    phase: Literal["values", "strengths", "interests", "purpose", "rumination"]
    thread_id: str = Field(min_length=1, max_length=100)
    messages: list[Message] = Field(default_factory=list, max_length=200)
    question_bank: str = Field(default="", max_length=16000)
    basic_info: str = Field(default="暂无", max_length=16000)
    prior_context: str = Field(default="", max_length=32000)
    values_info: str = Field(default="", max_length=16000)
    purpose_progress_injection: str = Field(default="", max_length=16000)
    conclusion_state_injection: str = Field(default="", max_length=16000)
    anchor_text: str = Field(default="", max_length=16000)
    user_context: str = Field(default="", max_length=32000)
    values_keywords: list[str] = Field(default_factory=list, max_length=100)
    combo: Combo | None = None
    source: Literal["manual", "debug_workspace"] = "manual"
    workflow_seed: dict | None = None

    @model_validator(mode="after")
    def coherent(self):
        if self.workflow_seed is not None:
            from app.services.test_center_workflow import METADATA_FIELDS, PHASES

            seed = self.workflow_seed
            allowed = {"completed_phases", "basic_info", "conclusions", "thread_metadata", "anchor"}
            if set(seed) - allowed:
                raise ValueError("业务起点含未知字段，不接受执行路径或产品配置")
            completed = seed.get("completed_phases", [])
            if not isinstance(completed, list) or any(
                p not in PHASES[: PHASES.index(self.phase)] for p in completed
            ):
                raise ValueError("前置完成阶段只能来自当前阶段之前")
            if any(not isinstance(seed.get(k, {}), dict) for k in allowed - {"completed_phases"}):
                raise ValueError("业务起点的资料、结论、状态与锚点必须为对象")
            if set(seed.get("conclusions", {})) - set(PHASES[:-1]):
                raise ValueError("只允许前四阶段结论")
            if any(not isinstance(c, dict) for c in seed.get("conclusions", {}).values()):
                raise ValueError("阶段结论必须为对象")
            meta = seed.get("thread_metadata", {})
            if set(meta) - METADATA_FIELDS:
                raise ValueError("线程状态含未知字段；不能传入产品配置或权限标记")
            if meta.get("conclusion_state", "none") not in {
                "none",
                "pending",
                "confirmed",
                "rejected",
            }:
                raise ValueError("结论状态无效")
            for key in ("conclusion_draft", "conclusion_final", "purpose_progress"):
                if meta.get(key) is not None and not isinstance(meta[key], dict):
                    raise ValueError(f"{key} 必须为对象")
            if "thread_completed" in meta and not isinstance(meta["thread_completed"], bool):
                raise ValueError("线程完成状态必须为布尔值")
            if "conclusion_feedback" in meta and not isinstance(meta["conclusion_feedback"], str):
                raise ValueError("结论反馈必须为文本")
            for key in ("conclusion_shown_at_turn", "conclusion_reject_baseline_user_count"):
                if meta.get(key) is not None and (type(meta[key]) is not int or meta[key] < 0):
                    raise ValueError("轮数必须为非负整数")
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", self.thread_id):
                raise ValueError("业务回放线程 ID 必须是安全的逻辑标识")
        if self.phase == "rumination":
            if not self.combo or self.combo.combo_id != self.thread_id:
                raise ValueError("v4 保存点必须包含对应 combo_id 的组合")
            if self.messages:
                raise ValueError("v4 历史只能放在所选组合内")
        elif self.combo:
            raise ValueError("前四阶段不能混入沉淀组合")
        elif not self.question_bank.strip():
            raise ValueError("前四阶段需要固定题库，不能在重跑时随机抽题")
        if len(self.model_dump_json().encode()) > 256 * 1024:
            raise ValueError("上下文超过 256 KiB，请缩减后保存")
        return self


def save_context(center, body):
    try:
        spec = ContextSpec.model_validate(body).model_dump()
    except ValidationError as error:
        raise ValueError(str(error)) from error
    context_id = digest(spec)
    payload = {"id": context_id, "created": time.time(), "spec": spec, "version": 1}
    with center.db() as db:
        db.execute(
            "INSERT OR IGNORE INTO contexts VALUES(?,?,?)",
            (context_id, payload["created"], encode(payload)),
        )
    return get_context(center, context_id)


def get_context(center, context_id):
    with center.db() as db:
        row = db.execute("SELECT payload FROM contexts WHERE id=?", (context_id,)).fetchone()
        if not row:
            raise KeyError(context_id)
        return json.loads(row[0])


def list_contexts(center):
    with center.db() as db:
        return [
            json.loads(r[0])
            for r in db.execute("SELECT payload FROM contexts ORDER BY created DESC")
        ]


def compile_ai(center, body, issues):
    try:
        context = get_context(center, body.get("context_id"))
    except KeyError:
        issues.append("请选择一个已保存的上下文起点")
        context = None
    if body.get("conversation_mode") == "workflow":
        from app.services.test_center_workflow import compile_workflow

        return {
            **compile_workflow(body, context, issues),
            "context_id": context["id"] if context else None,
            "repeats": body.get("repeats", 1),
            "targets": ["ai-replay"],
            "timeout": 1800,
            "conversation_mode": "workflow",
        }
    checks = []
    for text in body["assertions"]:
        text = text.strip()
        scoped = re.fullmatch(r"第([1-9][0-9]*)轮[：:]\s*(.+)", text, re.S)
        scope = {}
        if scoped:
            turn = int(scoped[1])
            if turn > len(body["inputs"]):
                issues.append(f"断言引用不存在的第 {turn} 轮")
                continue
            scope = {"turn": turn}
            text = scoped[2].strip()
        if text == "回复非空":
            checks.append({"type": "nonempty", **scope})
            continue
        match = re.fullmatch(r"(回复包含|回复不包含|语义)[：:]\s*(.+)", text, re.S)
        if not match or not match[2].strip():
            issues.append(
                f"未知断言：{text}；使用 回复非空 / 回复包含：… / 回复不包含：… / 语义：…"
            )
            continue
        checks.append(
            {
                "type": {
                    "回复包含": "contains",
                    "回复不包含": "excludes",
                    "语义": "semantic",
                }[match[1]],
                "value": match[2].strip(),
                **scope,
            }
        )
    mode = body.get("conversation_mode", "independent")
    if mode not in {"independent", "sequence"}:
        issues.append("对话模式必须是独立单轮或连续多轮")
    for turn in range(1, len(body["inputs"]) + 1):
        if not any(c.get("turn", turn) == turn for c in checks):
            issues.append(f"第 {turn} 轮缺少断言")
    return {
        "context_id": context["id"] if context else None,
        "checks": checks,
        "repeats": body.get("repeats", 1),
        "targets": ["ai-replay"],
        "timeout": 1800,
        "conversation_mode": mode,
    }


def build_messages(spec, user_input):
    """复用当前应用真正使用的构建器；不读/写业务数据或 Prompt Lab 全局绑定。"""
    if spec["phase"] == "rumination":
        from app.services.rumination_v4_service import build_chat_messages

        messages, _ = build_chat_messages(
            spec["combo"], user_input, spec["user_context"], spec["values_keywords"]
        )
        return [m.model_dump() for m in messages]
    from app.api.v1.simple_chat_routes import (
        _build_system_prompt,
        _trim_history_messages_for_llm,
    )
    from app.domain.conclusion_card_payload import build_conclusion_state_injection

    prompt = _build_system_prompt(
        spec["phase"],
        question_bank=spec["question_bank"],
        basic_info=spec["basic_info"],
        prior_context=spec["prior_context"],
        values_info=spec["values_info"],
        purpose_progress_injection=spec["purpose_progress_injection"],
    )
    prompt += "\n\n" + (
        spec["conclusion_state_injection"].strip()
        or build_conclusion_state_injection(spec["phase"], "none")
    )
    messages = [{"role": "system", "content": prompt}]
    if spec["anchor_text"]:
        messages.append({"role": "assistant", "content": "[此前对话要点]\n" + spec["anchor_text"]})
    messages.extend(_trim_history_messages_for_llm(spec["messages"]))
    return messages + [{"role": "user", "content": user_input}]
