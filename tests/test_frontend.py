from __future__ import annotations


def test_frontend_index(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Voice Notes" in response.text
    assert "/app.js" in response.text
    assert "/styles.css" in response.text


def test_frontend_assets(client):
    script = client.get("/app.js")
    worklet = client.get("/pcm-worklet.js")
    styles = client.get("/styles.css")
    icon = client.get("/favicon.svg")

    assert script.status_code == 200
    assert "javascript" in script.headers["content-type"]
    assert "startRecording" in script.text
    assert worklet.status_code == 200
    assert "AudioWorkletProcessor" in worklet.text
    assert styles.status_code == 200
    assert styles.headers["content-type"].startswith("text/css")
    assert "--accent" in styles.text
    assert icon.status_code == 200
    assert icon.headers["content-type"].startswith("image/svg+xml")


def test_docs_still_available(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
