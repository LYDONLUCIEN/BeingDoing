"""
FastAPI应用主入口
"""

import asyncio
import logging
import sys
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware import AudioModeMiddleware, ErrorHandlerMiddleware
from app.api.v1 import admin_bounces  # 新增：退信黑名单管理
from app.api.v1 import admin_notifications  # 新增：通知邮件群发
from app.api.v1 import site_notices  # 新增：站内公告（banner / 维护通知）
from app.api.v1 import admin_maintenance  # 新增：维护模式切换
from app.api.v1 import chat_optimized  # 新增：优化的对话API
from app.api.v1 import (  # 新增：简单模式激活与对话
    admin,
    analytics,
    answers,
    audio,
    auth,
    chat,
    debug,
    export,
    formula,
    questions,
    search,
    sessions,
    simple_auth,
    simple_chat,
    users,
)
from app.config.settings import settings
from app.utils.simple_activation_manager import SimpleActivationManager

# ========== 日志配置 ==========
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format=LOG_FORMAT,
    stream=sys.stdout,
)
# 第三方库太吵，只保留 WARNING
for noisy in (
    "httpcore",
    "httpx",
    "urllib3",
    "asyncio",
    "watchfiles",
    "multipart",
    "filelock",
    "aiosqlite",
    "sqlalchemy.engine",
    "sqlalchemy.pool",
    "sqlalchemy.dialects",
    "openai",
    "httpx._client",
):
    logging.getLogger(noisy).setLevel(logging.WARNING)

app = FastAPI(
    title="寻路 - 智能引导系统",
    description="一个沉浸式的智能引导系统，帮助用户找到真正想做的事",
    version="1.0.0",
    debug=settings.DEBUG,
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://47.96.75.69:3000",
        "http://60.205.194.159:3000",
        "https://career.soulhappylab.com",
        "http://career.soulhappylab.com",
        "https://xunlu.soulhappylab.com",
        "http://xunlu.soulhappylab.com",
        "https://admin.soulhappylab.com",
        "http://admin.soulhappylab.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 添加自定义中间件
app.add_middleware(ErrorHandlerMiddleware)
app.add_middleware(AudioModeMiddleware)

_recycle_cleanup_task: asyncio.Task | None = None


async def _recycle_cleanup_loop():
    """
    垃圾桶自动清理循环：
    每 12 小时执行一次，物理清理超过保留期（默认 30 天）的激活码数据。
    """
    while True:
        try:
            manager = SimpleActivationManager()
            purged = manager.purge_recycle_bin()
            if purged:
                logging.getLogger(__name__).info(
                    "recycle bin auto-purge removed %d records", purged
                )
        except Exception as e:
            logging.getLogger(__name__).exception("recycle bin auto-purge failed: %s", e)
        await asyncio.sleep(12 * 60 * 60)


@app.on_event("startup")
async def _start_background_tasks():
    global _recycle_cleanup_task
    if _recycle_cleanup_task is None or _recycle_cleanup_task.done():
        _recycle_cleanup_task = asyncio.create_task(_recycle_cleanup_loop())


@app.on_event("shutdown")
async def _stop_background_tasks():
    global _recycle_cleanup_task
    if _recycle_cleanup_task and not _recycle_cleanup_task.done():
        _recycle_cleanup_task.cancel()
        try:
            await _recycle_cleanup_task
        except asyncio.CancelledError:
            pass
    _recycle_cleanup_task = None


async def _run_profile_backfill_task():
    """启动时后台异步回填老用户 profile_completed,首次完成后写标记文件。"""
    try:
        from app.utils.profile_backfill import run_profile_backfill_if_needed

        await run_profile_backfill_if_needed()
    except Exception as e:
        logging.getLogger(__name__).warning("profile backfill failed: %s", e)


@app.on_event("startup")
async def _run_profile_backfill():
    """fire-and-forget 触发回填任务,不阻塞启动。"""
    try:
        asyncio.create_task(_run_profile_backfill_task())
    except Exception as e:
        logging.getLogger(__name__).warning("profile backfill schedule failed: %s", e)


async def _recover_notification_tasks_task():
    """启动时扫描 status='running' 的通知邮件任务，标记为 interrupted。"""
    try:
        from app.services.notification_service import NotificationService

        count = await NotificationService.recover_interrupted()
        if count:
            logging.getLogger(__name__).info("recovered %d interrupted notification tasks", count)
    except Exception as e:
        logging.getLogger(__name__).warning("notification recover failed: %s", e)


@app.on_event("startup")
async def _recover_notification_tasks():
    """启动时恢复中断的通知邮件群发任务（fire-and-forget）。"""
    try:
        asyncio.create_task(_recover_notification_tasks_task())
    except Exception as e:
        logging.getLogger(__name__).warning("notification recover schedule failed: %s", e)


async def _log_alembic_revision_task():
    """启动时打印当前 DB alembic revision，便于排查代码/DB 是否对齐。

    不阻断启动，失败只警告。
    """
    try:
        from sqlalchemy import create_engine as _ce, text as _text
        from app.models.database import database_url

        sync_url = str(database_url).replace("+aiosqlite", "").replace("+asyncpg", "")
        eng = _ce(sync_url)
        try:
            with eng.connect() as conn:
                # alembic_version 表可能不存在（首次部署），容错
                try:
                    row = conn.execute(
                        _text("SELECT version_num FROM alembic_version LIMIT 1")
                    ).fetchone()
                    rev = row[0] if row else "(empty)"
                except Exception as inner:
                    rev = f"(cannot read alembic_version: {type(inner).__name__})"
            logging.getLogger(__name__).info("DB alembic revision: %s", rev)
        finally:
            eng.dispose()
    except Exception as e:
        logging.getLogger(__name__).warning("cannot log alembic revision: %s", e)


@app.on_event("startup")
async def _log_alembic_revision():
    """启动时打印 alembic revision（fire-and-forget）。"""
    try:
        asyncio.create_task(_log_alembic_revision_task())
    except Exception as e:
        logging.getLogger(__name__).warning("alembic revision log schedule failed: %s", e)


# ─── 退信扫描定时任务（APScheduler） ───────────────────────
_bounce_scheduler: Any = None


def _start_bounce_scheduler() -> None:
    """启动 APScheduler，按 BOUNCE_SCAN_CRON 定时跑退信扫描

    - coalesce=True：错过多次只补跑一次
    - max_instances=1：不允许并发
    - misfire_grace_time=3600：服务重启后 1h 内还能补跑
    """
    global _bounce_scheduler
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        from app.services.bounce_scanner import BounceScanner

        sched = AsyncIOScheduler(timezone="Asia/Shanghai")
        sched.add_job(
            lambda: asyncio.create_task(BounceScanner.scan_once()),
            CronTrigger.from_crontab(settings.BOUNCE_SCAN_CRON),
            id="bounce_scan",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=3600,
        )
        sched.start()
        _bounce_scheduler = sched
        logging.getLogger(__name__).info(
            "bounce scheduler started, cron='%s'", settings.BOUNCE_SCAN_CRON
        )
    except Exception as e:
        # APScheduler 不可用不能阻断启动，只警告
        logging.getLogger(__name__).warning("start bounce scheduler failed: %s", e)


@app.on_event("startup")
async def _start_bounce_scan_scheduler():
    _start_bounce_scheduler()


@app.on_event("shutdown")
async def _stop_bounce_scan_scheduler():
    global _bounce_scheduler
    if _bounce_scheduler:
        try:
            _bounce_scheduler.shutdown(wait=False)
        except Exception:
            pass
        _bounce_scheduler = None


@app.get("/")
async def root():
    """根路径"""
    return {"message": "寻路 - 智能引导系统 API", "version": "1.0.0"}


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "healthy"}


