from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from app.config import Settings
from app.errors import AudioProcessingError
from app.services.stt import Transcriber


def _safe_suffix(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if re.fullmatch(r"\.[a-z0-9]{1,5}", suffix):
        return suffix
    return ".bin"


def transcribe_audio_bytes(
    data: bytes,
    filename: str,
    settings: Settings,
    transcriber: Transcriber,
) -> str:
    with tempfile.TemporaryDirectory(prefix="voice-note-") as temp_dir:
        input_path = Path(temp_dir) / f"input{_safe_suffix(filename)}"
        wav_path = Path(temp_dir) / "audio.wav"
        input_path.write_bytes(data)

        command = [
            settings.ffmpeg_bin,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-i",
            str(input_path),
            "-vn",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(wav_path),
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=settings.ffmpeg_timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise AudioProcessingError("ffmpeg is not installed or not on PATH") from exc
        except subprocess.TimeoutExpired as exc:
            raise AudioProcessingError("Audio conversion timed out") from exc

        if result.returncode != 0 or not wav_path.exists():
            detail = [line for line in (result.stderr or "").strip().splitlines() if line]
            raise AudioProcessingError(
                "Could not decode the uploaded audio",
                details=detail[-3:],
            )

        return transcriber.transcribe(wav_path)
