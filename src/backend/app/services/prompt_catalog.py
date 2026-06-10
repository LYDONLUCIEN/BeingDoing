"""
Admin Prompt Catalog：只读聚合 simple_chat 相关提示词与运行时注入元数据。
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

import yaml

from app.api.v1.simple_chat.prompt_builder import build_fallback_opening_question, build_system_prompt
from app.domain.conclusion_card_payload import build_state_json_draft_extension_protocol
from app.domain.prompts.loader import _get_loader, get_step_copy
from app.domain.rumination_prompt_strings import (
    DEEP_CHAT_STEP_SYSTEM_MAP,
    OPENING_USER_WITH_TABLE_ZH,
    RUMINATION_CHAT_STEP_ADDON_EN,
    RUMINATION_CHAT_STEP_ADDON_ZH,
    RUMINATION_CLOSING_EPILOGUE_SYSTEM_ZH,
    RUMINATION_CLOSING_EPILOGUE_USER_TEMPLATE_ZH,
    RUMINATION_ENTRY_INIT_SYSTEM_ZH,
    RUMINATION_ENTRY_INIT_USER_TEMPLATE_ZH,
    RUMINATION_SHORTPATH_SKIP_CLOSING_FIXED_ZH,
    STEP_1_OPENING_SYSTEM_ZH,
    STEP_2_OPENING_SYSTEM_ZH,
    STEP_3_OPENING_SYSTEM_ZH,
    STEP_4_OPENING_SYSTEM_ZH,
    STEP_4_OPENING_USER_TEMPLATE_ZH,
    STEP_5_OPENING_SYSTEM_ZH,
    STEP_6_OPENING_SYSTEM_ZH,
    STEP_7_OPENING_SYSTEM_ZH,
    STEP_OPENING_FIXED_ZH,
)
from app.domain.rumination_step_guidance import STEP_OPENING_MODE
from app.services.rumination_init_greeting import RUMINATION_INIT_FALLBACK_ZH
from app.utils.admin_prompt_lab import get_profile
from app.utils.purpose_progress import build_progress_injection, normalize_progress

PHASE_KEYS = ("values", "strengths", "interests", "purpose", "rumination")

PHASE_LABELS: Dict[str, str] = {
    "values": "价值观",
    "strengths": "优势",
    "interests": "热爱",
    "purpose": "使命",
    "rumination": "沉淀",
}

PHASE_COLORS: Dict[str, str] = {
    "values": "blue",
    "strengths": "amber",
    "interests": "rose",
    "purpose": "emerald",
    "rumination": "violet",
}

_STEP_OPENING_SYSTEM: Dict[int, str] = {
    1: STEP_1_OPENING_SYSTEM_ZH,
    2: STEP_2_OPENING_SYSTEM_ZH,
    3: STEP_3_OPENING_SYSTEM_ZH,
    4: STEP_4_OPENING_SYSTEM_ZH,
    5: STEP_5_OPENING_SYSTEM_ZH,
    6: STEP_6_OPENING_SYSTEM_ZH,
    7: STEP_7_OPENING_SYSTEM_ZH,
}

_VAR_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
_PHASE_BRANCH_PATTERN = re.compile(
    r"{%\s*if\s+phase\s*==\s*[\"'](\w+)[\"']\s*%}(.*?)(?={%\s*elif\s+phase|{%\s*else\s*%}|{%\s*endif\s*%})",
    re.DOTALL,
)
_ELIF_BRANCH_PATTERN = re.compile(
    r"{%\s*elif\s+phase\s*==\s*[\"'](\w+)[\"']\s*%}(.*?)(?={%\s*elif\s+phase|{%\s*else\s*%}|{%\s*endif\s*%})",
    re.DOTALL,
)
_ELSE_BRANCH_PATTERN = re.compile(
    r"{%\s*else\s*%}(.*?){%\s*endif\s*%}",
    re.DOTALL,
)
_NESTED_IF_PATTERN = re.compile(
    r"{%\s*if\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*%}(.*?)(?:{%\s*endif\s*%})",
    re.DOTALL,
)


def get_variable_samples(locale: str = "zh") -> Dict[str, str]:
    """Hover 示例：供前端 {{ var }} 标签展示。"""
    loc = (locale or "zh").strip().lower()
    addon = RUMINATION_CHAT_STEP_ADDON_ZH.get(3, "") if not loc.startswith("en") else RUMINATION_CHAT_STEP_ADDON_EN.get(3, "")
    prior = (
        "【价值观】成长、关系、平衡\n"
        "【优势】倾听、结构化思考\n"
        "【热爱】教育、写作\n"
        "【使命】帮助他人获得成长与启发"
    )
    return {
        "phase": "values",
        "question_bank": "1. 最近一次让你很有意义感的事情是什么？\n2. 你希望在工作中获得什么？",
        "basic_info": "姓名：小明\n职业：产品经理\n工作年限：5年",
        "prior_block": f"\n\n以下是该来访者在上一轮咨询中的谈话结果，供你参考：\n{prior}",
        "values_info": "成长、关系、身心平衡",
        "rumination_step_addon": addon[:200] + ("…" if len(addon) > 200 else ""),
        "row_count": "12",
        "table_json": '[{"passion":"写作","strength":"结构化思考"}]',
        "values_keywords": "成长、关系、平衡",
        "selected_summary": "1. 教育内容创作\n2. 职业咨询",
        "prior_block_entry": prior[:400],
    }


def _templates_dir() -> str:
    return _get_loader().templates_dir


def _load_yaml_file(name: str) -> Dict[str, Any]:
    path = os.path.join(_templates_dir(), f"{name}.yaml")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f.read())
    return data if isinstance(data, dict) else {}


def load_canonical_simple_chat_template() -> Tuple[str, str]:
    """返回 (source_path, raw prompt 模板文本)。"""
    rel = "domain/prompts/templates/simple_chat_system.yaml"
    data = _load_yaml_file("simple_chat_system")
    prompt = (data.get("prompt") or "").strip()
    return rel, prompt


def parse_content_segments(content: str) -> List[Dict[str, Any]]:
    """将文本拆分为 static / variable 片段。"""
    segments: List[Dict[str, Any]] = []
    last = 0
    for m in _VAR_PATTERN.finditer(content):
        if m.start() > last:
            text = content[last : m.start()]
            if text:
                segments.append({"type": "text", "content": text})
        segments.append({"type": "variable", "name": m.group(1), "raw": m.group(0)})
        last = m.end()
    if last < len(content):
        tail = content[last:]
        if tail:
            segments.append({"type": "text", "content": tail})
    return segments


def extract_phase_branches(template: str) -> List[Dict[str, Any]]:
    """从 simple_chat_system 模板提取各 phase 分支。"""
    branches: List[Dict[str, Any]] = []
    for m in _PHASE_BRANCH_PATTERN.finditer(template):
        phase = m.group(1)
        body = m.group(2).strip()
        branches.append(
            {
                "phase": phase,
                "content": body,
                "segments": parse_content_segments(body),
                "nested_conditions": _extract_nested_ifs(body),
            }
        )
    for m in _ELIF_BRANCH_PATTERN.finditer(template):
        phase = m.group(1)
        body = m.group(2).strip()
        if not any(b["phase"] == phase for b in branches):
            branches.append(
                {
                    "phase": phase,
                    "content": body,
                    "segments": parse_content_segments(body),
                    "nested_conditions": _extract_nested_ifs(body),
                }
            )
    em = _ELSE_BRANCH_PATTERN.search(template)
    if em:
        body = em.group(1).strip()
        branches.append(
            {
                "phase": "_else",
                "content": body,
                "segments": parse_content_segments(body),
                "nested_conditions": _extract_nested_ifs(body),
            }
        )
    return branches


def _extract_nested_ifs(body: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for m in _NESTED_IF_PATTERN.finditer(body):
        cond = m.group(1)
        inner = m.group(2).strip()
        out.append(
            {
                "condition": cond,
                "content": inner,
                "segments": parse_content_segments(inner),
            }
        )
    return out


def get_runtime_injection_catalog() -> List[Dict[str, Any]]:
    """全局运行时注入层元数据（按 build_system_prompt 及关联模块拼装顺序）。"""
    sample_prog = build_progress_injection(normalize_progress({"current_index": 2, "confirmed_rows": []}))
    protocol_sample = build_state_json_draft_extension_protocol("values")
    return [
        {
            "id": "purpose_progress",
            "label": "使命进度注入",
            "category": "runtime",
            "order": 20,
            "inject_after": "simple_chat_system 主模板",
            "trigger": "phase == purpose 且 metadata.purpose_progress 非空",
            "source_path": "utils/purpose_progress.py · build_progress_injection",
            "sample_content": sample_prog,
            "phases": ["purpose"],
        },
        {
            "id": "rumination_step_addon",
            "label": "沉淀子步 chat_addon",
            "category": "runtime",
            "order": 15,
            "inject_after": "simple_chat_system rumination 分支内",
            "trigger": "phase == rumination 且 filter_step 1-7",
            "source_path": "domain/rumination_step_guidance.py · get_rumination_chat_step_addon",
            "sample_content": RUMINATION_CHAT_STEP_ADDON_ZH.get(3, "")[:300],
            "phases": ["rumination"],
        },
        {
            "id": "neg_gate_deep_chat",
            "label": "深入讨论 neg gate 注入",
            "category": "runtime",
            "order": 25,
            "inject_after": "simple_chat_system 渲染后末尾追加",
            "trigger": "rumination 步骤 2/3/5/6 neg gate exploring",
            "source_path": "utils/rumination_neg_gate.py · build_injection_zh",
            "sample_content": list(DEEP_CHAT_STEP_SYSTEM_MAP.values())[0][:200] if DEEP_CHAT_STEP_SYSTEM_MAP else "",
            "phases": ["rumination"],
        },
        {
            "id": "pending_rejection_injection",
            "label": "结论卡拒绝后再聊聊",
            "category": "runtime",
            "order": 12,
            "inject_after": "主对话上下文（user/assistant 历史）",
            "trigger": "conclusion_state == rejected",
            "source_path": "domain/conclusion_card_payload.py · format_rejected_conclusion_injection",
            "sample_content": "上一版结论草案用户未采纳…",
            "phases": list(PHASE_KEYS[:4]),
        },
        {
            "id": "state_json_protocol",
            "label": "STATE_JSON 输出协议",
            "category": "runtime",
            "order": 90,
            "inject_after": "主模板 + purpose_progress 之后",
            "trigger": "每次 build_system_prompt",
            "source_path": "api/v1/simple_chat/prompt_builder.py · build_system_prompt",
            "sample_content": protocol_sample[:400],
            "phases": list(PHASE_KEYS),
        },
        {
            "id": "conclusion_rules",
            "label": "结论卡 draft 扩展字段规则",
            "category": "runtime",
            "order": 91,
            "inject_after": "STATE_JSON 协议块内",
            "trigger": "按 phase 动态生成 extension protocol",
            "source_path": "domain/conclusion_card_payload.py · build_state_json_draft_extension_protocol",
            "sample_content": protocol_sample,
            "phases": list(PHASE_KEYS[:4]),
        },
        {
            "id": "dimension_completion",
            "label": "confirmed 二次生成（非主对话）",
            "category": "runtime",
            "order": 100,
            "inject_after": "独立 LLM 调用（pending 确认后）",
            "trigger": "check_dimension_complete confirmed 分支",
            "source_path": "core/dimension_completion_checker.py",
            "sample_content": "【本阶段文风规则】…（独立 prompt，不进入主 system）",
            "phases": list(PHASE_KEYS[:4]),
        },
        {
            "id": "init_fallback",
            "label": "Init 兜底开场",
            "category": "fallback",
            "order": 5,
            "inject_after": "POST /init LLM 失败",
            "trigger": "LLM 不可用或返回空",
            "source_path": "api/v1/simple_chat/prompt_builder.py · build_fallback_opening_question",
            "sample_content": build_fallback_opening_question("values"),
            "phases": list(PHASE_KEYS),
        },
        {
            "id": "rumination_init_fallback",
            "label": "沉淀 entry_init 降级",
            "category": "fallback",
            "order": 6,
            "inject_after": "synthesize_rumination_entry_greeting 失败",
            "trigger": "rumination 首次 init LLM 失败",
            "source_path": "services/rumination_init_greeting.py · RUMINATION_INIT_FALLBACK_ZH",
            "sample_content": RUMINATION_INIT_FALLBACK_ZH,
            "phases": ["rumination"],
        },
        {
            "id": "extra_goal_hint",
            "label": "Prompt Lab 调试目标补充",
            "category": "addon",
            "order": 85,
            "inject_after": "simple_chat_system 渲染后",
            "trigger": "沙箱 Prompt Lab profile 绑定且 extra_goal_hint 非空",
            "source_path": "utils/admin_prompt_lab.py · resolve_simple_chat_prompt_override",
            "sample_content": "[管理员调试目标补充]\n（示例）更强调一次一问",
            "phases": list(PHASE_KEYS),
        },
    ]


def _build_main_layer_stack(
    phase: str,
    branches: List[Dict[str, Any]],
    runtime_catalog: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """主对话 layer stack：静态分支 + 运行时注入槽位。"""
    layers: List[Dict[str, Any]] = []
    for br in branches:
        match_phase = br["phase"]
        layers.append(
            {
                "id": f"phase_branch_{match_phase}",
                "kind": "static",
                "category": "main",
                "label": f"Jinja 分支 · phase={match_phase}",
                "phase_match": match_phase,
                "active": match_phase == phase,
                "content": br["content"],
                "segments": br["segments"],
                "nested_conditions": br.get("nested_conditions") or [],
            }
        )
    for rt in sorted(runtime_catalog, key=lambda x: x.get("order", 0)):
        if phase not in (rt.get("phases") or []):
            continue
        layers.append(
            {
                "id": rt["id"],
                "kind": "runtime",
                "category": rt.get("category", "runtime"),
                "label": rt["label"],
                "inject_after": rt.get("inject_after"),
                "trigger": rt.get("trigger"),
                "source_path": rt.get("source_path"),
                "collapsed_default": True,
                "content": rt.get("sample_content") or "",
            }
        )
    return layers


def _step_copy_section(phase: str, position: str, locale: str) -> Dict[str, Any]:
    content = get_step_copy(phase, position, locale)
    return {
        "key": position,
        "label": "阶段开场" if position == "intro" else "阶段结束",
        "category": "intro" if position == "intro" else "outro",
        "source_path": "domain/prompts/templates/step_copy.yaml",
        "content": content,
        "segments": parse_content_segments(content),
    }


def _rumination_step_sections(step: int, locale: str) -> List[Dict[str, Any]]:
    loc = (locale or "zh").strip().lower()
    mode = STEP_OPENING_MODE.get(step, "llm")
    sections: List[Dict[str, Any]] = []

    opening_label = "固定开场" if mode == "fixed" else "LLM 开场 system"
    opening_content = (
        STEP_OPENING_FIXED_ZH.get(step, "")
        if mode == "fixed"
        else _STEP_OPENING_SYSTEM.get(step, "")
    )
    sections.append(
        {
            "key": "opening",
            "label": opening_label,
            "category": "intro",
            "opening_mode": mode,
            "source_path": (
                "domain/rumination_prompt_strings.py · STEP_OPENING_FIXED_ZH"
                if mode == "fixed"
                else "domain/rumination_prompt_strings.py · STEP_{n}_OPENING_SYSTEM_ZH"
            ),
            "content": opening_content,
            "segments": parse_content_segments(opening_content),
        }
    )

    if mode == "llm":
        user_tpl = STEP_4_OPENING_USER_TEMPLATE_ZH if step == 4 else OPENING_USER_WITH_TABLE_ZH
        sections.append(
            {
                "key": "opening_user",
                "label": "LLM 开场 user 模板",
                "category": "main",
                "source_path": "domain/rumination_prompt_strings.py",
                "content": user_tpl,
                "segments": parse_content_segments(user_tpl),
            }
        )

    addon_map = RUMINATION_CHAT_STEP_ADDON_EN if loc.startswith("en") else RUMINATION_CHAT_STEP_ADDON_ZH
    addon = addon_map.get(step, "")
    sections.append(
        {
            "key": "chat_addon",
            "label": "主对话 chat_addon",
            "category": "addon",
            "source_path": "domain/rumination_prompt_strings.py · RUMINATION_CHAT_STEP_ADDON_*",
            "content": addon,
            "segments": parse_content_segments(addon),
        }
    )

    deep = DEEP_CHAT_STEP_SYSTEM_MAP.get(step, "")
    if deep:
        sections.append(
            {
                "key": "deep_chat",
                "label": "深入讨论 neg gate",
                "category": "runtime",
                "source_path": "domain/rumination_prompt_strings.py · DEEP_CHAT_STEP_SYSTEM_MAP",
                "content": deep,
                "segments": parse_content_segments(deep),
                "collapsed_default": True,
            }
        )
    return sections


def _simple_chat_diff(
    phase: str,
    locale: str,
    profile_id: Optional[str],
    branches: List[Dict[str, Any]],
) -> Dict[str, Any]:
    canonical_path, canonical_tpl = load_canonical_simple_chat_template()
    override_tpl: Optional[str] = None
    override_meta: Optional[Dict[str, Any]] = None
    extra_goal = ""

    if profile_id:
        profile = get_profile(profile_id)
        if profile:
            vid = profile.get("current_version_id")
            versions = profile.get("versions") or []
            current = next((v for v in versions if isinstance(v, dict) and v.get("version_id") == vid), None)
            if isinstance(current, dict):
                override_tpl = (current.get("simple_chat_system_prompt_template") or "").strip() or None
                extra_goal = (current.get("extra_goal_hint") or "").strip()
                override_meta = {
                    "profile_id": profile_id,
                    "profile_name": profile.get("name"),
                    "version_id": vid,
                }

    samples = get_variable_samples(locale)
    mock_ctx = {
        "phase": phase,
        "question_bank": samples["question_bank"],
        "basic_info": samples["basic_info"],
        "prior_block": samples["prior_block"],
        "values_info": samples["values_info"],
        "rumination_step_addon": samples["rumination_step_addon"],
    }

    effective = build_system_prompt(
        phase,
        question_bank=mock_ctx["question_bank"],
        basic_info=mock_ctx["basic_info"],
        prior_context=samples["prior_block"].strip(),
        template_override=override_tpl,
        extra_goal_hint=extra_goal,
        values_info=mock_ctx["values_info"],
        rumination_step_addon=mock_ctx["rumination_step_addon"],
        purpose_progress_injection=(
            build_progress_injection(normalize_progress({"current_index": 1, "confirmed_rows": []}))
            if phase == "purpose"
            else ""
        ),
    )

    active_branch = next((b for b in branches if b["phase"] == phase), None)

    return {
        "canonical_source": canonical_path,
        "canonical_template": canonical_tpl,
        "override_template": override_tpl,
        "override_meta": override_meta,
        "effective_preview": effective,
        "effective_phase": phase,
        "active_branch_content": (active_branch or {}).get("content"),
        "has_override": bool(override_tpl),
    }


def build_prompt_catalog(
    locale: str = "zh",
    *,
    profile_id: Optional[str] = None,
    preview_phase: str = "values",
) -> Dict[str, Any]:
    """组装完整 Prompt Catalog 响应。"""
    loc = (locale or "zh").strip().lower()
    if not loc.startswith("en"):
        loc = "zh"

    phase = (preview_phase or "values").strip().lower()
    if phase not in PHASE_KEYS:
        phase = "values"

    _, canonical_tpl = load_canonical_simple_chat_template()
    branches = extract_phase_branches(canonical_tpl)
    runtime_catalog = get_runtime_injection_catalog()
    variable_samples = get_variable_samples(loc)

    phases_out: List[Dict[str, Any]] = []
    for pk in PHASE_KEYS:
        sections: List[Dict[str, Any]] = [
            _step_copy_section(pk, "intro", loc),
            _step_copy_section(pk, "outro", loc),
            {
                "key": "init_fallback",
                "label": "Init 兜底开场",
                "category": "fallback",
                "source_path": "api/v1/simple_chat/prompt_builder.py",
                "content": build_fallback_opening_question(pk),
                "segments": parse_content_segments(build_fallback_opening_question(pk)),
            },
            {
                "key": "main_dialogue",
                "label": "主对话 System Prompt",
                "category": "main",
                "source_path": "domain/prompts/templates/simple_chat_system.yaml",
                "layer_stack": _build_main_layer_stack(pk, branches, runtime_catalog),
            },
        ]

        if pk == "rumination":
            sections.insert(
                2,
                {
                    "key": "entry_init",
                    "label": "首轮 entry_init",
                    "category": "intro",
                    "source_path": "domain/rumination_prompt_strings.py",
                    "items": [
                        {
                            "role": "system",
                            "content": RUMINATION_ENTRY_INIT_SYSTEM_ZH,
                            "segments": parse_content_segments(RUMINATION_ENTRY_INIT_SYSTEM_ZH),
                        },
                        {
                            "role": "user_template",
                            "content": RUMINATION_ENTRY_INIT_USER_TEMPLATE_ZH,
                            "segments": parse_content_segments(RUMINATION_ENTRY_INIT_USER_TEMPLATE_ZH),
                        },
                        {
                            "role": "fallback",
                            "label": "LLM 失败降级",
                            "content": RUMINATION_INIT_FALLBACK_ZH,
                            "source_path": "services/rumination_init_greeting.py",
                        },
                    ],
                },
            )
            sections.append(
                {
                    "key": "closing",
                    "label": "终步收束结语",
                    "category": "outro",
                    "source_path": "domain/rumination_prompt_strings.py",
                    "items": [
                        {
                            "role": "llm_system",
                            "content": RUMINATION_CLOSING_EPILOGUE_SYSTEM_ZH,
                        },
                        {
                            "role": "llm_user_template",
                            "content": RUMINATION_CLOSING_EPILOGUE_USER_TEMPLATE_ZH,
                            "segments": parse_content_segments(RUMINATION_CLOSING_EPILOGUE_USER_TEMPLATE_ZH),
                        },
                        {
                            "role": "fixed_shortpath",
                            "label": "短路径固定结语",
                            "content": RUMINATION_SHORTPATH_SKIP_CLOSING_FIXED_ZH,
                        },
                    ],
                },
            )
            rumination_steps = []
            for step in range(1, 8):
                rumination_steps.append(
                    {
                        "step": step,
                        "label": f"筛选步骤 {step}",
                        "opening_mode": STEP_OPENING_MODE.get(step, "llm"),
                        "sections": _rumination_step_sections(step, loc),
                    }
                )
        else:
            rumination_steps = None

        phase_obj: Dict[str, Any] = {
            "key": pk,
            "label": PHASE_LABELS.get(pk, pk),
            "color": PHASE_COLORS.get(pk, "gray"),
            "sections": sections,
        }
        if rumination_steps is not None:
            phase_obj["rumination_steps"] = rumination_steps
        phases_out.append(phase_obj)

    return {
        "locale": loc,
        "phases": phases_out,
        "variable_samples": variable_samples,
        "runtime_injection_catalog": runtime_catalog,
        "simple_chat_system_diff": _simple_chat_diff(phase, loc, profile_id, branches),
        "test_links": {
            "savepoint_resume": "/admin/sandboxes",
            "fork_from_scratch": "/admin/sandboxes",
        },
    }
