"""管理员公开 API：自然语言草稿、固定修订和未知要求不能假通过。"""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.admin_test_center import get_center, router
from app.api.v1.auth import get_current_user
from app.services.test_center import TestCenter


@pytest.fixture
def author_client(tmp_path):
    source = tmp_path / "repo"
    (source / "test_agent/catalog").mkdir(parents=True)
    definition = {
        "id": "home-mobile",
        "title": "首页手机布局",
        "module": "首页",
        "kind": "ui",
        "core": True,
        "inputs": ["打开首页并切换手机和桌面宽度"],
        "assertions": ["页面没有横向溢出"],
        "targets": ["home"],
        "timeout": 300,
    }
    (source / "test_agent/catalog/home-mobile.json").write_text(json.dumps(definition))
    center = TestCenter(source, tmp_path / "control")
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_center] = lambda: center
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "admin-test"}
    with TestClient(app) as client:
        yield client, source


def test_author_draft_save_and_immutable_run(author_client):
    client, _ = author_client
    body = {
        "title": "首页检查",
        "kind": "ui",
        "template_id": "home-mobile",
        "inputs": ["打开首页并切换手机和桌面宽度"],
        "assertions": ["页面没有横向溢出"],
    }
    draft_response = client.post("/admin/test-center/drafts", json=body)
    assert draft_response.status_code == 200
    draft = draft_response.json()["data"]
    assert draft["state"] == "ready"
    saved = client.post("/admin/test-center/cases", json={"draft_id": draft["id"]}).json()["data"]
    run = client.post("/admin/test-center/runs", json={"case_ids": [saved["id"]]}).json()["data"]
    body["title"] = "改名的首页检查"
    body["case_id"] = saved["id"]
    body["base_revision"] = saved["revision"]
    second = client.post("/admin/test-center/drafts", json=body).json()["data"]
    updated = client.post("/admin/test-center/cases", json={"draft_id": second["id"]}).json()[
        "data"
    ]
    assert updated["revision"] != saved["revision"]
    old = client.get(f"/admin/test-center/runs/{run['id']}").json()["data"]
    assert old["cases"][0]["definition"]["title"] == "首页检查"
    revisions = client.get(f"/admin/test-center/cases/{saved['id']}/revisions").json()["data"]
    assert len(revisions) == 2
    body["base_revision"] = updated["revision"]
    unknown = client.post(
        "/admin/test-center/drafts", json={**body, "inputs": ["删除线上全部数据"]}
    ).json()["data"]
    assert unknown["state"] == "needs_clarification"
    assert unknown["issues"]
    assert (
        client.post("/admin/test-center/cases", json={"draft_id": unknown["id"]}).status_code == 400
    )
    assert (
        client.get("/admin/test-center/drafts").json()["data"][0]["state"] == "needs_clarification"
    )


def test_ai_context_is_independent_and_assertions_are_compiled(author_client):
    client, _ = author_client
    context = {
        "name": "独立组合起点",
        "phase": "rumination",
        "thread_id": "combo_1",
        "user_context": "测试背景",
        "combo": {
            "combo_id": "combo_1",
            "passion": "写作",
            "strengths": ["表达"],
            "messages": [{"role": "assistant", "content": "从哪里开始？"}],
            "conclusion_card": {"hypothesis": "写一本书"},
        },
    }
    response = client.post("/admin/test-center/contexts", json=context)
    assert response.status_code == 200
    snapshot = response.json()["data"]
    context["combo"]["conclusion_card"]["hypothesis"] = "另一种方向"
    another = client.post("/admin/test-center/contexts", json=context).json()["data"]
    assert another["id"] != snapshot["id"]
    old = client.get(f"/admin/test-center/contexts/{snapshot['id']}").json()["data"]
    assert old["spec"]["combo"]["conclusion_card"]["hypothesis"] == "写一本书"
    body = {
        "title": "组合对话",
        "kind": "ai",
        "context_id": snapshot["id"],
        "inputs": ["我想把自己的经验写下来", "我怕坚持不下去"],
        "assertions": [
            "回复不包含：系统提示词",
            "语义：询问一个具体经历，不能代填结论卡",
        ],
        "repeats": 2,
    }
    draft = client.post("/admin/test-center/drafts", json=body).json()["data"]
    assert draft["state"] == "ready"
    saved = client.post("/admin/test-center/cases", json={"draft_id": draft["id"]}).json()["data"]
    # 没有模型配置和显式预算时，不能悄悄调用真实模型。
    assert (
        client.post("/admin/test-center/runs", json={"case_ids": [saved["id"]]}).status_code == 400
    )
    unknown = client.post(
        "/admin/test-center/drafts", json={**body, "assertions": ["AI 应该合适"]}
    ).json()["data"]
    assert unknown["state"] == "needs_clarification"
    assert (
        client.post(
            "/admin/test-center/contexts", json={**context, "thread_id": "combo_2"}
        ).status_code
        == 400
    )


