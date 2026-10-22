from __future__ import annotations

from typing import Any


class AppError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        code: str = "bad_request",
        details: Any = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details
        self.extra = extra or {}


class InvalidRequestError(AppError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, status_code=422, code="validation_error", **kwargs)


class PayloadTooLargeError(AppError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, status_code=413, code="payload_too_large", **kwargs)


class NotFoundError(AppError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, status_code=404, code="not_found", **kwargs)


class ConflictError(AppError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, status_code=409, code="conflict", **kwargs)


class AudioProcessingError(AppError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, status_code=422, code="audio_processing_failed", **kwargs)


class IntentExtractionError(AppError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, status_code=422, code="intent_extraction_failed", **kwargs)


class LLMUnavailableError(AppError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, status_code=503, code="llm_unavailable", **kwargs)
