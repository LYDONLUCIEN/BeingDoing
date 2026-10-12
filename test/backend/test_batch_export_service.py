"""
BatchExportService 单元测试：
- report 5 phase 全完成 / 仅 3 phase 完成 -> 章节数正确
- report 不存在 -> 返回 None（跳过）
- md / txt 两种格式
- raw json 含 report_step_locked 字段（locked 过滤支撑）
- 仅部分 phase locked 时，raw json 反映各自 locked 状态
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pytest

from app.services.batch_export_service import PHASE_LABEL_CN, BatchExportService
from app.utils.report_registry import STEP_IDS, ReportRegistry


def _write_record(root: Path, report_id: str, payload: dict) -> None:
    """写一份 record.json 到 root/reports/{report_id}/record.json。"""
    d = root / "reports" / report_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "record.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _write_step_session(
    root: Path,
    report_id: str,
    step_id: str,
    session_id: str,
    messages: Optional[List[dict]] = None,
) -> None:
    """写一份 {step}__{session}.json 源文件。"""
    d = root / "reports" / report_id
    d.mkdir(parents=True, exist_ok=True)
    if messages is None:
        messages = [
            {"role": "assistant", "content": "你好", "created_at": "2026-01-01T00:00:00Z"},
            {"role": "user", "content": "在的", "created_at": "2026-01-01T00:00:05Z"},
        ]
    payload = {
        "report_id": report_id,
        "category": f"{step_id}__{session_id}",
        "messages": messages,
        "metadata": {},
    }
    (d / f"{step_id}__{session_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _make_record(
    report_id: str,
    activation_code: str = "TESTCODE",
    user_id: str = "user-test",
    selected_sessions: Optional[Dict[str, str]] = None,
    locked_overrides: Optional[Dict[str, bool]] = None,
) -> dict:
    """
    构造一份 record。

    默认每个 phase: locked = (session 已选)。
    locked_overrides 可强制覆盖某些 phase 的 locked 值。
    """
    ts = "2026-01-01T00:00:00Z"
    steps = {}
    for sid in STEP_IDS:
        sess = (selected_sessions or {}).get(sid)
        locked = bool(sess)
        if locked_overrides and sid in locked_overrides:
            locked = locked_overrides[sid]
        steps[sid] = {
            "step_id": sid,
            "selected_session_id": sess,
            "locked": locked,
            "session_ids": [sess] if sess else [],
            "updated_at": ts,
        }
    return {
        "report_id": report_id,
        "activation_code": activation_code,
        "user_id": user_id,
        "created_at": ts,
        "updated_at": ts,
        "status": "in_progress",
        "final_conclusion": None,
        "steps": steps,
    }


@pytest.fixture
def batch_service(tmp_path: Path) -> BatchExportService:
    """构造一个用 tmp 目录的 BatchExportService（不依赖真实 DB / ExportService）。"""
    base = tmp_path / "simple"
    base.mkdir(parents=True, exist_ok=True)
    svc = BatchExportService()
    svc.registry = ReportRegistry(base_dir=str(base))
    return svc


def _find_file(
    files: List[Tuple[str, bytes]], prefix: str
) -> Tuple[str, bytes]:
    """从 collect_report_export 返回结果里按 inner_path 前缀找文件。"""
    for name, content in files:
        if name.startswith(prefix):
            return name, content
    raise AssertionError(f"未找到文件: {prefix}*；实际: {[n for n, _ in files]}")


# ── 基础：5 phase 全完成 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_collect_report_export_5_phases_md(
    batch_service: BatchExportService,
) -> None:
    """5 phase 全完成 -> md 文件含 5 个章节标题 + 5 个 raw json。"""
    root = batch_service.registry.simple_base_dir
    rid = "rpt-full-5"
    selected = {sid: f"sess-{sid}" for sid in STEP_IDS}
    record = _make_record(rid, selected_sessions=selected)
    _write_record(root, rid, record)
    for sid in STEP_IDS:
        _write_step_session(root, rid, sid, selected[sid])

    result = await batch_service.collect_report_export(rid, "md")

    assert result is not None
    # 找 md 文件
    _, md_content = _find_file(result, "report_rpt-full-5.md")
    md_text = md_content.decode("utf-8")
    for i, sid in enumerate(STEP_IDS, start=1):
        label = PHASE_LABEL_CN[sid]
        assert f"## {i}. {label}（{sid}）" in md_text
    assert "# 寻路·OpenLife 探索报告 - rpt-full-5" in md_text
    assert "用户ID: user-test" in md_text

    # 找 5 个 raw json
    for sid in STEP_IDS:
        _, raw_bytes = _find_file(result, f"raw/{sid}__sess-{sid}.json")
        raw = json.loads(raw_bytes)
        assert raw["report_step_locked"] is True
        assert raw["report_step_is_selected"] is True
        assert raw["report_user_id"] == "user-test"


# ── 仅 3 phase 完成（txt 格式）────────────────────────────────


@pytest.mark.asyncio
async def test_collect_report_export_3_phases_txt(
    batch_service: BatchExportService,
) -> None:
    """仅 3 phase 完成 -> txt 文件含 3 个章节，未完成 phase 不出现。"""
    root = batch_service.registry.simple_base_dir
    rid = "rpt-partial-3"
    selected = {
        "values": "sess-v",
        "strengths": "sess-s",
        "interests": "sess-i",
    }
    record = _make_record(rid, selected_sessions=selected)
    _write_record(root, rid, record)
    for sid, sess in selected.items():
        _write_step_session(root, rid, sid, sess)

    result = await batch_service.collect_report_export(rid, "txt")

    assert result is not None
    _, txt_content = _find_file(result, "report_rpt-partial-3.txt")
    txt_text = txt_content.decode("utf-8")
    assert "1. 价值观（values）" in txt_text
    assert "2. 优势（strengths）" in txt_text
    assert "3. 热爱（interests）" in txt_text
    assert "使命（purpose）" not in txt_text
    assert "沉淀（rumination）" not in txt_text


# ── report 不存在 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_collect_report_export_not_exist(
    batch_service: BatchExportService,
) -> None:
    """report 不存在 -> 返回 None。"""
    result = await batch_service.collect_report_export("nonexistent-id", "md")
    assert result is None


# ── 零 phase ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_collect_report_export_zero_phases(
    batch_service: BatchExportService,
) -> None:
    """所有 phase 均未完成 -> md 仅含头部 + 提示行。"""
    root = batch_service.registry.simple_base_dir
    rid = "rpt-empty"
    record = _make_record(rid, selected_sessions={})
    _write_record(root, rid, record)

    result = await batch_service.collect_report_export(rid, "md")
    assert result is not None
    _, md_bytes = _find_file(result, "report_rpt-empty.md")
    md_text = md_bytes.decode("utf-8")
    assert "（本报告暂无已完成的探索阶段）" in md_text


# ── locked 字段反映真实状态 ────────────────────────────────────


@pytest.mark.asyncio
async def test_raw_json_reflects_locked_status(
    batch_service: BatchExportService,
) -> None:
    """
    locked 状态混合：values locked、strengths 未 locked。
    raw json 的 report_step_locked 应各自反映真实状态。
    """
    root = batch_service.registry.simple_base_dir
    rid = "rpt-mixed-lock"
    selected = {"values": "sess-v", "strengths": "sess-s"}
    # values 锁定，strengths 不锁（即使 selected）
    locked_overrides = {"values": True, "strengths": False}
    record = _make_record(
        rid, selected_sessions=selected, locked_overrides=locked_overrides
    )
    _write_record(root, rid, record)
    for sid, sess in selected.items():
        _write_step_session(root, rid, sid, sess)

    result = await batch_service.collect_report_export(rid, "md")
    assert result is not None

    # values -> locked=True
    _, v_bytes = _find_file(result, "raw/values__sess-v.json")
    v_raw = json.loads(v_bytes)
    assert v_raw["report_step_locked"] is True

    # strengths -> locked=False（虽然 selected，但未 lock）
    _, s_bytes = _find_file(result, "raw/strengths__sess-s.json")
    s_raw = json.loads(s_bytes)
    assert s_raw["report_step_locked"] is False
    assert s_raw["report_step_is_selected"] is True


@pytest.mark.asyncio
async def test_native_v4_snapshot_export_and_staging_preserve_user_selection(
    batch_service, tmp_path
):
    """原生快照可从导出包无损恢复；旧矩阵不能替代缺失的用户终选。"""
    import importlib.util

    script = Path(__file__).resolve().parents[2] / "scripts" / "batch_generate_reports.py"
    spec = importlib.util.spec_from_file_location("batch_generate_reports", script)
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    root = batch_service.registry.simple_base_dir
    rid = "native-v4"
    selected = {sid: f"sess-{sid}" for sid in STEP_IDS}
    _write_record(root, rid, _make_record(rid, selected_sessions=selected))
    for sid in STEP_IDS:
        _write_step_session(root, rid, sid, selected[sid])
    state = {
        "combo_sessions": [
            {
                "combo_id": "combo_2",
                "status": "concluded",
                "conclusion_card": {"hypothesis": "写作"},
            }
        ],
        "final_selection": {"selected_combo_ids": ["combo_2"], "submitted": True},
    }
    source = root / "reports" / rid / "rumination_v4_progress.json"
    raw = json.dumps(state, ensure_ascii=False, indent=2).encode()
    source.write_bytes(raw)
    files = dict(await batch_service.collect_report_export(rid, "md"))
    assert files["raw/rumination_v4_progress.json"] == raw
    assert source.read_bytes() == raw

    package = tmp_path / "export" / rid
    for name, content in files.items():
        dest = package / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
    # 原始导出测试只填了对话，这里补齐四阶段结论，验证沉淀完整性门槛。
    summary = {
        "phases": {
            p: {"conclusion_final": {"keywords": [p]}} for p in STEP_IDS if p != "rumination"
        }
    }
    (package / "summary.json").write_text(json.dumps(summary))
    staging = tmp_path / "staging"
    result = adapter.stage_report(package, staging)
    assert result["complete"] is True
    assert (staging / rid / "rumination_v4_progress.json").read_bytes() == raw

    # 再使用同一个暂存目录，输入只有旧矩阵；不得复用上一次状态或制造 v4。
    (package / "raw" / "rumination_v4_progress.json").unlink()
    (package / "raw" / "rumination_progress.json").write_text(
        json.dumps(
            {
                "combo_matrix": [{"combo_id": "02", "hypothesis": "旧矩阵方向"}],
                "combo_conclusions": {"02": {"hypothesis": "旧矩阵方向"}},
            }
        )
    )
    result = adapter.stage_report(package, staging)
    assert result["complete"] is False
    assert result["confirmed_combos"] == 0
    assert not (staging / rid / "rumination_v4_progress.json").exists()
    assert source.read_bytes() == raw


@pytest.mark.asyncio
@pytest.mark.parametrize("schema_version,step_count", [(1, 9), (2, 7), (3, 7)])
async def test_legacy_export_preserves_original_steps_and_messages(
    batch_service, schema_version, step_count
):
    """旧九步与七步按源编号解释，表格和对话不截断、不迁移或写回。"""
    from app.utils.legacy_rumination_export import (
        build_rumination_tables,
        slice_conversation_by_step,
    )

    root = batch_service.registry.simple_base_dir
    rid = f"legacy-{schema_version}"
    _write_record(root, rid, _make_record(rid, selected_sessions={"rumination": "legacy"}))
    messages = [
        {"role": "user", "content": f"原步骤{n}对话", "filter_step": n}
        for n in range(1, step_count + 1)
    ]
    _write_step_session(root, rid, "rumination", "legacy", messages)
    original = {
        "schema_version": schema_version,
        "filter_step_snapshots": {
            str(n): {"submitted": [{"内容": f"原步骤{n}结论"}]} for n in range(1, step_count + 1)
        },
    }
    source = root / "reports" / rid / "rumination_progress.json"
    raw = json.dumps(original, ensure_ascii=False).encode()
    source.write_bytes(raw)
    tables = build_rumination_tables(rid, batch_service.registry)
    assert tables["source_schema_version"] == schema_version
    assert len(tables["steps"]) == step_count
    assert tables["steps"][str(step_count)]["rows"] == [{"内容": f"原步骤{step_count}结论"}]
    sliced = slice_conversation_by_step(messages)
    assert sliced[str(step_count)][0]["content"] == f"原步骤{step_count}对话"
    files = dict(await batch_service.collect_report_export(rid, "md"))
    md = files[f"report_{rid}.md"].decode()
    assert f"schema={schema_version}" in md
    for n in range(1, step_count + 1):
        assert f"### Step {n}（" in md
        assert f"原步骤{n}结论" in md
        assert f"原步骤{n}对话" in md
    assert tables["combo_matrix"] is None
    assert source.read_bytes() == raw
    assert not (source.parent / "rumination_v4_progress.json").exists()