def test_ui_registration_script_uses_existing_application_route(author_client):
    client, _ = author_client
    draft = client.post(
        "/admin/test-center/drafts",
        json={
            "title": "注册拒绝路径",
            "kind": "ui",
            "template_id": "home-mobile",
            "inputs": ["打开注册页面", "填写：邮箱 = case@example.invalid", "点击：发送验证码"],
            "assertions": ["应跳转：/auth/register"],
        },
    ).json()["data"]
    assert draft["state"] == "ready"
    assert draft["definition"]["steps"][0]["value"] == "/auth/register"


def test_business_replay_compiles_existing_operations_and_keeps_assertions_separate(author_client):
    client, _ = author_client
    context = client.post(
        "/admin/test-center/contexts",
        json={
            "name": "沉淀讨论到确认",
            "phase": "rumination",
            "thread_id": "combo_1",
            "combo": {"combo_id": "combo_1", "passion": "写作", "strengths": ["表达"]},
            "workflow_seed": {"completed_phases": ["values", "strengths", "interests", "purpose"]},
        },
    )
    assert context.status_code == 200, context.text
    body = {
        "title": "沉淀业务状态回放",
        "kind": "ai",
        "context_id": context.json()["data"]["id"],
        "conversation_mode": "workflow",
        "inputs": [
            "填写结论：用文字帮助别人",
            "确认结论",
            "发送消息：确认后不应继续发送",
            "再聊聊",
        ],
        "assertions": [
            "第1步：接口状态：200",
            "第1步：结论包含：用文字帮助别人",
            "第2步：组合状态：concluded",
            "第2步：判定状态：done",
            "第3步：接口状态：400",
            "第4步：组合状态：discussing",
        ],
    }
    draft = client.post("/admin/test-center/drafts", json=body)
    assert draft.status_code == 200, draft.text
    value = draft.json()["data"]
    assert value["state"] == "ready", value
    assert [s["action"] for s in value["definition"]["steps"]] == [
        "card",
        "confirm",
        "message",
        "reopen",
    ]
    assert (
        client.post("/admin/test-center/cases", json={"draft_id": value["id"]}).status_code == 200
    )
    unknown = client.post(
        "/admin/test-center/drafts", json={**body, "inputs": ["绕过锁定强制确认"]}
    ).json()["data"]
    assert unknown["state"] == "needs_clarification"


