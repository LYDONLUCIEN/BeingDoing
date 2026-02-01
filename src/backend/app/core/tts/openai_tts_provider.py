"""
OpenAI TTS Provider实现
"""
from typing import Optional
from openai import AsyncOpenAI
from app.core.tts.base import BaseTTSProvider, TTSResponse, TTSError
from app.config.settings import settings


class OpenAITTSProvider(BaseTTSProvider):
    """OpenAI TTS Provider实现"""
    
    # 支持的声音类型
    SUPPORTED_VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
    
    def __init__(self, api_key: Optional[str] = None, **kwargs):
        """
        初始化OpenAI TTS Provider
        
        Args:
            api_key: OpenAI API密钥
            **kwargs: 其他配置
        """
        super().__init__(api_key, **kwargs)
        self.client = AsyncOpenAI(
            api_key=api_key or settings.OPENAI_TTS_API_KEY or settings.OPENAI_API_KEY or "",
            timeout=kwargs.get("timeout", 60.0),
            max_retries=kwargs.get("max_retries", 3)
        )
        self.default_voice = kwargs.get("default_voice", "alloy")
    
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
            voice: 声音类型，None则使用默认
            speed: 语速（0.25-4.0）
            **kwargs: 其他参数（如response_format等）
        
        Returns:
            TTS响应
        """
        try:
            # 验证语速
            if not 0.25 <= speed <= 4.0:
                raise ValueError("语速必须在0.25-4.0之间")
            
            # 使用默认声音
            if voice is None:
                voice = self.default_voice
            
            # 验证声音类型
            if voice not in self.SUPPORTED_VOICES:
                raise ValueError(f"不支持的声音类型: {voice}，支持的类型: {self.SUPPORTED_VOICES}")
            
            # 调用OpenAI TTS API
            response = await self.client.audio.speech.create(
                model="tts-1",  # 或 tts-1-hd（更高质量）
                voice=voice,
                input=text,
                speed=speed,
                **kwargs
            )
            
            # 读取音频数据
            audio_data = response.content
            
            return TTSResponse(
                audio_data=audio_data,
                format=kwargs.get("response_format", "mp3"),
                duration=None  # OpenAI API不返回时长
            )
        
        except Exception as e:
            raise TTSError(f"OpenAI TTS API调用失败: {str(e)}")
    
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
        response = await self.synthesize(text, voice, speed, **kwargs)
        
        # 保存到文件
        with open(output_path, "wb") as f:
            f.write(response.audio_data)
        
        return output_path
