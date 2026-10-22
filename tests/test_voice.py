from __future__ import annotations

import io
import wave

from app.errors import AudioProcessingError
from tests.fakes import create_task_intent


def wav_bytes(duration_seconds: float = 0.1, sample_rate: int = 16_000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * int(sample_rate * duration_seconds))
    return buffer.getvalue()


def test_voice_transcription_runs_intent_pipeline(client, fake_transcriber, fake_extractor):
    fake_transcriber.text = "Remind me to review the PR tomorrow"
    fake_extractor.results.append(create_task_intent(title="Review the PR"))

    response = client.post(
        "/api/voice/transcribe",
        files={"file": ("sample.wav", wav_bytes(), "audio/wav")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["note"]["source"] == "voice"
    assert body["note"]["raw_transcript"] == "Remind me to review the PR tomorrow"
    assert body["intent"] == "CREATE_TASK"
    assert body["action"]["type"] == "task_created"
    assert len(fake_transcriber.calls) == 1


def test_voice_stt_failure_does_not_create_note(client, fake_transcriber):
    fake_transcriber.error = AudioProcessingError("model exploded")

    response = client.post(
        "/api/voice/transcribe",
        files={"file": ("sample.wav", wav_bytes(), "audio/wav")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "audio_processing_failed"
    assert client.get("/api/notes").json()["total"] == 0


def test_voice_blank_transcript_does_not_create_note(client, fake_transcriber):
    fake_transcriber.text = "   "

    response = client.post(
        "/api/voice/transcribe",
        files={"file": ("sample.wav", wav_bytes(), "audio/wav")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "audio_processing_failed"
    assert client.get("/api/notes").json()["total"] == 0


def test_voice_rejects_undecodable_audio(client):
    response = client.post(
        "/api/voice/transcribe",
        files={"file": ("bad.wav", b"this is not audio", "audio/wav")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "audio_processing_failed"


def test_voice_rejects_empty_upload(client):
    response = client.post(
        "/api/voice/transcribe",
        files={"file": ("empty.wav", b"", "audio/wav")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_voice_rejects_oversized_upload(client):
    client.app.state.settings.max_audio_mb = 1
    oversized = b"x" * (1024 * 1024 + 1)

    response = client.post(
        "/api/voice/transcribe",
        files={"file": ("big.wav", oversized, "audio/wav")},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


def test_voice_requires_file(client):
    response = client.post("/api/voice/transcribe")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