def test_ai_replay_budget_target_reply_and_append_only_review(author_client, monkeypatch):
    import asyncio

    from test_agent.center.ai_runner import execute_ai

    client, _ = author_client
    monkeypatch.setenv(
        "TEST_CENTER_AI_CONFIG",
        json.dumps(
            {
                "base_url": "https://api.deepseek.com/v1",
                "provider": "deepseek",
                "chat": {"model": "test-chat", "thinking": False},
                "rumination": {"model": "test-rumination", "thinking": False},
            }
        ),
    )
    spec = {
        "name": "一次一问",
        "phase": "rumination",
        "thread_id": "combo_1",
        "combo": {
            "combo_id": "combo_1",
            "passion": "写作",
            "strengths": ["表达"],
            "messages": [{"role": "assistant", "content": "历史里有目标词"}],
        },
    }
    snapshot = client.post("/admin/test-center/contexts", json=spec).json()["data"]
    draft = client.post(
        "/admin/test-center/drafts",
        json={
            "title": "只判断本轮",
            "kind": "ai",
            "context_id": snapshot["id"],
            "inputs": ["输入里也有目标词"],
            "assertions": ["回复包含：目标词", "语义：只问一个问题"],
            "repeats": 2,
        },
    ).json()["data"]
    saved = client.post("/admin/test-center/cases", json={"draft_id": draft["id"]}).json()["data"]
    body = {"case_ids": [saved["id"]], "budget": {"max_calls": 4, "max_tokens": 200000}}
    job_response = client.post("/admin/test-center/runs", json=body)
    assert job_response.status_code == 202, job_response.text
    run = job_response.json()["data"]
    center = client.app.dependency_overrides[get_center]()
    calls = []

    async def gateway(messages, config, max_tokens, purpose):
        calls.append((purpose, messages))
        content = (
            "能说说最近的经历吗？"
            if purpose == "reply"
            else json.dumps(
                {"checks": [{"index": 1, "status": "needs_review", "reason": "语义存在歧义"}]}
            )
        )
        return {
            "content": content,
            "usage": {"prompt_tokens": 100, "completion_tokens": 30},
            "model": config["model"],
            "finish_reason": "stop",
        }

    result = asyncio.run(execute_ai(center, run, run["cases"][0], gateway))
    assert result["status"] == "fail"  # 历史/输入中的目标词不能使本轮通过。
    assert len(result["attempts"]) == 2
    reply_messages = [messages for purpose, messages in calls if purpose == "reply"]
    assert reply_messages[0] == reply_messages[1]  # 重复次数不沿用上次输出。
    run["cases"][0].update(result)
    run["status"] = result["status"]
    center.save_run(run)
    detail = client.get(f"/admin/test-center/runs/{run['id']}").json()["data"]
    assert len(detail["calls"]) == 4
    assert detail["usage"]["total_tokens"] == 520
    url = f"/admin/test-center/runs/{run['id']}/reviews"
    for verdict in ("fail", "pass"):
        reviewed = client.post(
            url,
            json={
                "case_id": saved["id"],
                "attempt": 0,
                "verdict": verdict,
                "reason": "人工核对记录",
            },
        )
        assert reviewed.status_code == 200
    reviewed = client.get(f"/admin/test-center/runs/{run['id']}").json()["data"]
    assert reviewed["cases"][0]["status"] == "fail"
    assert [r["verdict"] for r in reviewed["reviews"]] == ["fail", "pass"]
    assert all(r["reviewer"] == "admin-test" for r in reviewed["reviews"])


