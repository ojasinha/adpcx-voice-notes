from __future__ import annotations

import asyncio
import contextlib
import io
import json
import logging
import tempfile
import wave
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.config import Settings
from app.domain import Source
from app.errors import (
    AppError,
    AudioProcessingError,
    InvalidRequestError,
    PayloadTooLargeError,
)
from app.schemas.notes import NoteProcessResponse
from app.services.intent import IntentExtractor
from app.services.pipeline import NotePipeline
from app.services.stt import Transcriber

logger = logging.getLogger(__name__)

PCM_SAMPLE_RATE = 16000
PCM_SAMPLE_WIDTH = 2
PARTIAL_CHUNK_SECONDS = 10
PARTIAL_INTERVAL_SECONDS = 1.25
MIN_PARTIAL_SECONDS = 0.5


@dataclass
class _StreamState:
    pcm: bytearray = field(default_factory=bytearray)
    committed_bytes: int = 0
    committed_text: str = ""
    last_partial: str = ""
    finished: bool = False


def _wav_bytes(pcm: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(PCM_SAMPLE_WIDTH)
        wav.setframerate(PCM_SAMPLE_RATE)
        wav.writeframes(pcm)
    return buffer.getvalue()


def _join_text(first: str, second: str) -> str:
    first = first.strip()
    second = second.strip()
    if not first:
        return second
    if not second:
        return first
    return f"{first} {second}"


def _transcribe_pcm(
    transcriber: Transcriber,
    pcm: bytes,
    *,
    beam_size: int | None = None,
) -> str:
    with tempfile.TemporaryDirectory(prefix="voice-stream-") as temp_dir:
        audio_path = Path(temp_dir) / "audio.wav"
        audio_path.write_bytes(_wav_bytes(pcm))
        return transcriber.transcribe(audio_path, beam_size=beam_size)


class VoiceStreamSession:
    def __init__(
        self,
        websocket: WebSocket,
        settings: Settings,
        transcriber: Transcriber,
        extractor: IntentExtractor,
        session_factory: Callable[[], Session],
    ) -> None:
        self.websocket = websocket
        self.settings = settings
        self.transcriber = transcriber
        self.extractor = extractor
        self.session_factory = session_factory
        self.state = _StreamState()
        self._partial_task: asyncio.Task[None] | None = None
        self._closed = False
        self._started = False

    async def run(self) -> None:
        await self.websocket.accept()
        try:
            await self._send(
                {
                    "type": "ready",
                    "sample_rate": PCM_SAMPLE_RATE,
                    "max_seconds": self.settings.max_stream_seconds,
                }
            )
            await self._receive_loop()
        except WebSocketDisconnect:
            pass
        except AppError as exc:
            await self._send_error(exc)
        except Exception:
            logger.exception("Unexpected voice stream failure")
            await self._send_error(
                AppError(
                    "An unexpected error occurred",
                    status_code=500,
                    code="internal_error",
                )
            )
        finally:
            self.state.finished = True
            await self._cancel_partial()
            await self._close()

    async def _receive_loop(self) -> None:
        while True:
            message = await self.websocket.receive()
            if message["type"] == "websocket.disconnect":
                return

            chunk = message.get("bytes")
            if chunk is not None:
                self._append_audio(chunk)
                if self._partial_task is None or self._partial_task.done():
                    self._partial_task = asyncio.create_task(self._partial_loop())
                continue

            text = message.get("text")
            if text is None:
                continue

            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise InvalidRequestError("Stream control messages must be JSON") from exc
            if not isinstance(payload, dict):
                raise InvalidRequestError("Stream control messages must be JSON objects")

            message_type = payload.get("type")
            if message_type == "start":
                self._handle_start(payload)
            elif message_type == "stop":
                await self._finish()
                return
            elif message_type == "cancel":
                await self._send({"type": "cancelled"})
                return
            else:
                raise InvalidRequestError(f"Unknown stream message type: {message_type!r}")

    def _handle_start(self, payload: dict[str, Any]) -> None:
        if self._started:
            raise InvalidRequestError("The stream has already been started")
        try:
            sample_rate = int(payload.get("sample_rate", PCM_SAMPLE_RATE))
        except (TypeError, ValueError) as exc:
            raise InvalidRequestError("sample_rate must be an integer") from exc
        if sample_rate != PCM_SAMPLE_RATE:
            raise InvalidRequestError(f"Streaming audio must use {PCM_SAMPLE_RATE} Hz PCM")
        self._started = True

    def _append_audio(self, chunk: bytes) -> None:
        if not chunk:
            return
        if len(chunk) % PCM_SAMPLE_WIDTH != 0:
            raise InvalidRequestError("PCM audio must contain complete 16-bit samples")
        max_bytes = self.settings.max_stream_seconds * PCM_SAMPLE_RATE * PCM_SAMPLE_WIDTH
        if len(self.state.pcm) + len(chunk) > max_bytes + PCM_SAMPLE_RATE * PCM_SAMPLE_WIDTH:
            raise PayloadTooLargeError(
                f"Streaming audio exceeds the {self.settings.max_stream_seconds}s limit"
            )
        self.state.pcm.extend(chunk)

    async def _partial_loop(self) -> None:
        while not self.state.finished:
            await asyncio.sleep(PARTIAL_INTERVAL_SECONDS)
            if self.state.finished:
                return
            try:
                await self._emit_partial()
            except asyncio.CancelledError:
                raise
            except AppError as exc:
                logger.debug("Live partial transcription failed: %s", exc.message)
            except Exception:
                logger.debug("Live partial transcription failed", exc_info=True)

    async def _emit_partial(self) -> None:
        chunk_bytes = PARTIAL_CHUNK_SECONDS * PCM_SAMPLE_RATE * PCM_SAMPLE_WIDTH
        while len(self.state.pcm) - self.state.committed_bytes >= chunk_bytes:
            start = self.state.committed_bytes
            end = start + chunk_bytes
            chunk = bytes(self.state.pcm[start:end])
            text = await asyncio.to_thread(_transcribe_pcm, self.transcriber, chunk, beam_size=1)
            self.state.committed_text = _join_text(self.state.committed_text, text)
            self.state.committed_bytes = end

        current = bytes(self.state.pcm[self.state.committed_bytes :])
        if len(current) < MIN_PARTIAL_SECONDS * PCM_SAMPLE_RATE * PCM_SAMPLE_WIDTH:
            return
        text = await asyncio.to_thread(_transcribe_pcm, self.transcriber, current, beam_size=1)
        combined = _join_text(self.state.committed_text, text)
        if not combined or combined == self.state.last_partial:
            return
        self.state.last_partial = combined
        await self._send(
            {
                "type": "partial",
                "text": combined,
                "seconds": round(len(self.state.pcm) / (PCM_SAMPLE_RATE * PCM_SAMPLE_WIDTH), 1),
            }
        )

    async def _finish(self) -> None:
        self.state.finished = True
        await self._cancel_partial()
        pcm = bytes(self.state.pcm)
        if not pcm:
            raise InvalidRequestError("No audio was received")

        await self._send(
            {
                "type": "status",
                "stage": "finalizing",
                "message": "Transcribing the final audio",
            }
        )
        text = await asyncio.to_thread(_transcribe_pcm, self.transcriber, pcm)
        if not text.strip():
            raise AudioProcessingError("No speech was detected in the recording")
        await self._send({"type": "final_transcript", "text": text})
        await self._send(
            {
                "type": "status",
                "stage": "extracting",
                "message": "Extracting the intent",
            }
        )
        result = await asyncio.to_thread(self._process, text)
        await self._send({"type": "result", "result": result.model_dump(mode="json")})

    def _process(self, text: str) -> NoteProcessResponse:
        session = self.session_factory()
        try:
            return NotePipeline(session, self.extractor).process(text, Source.VOICE)
        finally:
            session.close()

    async def _cancel_partial(self) -> None:
        task = self._partial_task
        self._partial_task = None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _send(self, payload: dict[str, Any]) -> None:
        if self._closed:
            return
        try:
            await self.websocket.send_json(payload)
        except (WebSocketDisconnect, RuntimeError):
            self._closed = True

    async def _send_error(self, exc: AppError) -> None:
        error: dict[str, Any] = {"code": exc.code, "message": exc.message}
        if exc.details is not None:
            error["details"] = exc.details
        payload: dict[str, Any] = {"type": "error", "error": error}
        payload.update(exc.extra)
        await self._send(payload)

    async def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with contextlib.suppress(RuntimeError):
            await self.websocket.close()
