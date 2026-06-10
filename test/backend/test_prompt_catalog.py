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
    for key in ("question_bank", "basic_info", "prior_block", "values_info", "rumination_step_addon"):
        assert key in samples
        assert samples[key]


def test_extract_phase_branches_includes_values():
    _, tpl = load_canonical_simple_chat_template()
    branches = extract_phase_branches(tpl)
    phases = {b["phase"] for b in branches}
    assert "values" in phases
    assert "rumination" in phases
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


def test_catalog_rumination_step3_fixed_opening():
    catalog = build_prompt_catalog("zh", preview_phase="rumination")
    rum = next(p for p in catalog["phases"] if p["key"] == "rumination")
    assert rum["rumination_steps"]
    step3 = next(s for s in rum["rumination_steps"] if s["step"] == 3)
    assert step3["opening_mode"] == "fixed"

    opening = next(sec for sec in step3["sections"] if sec["key"] == "opening")
    assert opening["opening_mode"] == "fixed"
    assert "假设生成" in opening["content"]

    addon = next(sec for sec in step3["sections"] if sec["key"] == "chat_addon")
    assert "子步 3" in addon["content"] or "假设" in addon["content"]


def test_catalog_en_locale_chat_addon():
    catalog = build_prompt_catalog("en", preview_phase="rumination")
    rum = next(p for p in catalog["phases"] if p["key"] == "rumination")
    step1 = next(s for s in rum["rumination_steps"] if s["step"] == 1)
    addon = next(sec for sec in step1["sections"] if sec["key"] == "chat_addon")
    assert "passion" in addon["content"].lower() or "strength" in addon["content"].lower()
