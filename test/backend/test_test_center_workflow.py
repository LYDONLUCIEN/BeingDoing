"""业务回放的公开编排与实际既有 HTTP 路由；每个测试进程/数据独立。"""

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from test.backend.test_test_center_authoring import author_client  # noqa: F401

import pytest
from test_agent.center.workflow_runner import execute_workflow, prepare_workspace

from app.api.v1.admin_test_center import get_center
from app.services.test_center import TestCenter


def workflow_job(
    author_client,
    tmp_path,
    monkeypatch,
    *,
    steps,
    checks,
    repeats=1,
    phase="rumination",
    history=None,
    max_tokens=2000000,
):
    client, _ = author_client
    center = TestCenter(Path(__file__).resolve().parents[2], tmp_path / "workflow-control")
    client.app.dependency_overrides[get_center] = lambda: center
    monkeypatch.setenv(
        "TEST_CENTER_AI_CONFIG",
        json.dumps(
            {
                "base_url": "https://model.example.invalid/v1",
                "provider": "deepseek",
                **{
                    scene: {"model": "test-model", "thinking": False}
                    for scene in ("chat", "rumination", "conclusion", "report", "unknown")
                },
            }
        ),
    )
    context = {
        "name": "业务起点",
        "phase": phase,
        "thread_id": "combo_1" if phase == "rumination" else "thread_1",
        "workflow_seed": {
            "completed_phases": (
                ["values", "strengths", "interests", "purpose"] if phase == "rumination" else []
            )
        },
    }
    if phase == "rumination":
        context["combo"] = {
            "combo_id": "combo_1",
            "passion": "写作",
            "strengths": ["表达"],
            "messages": history or [],
        }
    else:
        context.update(question_bank="固定题库", messages=history or [])
    created = client.post("/admin/test-center/contexts", json=context)
    assert created.status_code == 200, created.text
    draft = client.post(
        "/admin/test-center/drafts",
        json={
            "title": "业务回放验证",
            "purpose": "保护实际状态和业务拒绝条件",
            "kind": "ai",
            "context_id": created.json()["data"]["id"],
            "conversation_mode": "workflow",
            "repeats": repeats,
            "inputs": steps,
            "assertions": checks,
        },
    )
    assert draft.status_code == 200, draft.text
    value = draft.json()["data"]
    assert value["state"] == "ready", value
    saved = client.post("/admin/test-center/cases", json={"draft_id": value["id"]}).json()["data"]
    response = client.post(
        "/admin/test-center/runs",
        json={"case_ids": [saved["id"]], "budget": {"max_calls": 100, "max_tokens": max_tokens}},
    )
    assert response.status_code == 202, response.text
    return center, response.json()["data"]


def test_business_repeats_use_fresh_processes_and_keep_product_guards(
    author_client, tmp_path, monkeypatch
):
    center, run = workflow_job(
        author_client,
        tmp_path,
        monkeypatch,
        steps=["填写结论：独立副本的用户原文", "跳过组合", "填写结论：此时不允许改卡"],
        checks=[
            "第1步：接口状态：200",
            "第1步：结论包含：独立副本的用户原文",
            "第2步：组合状态：abandoned",
            "第3步：接口状态：400",
            "第3步：结论包含：独立副本的用户原文",
        ],
        repeats=2,
    )
    result = asyncio.run(execute_workflow(center, run, run["cases"][0]))
    assert result["status"] == "pass", result
    assert len(result["attempts"]) == 6
    assert result["attempts"][2]["http_status"] == result["attempts"][5]["http_status"] == 400
    for first in (result["attempts"][0], result["attempts"][3]):
        assert first["before_state"]["combo"]["status"] == "discussing"
        assert first["before_state"]["combo"]["conclusion_card"]["hypothesis"] == ""
    assert center.get_run(run["id"])["usage"]["calls"] == 0


