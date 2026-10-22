from __future__ import annotations

import time

from tests.fakes import create_task_intent


def test_stream_emits_partial_and_creates_task(client, fake_transcriber, fake_extractor):
    fake_extractor.results.append(create_task_intent(title="Streamed task"))

    with client.websocket_connect("/api/voice/stream") as websocket:
        ready = websocket.receive_json()
        assert ready["type"] == "ready"
        assert ready["sample_rate"] == 16000

        websocket.send_json({"type": "start", "sample_rate": 16000})
        websocket.send_bytes(b"\x00\x00" * 16000)
        time.sleep(1.6)

        partial = websocket.receive_json()
        assert partial["type"] == "partial"
        assert partial["text"] == fake_transcriber.text

        websocket.send_json({"type": "stop"})
        messages = []
        while True:
            message = websocket.receive_json()
            messages.append(message)
            if message["type"] in {"result", "error"}:
                break

    result = next(message for message in messages if message["type"] == "result")
    assert messages[-1]["type"] == "result"
    assert result["result"]["intent"] == "CREATE_TASK"
    assert result["result"]["note"]["raw_transcript"] == fake_transcriber.text
    assert "intent" not in result["result"]["note"]
    assert result["result"]["action"]["task"]["title"] == "Streamed task"

    notes = client.get("/api/notes").json()
    assert notes["total"] == 1
    assert notes["items"][0]["source"] == "voice"


def test_stream_rejects_wrong_sample_rate(client):
    with client.websocket_connect("/api/voice/stream") as websocket:
        assert websocket.receive_json()["type"] == "ready"
        websocket.send_json({"type": "start", "sample_rate": 48000})
        error = websocket.receive_json()

    assert error["type"] == "error"
    assert error["error"]["code"] == "validation_error"
