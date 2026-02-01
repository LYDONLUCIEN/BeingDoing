"""
ASR API基础接口
"""
from abc import ABC, abstractmethod
from typing import Optional, BinaryIO
from pydantic import BaseModel


class ASRResponse(BaseModel):
    """ASR响应模型"""
    text: str
    language: Optional[str] = None
    duration: Optional[float] = None  # 音频时长（秒）


class ASRError(Exception):
    """ASR相关错误"""
    pass


class BaseASRProvider(ABC):
    """ASR Provider基础类"""
    
    def __init__(self, api_key: Optional[str] = None, **kwargs):
        """
        初始化ASR Provider
        
        Args:
            api_key: API密钥
            **kwargs: 其他配置参数
        """
        self.api_key = api_key
        self.config = kwargs
    
    @abstractmethod
    async def transcribe(
        self,
        audio_file: BinaryIO,
        language: Optional[str] = None,
        **kwargs
    ) -> ASRResponse:
        """
        转录音频文件
        
        Args:
            audio_file: 音频文件（二进制流）
            language: 语言代码（如 zh, en），None表示自动检测
            **kwargs: 其他参数
        
        Returns:
            ASR响应
        """
        pass
    
    @abstractmethod
    async def transcribe_file(
        self,
        file_path: str,
        language: Optional[str] = None,
        **kwargs
    ) -> ASRResponse:
        """
        转录音频文件（从文件路径）
        
        Args:
            file_path: 音频文件路径
            language: 语言代码
            **kwargs: 其他参数
        
        Returns:
            ASR响应
        """
        pass
