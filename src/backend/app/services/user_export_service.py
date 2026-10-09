"""
按用户全量导出服务（2026-10-06 admin 数据导出需求）

导出单位是「用户」而非 report：一个用户的探索旅程可能跨多个激活码 / 多个 report
（真实数据：rumination 在新 report、前四阶段对话在旧 report），按用户聚合才能
拿到完整数据（修复「rumination 之前的聊天记录看不到」问题）。

zip 内目录结构（每用户一个子目录）::

    index.json                                  # 用户 → 邮箱/类型/report 数 索引
    users/{user_id}/profile.json                # 注册邮箱/用户名/profile/工作履历/激活码列表/类型/备注
    users/{user_id}/reports/{report_id}/...     # 复用 BatchExportService 的全部产物
    users/{user_id}/reports/{report_id}/report_markdown.md   # 已生成的报告全文（缓存存在才有）
    _skipped.txt                                # 无任何数据的用户清单（存在才写）
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.models.database import AsyncSessionLocal
from app.services.batch_export_service import BatchExportService
from app.utils.report_registry import ReportRegistry
from app.utils.simple_activation_manager import SimpleActivationManager
from app.utils.survey_storage import load_basic_info_by_user

logger = logging.getLogger(__name__)

# 单次按用户导出的用户数硬上限（每人可能挂多个 report，防 zip 过大 / 请求超时）
MAX_EXPORT_USERS = 50


class UserExportService:
    """按用户聚合的全量导出：profile + 激活码 + 名下全部 report（含全部对话与报告）。"""

    def __init__(self) -> None:
        self.registry = ReportRegistry()
        self.batch_service = BatchExportService()

    # ------------------------------------------------------------------
    # 用户 → report 映射
    # ------------------------------------------------------------------

    def list_user_reports(self, user_id: str) -> List[dict]:
        """列出某用户名下全部 report 记录（按创建时间正序，旅程顺序）。"""
        uid = (user_id or "").strip()
        if not uid:
            return []
        records = [
            r
            for r in self.registry.list_reports()
            if (r.get("user_id") or "").strip() == uid
        ]
        records.sort(key=lambda r: (r.get("created_at") or ""))
        return records

    def count_reports_for_users(self) -> Dict[str, int]:
        """统计每个用户名下的 report 数（供索引与预览）。"""
        counts: Dict[str, int] = {}
        for r in self.registry.list_reports():
            uid = (r.get("user_id") or "").strip()
            if uid:
                counts[uid] = counts.get(uid, 0) + 1
        return counts

    # ------------------------------------------------------------------
    # 单用户导出
    # ------------------------------------------------------------------

    async def collect_user_export(
        self, user_id: str, dirname: Optional[str] = None
    ) -> Optional[List[Tuple[str, bytes]]]:
        """
        收集单个用户的全部导出文件。

        Returns:
            ``[(zip_inner_path, file_bytes), ...]``，路径带 ``users/{dirname}/`` 前缀
            （dirname 缺省时按「昵称+邮箱」生成，见 build_user_export_dirname）；
            用户不存在返回 None；用户存在但无任何数据返回空列表。
        """
        from app.core.database import UserDB

        uid = (user_id or "").strip()
        if not uid:
            return None

        async with AsyncSessionLocal() as db:
            user_db = UserDB(db)
            user = await user_db.get_user_by_id(uid)
            if not user:
                logger.warning("按用户导出：用户不存在，跳过: %s", uid)
                return None

            profile = await user_db.get_user_profile(uid)
            work_histories = await user_db.get_user_work_histories(uid)

            work_list: List[Dict[str, Any]] = []
            for wh in work_histories:
                projects = await user_db.get_work_history_projects(wh.id)
                work_list.append(
                    {
                        "company": wh.company,
                        "position": wh.position,
                        "start_date": str(wh.start_date) if wh.start_date else None,
                        "end_date": str(wh.end_date) if wh.end_date else None,
                        "evaluation": wh.evaluation,
                        "skills_used": wh.skills_used,
                        "projects": [
                            {
                                "name": p.name,
                                "description": p.description,
                                "role": p.role,
                                "achievements": p.achievements,
                            }
                            for p in projects
                        ],
                    }
                )

        # 激活码（JSON 文件存储，按 owner_user_id 关联）
        activations: List[Dict[str, Any]] = []
        for _code, rec in SimpleActivationManager().list_activations().items():
            if (rec.owner_user_id or "").strip() != uid:
                continue
            activations.append(
                {
                    "activation_code": rec.code,
                    "status": rec.status,
                    "code_type": getattr(rec, "code_type", None),
                    "package_type": getattr(rec, "package_type", None),
                    "is_sandbox": bool(getattr(rec, "is_sandbox", False)),
                    "created_at": rec.created_at,
                    "expires_at": rec.expires_at,
                    "claimed_at": rec.claimed_at,
                }
            )
        activations.sort(key=lambda a: (a.get("created_at") or ""))

        # 名下全部 report（跨激活码的完整旅程）
        report_records = self.list_user_reports(uid)

        profile_payload: Dict[str, Any] = {
            "user_id": uid,
            "email": user.email,
            "phone": user.phone,
            "username": user.username,
            "user_type": getattr(user, "user_type", None) or "real",
            "admin_note": getattr(user, "admin_note", None),
            "is_active": user.is_active,
            "membership_plan": getattr(user, "membership_plan", "none"),
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login_at": (
                user.last_login_at.isoformat() if user.last_login_at else None
            ),
            "profile": {
                "gender": profile.gender if profile else None,
                "age": profile.age if profile else None,
                "profile_completed": profile.profile_completed if profile else False,
                "survey_data": load_basic_info_by_user(uid) or {},
            },
            "work_histories": work_list,
            "activations": activations,
            "reports": [
                {
                    "report_id": r.get("report_id"),
                    "activation_code": r.get("activation_code"),
                    "status": r.get("status"),
                    "created_at": r.get("created_at"),
                    "updated_at": r.get("updated_at"),
                }
                for r in report_records
            ],
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }

        files: List[Tuple[str, bytes]] = []
        prefix = f"users/{dirname or build_user_export_dirname(user)}"
        files.append(
            (
                f"{prefix}/profile.json",
                _dumps(profile_payload),
            )
        )

        for r in report_records:
            rid = r.get("report_id") or ""
            if not rid:
                continue
            report_files = await self.batch_service.collect_report_export(report_id=rid)
            if report_files is None:
                continue
            for inner_path, data in report_files:
                files.append((f"{prefix}/reports/{rid}/{inner_path}", data))

        return files


def _dumps(payload: Any) -> bytes:
    import json

    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


# zip 目录名不允许的字符（Windows/macOS/Linux 交集 + 控制字符）
_DIRNAME_UNSAFE = re.compile(r'[\\\\/:*?"<>|\x00-\x1f]+')


def build_user_export_dirname(user) -> str:
    """导出 zip 内用户目录名：「昵称+邮箱」（2026-10-09 起，运营视角可读性优先）。

    - 昵称缺失退化为邮箱；邮箱缺失退化为手机号；皆无退化为 ``user-{id前8位}``
    - 非法文件名字符替换为 ``_``，去首尾空格/点，截断 80 字符
    """
    uid = getattr(user, "id", "") or ""
    name = (getattr(user, "username", None) or "").strip()
    contact = (getattr(user, "email", None) or "").strip() or (
        getattr(user, "phone", None) or ""
    ).strip()
    label = "+".join(p for p in (name, contact) if p)
    label = _DIRNAME_UNSAFE.sub("_", label).strip(" .")
    if not label:
        label = f"user-{uid[:8]}"
    return label[:80]
