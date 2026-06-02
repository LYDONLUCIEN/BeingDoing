from __future__ import annotations

import json
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List
from uuid import uuid4

from test_agent.adapters.beingdoing.adapter import BeingDoingAdapter
from test_agent.core.ai_user.bridge_kimi import KimiBridge
from test_agent.core.ai_user.judge import L4Judge
from test_agent.core.ai_user.task_spec import TaskSpec
from test_agent.core.contracts.action_contract import ActionContract


class L4LocalRuntime:
    """L4 最小动作运行时，先确保轨迹可审计。"""

    def __init__(self, adapter: BeingDoingAdapter) -> None:
        self.adapter = adapter

    def execute(self, action: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        name = str(action.get("action") or "").strip()
        params = action.get("params") if isinstance(action.get("params"), dict) else {}

        if name == "goto":
            url = str(params.get("url") or "")
            if "talents" in url:
                context["phase"] = "talents"
            elif "rumination" in url:
                context["phase"] = "rumination"
            else:
                context["phase"] = "values"
            return {"status": "pass", "observation": f"goto {url}", "artifacts": []}

        if name == "chat_send":
            text = str(params.get("text") or "").strip()
            context["last_chat_message"] = text
            context.setdefault("messages", []).append({"role": "user", "text": text})
            return {"status": "pass", "observation": "chat_sent", "artifacts": []}

        if name == "stop":
            return {"status": "pass", "observation": "agent_stop", "artifacts": []}

        # 未覆盖动作先视作可执行，避免阻断主流程打通
        return {"status": "pass", "observation": f"{name}_executed", "artifacts": []}


class L4PlaywrightRuntime:
    """L4 真实浏览器运行时：复用 L2 Playwright runner。"""

    def __init__(
        self,
        project_root: Path,
        base_url: str,
        backend_url: str,
        activation_code: str | None = None,
        thread_id: str | None = None,
        savepoint_id: str | None = None,
        headless: bool = True,
        timeout_ms: int = 30000,
    ) -> None:
        self.project_root = project_root
        self.base_url = base_url
        self.backend_url = backend_url
        self.activation_code = activation_code or ""
        self.thread_id = thread_id or ""
        self.savepoint_id = savepoint_id or ""
        self.headless = headless
        self.timeout_ms = timeout_ms
        self._actions: List[Dict[str, Any]] = []

    def execute(self, action: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        action_name = str(action.get("action") or "").strip()
        params = action.get("params") if isinstance(action.get("params"), dict) else {}
        if action_name == "stop":
            return {"status": "pass", "observation": "agent_stop", "artifacts": []}

        expanded_actions = [ActionContract(action=action_name, params=params)]
        if action_name == "chat_send":
            expanded_actions.append(ActionContract(action="wait_for_ai", params={"delta": 1}))
        for item in expanded_actions:
            self._actions.append({"action": item.action, **item.params})

        return self._run_cumulative(context=context)

    def _run_cumulative(self, context: Dict[str, Any]) -> Dict[str, Any]:
        scenario = {
            "id": f"l4_runtime_{uuid4().hex[:8]}",
            "engine": "playwright",
            "data": {
                "base_url": self.base_url,
                "backend_url": self.backend_url,
            },
            "steps": self._actions,
        }
        if self.activation_code:
            scenario["data"]["activation_code"] = self.activation_code
        if self.thread_id:
            scenario["data"]["thread_id"] = self.thread_id
        if self.savepoint_id:
            scenario["data"]["savepoint_id"] = self.savepoint_id

        with NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8", delete=False) as tf:
            temp_path = Path(tf.name)
            tf.write(json.dumps(scenario, ensure_ascii=False, indent=2))
        cmd = [
            "node",
            str(self.project_root / "test_agent" / "l2" / "playwright_runner.mjs"),
            "--scenario",
            str(temp_path),
            "--base-url",
            self.base_url,
            "--backend-url",
            self.backend_url,
            "--headless",
            "true" if self.headless else "false",
            "--timeout-ms",
            str(self.timeout_ms),
        ]
        if self.activation_code:
            cmd.extend(["--activation-code", self.activation_code])
        if self.thread_id:
            cmd.extend(["--thread-id", self.thread_id])
        if self.savepoint_id:
            cmd.extend(["--savepoint-id", self.savepoint_id])

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                check=False,
            )
            payload = _parse_playwright_result(proc.stdout)
            artifacts = []
            if isinstance(payload.get("artifacts"), dict):
                artifacts = [str(v) for v in payload["artifacts"].values() if isinstance(v, str)]

            if proc.returncode == 0 and payload.get("passed") is True:
                self._sync_context_from_actions(context)
                return {"status": "pass", "observation": "playwright_step_ok", "artifacts": artifacts}

            error_text = _extract_playwright_error(payload)
            return {
                "status": "fail",
                "observation": "",
                "artifacts": artifacts,
                "error": error_text,
                "failure_type": _classify_failure(error_text),
            }
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                pass

    def _sync_context_from_actions(self, context: Dict[str, Any]) -> None:
        if not self._actions:
            return
        last = self._actions[-1]
        if str(last.get("action")) == "chat_send":
            context["last_chat_message"] = str(last.get("text") or "").strip()
        for item in reversed(self._actions):
            if str(item.get("action")) == "goto":
                url = str(item.get("url") or "")
                if "talents" in url:
                    context["phase"] = "talents"
                elif "rumination" in url:
                    context["phase"] = "rumination"
                elif "values" in url:
                    context["phase"] = "values"
                break


def _parse_playwright_result(stdout: str) -> Dict[str, Any]:
    m = re.search(r"=== L2_PLAYWRIGHT_RESULT ===\s*(\{[\s\S]*?\})\s*$", stdout.strip())
    if not m:
        return {}
    try:
        raw = json.loads(m.group(1))
        return raw if isinstance(raw, dict) else {}
    except json.JSONDecodeError:
        return {}


def _extract_playwright_error(payload: Dict[str, Any]) -> str:
    if isinstance(payload.get("fatal_error"), str):
        return payload["fatal_error"]
    action_failures = payload.get("action_failures", [])
    if isinstance(action_failures, list) and action_failures:
        first = action_failures[0]
        if isinstance(first, dict):
            return str(first.get("message") or "playwright_action_failed")
    assertion_failures = payload.get("assertion_failures", [])
    if isinstance(assertion_failures, list) and assertion_failures:
        return str(assertion_failures[0])
    return str(payload.get("error") or "playwright_runtime_failed")


def _classify_failure(error_text: str) -> str:
    text = (error_text or "").lower()
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "未找到" in text or "selector" in text:
        return "selector_not_found"
    if "assert" in text or "未包含文本" in text:
        return "assertion_failed"
    if (
        "connection refused" in text
        or "err_connection_refused" in text
        or "executable doesn't exist" in text
        or "enotfound" in text
        or "getaddrinfo" in text
        or "cannot find module" in text
    ):
        return "env_unavailable"
    return "runtime_error"


class L4AgentLoop:
    def __init__(
        self,
        adapter: BeingDoingAdapter | None = None,
        bridge: KimiBridge | None = None,
        judge: L4Judge | None = None,
        runtime_engine: str = "local",
        runtime_options: Dict[str, Any] | None = None,
        project_root: Path | None = None,
    ) -> None:
        self.adapter = adapter or BeingDoingAdapter()
        self.bridge = bridge or KimiBridge()
        self.judge = judge or L4Judge()
        self._transient_failure_types = {"timeout", "llm_invalid_json"}
        options = runtime_options or {}
        root = project_root or Path(__file__).resolve().parents[3]
        if runtime_engine == "playwright":
            self.runtime = L4PlaywrightRuntime(
                project_root=root,
                base_url=str(options.get("base_url") or "http://127.0.0.1:3000"),
                backend_url=str(options.get("backend_url") or "http://127.0.0.1:8000"),
                activation_code=str(options.get("activation_code") or ""),
                thread_id=str(options.get("thread_id") or ""),
                savepoint_id=str(options.get("savepoint_id") or ""),
                headless=bool(options.get("headless", True)),
                timeout_ms=int(options.get("timeout_ms", 30000)),
            )
        else:
            self.runtime = L4LocalRuntime(adapter=self.adapter)

    def run(self, task_spec: TaskSpec, artifacts_dir: Path) -> Dict[str, Any]:
        run_id = f"l4_{uuid4().hex[:12]}"
        context = self.adapter.prepare_data("l4", {"id": task_spec.task_id})
        timeline: List[Dict[str, Any]] = []
        started = time.time()

        for turn in range(1, task_spec.budget.max_turns + 1):
            if len(timeline) >= task_spec.budget.max_steps:
                break
            if time.time() - started > task_spec.budget.max_runtime_sec:
                context["hard_error"] = True
                break

            observation = self.adapter.fetch_runtime_state(context)
            proposed = self.bridge.propose_action(task_spec=task_spec, observation=observation, timeline=timeline)
            bridge_failure_type = self._classify_bridge_failure(proposed)
            if bridge_failure_type:
                recovered, final_type, final_error = self._retry_transient(
                    failure_type=bridge_failure_type,
                    action_label="bridge_propose_action",
                    operation=lambda: self.bridge.propose_action(
                        task_spec=task_spec, observation=observation, timeline=timeline
                    ),
                )
                if not recovered:
                    timeline.append(
                        {
                            "turn": turn,
                            "thought": "",
                            "action": "bridge_propose_action",
                            "params": {},
                            "status": "fail",
                            "observation": "",
                            "duration_ms": 0,
                            "raw_llm_io": None,
                            "error": final_error,
                            "failure_type": final_type,
                            "retries": 1 if final_type in self._transient_failure_types else 0,
                        }
                    )
                    context["hard_error"] = True
                    break
                proposed = recovered

            action_started = time.perf_counter()
            action_result = self.runtime.execute(proposed, context=context)
            duration_ms = int((time.perf_counter() - action_started) * 1000)
            retries = 0
            if action_result.get("status") == "fail":
                failure_type = str(action_result.get("failure_type") or "runtime_error")
                recovered_result, final_type, final_error = self._retry_transient(
                    failure_type=failure_type,
                    action_label=str(proposed.get("action") or ""),
                    operation=lambda: self.runtime.execute(proposed, context=context),
                )
                if recovered_result:
                    action_result = recovered_result
                    retries = 1
                else:
                    action_result["failure_type"] = final_type
                    action_result["error"] = final_error
                    retries = 1 if final_type in self._transient_failure_types else 0

            timeline.append(
                {
                    "turn": turn,
                    "thought": proposed.get("thought", ""),
                    "action": proposed.get("action"),
                    "params": proposed.get("params", {}),
                    "status": action_result.get("status", "pass"),
                    "observation": action_result.get("observation", ""),
                    "duration_ms": duration_ms,
                    "raw_llm_io": proposed.get("raw_llm"),
                    "error": action_result.get("error"),
                    "failure_type": action_result.get("failure_type"),
                    "retries": retries,
                }
            )
            if action_result.get("status") == "fail":
                context["hard_error"] = True
                break
            if proposed.get("action") == "stop":
                break

        judge_result = self.judge.evaluate(
            task_spec=task_spec,
            timeline=timeline,
            runtime_state=self.adapter.fetch_runtime_state(context),
        )
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        conversation_path = artifacts_dir / "conversation.json"
        conversation_path.write_text(
            json.dumps({"timeline": timeline}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return {
            "task_id": task_spec.task_id,
            "run_id": run_id,
            "status": judge_result["status"],
            "score": judge_result["score"],
            "signals": judge_result["signals"],
            "timeline": timeline,
            "artifacts": {
                "conversation_dump": str(conversation_path),
                "screenshots": str(artifacts_dir / "screenshots"),
                "trace": str(artifacts_dir / "trace.zip"),
            },
            "generated_at": datetime.utcnow().isoformat() + "Z",
        }

    def _retry_transient(
        self,
        failure_type: str,
        action_label: str,
        operation: Any,
    ) -> tuple[Dict[str, Any] | None, str, str]:
        """
        对瞬时错误重试 1 次。
        返回：(成功结果|None, 最终 failure_type, 最终 error)
        """
        if failure_type not in self._transient_failure_types:
            return None, failure_type, f"{action_label} failed"
        retry_result = operation()
        retry_failure_type = str(retry_result.get("failure_type") or "")
        retry_error = str(retry_result.get("error") or "")
        if not retry_failure_type and retry_result.get("bridge_error"):
            retry_failure_type = self._classify_bridge_failure(retry_result) or "runtime_error"
            retry_error = str(retry_result.get("bridge_error") or "bridge_error")
        if retry_result.get("status") == "fail" or retry_failure_type:
            return None, retry_failure_type or failure_type, retry_error or f"{action_label} retry failed"
        return retry_result, "", ""

    def _classify_bridge_failure(self, proposed: Dict[str, Any]) -> str | None:
        if not proposed.get("bridge_error"):
            return None
        explicit = str(proposed.get("failure_type") or "").strip()
        if explicit:
            return explicit
        text = str(proposed.get("bridge_error") or "").lower()
        if "json" in text or "parse" in text:
            return "llm_invalid_json"
        if "not found" in text or "enoent" in text or "connection" in text:
            return "env_unavailable"
        return "runtime_error"
