from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass(slots=True)
class GherkinStep:
    keyword: str
    text: str
    line_no: int


@dataclass(slots=True)
class GherkinScenario:
    feature: str
    scenario: str
    steps: List[GherkinStep] = field(default_factory=list)
    scenario_id: Optional[str] = None


STEP_KEYWORDS = ("Given", "When", "Then", "And", "But")


def parse_feature_file(path: Path) -> GherkinScenario:
    raw_lines = path.read_text(encoding="utf-8").splitlines()
    feature_name = ""
    scenario_name = ""
    scenario_id: Optional[str] = None
    steps: List[GherkinStep] = []
    last_keyword = "Given"

    for idx, line in enumerate(raw_lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.lower().startswith("feature:"):
            feature_name = stripped.split(":", 1)[1].strip()
            continue

        if stripped.lower().startswith("scenario:"):
            scenario_name = stripped.split(":", 1)[1].strip()
            continue

        if stripped.lower().startswith("@id:"):
            scenario_id = stripped.split(":", 1)[1].strip()
            continue

        for keyword in STEP_KEYWORDS:
            prefix = f"{keyword} "
            if stripped.startswith(prefix):
                text = stripped[len(prefix) :].strip()
                normalized_keyword = keyword
                if keyword in {"And", "But"}:
                    normalized_keyword = last_keyword
                else:
                    last_keyword = keyword
                steps.append(GherkinStep(keyword=normalized_keyword, text=text, line_no=idx))
                break

    if not feature_name:
        raise ValueError(f"Gherkin 解析失败：缺少 Feature: {path}")
    if not scenario_name:
        raise ValueError(f"Gherkin 解析失败：缺少 Scenario: {path}")
    if not steps:
        raise ValueError(f"Gherkin 解析失败：未找到 Given/When/Then 步骤: {path}")

    return GherkinScenario(
        feature=feature_name,
        scenario=scenario_name,
        steps=steps,
        scenario_id=scenario_id,
    )
