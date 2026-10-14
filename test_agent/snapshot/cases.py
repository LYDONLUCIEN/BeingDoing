"""真实脱敏副本的默认兼容性套件；不使用 create_all 或空库替代旧数据。"""

import json
import os
import sqlite3
from pathlib import Path

import pytest


def root():
    work = Path(os.environ["BD_SNAPSHOT_WORKSPACE"]).resolve()
    assert work == Path.cwd().resolve() and (work / ".snapshot-workspace.json").is_file()
    return work


def test_migrated_database_supports_current_model_reads():
    from test_agent.snapshot.runtime import database_state
    from test_agent.snapshot.sanitize import quote

    import app.models  # noqa: F401
    from app.models.database import Base

    database_state(root() / "app.db")
    with sqlite3.connect((root() / "app.db").as_uri() + "?mode=ro", uri=True) as db:
        # 即使表为空也验证所有当前模型字段存在；不让产品启动时补字段掩盖迁移缺失。
        for table in Base.metadata.sorted_tables:
            columns = ",".join(quote(column.name) for column in table.columns)
            db.execute(f"SELECT {columns} FROM {quote(table.name)} LIMIT 1").fetchall()
        assert (
            db.execute("SELECT count(*) FROM users").fetchone()[0] > 0
        ), "基准没有用户，不能证明存量兼容"


def test_stored_chat_and_report_text_remains_readable():
    from app.utils.report_registry import ReportRegistry, compute_explore_resume
    from app.utils.simple_activation_manager import SimpleActivationManager

    simple = root() / "data/simple"
    assert (simple / "activations.json").is_file(), "缺少业务激活索引"
    activations = json.loads((simple / "activations.json").read_text())
    manager = SimpleActivationManager(base_dir=str(simple))
    for code in activations:
        assert manager.get_activation(code) is not None, "现行产品无法读取历史激活记录"
    registry = ReportRegistry(base_dir=str(simple))
    records = list((simple / "reports").glob("*/record.json"))
    assert records, "没有报告记录；本套件不能证明报告存量兼容"
    for path in records:
        record = registry.get_report_by_id(path.parent.name)
        assert record is not None, "现行产品无法读取历史报告"
        state = compute_explore_resume(record)
        assert state["resume_phase"] in {
            "values",
            "strengths",
            "interests",
            "purpose",
            "rumination",
        }
    for path in simple.rglob("*.json"):
        value = json.loads(path.read_text())
        assert isinstance(value, (dict, list)), "历史业务文件结构错误"


@pytest.mark.asyncio
async def test_existing_account_api_reads_imported_user_with_normal_authentication():
    import httpx

    from app.main import app
    from app.services.auth_service import AuthService

    with sqlite3.connect(root() / "app.db") as db:
        row = db.execute(
            "SELECT id,email FROM users WHERE is_active=1 AND deleted_at IS NULL LIMIT 1"
        ).fetchone()
    assert row is not None, "无可用于登录读取验证的有效账户"
    token = AuthService.create_access_token({"sub": row[0]})
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://snapshot.invalid"
    ) as client:
        response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, "现行用户接口无法读取导入账户"
    payload = response.json()
    assert payload.get("data", payload).get("user_id") == row[0]