def execute_with_model_fixture(center, run, tmp_path, replies, *, unused=0):
    work = tmp_path / "source-copy"
    work.mkdir()
    env = prepare_workspace(center.source, work, run["id"])
    fixture = tmp_path / "model-replies.json"
    fixture.write_text(json.dumps(replies, ensure_ascii=False))
    output = tmp_path / "business-result.json"
    program = """
import asyncio, json, sys
from pathlib import Path
from app.services.test_center import TestCenter
from test_agent.center.workflow_runtime import execute_once
center = TestCenter(Path.cwd(), Path(sys.argv[1]))
run = center.get_run(sys.argv[2])
replies = json.loads(Path(sys.argv[3]).read_text())
async def model(messages, config, maximum, purpose):
    if not replies: raise RuntimeError('出现未预计的真实业务模型调用')
    reply = replies.pop(0)
    if isinstance(reply, dict) and reply.pop('_cancel', False): center.cancel(run['id'])
    return {'model': config['model'], 'usage': {'prompt_tokens': 10, 'completion_tokens': 20}, 'finish_reason': 'stop', **(reply if isinstance(reply, dict) else {'content': reply})}
result = asyncio.run(execute_once(center, run, run['cases'][0], 0, model))
result['unused_fixture_replies'] = len(replies)
Path(sys.argv[4]).write_text(json.dumps(result, ensure_ascii=False))
"""
    execution = subprocess.run(
        [sys.executable, "-c", program, str(center.root), run["id"], str(fixture), str(output)],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert execution.returncode == 0, execution.stderr[-6000:]
    result = json.loads(output.read_text())
    assert result["unused_fixture_replies"] == unused, result
    return result


def test_v4_replay_runs_real_confirmation_lock_and_reopen(author_client, tmp_path, monkeypatch):
    center, run = workflow_job(
        author_client,
        tmp_path,
        monkeypatch,
        steps=[
            "发送消息：我想写作",
            "填写结论：写一本帮助别人的书",
            "确认结论",
            "发送消息：已确认不能发送",
            "再聊聊",
            "发送消息：还想再打磨",
        ],
        checks=[
            "第1步：回复包含：具体经历",
            "第2步：结论包含：写一本帮助别人的书",
            "第3步：判定状态：done",
            "第3步：组合状态：concluded",
            "第4步：接口状态：400",
            "第5步：判定状态：none",
            "第6步：回复包含：继续打磨",
        ],
    )
    result = execute_with_model_fixture(
        center,
        run,
        tmp_path,
        ["能说说具体经历吗？", '{"balance_found":true}', "可以继续打磨这个方向。"],
    )
    assert result["status"] == "pass", result
    attempts = result["attempts"]
    assert "已确认不能发送" not in json.dumps(
        attempts[-1]["state"]["combo"]["messages"], ensure_ascii=False
    )
    assert "再聊聊" in json.dumps(attempts[-1]["model_calls"][0]["messages"], ensure_ascii=False)
    assert center.get_run(run["id"])["usage"]["calls"] == 3


def test_first_dimension_replay_generates_confirms_and_reopens(
    author_client, tmp_path, monkeypatch
):
    center, run = workflow_job(
        author_client,
        tmp_path,
        monkeypatch,
        phase="values",
        steps=["发送消息：成长和自由对我最重要", "确认结论", "再聊聊"],
        checks=[
            "第1步：结论状态：pending",
            "第1步：结论包含：成长",
            "第2步：线程完成：是",
            "第2步：结论状态：confirmed",
            "第3步：线程完成：否",
            "第3步：结论状态：rejected",
        ],
    )
    result = execute_with_model_fixture(
        center,
        run,
        tmp_path,
        [
            '可以看看结论卡。\n[STATE_JSON]{"state":"pending_ready","draft":{"summary":"成长与自由","keywords":["成长","自由"]}}[/STATE_JSON]',
            '{"goals":"成长与自由","personality":"","style":"","conflicts":""}',
        ],
    )
    assert result["status"] == "pass", result
    assert center.get_run(run["id"])["usage"]["calls"] == 2


def test_pending_conversation_advances_using_real_judge_and_keeps_submit_explicit(
    author_client, tmp_path, monkeypatch
):
    center, run = workflow_job(
        author_client,
        tmp_path,
        monkeypatch,
        phase="values",
        steps=["发送消息：成长和自由最重要", "发送消息：我确认这个结论"],
        checks=[
            "第1步：结论状态：pending",
            "第2步：结论状态：confirmed",
            "第2步：线程完成：否",
            "第2步：结论包含：成长",
            "第2步：摘要包含：成长",
        ],
    )
    result = execute_with_model_fixture(
        center,
        run,
        tmp_path,
        [
            '看看结论卡。\n[STATE_JSON]{"state":"pending_ready","draft":{"summary":"成长与自由","keywords":["成长","自由"]}}[/STATE_JSON]',
            '{"state":"confirmed","content":"我理解了你的确认"}',
            '{"summary":"我重视成长与自由","keywords":["成长","自由"]}',
            '{"goals":"成长与自由","personality":"","style":"","conflicts":""}',
        ],
    )
    assert result["status"] == "pass", json.dumps(result, ensure_ascii=False)
    assert center.get_run(run["id"])["usage"]["calls"] == 4


def test_manual_conclusion_uses_product_judge_and_generator(author_client, tmp_path, monkeypatch):
    center, run = workflow_job(
        author_client,
        tmp_path,
        monkeypatch,
        phase="values",
        history=[
            {"role": "user", "content": "我已经确认成长、自由是最重要的"},
            {"role": "assistant", "content": "我们已有明确的结论"},
        ],
        steps=["请求结论"],
        checks=["第1步：结论状态：pending", "第1步：结论包含：成长"],
    )
    result = execute_with_model_fixture(
        center,
        run,
        tmp_path,
        [
            '{"complete":true,"reason":"用户已明确确认"}',
            '{"summary":"我重视成长与自由","keywords":["成长","自由"]}',
        ],
    )
    assert result["status"] == "pass", result
    assert center.get_run(run["id"])["usage"]["calls"] == 2


def test_v4_summary_uses_real_thirtieth_round_threshold(author_client, tmp_path, monkeypatch):
    history = [
        message
        for i in range(29)
        for message in (
            {"role": "user", "content": f"第{i + 1}次讲述写作经历"},
            {"role": "assistant", "content": "还有哪些具体细节？"},
        )
    ]
    center, run = workflow_job(
        author_client,
        tmp_path,
        monkeypatch,
        history=history,
        steps=["发送消息：这是第三十轮的新事实"],
        checks=["第1步：回复非空", "第1步：摘要包含：三十轮写作经历"],
    )
    result = execute_with_model_fixture(
        center, run, tmp_path, ["你想怎样运用这些经验？", "三十轮写作经历以及新事实的摘要。"]
    )
    assert result["status"] == "pass", result
    assert result["attempts"][0]["state"]["combo"]["summary_last_round"] == 30
    assert center.get_run(run["id"])["usage"]["calls"] == 2


def test_v4_submit_runs_report_generation_and_preserves_lock(author_client, tmp_path, monkeypatch):
    center, run = workflow_job(
        author_client,
        tmp_path,
        monkeypatch,
        steps=["填写结论：写一本帮助别人的书", "确认结论", "选入终选", "提交终选", "再聊聊"],
        checks=[
            "第1步：接口状态：200",
            "第2步：判定状态：done",
            "第3步：接口状态：200",
            "第4步：终选提交：是",
            "第4步：阶段锁定：是",
            "第4步：报告包含：写作方向",
            "第5步：接口状态：400",
            "第5步：阶段锁定：是",
        ],
    )
    result = execute_with_model_fixture(
        center,
        run,
        tmp_path,
        ['{"balance_found":true}', "# 探索报告\n\n写作方向：写一本帮助别人的书。"],
    )
    assert result["status"] == "pass", result
    assert result["attempts"][3]["state"]["report_review_status"] == "pending_review"
    assert center.get_run(run["id"])["usage"]["calls"] == 2


def test_product_judge_retry_is_charged_without_replacing_its_logic(
    author_client, tmp_path, monkeypatch
):
    center, run = workflow_job(
        author_client,
        tmp_path,
        monkeypatch,
        steps=["填写结论：写作", "确认结论"],
        checks=["第1步：接口状态：200", "第2步：判定状态：done"],
    )
    result = execute_with_model_fixture(
        center, run, tmp_path, ["不是 JSON", '{"balance_found":false}']
    )
    assert result["status"] == "pass", result
    calls = center.get_run(run["id"])["calls"]
    assert [c["max_output_tokens"] for c in calls] == [8000, 16000]
    assert all(c["status"] == "completed" for c in calls)


def test_unknown_model_usage_stops_product_retry_and_later_steps(
    author_client, tmp_path, monkeypatch
):
    center, run = workflow_job(
        author_client,
        tmp_path,
        monkeypatch,
        steps=["填写结论：写作", "确认结论", "再聊聊"],
        checks=["第1步：接口状态：200", "第2步：接口状态：200", "第3步：组合状态：discussing"],
    )
    result = execute_with_model_fixture(
        center, run, tmp_path, [{"content": '{"balance_found":true}', "usage": None}]
    )
    assert result["status"] == "error"
    assert len(result["attempts"]) == 2
    usage = center.get_run(run["id"])["usage"]
    assert usage["calls"] == usage["unknown_calls"] == 1
    assert usage["charged_tokens"] > 8000


def test_workflow_refuses_shared_workspace_before_writing(author_client, tmp_path, monkeypatch):
    from test_agent.center.workflow_runtime import execute_once

    center, run = workflow_job(
        author_client,
        tmp_path,
        monkeypatch,
        steps=["填写结论：不得写入"],
        checks=["第1步：接口状态：200"],
    )
    with pytest.raises(RuntimeError, match="独立源码和数据库副本"):
        asyncio.run(execute_once(center, run, run["cases"][0], 0))


def test_workflow_token_limit_refuses_model_call(author_client, tmp_path, monkeypatch):
    center, run = workflow_job(
        author_client,
        tmp_path,
        monkeypatch,
        max_tokens=1,
        steps=["发送消息：预算不足不能发送给模型"],
        checks=["第1步：回复非空"],
    )
    result = asyncio.run(execute_workflow(center, run, run["cases"][0]))
    assert result["status"] == "incomplete", result
    assert "预算不足" in result["error"]
    assert center.get_run(run["id"])["usage"]["calls"] == 0


def test_cancelled_workflow_never_starts_a_model_call(author_client, tmp_path, monkeypatch):
    client, _ = author_client
    center, run = workflow_job(
        author_client,
        tmp_path,
        monkeypatch,
        steps=["发送消息：取消后不发出"],
        checks=["第1步：回复非空"],
    )
    assert client.post(f"/admin/test-center/runs/{run['id']}/cancel").status_code == 200
    result = asyncio.run(execute_workflow(center, run, run["cases"][0]))
    assert result["status"] == "cancelled"
    assert center.get_run(run["id"])["usage"]["calls"] == 0


def test_cancel_during_last_model_call_keeps_usage_and_cancelled_result(
    author_client, tmp_path, monkeypatch
):
    center, run = workflow_job(
        author_client,
        tmp_path,
        monkeypatch,
        steps=["发送消息：这次调用已经发出"],
        checks=["第1步：回复非空"],
    )
    result = execute_with_model_fixture(
        center, run, tmp_path, [{"content": "已完成的回复", "_cancel": True}]
    )
    assert result["status"] == "cancelled", result
    usage = center.get_run(run["id"])["usage"]
    assert usage["calls"] == 1
    assert usage["charged_tokens"] == 30
