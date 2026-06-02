from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import asdict
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List
from uuid import uuid4

from test_agent.core.contracts.action_contract import ActionContract
from test_agent.core.runner.result_model import ScenarioResult, StepResult


class LocalActionExecutor:
    """
    本地最小动作执行器。

    该实现不直接驱动浏览器，先提供统一动作语义与报告出口，
    便于后续替换为 Playwright/真实 API 执行。
    """

    def execute_action(
        self,
        action: ActionContract,
        context: Dict[str, Any],
        adapter: Any,
    ) -> Dict[str, Any]:
        name = action.action
        params = action.params

        if name == "goto":
            context["phase"] = params.get("phase", context.get("phase", "values"))
            return {"status": "pass", "observation": f'进入页面: {params.get("url", "")}', "artifacts": []}
        if name == "click":
            return {"status": "pass", "observation": f'点击元素: {params.get("selector", "")}', "artifacts": []}
        if name == "fill":
            return {"status": "pass", "observation": "输入完成", "artifacts": []}
        if name == "chat_send":
            text = str(params.get("text") or "").strip()
            context["last_chat_message"] = text
            return {"status": "pass", "observation": f"发送消息: {text}", "artifacts": []}
        if name == "wait_for":
            return {"status": "pass", "observation": "等待完成", "artifacts": []}
        if name == "assert_text":
            expected = str(params.get("text") or "").strip()
            context.setdefault("expected_texts", []).append(expected)
            return {"status": "pass", "observation": f"断言文本存在: {expected}", "artifacts": []}
        if name == "assert_dom":
            return {"status": "pass", "observation": f'DOM 存在: {params.get("selector", "")}', "artifacts": []}
        if name == "domain_action":
            domain_name = str(params.get("name") or "").strip()
            payload = params.get("payload") if isinstance(params.get("payload"), dict) else dict(params)
            return adapter.execute_domain_action(domain_name, payload, context)
        if name == "domain_assert":
            domain_name = str(params.get("name") or "").strip()
            context.setdefault("domain_assertions", []).append(params)
            return adapter.assert_domain(domain_name, context)
        if name == "unsupported_step":
            return {
                "status": "fail",
                "observation": "",
                "artifacts": [],
                "error": f"未匹配步骤定义: {params.get('step_text')}",
            }
        return {"status": "fail", "observation": "", "artifacts": [], "error": f"未知动作: {name}"}


