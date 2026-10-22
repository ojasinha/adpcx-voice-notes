from __future__ import annotations

from datetime import date

from app.domain import Priority
from tests.fakes import create_task_intent


def create_task(client, fake_extractor, title: str, **intent_kwargs) -> dict:
    fake_extractor.results.append(create_task_intent(title=title, **intent_kwargs))
    response = client.post("/api/notes", json={"text": f"Create {title}"})
    assert response.status_code == 201
    return response.json()["action"]["task"]


def test_list_tasks_filters_and_paginates(client, fake_extractor):
    first = create_task(
        client,
        fake_extractor,
        "First task",
        priority=Priority.HIGH,
        due_date=date(2026, 1, 10),
    )
    second = create_task(
        client,
        fake_extractor,
        "Second task",
        priority=Priority.LOW,
        due_date=date(2026, 2, 10),
    )
    client.patch(f"/api/tasks/{second['id']}", json={"status": "IN_PROGRESS"})

    pending = client.get("/api/tasks?status=PENDING").json()
    assert pending["total"] == 1
    assert pending["items"][0]["id"] == first["id"]

    low = client.get("/api/tasks?priority=LOW").json()
    assert low["total"] == 1
    assert low["items"][0]["id"] == second["id"]

    february = client.get("/api/tasks?due_from=2026-02-01&due_to=2026-02-28").json()
    assert february["total"] == 1
    assert february["items"][0]["id"] == second["id"]

    page = client.get("/api/tasks?limit=1&offset=1").json()
    assert page["total"] == 2
    assert len(page["items"]) == 1


def test_list_tasks_rejects_inverted_date_range(client):
    response = client.get("/api/tasks?due_from=2026-02-01&due_to=2026-01-01")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_patch_task(client, fake_extractor):
    task = create_task(client, fake_extractor, "Patch me")

    response = client.patch(
        f"/api/tasks/{task['id']}",
        json={
            "title": "Updated title",
            "status": "IN_PROGRESS",
            "priority": "URGENT",
            "due_date": "2026-03-01",
            "description": "Updated description",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Updated title"
    assert body["status"] == "IN_PROGRESS"
    assert body["priority"] == "URGENT"
    assert body["due_date"] == "2026-03-01"
    assert body["description"] == "Updated description"


def test_patch_task_can_clear_optional_fields(client, fake_extractor):
    task = create_task(
        client,
        fake_extractor,
        "Clear me",
        due_date=date(2026, 3, 1),
        priority=Priority.HIGH,
    )

    response = client.patch(
        f"/api/tasks/{task['id']}",
        json={"due_date": None, "priority": None, "description": None},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["due_date"] is None
    assert body["priority"] is None
    assert body["description"] is None


def test_patch_task_rejects_empty_or_null_required_fields(client, fake_extractor):
    task = create_task(client, fake_extractor, "Validate me")

    empty = client.patch(f"/api/tasks/{task['id']}", json={})
    assert empty.status_code == 422

    null_title = client.patch(f"/api/tasks/{task['id']}", json={"title": None})
    assert null_title.status_code == 422

    blank_title = client.patch(f"/api/tasks/{task['id']}", json={"title": "   "})
    assert blank_title.status_code == 422

    null_status = client.patch(f"/api/tasks/{task['id']}", json={"status": None})
    assert null_status.status_code == 422


def test_delete_task_keeps_linked_note(client, fake_extractor):
    fake_extractor.results.append(create_task_intent(title="Delete me"))
    created = client.post("/api/notes", json={"text": "Create a task to delete"}).json()
    task_id = created["action"]["task"]["id"]
    note_id = created["note"]["id"]

    response = client.delete(f"/api/tasks/{task_id}")
    assert response.status_code == 204

    assert client.get(f"/api/tasks/{task_id}").status_code == 404

    note = client.get(f"/api/notes/{note_id}").json()
    assert note["task_id"] is None
    assert note["task"] is None


def test_unknown_task_returns_404(client):
    assert client.get("/api/tasks/task_missing").status_code == 404
    assert client.patch("/api/tasks/task_missing", json={"status": "COMPLETED"}).status_code == 404
    assert client.delete("/api/tasks/task_missing").status_code == 404