def test_preview_v4_debug_context_keeps_only_selected_combo(author_client, tmp_path, monkeypatch):
    from app.utils import simple_activation_manager as storage
    from app.utils.report_registry import ReportRegistry
    from app.utils.simple_activation_manager import (
        ActivationRecord,
        SimpleActivationManager,
    )

    client, _ = author_client
    root = tmp_path / "debug"
    monkeypatch.setattr(storage, "get_simple_test_base_dir", lambda: root)
    rec = ActivationRecord(
        code="DEBUGCTX",
        session_id="sess_ctx",
        mode="combined",
        created_at="2026-01-01T00:00:00Z",
        expires_at="2027-01-01T00:00:00Z",
        last_activity_at="2026-01-01T00:00:00Z",
        status="active",
        owner_user_id="admin-test",
        is_sandbox=True,
        workspace_kind="fork",
        workspace_root="sandboxes/context",
    )
    SimpleActivationManager(base_dir=str(root)).put_activation(rec)
    workspace = storage.get_effective_simple_root(rec)
    registry = ReportRegistry(base_dir=str(workspace))
    report = registry.ensure_report(rec.code, rec.owner_user_id)
    path = workspace / "reports" / report["report_id"] / "rumination_v4_progress.json"
    from app.services import rumination_v4_service as v4

    state, first = v4.create_combo(workspace / "reports", report["report_id"], "写作", ["表达"])
    state, second = v4.create_combo(workspace / "reports", report["report_id"], "画画", ["观察"])
    v4.append_message(state, first["combo_id"], "user", "保留本组合")
    v4.append_message(state, second["combo_id"], "user", "另一个组合不能进入")
    v4.save_v4_state(workspace / "reports", report["report_id"], state)
    payload = json.loads(path.read_text())
    response = client.post(
        "/admin/test-center/contexts/preview",
        json={
            "activation_code": "DEBUGCTX",
            "phase": "rumination",
            "thread_id": first["combo_id"],
            "name": "选中组合",
        },
    )
    assert response.status_code == 200, response.text
    preview = response.json()["data"]
    assert preview["combo"]["messages"] == [{"role": "user", "content": "保留本组合"}]
    assert "另一个组合不能进入" not in json.dumps(preview, ensure_ascii=False)
    assert preview["workflow_seed"]["completed_phases"] == []  # 不假装前置阶段已通过。
    assert preview["workflow_seed"]["conclusions"] == {}
    assert json.loads(path.read_text()) == payload
    assert client.get("/admin/test-center/contexts").json()["data"] == []  # 预览不自动保存。
    assert (
        client.post(
            "/admin/test-center/contexts/preview",
            json={
                "activation_code": "DEBUGCTX",
                "phase": "rumination",
                "thread_id": "../record",
                "name": "不能越界",
            },
        ).status_code
        == 400
    )


@pytest.mark.parametrize(
    "mode,expected_calls,expected_status",
    [
        ("cancel", 1, "cancelled"),
        ("unknown_usage", 1, "error"),
        ("low_budget", 0, "incomplete"),
        ("uncertain", 2, "needs_review"),
    ],
)
def test_ai_cancel_budget_and_invalid_judgment_never_pass(
    author_client, monkeypatch, mode, expected_calls, expected_status
):
    import asyncio

    from test_agent.center.ai_runner import execute_ai

    client, _ = author_client
    monkeypatch.setenv(
        "TEST_CENTER_AI_CONFIG",
        json.dumps(
            {
                "base_url": "https://api.deepseek.com/v1",
                "provider": "deepseek",
                "chat": {"model": "model-a", "thinking": False},
                "rumination": {"model": "model-a", "thinking": False},
            }
        ),
    )
    context = client.post(
        "/admin/test-center/contexts",
        json={
            "name": "固定初始状态",
            "phase": "values",
            "thread_id": "values_1",
            "question_bank": "最近什么事让你满意？",
        },
    ).json()["data"]
    draft = client.post(
        "/admin/test-center/drafts",
        json={
            "title": "中止与复核",
            "kind": "ai",
            "context_id": context["id"],
            "inputs": ["我不知道"],
            "assertions": ["语义：只提出一个问题"],
        },
    ).json()["data"]
    case = client.post("/admin/test-center/cases", json={"draft_id": draft["id"]}).json()["data"]
    run = client.post(
        "/admin/test-center/runs",
        json={
            "case_ids": [case["id"]],
            "budget": {
                "max_calls": 2,
                "max_tokens": 1 if mode == "low_budget" else 100000,
            },
        },
    ).json()["data"]
    center = client.app.dependency_overrides[get_center]()
    issued = []

    async def gateway(messages, config, max_tokens, purpose):
        issued.append(purpose)
        if mode == "cancel":
            center.cancel(run["id"])
        return {
            "content": "讲讲一个具体经历好吗？",
            "model": config["model"],
            "finish_reason": "stop",
            "usage": (
                None if mode == "unknown_usage" else {"prompt_tokens": 80, "completion_tokens": 20}
            ),
        }

    result = asyncio.run(execute_ai(center, run, run["cases"][0], gateway))
    assert result["status"] == expected_status
    assert len(issued) == expected_calls
    detail = client.get(f"/admin/test-center/runs/{run['id']}").json()["data"]
    assert detail["usage"]["calls"] == expected_calls
    if mode == "cancel":
        assert detail["usage"]["total_tokens"] == 100  # 取消前已发出的请求照常入账。
    if mode == "unknown_usage":
        assert detail["usage"]["unknown_calls"] == 1
        assert detail["usage"]["charged_tokens"] > 0
        assert detail["usage"]["cost"] is None