@app.get("/api/v1/config/architecture")
async def get_architecture_config():
    """获取架构配置"""
    from app.config.architecture import ARCHITECTURE_MODE, get_arch_config
    from app.config.audio_config import AudioConfig

    config = get_arch_config()
    return {
        "architecture_mode": ARCHITECTURE_MODE,
        "audio_mode": AudioConfig.is_audio_enabled(),
        "features": {
            "gateway": config.get("use_gateway", False),
            "vector_db": config.get("use_vector_db", False),
            "redis": config.get("use_redis", False),
            "celery": config.get("use_celery", False),
        },
    }


# 注册API路由
app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(sessions.router, prefix="/api/v1")
app.include_router(questions.router, prefix="/api/v1")
app.include_router(answers.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(
    chat_optimized.router, prefix="/api/v1"
)  # 新增：优化的对话API路由（使用 /api/v1/chat-optimized 前缀）
app.include_router(simple_auth.router, prefix="/api/v1")  # 简单模式认证（激活码）
app.include_router(simple_chat.router, prefix="/api/v1")  # 简单模式对话
app.include_router(debug.router, prefix="/api/v1")  # Debug 模式
app.include_router(search.router, prefix="/api/v1")
app.include_router(formula.router, prefix="/api/v1")
app.include_router(audio.router, prefix="/api/v1")
app.include_router(export.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")
app.include_router(admin_notifications.router, prefix="/api/v1")  # 通知邮件群发
app.include_router(admin_bounces.router, prefix="/api/v1")  # 退信黑名单
app.include_router(site_notices.router, prefix="/api/v1")  # 站内公告（公开 + admin）
app.include_router(admin_maintenance.router, prefix="/api/v1")  # 维护模式切换（admin）
