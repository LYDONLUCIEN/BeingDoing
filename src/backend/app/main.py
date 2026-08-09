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
from app.api.v1 import admin_model_config  # 新增：LLM 模型配置后台
from app.api.v1 import chat_optimized  # 新增：优化的对话API
from app.api.v1 import feedbacks  # 新增：用户反馈
from app.api.v1 import notifications  # 新增：站内信
from app.api.v1 import admin_feedbacks  # 新增：管理员反馈管理
from app.api.v1 import admin_payment  # 新增：支付管理（P1 折扣券 / P2a 订单退款）
from app.api.v1 import payment  # 新增：支付（P2a 用户侧下单/订单）
from app.api.v1 import payment_webhook  # 新增：支付回调（P2a，无登录鉴权）
from app.api.v1 import consultation  # 新增：报告解读咨询（P-D 用户侧）
from app.api.v1 import admin_consultations  # 新增：咨询管理（P-D admin）
from app.api.v1 import team_analysis  # 新增：团队分析（P-E）
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
    title="寻路·OpenLife - 智能引导系统",
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
        "https://openlife.soulhappylab.com",
        "http://openlife.soulhappylab.com",
        "https://admin.soulhappylab.com",
        "http://admin.soulhappylab.com",
        # 双域名并存：beyondego.me 与 soulhappylab.com 同时可用
        "https://career.beyondego.me",
        "http://career.beyondego.me",
        "https://openlife.beyondego.me",
        "http://openlife.beyondego.me",
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


_account_purge_task: asyncio.Task | None = None


async def _account_purge_loop():
    """
    账户注销到期清除循环：
    启动时先跑一次，之后每小时扫描一次 deleted_at 到期用户并物理清除。
    """
    while True:
        try:
            from app.services.account_deletion_service import AccountDeletionService

            purged = await AccountDeletionService.purge_expired_accounts()
            if purged:
                logging.getLogger(__name__).info(
                    "account deletion auto-purge removed %d accounts", purged
                )
        except Exception as e:
            logging.getLogger(__name__).exception("account deletion auto-purge failed: %s", e)
        await asyncio.sleep(3600)


@app.on_event("startup")
async def _start_background_tasks():
    global _recycle_cleanup_task, _account_purge_task
    if _recycle_cleanup_task is None or _recycle_cleanup_task.done():
        _recycle_cleanup_task = asyncio.create_task(_recycle_cleanup_loop())
    if _account_purge_task is None or _account_purge_task.done():
        _account_purge_task = asyncio.create_task(_account_purge_loop())


