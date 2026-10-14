"""旧执行器未真正执行动作时不得输出通过。"""

import pytest
from test_agent.adapters.beingdoing.adapter import BeingDoingAdapter
from test_agent.core.bdd.executor import BddExecutor


@pytest.mark.parametrize("engine", ["local", "playwright"])
@pytest.mark.parametrize(
    "steps",
    [
        [],
        [{"keyword": "Then", "text": "页面应包含“根本不存在的文字”"}],
        [{"raw": {"action": "domain_assert", "name": "no_repeat_question"}}],
        [{"raw": {"action": "domain_action", "name": "ensure_login"}}],
    ],
)
def test_unexecuted_scenario_cannot_pass(engine, steps):
    result = BddExecutor(BeingDoingAdapter(), engine=engine).run("unexecuted", steps)
    assert result.status == "fail"
    assert result.failure_type


def test_ai_judge_does_not_infer_success_from_two_user_messages():
    from test_agent.core.ai_user.judge import L4Judge
    from test_agent.core.ai_user.task_spec import TaskSpec

    result = L4Judge().evaluate(
        TaskSpec("task", "回答目标问题"),
        [{"action": "chat_send", "status": "pass"}, {"action": "chat_send", "status": "pass"}],
        {"phase": "talents"},
    )
    assert result["status"] not in {"passed", "passed_with_risk"}


def test_replay_requires_explicit_user_input(tmp_path):
    import json
    import subprocess
    import sys
    from pathlib import Path

    scenario = tmp_path / "scenario.json"
    scenario.write_text(
        json.dumps(
            {
                "data": {"fixture_report_dir": "/tmp/fixture", "thread_id": "one"},
                "assertions": {"expected_hint": "这只是期待的回答"},
            }
        )
    )
    command = [
        sys.executable,
        str(Path(__file__).resolve().parents[2] / "test_agent/l2/run_scenario.py"),
        "--scenario",
        str(scenario),
        "--dry-run",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode != 0
    assert "输入" in result.stderr
