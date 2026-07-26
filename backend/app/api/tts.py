"""
TTS router
==========
POST /tts — generates audio and streams it back, with guaranteed temp file cleanup.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.models import TTSRequest
from voice.tts import generate_audio_bytes
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.post("/tts")
async def tts(request: TTSRequest):
    try:
        audio_bytes = await generate_audio_bytes(request.message, request.emotion)
        return Response(content=audio_bytes, media_type="audio/mpeg")
    except Exception as exc:
        logger.exception("TTS error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
