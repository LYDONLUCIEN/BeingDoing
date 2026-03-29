"""
FastAPI应用主入口
"""
import logging
import sys
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config.settings import settings
from app.api.middleware import AudioModeMiddleware, ErrorHandlerMiddleware
from app.api.v1 import auth, users, sessions, questions, answers, chat, search, formula, audio, export, debug, admin, analytics
from app.api.v1 import chat_optimized  # 新增：优化的对话API
from app.api.v1 import simple_auth, simple_chat  # 新增：简单模式激活与对话
from app.utils.simple_activation_manager import SimpleActivationManager

# ========== 日志配置 ==========
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format=LOG_FORMAT,
    stream=sys.stdout,
)
# 第三方库太吵，只保留 WARNING
for noisy in ("httpcore", "httpx", "urllib3", "asyncio", "watchfiles", "multipart"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

app = FastAPI(
    title="找到想做的事 - 智能引导系统",
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
        "https://career.soulhappylab.com",
        "http://career.soulhappylab.com",
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
                logging.getLogger(__name__).info("recycle bin auto-purge removed %d records", purged)
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


@app.get("/")
async def root():
    """根路径"""
    return {"message": "找到想做的事 - 智能引导系统 API", "version": "1.0.0"}


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "healthy"}


@app.get("/api/v1/config/architecture")
async def get_architecture_config():
    """获取架构配置"""
    from app.config.architecture import get_arch_config, ARCHITECTURE_MODE
    from app.config.audio_config import AudioConfig
    
    config = get_arch_config()
    return {
        "architecture_mode": ARCHITECTURE_MODE,
        "audio_mode": AudioConfig.is_audio_enabled(),
        "features": {
            "gateway": config.get("use_gateway", False),
            "vector_db": config.get("use_vector_db", False),
            "redis": config.get("use_redis", False),
            "celery": config.get("use_celery", False)
        }
    }


# 注册API路由
app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(sessions.router, prefix="/api/v1")
app.include_router(questions.router, prefix="/api/v1")
app.include_router(answers.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(chat_optimized.router, prefix="/api/v1")  # 新增：优化的对话API路由（使用 /api/v1/chat-optimized 前缀）
app.include_router(simple_auth.router, prefix="/api/v1")  # 简单模式认证（激活码）
app.include_router(simple_chat.router, prefix="/api/v1")  # 简单模式对话
app.include_router(debug.router, prefix="/api/v1")  # Debug 模式
app.include_router(search.router, prefix="/api/v1")
app.include_router(formula.router, prefix="/api/v1")
app.include_router(audio.router, prefix="/api/v1")
app.include_router(export.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")
