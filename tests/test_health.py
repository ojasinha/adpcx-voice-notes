from __future__ import annotations


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "Voice Notes API",
        "version": "0.1.0",
    }
