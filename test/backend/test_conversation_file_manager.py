"""
对话记录文件管理器测试
"""
import pytest
import json
import tempfile
import shutil
from pathlib import Path
from app.utils.conversation_file_manager import (
    ConversationFileManager,
    ConversationCategory
)


@pytest.fixture
def temp_dir():
    """创建临时目录"""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path)


@pytest.fixture
def file_manager(temp_dir):
    """创建文件管理器实例"""
    return ConversationFileManager(base_dir=str(temp_dir))


def test_add_message(file_manager):
    """测试添加消息"""
    session_id = "test_session_123"
    category = ConversationCategory.MAIN_FLOW
    
    message = file_manager.add_message(
        session_id=session_id,
        category=category,
        role="user",
        content="测试消息",
        context={"current_step": "values_exploration"}
    )
    
    assert message["id"] is not None
    assert message["role"] == "user"
    assert message["content"] == "测试消息"
    assert message["context"]["current_step"] == "values_exploration"


def test_get_messages(file_manager):
    """测试获取消息"""
    session_id = "test_session_123"
    category = ConversationCategory.MAIN_FLOW
    
    # 添加多条消息
    file_manager.add_message(session_id, category, "user", "消息1")
    file_manager.add_message(session_id, category, "assistant", "回复1")
    file_manager.add_message(session_id, category, "user", "消息2")
    
    # 获取消息
    messages = file_manager.get_messages(session_id, category)
    assert len(messages) == 3
    assert messages[0]["content"] == "消息1"
    assert messages[1]["content"] == "回复1"
    assert messages[2]["content"] == "消息2"


def test_get_messages_with_limit(file_manager):
    """测试限制返回数量"""
    session_id = "test_session_123"
    category = ConversationCategory.MAIN_FLOW
    
    # 添加5条消息
    for i in range(5):
        file_manager.add_message(session_id, category, "user", f"消息{i+1}")
    
    # 获取最后2条
    messages = file_manager.get_messages(session_id, category, limit=2)
    assert len(messages) == 2
    assert messages[0]["content"] == "消息4"
    assert messages[1]["content"] == "消息5"


def test_get_all_categories(file_manager):
    """测试获取所有分类的消息"""
    session_id = "test_session_123"
    
    # 在不同分类中添加消息
    file_manager.add_message(session_id, ConversationCategory.MAIN_FLOW, "user", "主流程消息")
    file_manager.add_message(session_id, ConversationCategory.GUIDANCE, "assistant", "引导消息")
    
    # 获取所有消息
    messages = file_manager.get_messages(session_id, category=None)
    assert len(messages) == 2


def test_get_conversation_history(file_manager):
    """测试获取完整对话历史"""
    session_id = "test_session_123"
    
    # 添加消息
    file_manager.add_message(session_id, ConversationCategory.MAIN_FLOW, "user", "消息1")
    file_manager.add_message(session_id, ConversationCategory.GUIDANCE, "assistant", "消息2")
    
    # 获取历史
    history = file_manager.get_conversation_history(session_id)
    assert "conversations" in history
    assert "main_flow" in history["conversations"]
    assert "guidance" in history["conversations"]


def test_delete_session(file_manager):
    """测试删除会话"""
    session_id = "test_session_123"
    
    # 添加消息
    file_manager.add_message(session_id, ConversationCategory.MAIN_FLOW, "user", "消息")
    
    # 删除会话
    file_manager.delete_session(session_id)
    
    # 验证已删除
    messages = file_manager.get_messages(session_id, ConversationCategory.MAIN_FLOW)
    assert len(messages) == 0


def test_file_structure(file_manager, temp_dir):
    """测试文件结构"""
    session_id = "test_session_123"
    
    # 添加消息
    file_manager.add_message(session_id, ConversationCategory.MAIN_FLOW, "user", "测试")
    
    # 验证文件结构
    file_path = temp_dir / session_id / "main_flow.json"
    assert file_path.exists()
    
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    assert data["session_id"] == session_id
    assert data["category"] == "main_flow"
    assert "messages" in data
    assert "metadata" in data
    assert len(data["messages"]) == 1