@app.on_event("shutdown")
async def _stop_background_tasks():
    global _recycle_cleanup_task, _account_purge_task
    for task in (_recycle_cleanup_task, _account_purge_task):
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    _recycle_cleanup_task = None
    _account_purge_task = None


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
        from app.services.feedback_orphan_cleanup import cleanup_orphan_attachments

        sched = AsyncIOScheduler(timezone="Asia/Shanghai")
        # 注意：AsyncIOScheduler 只会在事件循环里直接调度「协程函数」，
        # 普通 callable（如 lambda）会被丢到线程池执行，那里没有 running loop，
        # lambda 里再 asyncio.create_task 会 RuntimeError: no running event loop。
        # 因此这里一律直接传协程函数本身。
        sched.add_job(
            BounceScanner.scan_once,
            CronTrigger.from_crontab(settings.BOUNCE_SCAN_CRON),
            id="bounce_scan",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=3600,
        )
        # 反馈附件孤儿清理（每日 04:00，单独 cron）
        sched.add_job(
            cleanup_orphan_attachments,
            CronTrigger.from_crontab(settings.FEEDBACK_ORPHAN_CLEANUP_CRON),
            id="feedback_orphan_cleanup",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=3600,
        )
        # 支付超时关单（每 5 分钟，job 内部异常不得影响调度器）
        from apscheduler.triggers.interval import IntervalTrigger
        from app.services.payment_service import PaymentService

        async def _close_timeout_orders_safe() -> None:
            try:
                await PaymentService.close_timeout_orders()
            except Exception as job_err:
                logging.getLogger(__name__).error("close timeout orders job failed: %s", job_err)

        sched.add_job(
            _close_timeout_orders_safe,
            IntervalTrigger(minutes=5),
            id="payment_close_timeout_orders",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=600,
        )
        # 支付主动查单对账（notify 兜底，每 2 分钟；job 内部异常不得影响调度器）
        async def _reconcile_orders_safe() -> None:
            try:
                await PaymentService.reconcile_pending_orders()
            except Exception as job_err:
                logging.getLogger(__name__).error("reconcile orders job failed: %s", job_err)

        sched.add_job(
            _reconcile_orders_safe,
            IntervalTrigger(minutes=2),
            id="payment_reconcile_orders",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=600,
        )
        # 报告审核超时自动批复（ADR-0009，每 10 分钟扫描）
        from app.services.feedback_overdue_scan import scan_overdue_feedbacks
        from app.services.report_review_service import auto_approve_overdue
        from app.utils.report_review import REVIEW_SCAN_INTERVAL_MINUTES

        async def _auto_approve_reports_safe() -> None:
            try:
                await auto_approve_overdue()
            except Exception as job_err:
                logging.getLogger(__name__).error(
                    "report review auto approve job failed: %s", job_err
                )

        sched.add_job(
            _auto_approve_reports_safe,
            IntervalTrigger(minutes=REVIEW_SCAN_INTERVAL_MINUTES),
            id="report_review_auto_approve",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=600,
        )
        # 反馈超时扫描（每日，站内信提醒所有 super_admin，当天幂等）
        async def _feedback_overdue_scan_safe() -> None:
            try:
                await scan_overdue_feedbacks()
            except Exception as job_err:
                logging.getLogger(__name__).error(
                    "feedback overdue scan job failed: %s", job_err
                )

        sched.add_job(
            _feedback_overdue_scan_safe,
            CronTrigger.from_crontab(settings.FEEDBACK_OVERDUE_SCAN_CRON),
            id="feedback_overdue_scan",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=3600,
        )
        # 激活码过期扫描（ADR-0015，每日）：给首次过期的完整码激活人发
        # 「免费领取 7 天续期」邮件+站内信（每码一次，offered 标记幂等）
        from app.services.activation_expiry_scan import scan_expired_activations

        async def _activation_expiry_scan_safe() -> None:
            try:
                await scan_expired_activations()
            except Exception as job_err:
                logging.getLogger(__name__).error(
                    "activation expiry scan job failed: %s", job_err
                )

        sched.add_job(
            _activation_expiry_scan_safe,
            CronTrigger.from_crontab(settings.ACTIVATION_EXPIRY_SCAN_CRON),
            id="activation_expiry_scan",
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
        logging.getLogger(__name__).info(
            "feedback orphan cleanup scheduler started, cron='%s'",
            settings.FEEDBACK_ORPHAN_CLEANUP_CRON,
        )
        logging.getLogger(__name__).info(
            "report review auto approve scheduler started, interval=%dmin",
            REVIEW_SCAN_INTERVAL_MINUTES,
        )
        logging.getLogger(__name__).info(
            "feedback overdue scan scheduler started, cron='%s'",
            settings.FEEDBACK_OVERDUE_SCAN_CRON,
        )
        logging.getLogger(__name__).info(
            "activation expiry scan scheduler started, cron='%s'",
            settings.ACTIVATION_EXPIRY_SCAN_CRON,
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
    return {"message": "寻路·OpenLife - 智能引导系统 API", "version": "1.0.0"}


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
app.include_router(admin_model_config.router, prefix="/api/v1")  # LLM 模型配置（admin）
app.include_router(feedbacks.router, prefix="/api/v1")  # 用户反馈（提反馈、传截图）
app.include_router(notifications.router, prefix="/api/v1")  # 站内信（用户侧）
app.include_router(admin_feedbacks.router, prefix="/api/v1")  # 管理员反馈管理
app.include_router(admin_payment.router, prefix="/api/v1")  # 支付管理（P1 折扣券 / P2a 订单退款）
app.include_router(payment.router, prefix="/api/v1")  # 支付（P2a 用户侧下单/订单）
app.include_router(payment_webhook.router, prefix="/api/v1")  # 支付回调（P2a，无登录鉴权）
app.include_router(consultation.router, prefix="/api/v1")  # 报告解读咨询（P-D 用户侧）
app.include_router(admin_consultations.router, prefix="/api/v1")  # 咨询管理（P-D admin）
app.include_router(team_analysis.router, prefix="/api/v1")  # 团队分析（P-E）
