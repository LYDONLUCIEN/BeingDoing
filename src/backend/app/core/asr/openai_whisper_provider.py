"""
OpenAI Whisper ASR Provider实现
"""
from typing import Optional, BinaryIO
from openai import AsyncOpenAI
from app.core.asr.base import BaseASRProvider, ASRResponse, ASRError
from app.config.settings import settings


class OpenAIWhisperProvider(BaseASRProvider):
    """OpenAI Whisper Provider实现"""
    
    def __init__(self, api_key: Optional[str] = None, **kwargs):
        """
        初始化OpenAI Whisper Provider
        
        Args:
            api_key: OpenAI API密钥
            **kwargs: 其他配置
        """
        super().__init__(api_key, **kwargs)
        self.client = AsyncOpenAI(
            api_key=api_key or settings.OPENAI_WHISPER_API_KEY or settings.OPENAI_API_KEY or "",
            timeout=kwargs.get("timeout", 60.0),
            max_retries=kwargs.get("max_retries", 3)
        )
    
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
            **kwargs: 其他参数（如response_format, temperature等）
        
        Returns:
            ASR响应
        """
        try:
            # 调用OpenAI Whisper API
            response = await self.client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language=language,
                **kwargs
            )
            
            return ASRResponse(
                text=response.text,
                language=language or response.language if hasattr(response, 'language') else None,
                duration=None  # OpenAI API不返回时长
            )
        
        except Exception as e:
            raise ASRError(f"OpenAI Whisper API调用失败: {str(e)}")
    
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
        with open(file_path, "rb") as f:
            return await self.transcribe(f, language, **kwargs)