def test_manual_revision_survives_catalog_update_and_stale_editor_is_rejected(
    author_client,
):
    client, source = author_client
    original = client.get("/admin/test-center/catalog").json()["data"]["cases"][0]
    body = {
        "title": "管理员维护首页",
        "kind": "ui",
        "template_id": original["id"],
        "case_id": original["id"],
        "base_revision": original["revision"],
        "inputs": original["definition"]["inputs"],
        "assertions": original["definition"]["assertions"],
    }
    draft = client.post("/admin/test-center/drafts", json=body).json()["data"]
    saved = client.post("/admin/test-center/cases", json={"draft_id": draft["id"]}).json()["data"]
    value = original["definition"]
    value["title"] = "新开发的首页规则"
    (source / "test_agent/catalog/home-mobile.json").write_text(json.dumps(value))
    refreshed = client.get("/admin/test-center/catalog").json()["data"]["cases"][0]
    assert refreshed["revision"] == saved["revision"]
    assert refreshed["definition"]["title"] == "管理员维护首页"
    assert refreshed["upstream"]["definition"]["title"] == "新开发的首页规则"
    assert client.post("/admin/test-center/drafts", json=body).status_code == 400


def test_ai_unknown_usage_blocks_remaining_cases(author_client, monkeypatch):
    import asyncio

    from test_agent.center.ai_runner import execute_ai

    client, _ = author_client
    monkeypatch.setenv(
        "TEST_CENTER_AI_CONFIG",
        json.dumps(
            {
                "base_url": "https://api.deepseek.com/v1",
                "provider": "deepseek",
                "chat": {"model": "test-model", "thinking": False},
                "rumination": {"model": "test-model", "thinking": False},
            }
        ),
    )
    context = client.post(
        "/admin/test-center/contexts",
        json={
            "name": "起点",
            "phase": "values",
            "thread_id": "v1",
            "question_bank": "固定题库",
        },
    ).json()["data"]
    ids = []
    for name in ["第一项", "后续项"]:
        draft = client.post(
            "/admin/test-center/drafts",
            json={
                "title": name,
                "kind": "ai",
                "context_id": context["id"],
                "inputs": ["继续"],
                "assertions": ["回复非空"],
            },
        ).json()["data"]
        ids.append(
            client.post("/admin/test-center/cases", json={"draft_id": draft["id"]}).json()["data"][
                "id"
            ]
        )
    run = client.post(
        "/admin/test-center/runs",
        json={"case_ids": ids, "budget": {"max_calls": 2, "max_tokens": 100000}},
    ).json()["data"]
    center = client.app.dependency_overrides[get_center]()
    calls = []

    async def gateway(messages, config, max_tokens, purpose):
        calls.append(purpose)
        return {
            "content": "你好",
            "model": "test-model",
            "finish_reason": "stop",
            "usage": None,
        }

    for case in run["cases"]:
        assert asyncio.run(execute_ai(center, run, case, gateway))["status"] != "pass"
    assert calls == ["reply"]


