"""跨路由的访问校验；在读取文件、调用模型或修改数据前执行。"""

import re
from typing import Any

from fastapi import Depends, HTTPException

from app.api.v1.auth import get_current_user
from app.services.answer_service import AnswerService
from app.services.session_service import SessionService
from app.utils.simple_activation_manager import get_activation_with_manager
from app.utils.super_admin import is_super_admin_user


def require_super_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """内部运维接口只允许已登录的超级管理员。"""
    if not is_super_admin_user(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    return current_user


async def require_session_owner(session_id: str, current_user: dict) -> dict[str, Any]:
    """校验旧版数据库会话归属，同时拒绝可用于目录穿越的标识。"""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id):
        raise HTTPException(status_code=400, detail="无效的会话标识")
    session = await SessionService.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if not current_user or session.get("user_id") != current_user.get("user_id"):
        raise HTTPException(status_code=403, detail="无权访问此会话")
    return session


async def require_answer_owner(answer_id: str, current_user: dict) -> dict[str, Any]:
    """回答的访问权限继承所属会话，不以知道回答 ID 作为授权依据。"""
    answer = await AnswerService.get_answer(answer_id)
    if not answer:
        raise HTTPException(status_code=404, detail="回答不存在")
    await require_session_owner(answer["session_id"], current_user)
    return answer


async def require_analytics_owner(
    session_id: str, current_user: dict, activation_code: str | None = None
) -> None:
    """点赞/报告埋点只能引用自己的探索，兼容两种现有会话标识。"""
    if not activation_code:
        await require_session_owner(session_id, current_user)
        return
    manager, record = get_activation_with_manager(activation_code)
    if (
        not record
        or not (record.owner_user_id or record.owner_email)
        or not manager.is_owner(record, current_user)
    ):
        raise HTTPException(status_code=403, detail="无权访问此探索")
    # 四阶段传 activation_session_id，沉淀 v4 的现有客户端传激活码。
    if session_id not in {record.code, record.session_id, record.activation_session_id}:
        raise HTTPException(status_code=403, detail="会话不属于此探索")
