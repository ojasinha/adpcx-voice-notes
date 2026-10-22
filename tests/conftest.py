from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_intent_extractor, get_transcriber
from app.config import Settings
from app.factory import create_app
from tests.fakes import FakeIntentExtractor, FakeTranscriber


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        llm_base_url="http://127.0.0.1:9/v1",
        llm_api_key="test-key",
        llm_model="test-model",
        whisper_model="tiny",
        whisper_device="cpu",
    )


@pytest.fixture
def fake_transcriber() -> FakeTranscriber:
    return FakeTranscriber()


@pytest.fixture
def fake_extractor() -> FakeIntentExtractor:
    return FakeIntentExtractor()


@pytest.fixture
def app(settings: Settings, fake_transcriber, fake_extractor):
    application = create_app(settings)
    application.state.transcriber = fake_transcriber
    application.state.intent_extractor = fake_extractor
    application.dependency_overrides[get_transcriber] = lambda: fake_transcriber
    application.dependency_overrides[get_intent_extractor] = lambda: fake_extractor
    yield application
    application.dependency_overrides.clear()
    application.state.engine.dispose()


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client
