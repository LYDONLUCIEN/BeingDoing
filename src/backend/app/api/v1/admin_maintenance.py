"""
Admin 维护模式切换 API

POST /api/v1/admin/maintenance { action, end_at?, reason? }
  - action: "on" | "off"
  - end_at / reason: 仅 on 时传，写入维护页 HTML

内部 subprocess 调 scripts/maintenance.sh，复用同一份逻辑。
成功 on 时自动 Set-Cookie: bypass_maintenance=1，让管理员立即绕过维护页验证。
"""

import os
import subprocess
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from app.api.v1.auth import get_current_user
from app.utils.super_admin import is_super_admin_user

router = APIRouter(prefix="/admin/maintenance", tags=["Admin-Maintenance"])

# 推导 REPO_ROOT:__file__ = src/backend/app/api/v1/admin_maintenance.py
# 向上 5 层 .dirname 才到仓库根(src/backend/app/api/v1/ → v1 → api → app → backend → src → 仓库根)
_HERE = os.path.dirname(os.path.abspath(__file__))
_CANDIDATES = [
    os.path.abspath(os.path.join(_HERE, "..", "..", "..", "..", "..")),  # 标准 source install
    "/home/gitclone/BeingDoing",  # 服务器部署路径兜底
]
REPO_ROOT = next((p for p in _CANDIDATES if os.path.isfile(os.path.join(p, "scripts", "maintenance.sh"))), _CANDIDATES[0])
MAINT_SCRIPT = os.path.join(REPO_ROOT, "scripts", "maintenance.sh")
BYPASS_COOKIE_NAME = os.getenv("BYPASS_COOKIE_NAME", "bypass_maintenance")
# 主访问域名（用于 cookie domain）
COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN", ".soulhappylab.com")


def _is_super_admin(user: Optional[dict]) -> bool:
    return is_super_admin_user(user)


class MaintenanceAction(BaseModel):
    action: str = Field(..., description="on | off")
    end_at: Optional[str] = Field(None, description="预计恢复时间，仅 on 用")
    reason: Optional[str] = Field(None, description="维护原因，仅 on 用")
    env: str = Field("prod", description="环境（dev/prod），默认 prod")


@router.post("")
async def set_maintenance_mode(
    payload: MaintenanceAction,
    response: Response,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """切换维护模式

    - on: 内部调用 `scripts/maintenance.sh on --env ... --end ... --reason ...`
    - off: 内部调用 `scripts/maintenance.sh off --env ...`
    - on 成功后设置 bypass cookie，管理员立即绕过维护页验证

    Returns:
        { ok, action, env, message }
    """
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")

    if payload.action not in ("on", "off"):
        raise HTTPException(status_code=400, detail="action 必须是 on 或 off")

    if not os.path.isfile(MAINT_SCRIPT):
        raise HTTPException(status_code=500, detail=f"脚本不存在: {MAINT_SCRIPT}")

    cmd = ["bash", MAINT_SCRIPT, payload.action, "--env", payload.env]
    if payload.action == "on":
        if payload.end_at:
            cmd += ["--end", payload.end_at]
        if payload.reason:
            cmd += ["--reason", payload.reason]

    try:
        # 同步执行（脚本里有 nginx reload，通常 < 2s）
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
            cwd=REPO_ROOT,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="maintenance.sh 超时")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"执行失败: {e}")

    if result.returncode != 0:
        # 脚本失败（权限、nginx reload 失败等）
        detail = result.stderr.strip() or result.stdout.strip() or "未知错误"
        raise HTTPException(status_code=500, detail=f"脚本失败: {detail}")

    # on 成功后给管理员浏览器种 cookie
    if payload.action == "on":
        response.set_cookie(
            key=BYPASS_COOKIE_NAME,
            value="1",
            max_age=86400,  # 1 天
            path="/",
            domain=COOKIE_DOMAIN,
            httponly=False,  # 前端需要能读（虽然不必要）
            samesite="lax",
        )

    return {
        "code": 200,
        "message": "success",
        "data": {
            "ok": True,
            "action": payload.action,
            "env": payload.env,
            "stdout": result.stdout.strip(),
        },
    }


@router.get("/status")
async def get_maintenance_status(
    current_user: Optional[dict] = Depends(get_current_user),
):
    """查询当前维护模式状态（读 flag 文件是否存在）"""
    if not _is_super_admin(current_user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")

    flag_path = os.getenv(
        "MAINTENANCE_FLAG_PATH", "/www/sites/zhiyinapp/maintenance.flag"
    )
    is_on = os.path.isfile(flag_path)
    meta: Dict[str, Any] = {}
    if is_on:
        try:
            with open(flag_path, "r", encoding="utf-8") as f:
                meta["raw"] = f.read().strip()
        except Exception:
            pass

    return {
        "code": 200,
        "message": "success",
        "data": {"is_on": is_on, "flag_path": flag_path, "meta": meta},
    }
