"""
基于真实历史数据的 simple-chat pending 流程测试。

说明：
- 测试会从 data/simple/reports/5c4f63d0-353e-41b5-8d3f-9cf4aa944c56 复制数据到临时目录
- 通过 monkeypatch 将 simple 模块数据根目录指向临时目录，避免污染真实数据
- 全部通过后端 API 调用（不依赖前端）
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from app.api.v1.auth import get_current_user
from app.main import app
import app.api.v1.simple_chat_routes as simple_chat_api
import app.utils.simple_activation_manager as activation_manager_mod
from app.utils.simple_activation_manager import SimpleActivationManager


REAL_REPORT_ID = "5c4f63d0-353e-41b5-8d3f-9cf4aa944c56"
REAL_REPORT_DIR = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "simple"
    / "reports"
    / REAL_REPORT_ID
)
TEST_USER = {
    "user_id": "pytest-user-real-history",
    "email": "pytest-real-history@example.com",
}


class FakeDialogueLLM:
    def __init__(self, stream_reply: str = "", chat_reply: str = "测试回复"):
        self.stream_reply = stream_reply
        self.chat_reply = chat_reply
        self._last_stream_usage = None

    async def chat(self, messages, temperature=0.7, response_format=None):
        return SimpleNamespace(content=self.chat_reply, usage={})

    async def chat_stream(self, messages, temperature=0.7):
        if self.stream_reply:
            yield self.stream_reply


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _stream_events(client: TestClient, headers: Dict[str, str], payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    with client.stream("POST", "/api/v1/simple-chat/message/stream", json=payload, headers=headers) as resp:
        assert resp.status_code == 200
        for line in resp.iter_lines():
            if not line:
                continue
            text = line.decode("utf-8") if isinstance(line, bytes) else line
            if not text.startswith("data: "):
                continue
            events.append(json.loads(text[6:]))
    return events


@pytest.fixture()
def seeded_env(tmp_path, monkeypatch):
    assert REAL_REPORT_DIR.is_dir(), f"真实历史目录不存在: {REAL_REPORT_DIR}"

    simple_root = tmp_path / "simple"
    reports_root = simple_root / "reports"
    reports_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(REAL_REPORT_DIR, reports_root / REAL_REPORT_ID, dirs_exist_ok=True)

    # 将 simple 数据根目录重定向到测试临时目录
    monkeypatch.setattr(activation_manager_mod, "get_simple_base_dir", lambda: simple_root)

    # 覆盖认证依赖，避免走真实用户体系
    app.dependency_overrides[get_current_user] = lambda: TEST_USER

    # 创建激活码并与复制的 report 绑定
    manager = SimpleActivationManager(base_dir=str(simple_root))
    rec = manager.create_activation(mode="values", ttl_minutes=120)
    manager.claim_owner(rec.code, TEST_USER)

    record_path = reports_root / REAL_REPORT_ID / "record.json"
    record = _read_json(record_path)
    record["activation_code"] = rec.code
    record["user_id"] = TEST_USER["user_id"]
    _write_json(record_path, record)

    # 避免后台异步锚点提炼触发真实 LLM
    monkeypatch.setattr(simple_chat_api, "_trigger_anchor_refiner", lambda *args, **kwargs: None)

    client = TestClient(app)
    headers = {"Authorization": "Bearer fake-token"}
    yield {
        "client": client,
        "headers": headers,
        "activation_code": rec.code,
        "report_id": REAL_REPORT_ID,
        "simple_root": simple_root,
        "reports_root": reports_root,
    }
    app.dependency_overrides.clear()


def test_flow_1_load_real_pending_history(seeded_env, monkeypatch):
    """实例1：加载真实 pending 线程，走 continue 分支（继续聊天）"""
    client = seeded_env["client"]
    headers = seeded_env["headers"]
    code = seeded_env["activation_code"]
    thread_id = "t_1774270521244_djka2wr"  # 真实数据：pending 样本

    async def fake_decide(*args, **kwargs):
        return {"state": "continue", "content": "继续聊聊更稳妥。"}

    monkeypatch.setattr(simple_chat_api, "_decide_pending_action_by_llm", fake_decide)
    monkeypatch.setattr(
        simple_chat_api,
        "_get_dialogue_llm_provider",
        lambda vip_level=1: FakeDialogueLLM(
            stream_reply="我们先继续补充。\n[STATE_JSON]{\"state\":\"continue\",\"draft\":null}[/STATE_JSON]"
        ),
    )

    events = _stream_events(
        client,
        headers,
        {
            "activation_code": code,
            "phase": "values",
            "thread_id": thread_id,
            "message": "嗯我再想想",
        },
    )
    assert any(e.get("done") is True for e in events)
    # continue 不应直接下发结论卡事件
    assert not any("dimension_conclusion" in e for e in events)


def test_flow_2_pending_confirm_emit_card(seeded_env, monkeypatch):
    """实例2：真实 pending 线程 + 用户确认 -> 进入结论卡输出"""
    client = seeded_env["client"]
    headers = seeded_env["headers"]
    code = seeded_env["activation_code"]
    thread_id = "t_1774270521244_djka2wr"

    async def fake_decide(*args, **kwargs):
        return {"state": "confirmed", "content": "收到你的确认，我将生成结论卡。"}

    async def fake_check(*args, **kwargs):
        return {
            "summary": "基于历史确认：成长、创新、意义感、身心健康、心流。",
            "keywords": ["成长", "创新", "意义感", "身心健康", "心流"],
        }

    monkeypatch.setattr(simple_chat_api, "_decide_pending_action_by_llm", fake_decide)
    monkeypatch.setattr(simple_chat_api, "check_dimension_complete", fake_check)
    monkeypatch.setattr(simple_chat_api, "_get_reasoning_llm_provider", lambda vip_level=1: object())

    events = _stream_events(
        client,
        headers,
        {
            "activation_code": code,
            "phase": "values",
            "thread_id": thread_id,
            "message": "我确认",
        },
    )

    assert any("dimension_conclusion" in e for e in events)
    assert any(e.get("done") is True for e in events)

    history = client.get(
        "/api/v1/simple-chat/history",
        params={"activation_code": code, "phase": "values", "thread_id": thread_id},
        headers=headers,
    ).json()["data"]
    assert any((m or {}).get("role") == "conclusion_card" for m in history["messages"])


def test_flow_3_pending_rejected_then_continue_chat(seeded_env, monkeypatch):
    """实例3：真实 pending 线程 + 用户否定 -> 拒绝后继续对话"""
    client = seeded_env["client"]
    headers = seeded_env["headers"]
    code = seeded_env["activation_code"]
    thread_id = "t_1774270521244_djka2wr"

    async def fake_decide(*args, **kwargs):
        return {"state": "rejected", "content": "先不确认，我们继续聊。"}

    monkeypatch.setattr(simple_chat_api, "_decide_pending_action_by_llm", fake_decide)
    monkeypatch.setattr(
        simple_chat_api,
        "_get_dialogue_llm_provider",
        lambda vip_level=1: FakeDialogueLLM(
            stream_reply="明白，我们继续补充。\n[STATE_JSON]{\"state\":\"continue\",\"draft\":null}[/STATE_JSON]"
        ),
    )

    _stream_events(
        client,
        headers,
        {
            "activation_code": code,
            "phase": "values",
            "thread_id": thread_id,
            "message": "不准确，继续聊",
        },
    )

    thread_file = (
        seeded_env["reports_root"]
        / REAL_REPORT_ID
        / "values__t_1774270521244_djka2wr.json"
    )
    meta = _read_json(thread_file).get("metadata", {})
    assert meta.get("conclusion_state") == "rejected"
    assert (meta.get("conclusion_feedback") or "") != ""


def test_flow_4_thread_complete_from_real_pending(seeded_env):
    """实例4：真实 pending 线程直接调用 complete -> completed + conclusion_card"""
    client = seeded_env["client"]
    headers = seeded_env["headers"]
    code = seeded_env["activation_code"]
    thread_id = "t_1774270521244_djka2wr"

    resp = client.post(
        "/api/v1/simple-chat/thread/complete",
        json={"activation_code": code, "phase": "values", "thread_id": thread_id},
        headers=headers,
    )
    assert resp.status_code == 200

    history = client.get(
        "/api/v1/simple-chat/history",
        params={"activation_code": code, "phase": "values", "thread_id": thread_id},
        headers=headers,
    ).json()["data"]
    assert history["metadata"]["thread_completed"] is True
    assert any((m or {}).get("role") == "conclusion_card" for m in history["messages"])


def test_flow_5_reopen_after_complete(seeded_env):
    """实例5：先 complete 再 reopen -> 线程回到 in-progress"""
    client = seeded_env["client"]
    headers = seeded_env["headers"]
    code = seeded_env["activation_code"]
    thread_id = "t_1774270521244_djka2wr"

    client.post(
        "/api/v1/simple-chat/thread/complete",
        json={"activation_code": code, "phase": "values", "thread_id": thread_id},
        headers=headers,
    )
    reopen = client.post(
        "/api/v1/simple-chat/thread/reopen",
        json={"activation_code": code, "phase": "values", "thread_id": thread_id},
        headers=headers,
    )
    assert reopen.status_code == 200

    threads = client.get(
        "/api/v1/simple-chat/threads",
        params={"activation_code": code, "phase": "values"},
        headers=headers,
    ).json()["data"]["threads"]
    target = [t for t in threads if t["id"] == thread_id][0]
    assert target["status"] == "in-progress"


def test_flow_6_rejected_history_can_reenter_pending(seeded_env, monkeypatch):
    """实例6：基于真实 rejected 线程（再聊聊）再次进入 pending_ready"""
    client = seeded_env["client"]
    headers = seeded_env["headers"]
    code = seeded_env["activation_code"]
    thread_id = "t_1774259620198_qxo0otx"  # 真实数据：conclusion_state=rejected

    monkeypatch.setattr(
        simple_chat_api,
        "_get_dialogue_llm_provider",
        lambda vip_level=1: FakeDialogueLLM(
            stream_reply=(
                "根据你补充的信息，我先整理新摘要。\n"
                "[STATE_JSON]"
                "{\"state\":\"pending_ready\",\"draft\":{\"summary\":\"新版价值观摘要\",\"keywords\":[\"成长\",\"创新\",\"意义\"]}}"
                "[/STATE_JSON]"
            )
        ),
    )

    events = _stream_events(
        client,
        headers,
        {
            "activation_code": code,
            "phase": "values",
            "thread_id": thread_id,
            "message": "我补充一下最终排序",
        },
    )
    assert any(e.get("done") is True for e in events)

    thread_file = seeded_env["reports_root"] / REAL_REPORT_ID / f"values__{thread_id}.json"
    meta = _read_json(thread_file).get("metadata", {})
    assert meta.get("conclusion_state") == "pending"
    assert isinstance(meta.get("conclusion_draft"), dict)
    assert (meta.get("conclusion_draft") or {}).get("summary") == "新版价值观摘要"
