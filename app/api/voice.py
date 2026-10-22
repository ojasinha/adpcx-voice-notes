from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, UploadFile, WebSocket

from app.api.deps import (
    IntentExtractorDep,
    SessionDep,
    SettingsDep,
    TranscriberDep,
)
from app.domain import Source
from app.errors import AudioProcessingError, InvalidRequestError, PayloadTooLargeError
from app.schemas.notes import NoteProcessResponse
from app.services.audio import transcribe_audio_bytes
from app.services.pipeline import NotePipeline
from app.services.streaming import VoiceStreamSession

router = APIRouter(prefix="/api/voice", tags=["voice"])

AudioFile = Annotated[UploadFile, File()]


@router.post("/transcribe", response_model=NoteProcessResponse, status_code=201)
def transcribe(
    file: AudioFile,
    settings: SettingsDep,
    transcriber: TranscriberDep,
    extractor: IntentExtractorDep,
    session: SessionDep,
) -> NoteProcessResponse:
    max_bytes = settings.max_audio_mb * 1024 * 1024
    data = file.file.read(max_bytes + 1)

    if not data:
        raise InvalidRequestError("Uploaded audio file is empty")
    if len(data) > max_bytes:
        raise PayloadTooLargeError(f"Audio file exceeds the {settings.max_audio_mb} MB limit")

    text = transcribe_audio_bytes(
        data,
        filename=file.filename or "audio",
        settings=settings,
        transcriber=transcriber,
    )
    if not text.strip():
        raise AudioProcessingError("No speech was detected in the uploaded audio")

    pipeline = NotePipeline(session, extractor)
    return pipeline.process(text, Source.VOICE)


@router.websocket("/stream")
async def stream_voice(websocket: WebSocket) -> None:
    app = websocket.app
    await VoiceStreamSession(
        websocket=websocket,
        settings=app.state.settings,
        transcriber=app.state.transcriber,
        extractor=app.state.intent_extractor,
        session_factory=app.state.session_factory,
    ).run()
