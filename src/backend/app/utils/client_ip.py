"""使用 ASGI 服务器校验后的客户端地址，不自行信任外部转发头。"""

from starlette.requests import Request


def get_client_ip(request: Request | None) -> str:
    """代理链只由 Uvicorn 的 trusted proxy 配置解析，应用不重复读取 XFF。"""
    return request.client.host if request is not None and request.client else ""