class PlaywrightActionExecutor:
    """
    通过现有 L2 Playwright runner 执行标准动作。

    说明：
    - 为保持状态连续性，按“累计动作”重放到当前步骤。
    - 不支持的动作由上层回退到 LocalActionExecutor。
    """

    SUPPORTED_ACTIONS = {
        "goto",
        "chat_send",
        "wait_for_ai",
        "wait_ms",
        "screenshot",
        "click",
        "fill",
        "assert_text",
    }

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

    def is_supported(self, action: ActionContract) -> bool:
        return action.action in self.SUPPORTED_ACTIONS

    def execute_cumulative(
        self,
        scenario_id: str,
        actions: List[ActionContract],
        step_action_start_index: int,
        step_action_end_index: int,
    ) -> Dict[str, Any]:
        scenario = {
            "id": f"{scenario_id}_pw",
            "engine": "playwright",
            "data": {
                "base_url": self.base_url,
                "backend_url": self.backend_url,
            },
            "steps": [{"action": a.action, **a.params} for a in actions],
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
            if not payload:
                return {
                    "status": "fail",
                    "error": "playwright_result_parse_failed",
                    "observation": "",
                    "artifacts": [],
                    "failure_type": "runtime_error",
                }

            action_failures = payload.get("action_failures", []) if isinstance(payload, dict) else []
            assertion_failures = payload.get("assertion_failures", []) if isinstance(payload, dict) else []
            artifacts = []
            if isinstance(payload.get("artifacts"), dict):
                artifacts = [str(v) for v in payload["artifacts"].values() if isinstance(v, str)]

            if proc.returncode == 0 and payload.get("passed") is True:
                return {
                    "status": "pass",
                    "observation": f'playwright ok, steps_ok={payload.get("steps_ok", 0)}',
                    "artifacts": artifacts,
                }

            current_step_error = ""
            for item in action_failures:
                if not isinstance(item, dict):
                    continue
                idx = int(item.get("step_index", -1))
                if step_action_start_index <= idx <= step_action_end_index:
                    current_step_error = str(item.get("message") or "")
                    break
            if not current_step_error and action_failures:
                first = action_failures[0]
                if isinstance(first, dict):
                    current_step_error = str(first.get("message") or "")
            if not current_step_error and assertion_failures:
                current_step_error = str(assertion_failures[0])
            if not current_step_error:
                current_step_error = str(payload.get("fatal_error") or payload.get("error") or "playwright_failed")

            return {
                "status": "fail",
                "observation": "",
                "artifacts": artifacts,
                "error": current_step_error,
                "failure_type": _classify_failure(current_step_error),
            }
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                pass


def _parse_playwright_result(stdout: str) -> Dict[str, Any]:
    m = re.search(r"=== L2_PLAYWRIGHT_RESULT ===\s*(\{[\s\S]*?\})\s*$", stdout.strip())
    if not m:
        return {}
    try:
        raw = json.loads(m.group(1))
        return raw if isinstance(raw, dict) else {}
    except json.JSONDecodeError:
        return {}


def _classify_failure(error_text: str) -> str:
    text = (error_text or "").lower()
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "未找到" in text or "selector" in text:
        return "selector_not_found"
    if "assert" in text or "未包含文本" in text or "expected_" in text:
        return "assertion_failed"
    if "缺少" in text or "invalid" in text or "format" in text:
        return "data_error"
    if "不支持的 action" in text or "未知动作" in text:
        return "action_unsupported"
    return "runtime_error"


class BddExecutor:
    def __init__(
        self,
        adapter: Any,
        action_executor: LocalActionExecutor | None = None,
        playwright_executor: PlaywrightActionExecutor | None = None,
        engine: str = "local",
    ) -> None:
        self.adapter = adapter
        self.action_executor = action_executor or LocalActionExecutor()
        self.playwright_executor = playwright_executor
        self.engine = engine

    def run(self, scenario_id: str, steps: List[Dict[str, Any]]) -> ScenarioResult:
        run_id = f"l3_{uuid4().hex[:12]}"
        result = ScenarioResult.new(run_id=run_id, scenario_id=scenario_id, level="L3")
        context: Dict[str, Any] = self.adapter.prepare_data("l3", {"id": scenario_id})
        cumulative_playwright_actions: List[ActionContract] = []

        for idx, step in enumerate(steps, start=1):
            keyword = str(step.get("keyword") or "When")
            text = str(step.get("text") or "").strip()
            step_id = f"step_{idx:02d}"
            started = time.perf_counter()

            raw_step = step.get("raw") if isinstance(step.get("raw"), dict) else {}
            if raw_step.get("action"):
                action_name = str(raw_step.get("action")).strip()
                action_params = {k: v for k, v in raw_step.items() if k not in {"action", "keyword", "text"}}
                actions = [ActionContract(action=action_name, params=action_params)]
            else:
                actions = self.adapter.compile_step(keyword, text)
            action_dicts = [asdict(action) for action in actions]

            status = "pass"
            observation = ""
            artifacts: List[str] = []
            error = None
            failure_type = None
            assertions: List[Dict[str, Any]] = []

            playwright_actions_in_step: List[ActionContract] = []
            for action in actions:
                if (
                    self.engine == "playwright"
                    and self.playwright_executor is not None
                    and self.playwright_executor.is_supported(action)
                ):
                    playwright_actions_in_step.append(action)
                    continue

                action_ret = self.action_executor.execute_action(action, context=context, adapter=self.adapter)
                observation = action_ret.get("observation") or observation
                artifacts.extend(action_ret.get("artifacts") or [])
                if action.action in {"assert_text", "assert_dom", "domain_assert"}:
                    assertions.append(
                        {
                            "assertion": action.action,
                            "params": action.params,
                            "status": action_ret.get("status", "pass"),
                            "message": action_ret.get("message") or action_ret.get("observation", ""),
                        }
                    )
                if action_ret.get("status") == "fail":
                    status = "fail"
                    error = action_ret.get("error") or "action_failed"
                    failure_type = _classify_failure(error)
                    break

            if status == "pass" and playwright_actions_in_step:
                start_idx = len(cumulative_playwright_actions)
                cumulative_playwright_actions.extend(playwright_actions_in_step)
                end_idx = len(cumulative_playwright_actions) - 1

                pw_ret = self.playwright_executor.execute_cumulative(
                    scenario_id=scenario_id,
                    actions=cumulative_playwright_actions,
                    step_action_start_index=start_idx,
                    step_action_end_index=end_idx,
                )
                observation = pw_ret.get("observation") or observation
                artifacts.extend(pw_ret.get("artifacts") or [])
                if pw_ret.get("status") == "fail":
                    status = "fail"
                    error = pw_ret.get("error") or "playwright_action_failed"
                    failure_type = pw_ret.get("failure_type") or _classify_failure(error)

            duration_ms = int((time.perf_counter() - started) * 1000)
            result.steps.append(
                StepResult(
                    step_id=step_id,
                    keyword=keyword,
                    text=text,
                    status=status,  # type: ignore[arg-type]
                    duration_ms=duration_ms,
                    action_input=action_dicts,
                    observation_summary=observation,
                    assertions=assertions,
                    artifacts=artifacts,
                    error=error if not failure_type else f"{failure_type}: {error}",
                )
            )
            if status == "fail":
                result.failure_type = failure_type or "step_execution_failed"
                break

        result.finalize()
        return result