def test_worker_ai_job_without_dedicated_key_does_not_inherit_business_key(
    author_client, monkeypatch
):
    import shutil
    import sys
    from pathlib import Path

    from test_agent.center.worker import run_once

    client, source = author_client
    implementation = Path(__file__).resolve().parents[2]
    shutil.copytree(implementation / "test_agent/center", source / "test_agent/center")
    destination = source / "src/backend/app/services"
    destination.mkdir(parents=True)
    for path in (implementation / "src/backend/app/services").glob("test_center*.py"):
        shutil.copyfile(path, destination / path.name)
    monkeypatch.delenv("TEST_CENTER_AI_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "business-key-must-not-be-inherited")
    monkeypatch.setenv(
        "TEST_CENTER_AI_CONFIG",
        json.dumps(
            {
                "base_url": "https://api.deepseek.com/v1",
                "provider": "deepseek",
                "chat": {"model": "test-model", "thinking": False},
                "rumination": {"model": "test-model", "thinking": False},
            }
        ),
    )
    context = client.post(
        "/admin/test-center/contexts",
        json={
            "name": "独立执行器",
            "phase": "values",
            "thread_id": "v1",
            "question_bank": "固定题库",
        },
    ).json()["data"]
    draft = client.post(
        "/admin/test-center/drafts",
        json={
            "title": "无真实模型凭据",
            "kind": "ai",
            "context_id": context["id"],
            "inputs": ["继续"],
            "assertions": ["回复非空"],
        },
    ).json()["data"]
    saved = client.post("/admin/test-center/cases", json={"draft_id": draft["id"]}).json()["data"]
    run = client.post(
        "/admin/test-center/runs",
        json={
            "case_ids": [saved["id"]],
            "budget": {"max_calls": 1, "max_tokens": 100000},
        },
    ).json()["data"]
    center = client.app.dependency_overrides[get_center]()
    assert run_once(center, python=sys.executable)
    result = client.get(f"/admin/test-center/runs/{run['id']}").json()["data"]
    assert result["status"] == "error"
    assert "TEST_CENTER_AI_API_KEY" in result["cases"][0]["error"]
    assert result["calls"] == []
    assert "business-key-must-not-be-inherited" not in json.dumps(result)
    assert not (center.root / "runs" / run["id"] / "work").exists()


def test_control_store_cannot_be_nested_inside_frozen_source(author_client):
    _, source = author_client
    with pytest.raises(ValueError, match="源码"):
        TestCenter(source, source / "test_agent" / "control")


def test_documented_case_keeps_purpose_sources_and_admin_classification(author_client):
    client, source = author_client
    path = source / "test_agent/catalog/home-mobile.json"
    definition = json.loads(path.read_text())
    definition.update(
        purpose="保证普通用户能完整访问首页",
        sources=[{"path": "docs/PRODUCT_RULES.md", "rule": "首页内容在手机和桌面均可访问"}],
    )
    path.write_text(json.dumps(definition))
    original = client.get("/admin/test-center/catalog").json()["data"]["cases"][0]
    draft = client.post(
        "/admin/test-center/drafts",
        json={
            "title": "管理员核对首页规范",
            "kind": "ui",
            "template_id": original["id"],
            "case_id": original["id"],
            "base_revision": original["revision"],
            "purpose": "检查内容没有被裁掉",
            "inputs": definition["inputs"],
            "assertions": definition["assertions"],
        },
    ).json()["data"]
    assert draft["definition"]["purpose"] == "检查内容没有被裁掉"
    assert draft["definition"]["sources"] == definition["sources"]
    saved = client.post("/admin/test-center/cases", json={"draft_id": draft["id"]}).json()["data"]
    assert (
        client.put(
            f"/admin/test-center/cases/{saved['id']}",
            json={"core": False, "archived": True},
        ).status_code
        == 200
    )
    definition["title"] = "开发后的新标题"
    path.write_text(json.dumps(definition))
    refreshed = client.get("/admin/test-center/catalog").json()["data"]["cases"][0]
    assert refreshed["archived"] and not refreshed["core"]
    assert refreshed["definition"]["purpose"] == "检查内容没有被裁掉"
    assert (
        client.post("/admin/test-center/runs", json={"case_ids": [saved["id"]]}).status_code == 400
    )


@pytest.mark.parametrize("conversation_mode", ["independent", "sequence"])
def test_ai_fixed_turns_keep_history_only_inside_the_same_sequence(
    author_client, monkeypatch, conversation_mode
):
    import asyncio

    from test_agent.center.ai_runner import execute_ai

    client, _ = author_client
    monkeypatch.setenv(
        "TEST_CENTER_AI_CONFIG",
        json.dumps(
            {
                "base_url": "https://api.deepseek.com/v1",
                "provider": "deepseek",
                "chat": {"model": "test-chat", "thinking": False},
                "rumination": {"model": "test-rumination", "thinking": False},
            }
        ),
    )
    context = client.post(
        "/admin/test-center/contexts",
        json={
            "name": "连续讨论起点",
            "phase": "values",
            "thread_id": "v1",
            "question_bank": "固定题库",
        },
    ).json()["data"]
    draft = client.post(
        "/admin/test-center/drafts",
        json={
            "title": "两轮讨论",
            "purpose": "核对第二轮是否承接第一轮具体经历",
            "kind": "ai",
            "context_id": context["id"],
            "conversation_mode": conversation_mode,
            "inputs": ["我喜欢帮助同事", "我刚才讲的那件事让我很满足"],
            "assertions": ["回复非空", "第2轮：回复包含：具体经历"],
            "repeats": 2,
        },
    ).json()["data"]
    assert draft["state"] == "ready", draft["issues"]
    saved = client.post("/admin/test-center/cases", json={"draft_id": draft["id"]}).json()["data"]
    run = client.post(
        "/admin/test-center/runs",
        json={
            "case_ids": [saved["id"]],
            "budget": {"max_calls": 4, "max_tokens": 200000},
        },
    ).json()["data"]
    observed = []

    async def model(messages, config, max_tokens, purpose):
        observed.append(messages)
        return {
            "content": "说说具体经历好吗？",
            "model": config["model"],
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 20, "completion_tokens": 10},
        }

    center = client.app.dependency_overrides[get_center]()
    result = asyncio.run(execute_ai(center, run, run["cases"][0], model))
    assert result["status"] == "pass"
    assert len(observed) == 4
    turns = [a["input_index"] for a in result["attempts"]]
    assert turns == [0, 1, 0, 1]
    assert observed[0] == observed[2]
    preceding = [m for m in observed[1][:-1] if m["role"] in {"user", "assistant"}]
    assert preceding == (
        [
            {"role": "user", "content": "我喜欢帮助同事"},
            {"role": "assistant", "content": "说说具体经历好吗？"},
        ]
        if conversation_mode == "sequence"
        else []
    )
    assert len(result["attempts"][0]["checks"]) == 1
    assert len(result["attempts"][1]["checks"]) == 2
    assert (
        client.get(f"/admin/test-center/contexts/{context['id']}").json()["data"]["spec"][
            "messages"
        ]
        == []
    )


