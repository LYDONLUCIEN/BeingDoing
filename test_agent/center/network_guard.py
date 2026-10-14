"""普通 API 回归禁用外部网络；仅保留事件循环使用的本机 Unix socket。"""

import socket

_original_connect = socket.socket.connect
_original_connect_ex = socket.socket.connect_ex


def connect(self, address):
    if self.family != socket.AF_UNIX:
        raise RuntimeError("测试中心禁止真实支付/邮件/OSS/LLM 网络调用，请替换外部边界")
    return _original_connect(self, address)


def connect_ex(self, address):
    if self.family != socket.AF_UNIX:
        raise RuntimeError("测试中心禁止外部网络")
    return _original_connect_ex(self, address)


socket.socket.connect = connect
socket.socket.connect_ex = connect_ex


def pytest_configure(config):
    # 按产品启动时的包入口导入，测试不要求产品改成延迟导出。
    import importlib
    from pathlib import Path

    if (Path.cwd() / "src/backend/app/api/v1/simple_chat/__init__.py").is_file():
        importlib.import_module("app.api.v1.simple_chat")
