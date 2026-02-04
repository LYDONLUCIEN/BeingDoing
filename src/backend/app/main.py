"""
FastAPI应用主入口
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config.settings import settings
from app.api.middleware import AudioModeMiddleware, ErrorHandlerMiddleware
from app.api.v1 import auth, users, sessions, questions, answers, chat, search, formula, audio, export

app = FastAPI(
    title="找到想做的事 - 智能引导系统",
    description="一个沉浸式的智能引导系统，帮助用户找到真正想做的事",
    version="1.0.0",
    debug=settings.DEBUG,
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # 前端开发服务器
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 添加自定义中间件
app.add_middleware(ErrorHandlerMiddleware)
app.add_middleware(AudioModeMiddleware)


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
app.include_router(search.router, prefix="/api/v1")
app.include_router(formula.router, prefix="/api/v1")
app.include_router(audio.router, prefix="/api/v1")
app.include_router(export.router, prefix="/api/v1")
