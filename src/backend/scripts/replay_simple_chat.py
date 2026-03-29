#!/usr/bin/env python3
"""
Simple Chat 回放脚本（单条 + 批量）。

目标：
- 指定激活码/阶段/thread/message，直接看 /simple-chat/message/stream 输出
- 支持按用例文件批量回放
- 支持可选沙箱 Fork（便于快速隔离调试）
- 支持可选 Prompt 覆盖（一次性模板）或绑定 Prompt Lab profile

示例：
  # 单条（已有激活码）
  python src/backend/scripts/replay_simple_chat.py \
    --activation-code ABC12345 --phase values --thread-id t_demo_1 --message "我再补充一点"

  # 单条（先从源激活码 Fork 出沙箱再回放）
  python src/backend/scripts/replay_simple_chat.py \
    --fork-from ABC12345 --phase values --thread-id t_demo_1 --message "继续" \
    --user-id admin-1 --user-email admin@example.com

  # 批量（读取 test/backend/fixtures/simple_chat_cases/*.json）
  python src/backend/scripts/replay_simple_chat.py \
    --cases-file test/backend/fixtures/simple_chat_cases/batch_basic.json
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Iterator, List, Optional

from fastapi.testclient import TestClient


def _load_env_and_paths() -> Path:
    backend_dir = Path(__file__).resolve().parent.parent
    project_root = backend_dir.parent.parent
    env_file = project_root / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(env_file)
        except Exception:
            pass
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
    return project_root


PROJECT_ROOT = _load_env_and_paths()

app = None
get_current_user = None
simple_chat_api = None
activation_manager_mod = None
bind_profile_to_activation = None
set_current_version = None
fork_activation_from_source = None
SimpleActivationManager = None


def _bootstrap_backend() -> None:
    global app
    global get_current_user
    global simple_chat_api
    global activation_manager_mod
    global bind_profile_to_activation
    global set_current_version
    global fork_activation_from_source
    global SimpleActivationManager

    if app is not None:
        return

    from app.api.v1.auth import get_current_user as _get_current_user
    from app.main import app as _app
    import app.api.v1.simple_chat as _simple_chat_api
    import app.utils.simple_activation_manager as _activation_manager_mod
    from app.utils.admin_prompt_lab import (
        bind_profile_to_activation as _bind_profile_to_activation,
        set_current_version as _set_current_version,
    )
    from app.utils.sandbox_fork import fork_activation_from_source as _fork_activation_from_source
    from app.utils.simple_activation_manager import SimpleActivationManager as _SimpleActivationManager

    app = _app
    get_current_user = _get_current_user
    simple_chat_api = _simple_chat_api
    activation_manager_mod = _activation_manager_mod
    bind_profile_to_activation = _bind_profile_to_activation
    set_current_version = _set_current_version
    fork_activation_from_source = _fork_activation_from_source
    SimpleActivationManager = _SimpleActivationManager


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


class _PatchBag:
    def __init__(self):
        self._restore: List[Any] = []

    def set_attr(self, obj: Any, attr: str, value: Any) -> None:
        old = getattr(obj, attr)
        self._restore.append((obj, attr, old))
        setattr(obj, attr, value)

    def restore(self) -> None:
        while self._restore:
            obj, attr, old = self._restore.pop()
            setattr(obj, attr, old)


@contextmanager
def _overrides_ctx(
    user: Dict[str, Any],
    *,
    simple_root: Optional[Path] = None,
    prompt_template: Optional[str] = None,
    extra_goal_hint: str = "",
    mock: Optional[Dict[str, Any]] = None,
) -> Iterator[None]:
    bag = _PatchBag()
    try:
        # auth override
        app.dependency_overrides[get_current_user] = lambda: user

        # optional simple storage root override
        if simple_root is not None:
            bag.set_attr(activation_manager_mod, "get_simple_base_dir", lambda: simple_root)

        # optional one-off prompt override (复用 simple_chat 既有注入点)
        if (prompt_template or "").strip():
            payload = {
                "template": (prompt_template or "").strip(),
                "extra_goal_hint": (extra_goal_hint or "").strip(),
                "meta": {"source": "replay_simple_chat"},
            }
            bag.set_attr(
                simple_chat_api,
                "_resolve_prompt_lab_override_for_request",
                lambda rec, current_user: payload,
            )

        # optional mock llm behavior
        if isinstance(mock, dict):
            stream_reply = str(mock.get("stream_reply") or "")
            chat_reply = str(mock.get("chat_reply") or "测试回复")
            if stream_reply or chat_reply:
                bag.set_attr(
                    simple_chat_api,
                    "_get_dialogue_llm_provider",
                    lambda vip_level=1: FakeDialogueLLM(
                        stream_reply=stream_reply,
                        chat_reply=chat_reply,
                    ),
                )

            if isinstance(mock.get("pending_decision"), dict):
                decision = mock.get("pending_decision")

                async def _fake_decide(*args, **kwargs):
                    return decision

                bag.set_attr(simple_chat_api, "_decide_pending_action_by_llm", _fake_decide)

            if isinstance(mock.get("dimension_conclusion"), dict):
                conclusion = mock.get("dimension_conclusion")

                async def _fake_check(*args, **kwargs):
                    return conclusion

                bag.set_attr(simple_chat_api, "check_dimension_complete", _fake_check)
                bag.set_attr(simple_chat_api, "_get_reasoning_llm_provider", lambda vip_level=1: object())

        # avoid background refiner noise in replay
        bag.set_attr(simple_chat_api, "_trigger_anchor_refiner", lambda *args, **kwargs: None)
        yield
    finally:
        app.dependency_overrides.clear()
        bag.restore()


def _stream_events(client: TestClient, headers: Dict[str, str], payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    with client.stream("POST", "/api/v1/simple-chat/message/stream", json=payload, headers=headers) as resp:
        if resp.status_code != 200:
            raise RuntimeError(f"stream status={resp.status_code} body={resp.text}")
        for line in resp.iter_lines():
            if not line:
                continue
            text = line.decode("utf-8") if isinstance(line, bytes) else line
            if not text.startswith("data: "):
                continue
            try:
                events.append(json.loads(text[6:]))
            except json.JSONDecodeError:
                continue
    return events


def _seed_report_fixture(
    fixture_dir: Path,
    *,
    user: Dict[str, Any],
    ttl_minutes: int = 180,
) -> Dict[str, Any]:
    """
    将 fixture report 拷贝到临时 simple 目录并自动创建激活码绑定。
    fixture_dir 需要包含 record.json 与若干 {step}__{thread}.json。
    """
    if not fixture_dir.is_dir():
        raise ValueError(f"fixture_dir 不存在: {fixture_dir}")
    record_file = fixture_dir / "record.json"
    if not record_file.is_file():
        raise ValueError(f"fixture 缺少 record.json: {record_file}")

    record = json.loads(record_file.read_text(encoding="utf-8") or "{}")
    report_id = str(record.get("report_id") or "").strip()
    if not report_id:
        raise ValueError("fixture record.json 缺少 report_id")

    # 每次 seed 到独立临时目录，避免污染真实 data/simple
    replay_root = PROJECT_ROOT / "data" / "test" / "simple" / "replay_runs"
    replay_root.mkdir(parents=True, exist_ok=True)
    run_root = replay_root / f"run_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    if run_root.exists():
        shutil.rmtree(run_root, ignore_errors=True)
    reports_root = run_root / "reports"
    reports_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(fixture_dir, reports_root / report_id, dirs_exist_ok=True)

    manager = SimpleActivationManager(base_dir=str(run_root))
    rec = manager.create_activation(mode="values", ttl_minutes=ttl_minutes)
    manager.claim_owner(rec.code, user)

    rec_path = reports_root / report_id / "record.json"
    rec_data = json.loads(rec_path.read_text(encoding="utf-8") or "{}")
    rec_data["activation_code"] = rec.code
    rec_data["user_id"] = user.get("user_id")
    rec_path.write_text(json.dumps(rec_data, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "simple_root": run_root,
        "activation_code": rec.code,
        "report_id": report_id,
    }


def _history(client: TestClient, headers: Dict[str, str], activation_code: str, phase: str, thread_id: str) -> Dict[str, Any]:
    resp = client.get(
        "/api/v1/simple-chat/history",
        params={"activation_code": activation_code, "phase": phase, "thread_id": thread_id},
        headers=headers,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"history status={resp.status_code} body={resp.text}")
    return (resp.json() or {}).get("data") or {}


def _run_one_case(case: Dict[str, Any], default_user: Dict[str, Any]) -> Dict[str, Any]:
    name = str(case.get("name") or "unnamed_case")
    phase = str(case.get("phase") or "values")
    thread_id = str(case.get("thread_id") or "").strip()
    message = str(case.get("message") or "").strip()
    if not thread_id or not message:
        raise ValueError(f"[{name}] thread_id/message 不能为空")

    user = dict(default_user)
    user.update(case.get("user") or {})
    headers = {"Authorization": "Bearer replay-token"}

    # activation source:
    activation_code = str(case.get("activation_code") or "").strip().upper()
    simple_root: Optional[Path] = None
    fixture_cfg = case.get("seed_fixture") or {}
    if isinstance(fixture_cfg, dict) and fixture_cfg.get("report_dir"):
        seeded = _seed_report_fixture(
            (PROJECT_ROOT / str(fixture_cfg["report_dir"])).resolve(),
            user=user,
            ttl_minutes=int(fixture_cfg.get("ttl_minutes") or 180),
        )
        simple_root = seeded["simple_root"]
        activation_code = seeded["activation_code"]

    if not activation_code:
        fork_from = str(case.get("fork_from") or "").strip().upper()
        if fork_from:
            rec, _summary = fork_activation_from_source(fork_from, user)
            activation_code = rec.code
        else:
            raise ValueError(f"[{name}] activation_code 或 fork_from 至少提供一个")

    # optional prompt-lab binding reuse
    profile_id = str(case.get("prompt_profile_id") or "").strip()
    version_id = str(case.get("prompt_version_id") or "").strip()
    if profile_id:
        if version_id:
            set_current_version(profile_id, version_id)
        bind_profile_to_activation(activation_code, profile_id, actor=user)

    prompt_template = None
    prompt_template_file = str(case.get("prompt_template_file") or "").strip()
    if prompt_template_file:
        f = (PROJECT_ROOT / prompt_template_file).resolve()
        prompt_template = f.read_text(encoding="utf-8")

    with _overrides_ctx(
        user,
        simple_root=simple_root,
        prompt_template=prompt_template,
        extra_goal_hint=str(case.get("extra_goal_hint") or ""),
        mock=case.get("mock") if isinstance(case.get("mock"), dict) else None,
    ):
        client = TestClient(app)
        payload = {
            "activation_code": activation_code,
            "phase": phase,
            "thread_id": thread_id,
            "message": message,
        }
        events = _stream_events(client, headers, payload)
        hist = _history(client, headers, activation_code, phase, thread_id)

    chunks = "".join([str(e.get("chunk") or "") for e in events if isinstance(e, dict)])
    result = {
        "name": name,
        "activation_code": activation_code,
        "phase": phase,
        "thread_id": thread_id,
        "message": message,
        "events_count": len(events),
        "done": any((e or {}).get("done") is True for e in events),
        "chunks_preview": chunks[:300],
        "has_state_json_leak": "[STATE_JSON]" in chunks or "[/STATE_JSON]" in chunks,
        "history_metadata": (hist.get("metadata") or {}),
        "history_messages_count": len(hist.get("messages") or []),
    }
    return result


def _print_case_result(result: Dict[str, Any]) -> None:
    print(f"\n=== {result.get('name')} ===")
    print(
        f"activation={result.get('activation_code')} phase={result.get('phase')} "
        f"thread={result.get('thread_id')}"
    )
    print(
        f"events={result.get('events_count')} done={result.get('done')} "
        f"state_json_leak={result.get('has_state_json_leak')}"
    )
    meta = result.get("history_metadata") or {}
    print(
        "meta:",
        {
            "thread_completed": meta.get("thread_completed"),
            "step_locked": meta.get("step_locked"),
            "conclusion_state": meta.get("conclusion_state"),
            "pending_status": meta.get("pending_status"),
        },
    )
    preview = (result.get("chunks_preview") or "").strip()
    if preview:
        print("chunks_preview:", preview)


def _single_case_from_args(args: argparse.Namespace) -> Dict[str, Any]:
    case: Dict[str, Any] = {
        "name": args.name or "single",
        "activation_code": (args.activation_code or "").strip().upper(),
        "phase": args.phase,
        "thread_id": args.thread_id,
        "message": args.message,
        "fork_from": (args.fork_from or "").strip().upper(),
        "prompt_profile_id": (args.prompt_profile_id or "").strip(),
        "prompt_version_id": (args.prompt_version_id or "").strip(),
        "prompt_template_file": (args.prompt_template_file or "").strip(),
        "extra_goal_hint": args.extra_goal_hint or "",
    }
    if args.seed_report_dir:
        case["seed_fixture"] = {
            "report_dir": args.seed_report_dir,
            "ttl_minutes": args.seed_ttl_minutes,
        }
    if args.mock_stream_reply or args.mock_chat_reply or args.mock_pending_state:
        mock_payload: Dict[str, Any] = {}
        if args.mock_stream_reply:
            mock_payload["stream_reply"] = args.mock_stream_reply
        if args.mock_chat_reply:
            mock_payload["chat_reply"] = args.mock_chat_reply
        if args.mock_pending_state:
            mock_payload["pending_decision"] = {
                "state": args.mock_pending_state,
                "content": args.mock_pending_content or "mock pending decision",
            }
        if args.mock_conclusion_summary:
            kws = []
            if args.mock_conclusion_keywords:
                kws = [x.strip() for x in args.mock_conclusion_keywords.split(",") if x.strip()]
            mock_payload["dimension_conclusion"] = {
                "summary": args.mock_conclusion_summary,
                "keywords": kws,
            }
        case["mock"] = mock_payload
    return case


def _load_cases_file(path: Path) -> List[Dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8") or "{}")
    if isinstance(raw, dict) and isinstance(raw.get("cases"), list):
        return [x for x in raw["cases"] if isinstance(x, dict)]
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    raise ValueError(f"cases 文件格式错误: {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay simple-chat stream for fast backend/prompt tuning.")
    parser.add_argument("--name", default="single")
    parser.add_argument("--activation-code", default="")
    parser.add_argument("--fork-from", default="")
    parser.add_argument("--phase", default="values")
    parser.add_argument("--thread-id", default="t_replay_001")
    parser.add_argument("--message", default="我再补充一点")
    parser.add_argument("--user-id", default="replay-user")
    parser.add_argument("--user-email", default="replay@example.com")
    parser.add_argument("--prompt-profile-id", default="")
    parser.add_argument("--prompt-version-id", default="")
    parser.add_argument("--prompt-template-file", default="")
    parser.add_argument("--extra-goal-hint", default="")
    parser.add_argument("--seed-report-dir", default="")
    parser.add_argument("--seed-ttl-minutes", type=int, default=180)
    parser.add_argument("--cases-file", default="")
    parser.add_argument("--output-json", default="")

    # mock flags (可选)
    parser.add_argument("--mock-stream-reply", default="")
    parser.add_argument("--mock-chat-reply", default="")
    parser.add_argument("--mock-pending-state", default="")
    parser.add_argument("--mock-pending-content", default="")
    parser.add_argument("--mock-conclusion-summary", default="")
    parser.add_argument("--mock-conclusion-keywords", default="")
    args = parser.parse_args()
    _bootstrap_backend()

    user = {"user_id": args.user_id, "email": args.user_email}
    if not user["user_id"]:
        raise RuntimeError("user_id 不能为空")

    if args.cases_file:
        cases = _load_cases_file((PROJECT_ROOT / args.cases_file).resolve())
    else:
        cases = [_single_case_from_args(args)]

    results: List[Dict[str, Any]] = []
    failures: List[str] = []
    for c in cases:
        try:
            ret = _run_one_case(c, user)
            _print_case_result(ret)
            results.append(ret)
        except Exception as e:
            name = str(c.get("name") or "unnamed_case")
            failures.append(f"{name}: {type(e).__name__}: {e}")
            print(f"\n=== {name} FAILED ===")
            print(f"{type(e).__name__}: {e}")

    summary = {
        "total": len(cases),
        "passed": len(results),
        "failed": len(failures),
        "failures": failures,
        "results": results,
    }
    print("\n=== SUMMARY ===")
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, ensure_ascii=False, indent=2))

    if args.output_json:
        out_file = (PROJECT_ROOT / args.output_json).resolve()
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"saved: {out_file}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

