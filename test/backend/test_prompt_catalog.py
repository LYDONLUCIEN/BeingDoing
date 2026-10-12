"""Prompt Catalog assembler 与 API 结构测试。"""
from __future__ import annotations

from app.services.prompt_catalog import (
    build_prompt_catalog,
    extract_phase_branches,
    get_variable_samples,
    load_canonical_simple_chat_template,
)


def test_variable_samples_has_core_keys():
    samples = get_variable_samples("zh")
    for key in ("question_bank", "basic_info", "prior_block", "values_info"):
        assert key in samples
        assert samples[key]


def test_extract_phase_branches_includes_values():
    _, tpl = load_canonical_simple_chat_template()
    branches = extract_phase_branches(tpl)
    phases = {b["phase"] for b in branches}
    assert "values" in phases
    assert "rumination" not in phases
    values_branch = next(b for b in branches if b["phase"] == "values")
    assert "价值观" in values_branch["content"]
    assert any(s.get("type") == "variable" and s.get("name") == "question_bank" for s in values_branch["segments"])


def test_catalog_values_phase_structure():
    catalog = build_prompt_catalog("zh", preview_phase="values")
    assert catalog["locale"] == "zh"
    values = next(p for p in catalog["phases"] if p["key"] == "values")
    assert values["label"] == "价值观"
    assert values["color"] == "blue"

    intro = next(s for s in values["sections"] if s["key"] == "intro")
    assert intro["category"] == "intro"
    assert "价值观" in intro["content"]

    main = next(s for s in values["sections"] if s["key"] == "main_dialogue")
    stack = main["layer_stack"]
    assert any(l["kind"] == "static" and l.get("active") for l in stack)
    assert any(l["id"] == "state_json_protocol" and l["kind"] == "runtime" for l in stack)

    diff = catalog["simple_chat_system_diff"]
    assert diff["canonical_template"]
    assert diff["effective_preview"]
    assert "STATE_JSON" in diff["effective_preview"]


def test_catalog_rumination_uses_real_v4_prompts():
    from app.domain.rumination_v4_prompt import BALANCE_JUDGE_PROMPT, MEGA_PROMPT

    catalog = build_prompt_catalog("zh", preview_phase="rumination")
    rum = next(p for p in catalog["phases"] if p["key"] == "rumination")
    sections = {s["key"]: s for s in rum["sections"]}
    assert sections["main_dialogue"]["content"] == MEGA_PROMPT
    assert sections["balance_judge"]["content"] == BALANCE_JUDGE_PROMPT
    assert "rumination_steps" not in rum
    assert "STATE_JSON" not in catalog["simple_chat_system_diff"]["effective_preview"]


def test_catalog_v4_does_not_invent_an_english_legacy_prompt():
    catalog = build_prompt_catalog("en", preview_phase="rumination")
    rum = next(p for p in catalog["phases"] if p["key"] == "rumination")
    assert all(s["source_path"] == "domain/rumination_v4_prompt.py" for s in rum["sections"])
