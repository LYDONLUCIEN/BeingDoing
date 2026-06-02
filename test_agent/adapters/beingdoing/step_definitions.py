from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Match, Optional, Pattern

from test_agent.core.contracts.action_contract import ActionContract


@dataclass(slots=True)
class StepDefinition:
    pattern: Pattern[str]
    handler_name: str


class BeingDoingStepDefinitions:
    """
    BeingDoing 业务语句映射器。

    只做“业务句子 -> 标准动作”转换，不直接执行浏览器动作。
    """

    def __init__(self) -> None:
        self._phase_paths = {
            "values": "/explore/chat/values",
            "rumination": "/explore/chat/rumination",
            "talents": "/explore/chat/talents",
            "interests": "/explore/chat/interests",
        }
        self._definitions: List[StepDefinition] = [
            StepDefinition(re.compile(r'^我已进入\s*"?(?P<phase>[\w-]+)"?\s*页面$'), "_goto_phase"),
            StepDefinition(re.compile(r'^我已进入\s*"?(?P<phase>[\w-]+)"?\s*阶段$'), "_goto_phase"),
            StepDefinition(re.compile(r'^我使用测试账号\s*"(?P<account>[^"]+)"\s*登录系统$'), "_ensure_login"),
            StepDefinition(
                re.compile(r'^我把第\s*(?P<row>\d+)\s*行假设修改为\s*"(?P<value>[^"]+)"$'),
                "_edit_hypothesis",
            ),
            StepDefinition(re.compile(r"^我点击表格外空白区域$"), "_blur_table"),
            StepDefinition(re.compile(r'^我回复\s*"(?P<text>[^"]+)"$'), "_chat_send"),
            StepDefinition(re.compile(r'^我输入\s*"(?P<text>[^"]+)"$'), "_chat_send"),
            StepDefinition(re.compile(r"^我点击发送$"), "_click_send"),
            StepDefinition(
                re.compile(r'^右侧应出现引导语\s*"(?P<text>[^"]+)"$'),
                "_assert_text",
            ),
            StepDefinition(
                re.compile(r'^我应该看到助手继续追问细节$'),
                "_assert_followup",
            ),
            StepDefinition(
                re.compile(r'^在后续\s*(?P<turns>\d+)\s*轮内，不应出现“(?P<text>[^”]+)”$'),
                "_assert_no_repeat",
            ),
            StepDefinition(
                re.compile(r'^当前阶段应保持在\s*"(?P<phase>[\w-]+)"\s*或进入下一步$'),
                "_assert_phase_progress",
            ),
            StepDefinition(re.compile(r"^当前有可编辑的假设表格$"), "_assert_table_exists"),
        ]

    def compile_step(self, keyword: str, step_text: str) -> List[ActionContract]:
        for item in self._definitions:
            match = item.pattern.match(step_text)
            if not match:
                continue
            handler = getattr(self, item.handler_name)
            return handler(keyword, match)
        return [ActionContract(action="unsupported_step", params={"step_text": step_text, "keyword": keyword})]

    def _goto_phase(self, _: str, m: Match[str]) -> List[ActionContract]:
        phase = m.group("phase").strip().lower()
        path = self._phase_paths.get(phase, f"/explore/chat/{phase}")
        return [ActionContract(action="goto", params={"url": path, "phase": phase})]

    def _ensure_login(self, _: str, m: Match[str]) -> List[ActionContract]:
        return [
            ActionContract(
                action="domain_action",
                params={"name": "ensure_login", "account": m.group("account").strip()},
            )
        ]

    def _edit_hypothesis(self, _: str, m: Match[str]) -> List[ActionContract]:
        return [
            ActionContract(
                action="domain_action",
                params={
                    "name": "table_edit",
                    "payload": {
                        "row": int(m.group("row")),
                        "field": "hypothesis",
                        "value": m.group("value").strip(),
                    },
                },
            )
        ]

    def _blur_table(self, _: str, __: Match[str]) -> List[ActionContract]:
        return [ActionContract(action="click", params={"selector": "body"})]

    def _chat_send(self, _: str, m: Match[str]) -> List[ActionContract]:
        text = m.group("text").strip()
        return [ActionContract(action="chat_send", params={"text": text})]

    def _click_send(self, _: str, __: Match[str]) -> List[ActionContract]:
        return [ActionContract(action="click", params={"selector": '[data-testid="chat-send"]'})]

    def _assert_text(self, _: str, m: Match[str]) -> List[ActionContract]:
        return [ActionContract(action="assert_text", params={"text": m.group("text").strip()})]

    def _assert_followup(self, _: str, __: Match[str]) -> List[ActionContract]:
        return [ActionContract(action="assert_text", params={"text": "追问"})]

    def _assert_no_repeat(self, _: str, m: Match[str]) -> List[ActionContract]:
        return [
            ActionContract(
                action="domain_assert",
                params={
                    "name": "no_repeat_question",
                    "turns": int(m.group("turns")),
                    "text": m.group("text").strip(),
                },
            )
        ]

    def _assert_phase_progress(self, _: str, m: Match[str]) -> List[ActionContract]:
        return [
            ActionContract(
                action="domain_assert",
                params={"name": "phase_in_or_next", "phase": m.group("phase").strip().lower()},
            )
        ]

    def _assert_table_exists(self, _: str, __: Match[str]) -> List[ActionContract]:
        return [ActionContract(action="assert_dom", params={"selector": ".rumination-table-widget table"})]
