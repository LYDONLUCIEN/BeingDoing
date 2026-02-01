"""
pytest配置文件
共享的测试fixtures
"""
import pytest
import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
backend_path = project_root / "src" / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))


@pytest.fixture(scope="session")
def test_env():
    """测试环境配置"""
    # 设置测试环境变量
    os.environ["APP_ENV"] = "test"
    os.environ["DEBUG"] = "True"
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test.db"
    os.environ["AUDIO_MODE"] = "False"
    yield
    # 清理
    if os.path.exists("test.db"):
        os.remove("test.db")
