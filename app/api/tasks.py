from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query, Response

from app.api.deps import SessionDep
from app.domain import Priority, TaskStatus
from app.errors import InvalidRequestError, NotFoundError
from app.repositories import TaskRepository
from app.schemas.common import Page
from app.schemas.tasks import TaskOut, TaskUpdate

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("", response_model=Page[TaskOut])
def list_tasks(
    session: SessionDep,
    status: TaskStatus | None = None,
    priority: Priority | None = None,
    due_from: date | None = None,
    due_to: date | None = None,
    q: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Page[TaskOut]:
    if due_from and due_to and due_from > due_to:
        raise InvalidRequestError("due_from must be on or before due_to")

    tasks, total = TaskRepository(session).list(
        status=status,
        priority=priority,
        due_from=due_from,
        due_to=due_to,
        query=q,
        limit=limit,
        offset=offset,
    )
    return Page(
        items=[TaskOut.model_validate(task) for task in tasks],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: str, session: SessionDep) -> TaskOut:
    task = TaskRepository(session).get(task_id)
    if task is None:
        raise NotFoundError(f"Task {task_id!r} not found")
    return TaskOut.model_validate(task)


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: str,
    payload: TaskUpdate,
    session: SessionDep,
) -> TaskOut:
    repository = TaskRepository(session)
    task = repository.get(task_id)
    if task is None:
        raise NotFoundError(f"Task {task_id!r} not found")

    repository.update(task, payload.model_dump(exclude_unset=True))
    session.commit()
    session.refresh(task)
    return TaskOut.model_validate(task)


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: str, session: SessionDep) -> Response:
    repository = TaskRepository(session)
    task = repository.get(task_id)
    if task is None:
        raise NotFoundError(f"Task {task_id!r} not found")

    repository.delete(task)
    session.commit()
    return Response(status_code=204)
