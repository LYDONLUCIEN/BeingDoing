"""
引导策略配置
"""
from app.config.settings import settings


class GuideConfig:
    """引导配置类"""
    
    # 空闲超时时间（秒）
    IDLE_TIMEOUT: int = settings.GUIDE_IDLE_TIMEOUT
    
    # 安静模式超时时间（秒）
    QUIET_TIMEOUT: int = settings.GUIDE_QUIET_TIMEOUT
    
    # 回答过短阈值（字数）
    SHORT_ANSWER_THRESHOLD: int = settings.GUIDE_SHORT_ANSWER_THRESHOLD
    
    # 引导偏好
    PREFERENCE_NORMAL: str = "normal"
    PREFERENCE_QUIET: str = "quiet"
    
    @classmethod
    def get_timeout(cls, preference: str) -> int:
        """根据偏好获取超时时间"""
        if preference == cls.PREFERENCE_QUIET:
            return cls.QUIET_TIMEOUT
        return cls.IDLE_TIMEOUT
