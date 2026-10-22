from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Protocol

from faster_whisper import WhisperModel

from app.config import Settings
from app.errors import AudioProcessingError


class Transcriber(Protocol):
    def transcribe(self, audio_path: Path, *, beam_size: int | None = None) -> str: ...


class FasterWhisperTranscriber:
    """Lazily loads faster-whisper so tests and health checks do not pay the cost."""

    def __init__(self, settings: Settings) -> None:
        self.model_name = settings.whisper_model
        self.device = settings.whisper_device
        self.compute_type = settings.whisper_compute_type
        self.language = settings.whisper_language
        self.beam_size = settings.whisper_beam_size
        self._model: WhisperModel | None = None
        self._load_lock = Lock()
        self._inference_lock = Lock()

    def _get_model(self) -> WhisperModel:
        if self._model is None:
            with self._load_lock:
                if self._model is None:
                    try:
                        self._model = WhisperModel(
                            self.model_name,
                            device=self.device,
                            compute_type=self.compute_type,
                        )
                    except Exception as exc:
                        raise AudioProcessingError(f"Failed to load the STT model: {exc}") from exc
        return self._model

    def transcribe(self, audio_path: Path, *, beam_size: int | None = None) -> str:
        model = self._get_model()
        language = None if self.language.lower() == "auto" else self.language

        try:
            with self._inference_lock:
                segments, _info = model.transcribe(
                    str(audio_path),
                    language=language,
                    beam_size=beam_size or self.beam_size,
                    vad_filter=True,
                )
                text = " ".join(segment.text.strip() for segment in segments).strip()
        except Exception as exc:
            raise AudioProcessingError(f"Transcription failed: {exc}") from exc

        if not text:
            raise AudioProcessingError("No speech was detected in the uploaded audio")

        return text
