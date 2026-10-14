"""开发验证入口必须保护已有业务数据和外部凭据。"""

from pathlib import Path


def test_development_verification_never_reuses_source_database_or_credentials(
    tmp_path, monkeypatch
):
    from test_agent.center.verify_backend import verify

    source = tmp_path / "source"
    tests = source / "test/backend"
    tests.mkdir(parents=True)
    (source / "app.db").write_text("原有本地数据不可覆盖")
    (source / ".env").write_text("API_KEY=not-for-tests")
    (source / "test_agent/center").mkdir(parents=True)
    implementation = Path(__file__).resolve().parents[2]
    (source / "test_agent/center/network_guard.py").write_bytes(
        (implementation / "test_agent/center/network_guard.py").read_bytes()
    )
    (tests / "test_isolated.py").write_text("""
import os
from pathlib import Path
def test_local_database():
    assert not Path('app.db').exists()
    assert not Path('.env').exists()
    assert 'BUSINESS_CREDENTIAL' not in os.environ
    Path('app.db').write_text('执行副本产生的数据')
""")
    monkeypatch.setenv("BUSINESS_CREDENTIAL", "private-value")
    result = verify(source, tmp_path / "evidence", ["test/backend"])
    assert result["status"] == "pass" and result["counts"]["tests"] == 1
    assert (source / "app.db").read_text() == "原有本地数据不可覆盖"
    assert (tmp_path / "evidence/results.xml").is_file()
