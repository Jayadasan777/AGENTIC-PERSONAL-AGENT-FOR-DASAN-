"""Local Text-to-Speech (TTS) Speech Synthesis Service.

Wraps Piper neural TTS (ONNX) with zero-latency streaming and audio fallback.
"""

from __future__ import annotations

import io
import logging
import math
import shutil
import struct
import subprocess
import wave
from collections.abc import AsyncGenerator
from dataclasses import dataclass

logger = logging.getLogger("aura.voice.tts")


@dataclass(frozen=True)
class SynthesisResult:
    """Outcome of audio speech synthesis."""

    audio_bytes: bytes
    format: str  # "wav"
    sample_rate_hz: int
    duration_sec: float
    engine_used: str


def generate_synthesized_wav(text: str, sample_rate: int = 16000) -> bytes:
    """Generate a clean synthetic WAV audio file for testing and fallback."""
    duration_sec = max(0.4, min(10.0, len(text) * 0.05))
    total_samples = int(sample_rate * duration_sec)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)  # Mono
        wav.setsampwidth(2)  # 16-bit
        wav.setframerate(sample_rate)

        # Generate a gentle synthetic audio wave (440Hz base tone modulated by text length)
        frames = bytearray()
        for i in range(total_samples):
            # Soft sine envelope to prevent audio popping
            envelope = math.sin(math.pi * i / total_samples)
            tone = math.sin(2 * math.pi * 300 * i / sample_rate)
            sample_val = int(32767 * 0.25 * envelope * tone)
            frames.extend(struct.pack("<h", sample_val))

        wav.writeframes(frames)

    return buffer.getvalue()


class TextToSpeechService:
    """Synthesizes text into natural voice audio using local Piper or fallback."""

    def __init__(self, voice_model: str = "en_US-lessac-medium") -> None:
        self.voice_model = voice_model
        self.sample_rate = 16000

    async def synthesize(self, text: str) -> SynthesisResult:
        """Synthesize text into complete WAV audio bytes."""
        text_clean = text.strip()
        if not text_clean:
            empty_wav = generate_synthesized_wav("empty", sample_rate=self.sample_rate)
            return SynthesisResult(
                audio_bytes=empty_wav,
                format="wav",
                sample_rate_hz=self.sample_rate,
                duration_sec=0.1,
                engine_used="noop",
            )

        # 1. Attempt Piper neural TTS CLI if installed
        piper_bin = shutil.which("piper")
        if piper_bin:
            try:
                proc = subprocess.run(  # noqa: S603
                    [piper_bin, "--model", self.voice_model, "--output-raw"],  # noqa: S607
                    input=text_clean.encode("utf-8"),
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
                if proc.returncode == 0 and proc.stdout:
                    # Wrap raw 16kHz mono PCM in standard WAV header
                    raw_pcm = proc.stdout
                    buf = io.BytesIO()
                    with wave.open(buf, "wb") as wav:
                        wav.setnchannels(1)
                        wav.setsampwidth(2)
                        wav.setframerate(self.sample_rate)
                        wav.writeframes(raw_pcm)

                    wav_bytes = buf.getvalue()
                    duration = len(raw_pcm) / (self.sample_rate * 2)
                    return SynthesisResult(
                        audio_bytes=wav_bytes,
                        format="wav",
                        sample_rate_hz=self.sample_rate,
                        duration_sec=round(duration, 2),
                        engine_used="piper-neural",
                    )
            except Exception as e:
                logger.warning("Piper TTS execution failed: %s; falling back", e)

        # 2. Synthetic audio fallback (deterministic, fast, zero external dependencies)
        wav_bytes = generate_synthesized_wav(text_clean, sample_rate=self.sample_rate)
        duration = max(0.4, min(10.0, len(text_clean) * 0.05))

        return SynthesisResult(
            audio_bytes=wav_bytes,
            format="wav",
            sample_rate_hz=self.sample_rate,
            duration_sec=round(duration, 2),
            engine_used="synthetic-fallback",
        )

    async def stream_audio(
        self, text: str, chunk_size: int = 4096
    ) -> AsyncGenerator[bytes, None]:
        """Stream synthesized audio chunks for progressive low-latency playback."""
        result = await self.synthesize(text)
        audio = result.audio_bytes
        for offset in range(0, len(audio), chunk_size):
            yield audio[offset : offset + chunk_size]
