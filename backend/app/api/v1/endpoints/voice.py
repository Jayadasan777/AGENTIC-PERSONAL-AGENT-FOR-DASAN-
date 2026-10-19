"""Voice Intelligence Endpoints: Local Speech-to-Text and Text-to-Speech.

Provides:
- POST /voice/transcribe — Upload audio file (WAV/MP3/WebM) and get text transcription.
- POST /voice/synthesize — Send text and receive synthesized WAV audio.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field

from backend.app.api.v1.dependencies.auth import get_current_user
from backend.app.models.user import User
from backend.app.voice.stt import SpeechToTextService, TranscriptionResult
from backend.app.voice.tts import TextToSpeechService

router = APIRouter(prefix="/voice", tags=["Voice Intelligence"])

_stt_service = SpeechToTextService(model_size="base")
_tts_service = TextToSpeechService(voice_model="en_US-lessac-medium")


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------


class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    voice: str | None = Field(default="en_US-lessac-medium", max_length=64)


class TranscriptionSegmentResponse(BaseModel):
    start_sec: float
    end_sec: float
    text: str


class TranscriptionResponse(BaseModel):
    text: str
    language: str
    duration_sec: float
    segments: list[TranscriptionSegmentResponse]
    confidence_score: float
    engine_used: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/transcribe",
    response_model=TranscriptionResponse,
    summary="Transcribe audio file to text using local speech recognition",
)
async def transcribe_audio(
    file: UploadFile = File(...),
    language: str | None = None,
    current_user: User = Depends(get_current_user),
) -> TranscriptionResponse:
    """Accept an audio recording and return high-accuracy text transcription."""
    MAX_AUDIO_SIZE = 25 * 1024 * 1024  # 25 MB limit
    content = await file.read(MAX_AUDIO_SIZE + 1)
    if len(content) > MAX_AUDIO_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Audio file exceeds 25MB limit",
        )

    result: TranscriptionResult = await _stt_service.transcribe(
        audio_bytes=content,
        language=language,
        filename_hint=file.filename or "recording.wav",
    )

    return TranscriptionResponse(
        text=result.text,
        language=result.language,
        duration_sec=result.duration_sec,
        segments=[
            TranscriptionSegmentResponse(
                start_sec=s.start_sec,
                end_sec=s.end_sec,
                text=s.text,
            )
            for s in result.segments
        ],
        confidence_score=result.confidence_score,
        engine_used=result.engine_used,
    )


@router.post(
    "/synthesize",
    summary="Synthesize text to audio speech using local Piper TTS",
    responses={
        200: {
            "content": {"audio/wav": {}},
            "description": "Synthesized WAV audio stream.",
        }
    },
)
async def synthesize_speech(
    payload: SynthesizeRequest,
    current_user: User = Depends(get_current_user),
) -> Response:
    """Convert text to natural speech and return as standard audio/wav binary."""
    result = await _tts_service.synthesize(payload.text)
    return Response(
        content=result.audio_bytes,
        media_type="audio/wav",
        headers={
            "Content-Disposition": 'inline; filename="synthesized_speech.wav"',
            "X-Audio-Duration": str(result.duration_sec),
            "X-Audio-Sample-Rate": str(result.sample_rate_hz),
            "X-TTS-Engine": result.engine_used,
        },
    )
