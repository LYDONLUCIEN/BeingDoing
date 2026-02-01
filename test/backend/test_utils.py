"""
工具函数测试
"""
import pytest
from app.utils.helpers import (
    generate_uuid,
    get_current_timestamp,
    format_response,
    format_error_response
)


def test_generate_uuid():
    """测试UUID生成"""
    uuid1 = generate_uuid()
    uuid2 = generate_uuid()
    
    assert uuid1 != uuid2
    assert len(uuid1) == 36  # UUID格式长度
    assert isinstance(uuid1, str)


def test_get_current_timestamp():
    """测试时间戳获取"""
    timestamp = get_current_timestamp()
    assert timestamp is not None
    assert hasattr(timestamp, "isoformat")


def test_format_response():
    """测试响应格式化"""
    data = {"key": "value"}
    response = format_response(data)
    
    assert response["code"] == 200
    assert response["message"] == "success"
    assert response["data"] == data
    assert "timestamp" in response


def test_format_error_response():
    """测试错误响应格式化"""
    response = format_error_response("Error message", code=400)
    
    assert response["code"] == 400
    assert response["message"] == "Error message"
    assert "timestamp" in response


def test_format_error_response_with_details():
    """测试带详情的错误响应"""
    details = {"field": "error detail"}
    response = format_error_response("Error", details=details)
    
    assert response["details"] == details
