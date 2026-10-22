from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import Settings
from app.services.intent import IntentExtractor
from app.services.stt import Transcriber


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_session(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def get_intent_extractor(request: Request) -> IntentExtractor:
    return request.app.state.intent_extractor


def get_transcriber(request: Request) -> Transcriber:
    return request.app.state.transcriber


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
SessionDep = Annotated[Session, Depends(get_session)]
IntentExtractorDep = Annotated[IntentExtractor, Depends(get_intent_extractor)]
TranscriberDep = Annotated[Transcriber, Depends(get_transcriber)]
