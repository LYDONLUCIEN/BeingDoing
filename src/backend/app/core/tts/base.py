"""
TTS API基础接口
"""
from abc import ABC, abstractmethod
from typing import Optional, BinaryIO
from pydantic import BaseModel


class TTSResponse(BaseModel):
    """TTS响应模型"""
    audio_data: bytes
    format: str  # mp3, wav等
    duration: Optional[float] = None  # 音频时长（秒）


class TTSError(Exception):
    """TTS相关错误"""
    pass


class BaseTTSProvider(ABC):
    """TTS Provider基础类"""
    
    def __init__(self, api_key: Optional[str] = None, **kwargs):
        """
        初始化TTS Provider
        
        Args:
            api_key: API密钥
            **kwargs: 其他配置参数
        """
        self.api_key = api_key
        self.config = kwargs
    
    @abstractmethod
    async def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: float = 1.0,
        **kwargs
    ) -> TTSResponse:
        """
        合成语音
        
        Args:
            text: 要合成的文本
            voice: 声音类型（如 alloy, echo, fable等）
            speed: 语速（0.25-4.0）
            **kwargs: 其他参数
        
        Returns:
            TTS响应（包含音频数据）
        """
        pass
    
    @abstractmethod
    async def synthesize_to_file(
        self,
        text: str,
        output_path: str,
        voice: Optional[str] = None,
        speed: float = 1.0,
        **kwargs
    ) -> str:
        """
        合成语音并保存到文件
        
        Args:
            text: 要合成的文本
            output_path: 输出文件路径
            voice: 声音类型
            speed: 语速
            **kwargs: 其他参数
        
        Returns:
            输出文件路径
        """
        pass
