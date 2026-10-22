from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api import health, notes, tasks, voice
from app.config import Settings, get_settings
from app.db import create_db_engine, create_session_factory, init_db
from app.errors import AppError
from app.services.intent import build_intent_extractor
from app.services.stt import FasterWhisperTranscriber

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level.upper())

    engine = create_db_engine(settings.database_url)
    init_db(engine)
    session_factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        engine.dispose()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Voice-driven note taking with validated intent extraction.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.transcriber = FasterWhisperTranscriber(settings)
    app.state.intent_extractor = build_intent_extractor(settings)

    app.include_router(health.router)
    app.include_router(notes.router)
    app.include_router(tasks.router)
    app.include_router(voice.router)

    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        error: dict[str, Any] = {"code": exc.code, "message": exc.message}
        if exc.details is not None:
            error["details"] = exc.details
        content: dict[str, Any] = {"error": error}
        content.update(exc.extra)
        return JSONResponse(status_code=exc.status_code, content=jsonable_encoder(content))

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {
                "loc": list(error.get("loc", [])),
                "msg": error.get("msg", "Invalid value"),
                "type": error.get("type", "value_error"),
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed",
                    "details": details,
                }
            },
        )

    @app.exception_handler(HTTPException)
    async def handle_http_exception(_request: Request, exc: HTTPException) -> JSONResponse:
        code = "not_found" if exc.status_code == 404 else "http_error"
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": code, "message": str(exc.detail)}},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "An unexpected error occurred",
                }
            },
        )

    return app
