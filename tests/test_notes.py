from __future__ import annotations

from datetime import date

from app.domain import Priority, TaskStatus
from app.errors import IntentExtractionError
from tests.fakes import (
    create_task_intent,
    general_note_intent,
    query_intent,
    update_status_intent,
)


def test_text_note_creates_task_and_links_note(client, fake_extractor):
    fake_extractor.results.append(
        create_task_intent(
            title="Review the PR",
            due_date=date(2026, 10, 23),
            priority=Priority.HIGH,
        )
    )

    response = client.post(
        "/api/notes",
        json={"text": "Remind me to review the PR tomorrow, it's high priority"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["intent"] == "CREATE_TASK"
    assert body["action"]["type"] == "task_created"
    assert body["action"]["task"]["title"] == "Review the PR"
    assert body["action"]["task"]["status"] == "PENDING"
    assert body["action"]["task"]["priority"] == "HIGH"
    assert body["action"]["task"]["due_date"] == "2026-10-23"
    assert body["note"]["source"] == "text"
    assert body["note"]["task_id"] == body["action"]["task"]["id"]

    note = client.get(f"/api/notes/{body['note']['id']}").json()
    assert note["task"]["id"] == body["action"]["task"]["id"]

    task = client.get(f"/api/tasks/{body['action']['task']['id']}").json()
    assert task["title"] == "Review the PR"


def test_general_note_creates_no_task(client, fake_extractor):
    fake_extractor.results.append(general_note_intent())

    response = client.post(
        "/api/notes",
        json={"text": "Interesting idea: use Qdrant for semantic search"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["intent"] == "GENERAL_NOTE"
    assert body["action"] == {"type": "note_saved", "task": None, "tasks": None, "total": None}
    assert body["note"]["task_id"] is None
    assert client.get("/api/tasks").json()["total"] == 0


def test_update_task_status_by_title(client, fake_extractor):
    fake_extractor.results.append(create_task_intent(title="Fix login bug"))
    created = client.post("/api/notes", json={"text": "Create a login bug task"}).json()
    task_id = created["action"]["task"]["id"]

    fake_extractor.results.append(update_status_intent("login bug", status=TaskStatus.COMPLETED))
    response = client.post("/api/notes", json={"text": "Mark the login bug as done"})

    assert response.status_code == 201
    body = response.json()
    assert body["intent"] == "UPDATE_TASK_STATUS"
    assert body["action"]["type"] == "task_updated"
    assert body["action"]["task"]["id"] == task_id
    assert body["action"]["task"]["status"] == "COMPLETED"
    assert body["note"]["task_id"] == task_id


def test_update_unknown_task_returns_404_and_preserves_note(client, fake_extractor):
    fake_extractor.results.append(update_status_intent("missing task"))

    response = client.post("/api/notes", json={"text": "Mark the missing task as done"})

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert body["note"]["processing_error"] == "No task matched 'missing task'"

    saved = client.get(f"/api/notes/{body['note']['id']}").json()
    assert saved["processing_error"] is not None
    assert saved["intent"] is None


def test_update_ambiguous_task_returns_candidates(client, fake_extractor):
    for title in ("Fix login bug", "Fix signup bug"):
        fake_extractor.results.append(create_task_intent(title=title))
        client.post("/api/notes", json={"text": f"Create {title}"})

    fake_extractor.results.append(update_status_intent("bug"))
    response = client.post("/api/notes", json={"text": "Mark bug as done"})

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "conflict"
    assert len(body["error"]["details"]["candidates"]) == 2
    assert body["note"]["id"]


def test_query_tasks_returns_filtered_tasks(client, fake_extractor):
    fake_extractor.results.append(create_task_intent(title="Pending task", priority=Priority.HIGH))
    pending = client.post("/api/notes", json={"text": "Create pending task"}).json()
    fake_extractor.results.append(create_task_intent(title="Other task", priority=Priority.LOW))
    other = client.post("/api/notes", json={"text": "Create other task"}).json()

    client.patch(
        f"/api/tasks/{other['action']['task']['id']}",
        json={"status": "IN_PROGRESS"},
    )

    fake_extractor.results.append(query_intent(status=TaskStatus.PENDING))
    response = client.post("/api/notes", json={"text": "What tasks are pending?"})

    assert response.status_code == 201
    body = response.json()
    assert body["intent"] == "QUERY_TASKS"
    assert body["action"]["type"] == "tasks_listed"
    assert body["action"]["total"] == 1
    assert body["action"]["tasks"][0]["id"] == pending["action"]["task"]["id"]


def test_invalid_llm_output_returns_422_and_preserves_note(client, fake_extractor):
    fake_extractor.results.append(IntentExtractionError("LLM output failed validation"))

    response = client.post("/api/notes", json={"text": "Remind me to do something"})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "intent_extraction_failed"
    assert body["note"]["processing_error"] == "LLM output failed validation"

    saved = client.get(f"/api/notes/{body['note']['id']}").json()
    assert saved["intent"] is None
    assert saved["processing_error"] == "LLM output failed validation"


def test_list_notes_is_paginated_and_filterable(client, fake_extractor):
    for index in range(3):
        fake_extractor.results.append(general_note_intent())
        client.post("/api/notes", json={"text": f"Note {index}"})

    page = client.get("/api/notes?limit=2&offset=0").json()
    assert page["total"] == 3
    assert len(page["items"]) == 2

    text_notes = client.get("/api/notes?source=text").json()
    assert text_notes["total"] == 3

    voice_notes = client.get("/api/notes?source=voice").json()
    assert voice_notes["total"] == 0


def test_empty_note_text_is_rejected(client):
    for text in ("", "   "):
        response = client.post("/api/notes", json={"text": text})

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"


def test_unknown_note_returns_404(client):
    response = client.get("/api/notes/note_missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
