"""数据模型：TestItem / TestSuiteResult / AggregateReport"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TestItem:
    task_ids: List[str]
    description: str
    section: str
    category: str
    item_type: str  # automated | human_reviewed
    priority: str = ""  # P0 | P1 | P2 | ""
    status: str = "pending"  # pending | passed | failed | skipped
    test_file: Optional[str] = None
    evidence: Optional[str] = None


@dataclass
class TestRunDetail:
    file: str
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    fail_messages: List[str] = field(default_factory=list)


@dataclass
class TestSuiteResult:
    test_type: str  # backend | frontend | e2e
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    duration: float = 0.0
    details: List[TestRunDetail] = field(default_factory=list)
    raw_output: str = ""


@dataclass
class AggregateReport:
    timestamp: str = ""
    checklist_file: str = ""
    total_items: int = 0
    automated_passed: int = 0
    automated_failed: int = 0
    automated_skipped: int = 0
    human_reviewed_pending: int = 0
    suite_results: List[TestSuiteResult] = field(default_factory=list)
    items: List[TestItem] = field(default_factory=list)
