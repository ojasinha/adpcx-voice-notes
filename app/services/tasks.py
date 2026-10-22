from __future__ import annotations

from app.errors import ConflictError, NotFoundError
from app.models import Task
from app.repositories import TaskRepository


def resolve_task(repository: TaskRepository, reference: str) -> Task:
    task = repository.get(reference)
    if task is not None:
        return task

    candidates = repository.find_by_reference(reference)
    if not candidates:
        raise NotFoundError(f"No task matched {reference!r}")
    if len(candidates) > 1:
        raise ConflictError(
            f"Multiple tasks matched {reference!r}; be more specific",
            details={
                "candidates": [
                    {"id": task.id, "title": task.title, "status": task.status.value}
                    for task in candidates
                ]
            },
        )
    return candidates[0]