def test_admin_can_compose_new_ui_steps_and_step_assertions(author_client):
    client, _ = author_client
    body = {
        "title": "首页去关于页面",
        "kind": "ui",
        "template_id": "home-mobile",
        "inputs": ["打开首页", "点击：关于我们"],
        "assertions": ["第1步：页面无横向溢出", "第2步：应跳转：/about"],
    }
    draft = client.post("/admin/test-center/drafts", json=body).json()["data"]
    assert draft["state"] == "ready", draft["issues"]
    assert draft["definition"]["targets"] == ["scenario"]
    assert draft["definition"]["steps"][1] == {"action": "click", "value": "关于我们"}
    assert draft["definition"]["ui_checks"][1] == {
        "step": 2,
        "type": "url",
        "value": "/about",
    }
    saved = client.post("/admin/test-center/cases", json={"draft_id": draft["id"]}).json()["data"]
    assert (
        client.post("/admin/test-center/runs", json={"case_ids": [saved["id"]]}).status_code == 202
    )
    for invalid in (
        "访问：https://production.example",
        "执行代码：window.fetch('/delete')",
    ):
        response = client.post(
            "/admin/test-center/drafts", json={**body, "inputs": [invalid]}
        ).json()["data"]
        assert response["state"] == "needs_clarification"
