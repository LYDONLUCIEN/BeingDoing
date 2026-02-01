"""
语音API（可选，AUDIO_MODE控制）
"""
from fastapi import APIRouter, HTTPException, Depends, status, UploadFile, File
from pydantic import BaseModel
from typing import Optional
from app.api.v1.auth import get_current_user
from app.config.audio_config import get_audio_config

router = APIRouter(prefix="/audio", tags=["语音"])


class SynthesizeRequest(BaseModel):
    """语音合成请求"""
    text: str
    voice: Optional[str] = "alloy"  # alloy, echo, fable, onyx, nova, shimmer
    speed: float = 1.0


class StandardResponse(BaseModel):
    """标准响应"""
    code: int = 200
    message: str = "success"
    data: dict


@router.post("/transcribe", response_model=StandardResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
    language: Optional[str] = None,
    current_user: Optional[dict] = Depends(get_current_user)
):
    """转录音频（ASR）"""
    # 检查音频模式
    audio_config = get_audio_config()
    if not audio_config.get("audio_mode", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="音频模式未启用"
        )
    
    try:
        from app.core.asr import get_default_asr_provider
        
        asr = get_default_asr_provider()
        if not asr:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="ASR服务不可用"
            )
        
        # 读取音频文件
        audio_data = await file.read()
        
        # 转录音频
        result = await asr.transcribe(audio_data, language=language)
        
        return StandardResponse(
            code=200,
            message="转录成功",
            data={
                "text": result.text,
                "language": result.language,
                "duration": result.duration
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"转录失败: {str(e)}"
        )


@router.post("/synthesize", response_model=StandardResponse)
async def synthesize_speech(
    request: SynthesizeRequest,
    current_user: Optional[dict] = Depends(get_current_user)
):
    """合成语音（TTS）"""
    # 检查音频模式
    audio_config = get_audio_config()
    if not audio_config.get("audio_mode", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="音频模式未启用"
        )
    
    try:
        from app.core.tts import get_default_tts_provider
        import base64
        
        tts = get_default_tts_provider()
        if not tts:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="TTS服务不可用"
            )
        
        # 合成语音
        result = await tts.synthesize(
            text=request.text,
            voice=request.voice,
            speed=request.speed
        )
        
        # 将音频数据编码为base64
        audio_base64 = base64.b64encode(result.audio_data).decode('utf-8')
        
        return StandardResponse(
            code=200,
            message="合成成功",
            data={
                "audio_data": audio_base64,
                "format": result.format,
                "duration": result.duration
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"合成失败: {str(e)}"
        )
