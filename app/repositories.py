from __future__ import annotations

import re
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.domain import Priority, Source, TaskStatus, new_id
from app.models import Note, Task, utcnow

_STOP_WORDS = {"a", "an", "the", "to", "for", "of", "my", "me", "please"}


def normalize_reference(text: str) -> str:
    text = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    tokens = [token for token in text.split() if token not in _STOP_WORDS]
    return " ".join(tokens)


class NoteRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, raw_transcript: str, source: Source) -> Note:
        note = Note(
            id=new_id("note"),
            raw_transcript=raw_transcript,
            source=source,
            created_at=utcnow(),
        )
        self.session.add(note)
        self.session.flush()
        return note

    def get(self, note_id: str, *, with_task: bool = False) -> Note | None:
        statement = select(Note).where(Note.id == note_id)
        if with_task:
            statement = statement.options(selectinload(Note.task))
        return self.session.scalar(statement)

    def list(
        self,
        *,
        source: Source | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        task_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Note], int]:
        conditions = []
        if source is not None:
            conditions.append(Note.source == source)
        if created_from is not None:
            conditions.append(Note.created_at >= created_from)
        if created_to is not None:
            conditions.append(Note.created_at <= created_to)
        if task_id is not None:
            conditions.append(Note.task_id == task_id)

        total = self.session.scalar(select(func.count()).select_from(Note).where(*conditions))
        statement = (
            select(Note)
            .where(*conditions)
            .order_by(Note.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.scalars(statement)), int(total or 0)

    def mark_failed(self, note_id: str, error: str) -> Note | None:
        note = self.session.get(Note, note_id)
        if note is None:
            return None
        note.processing_error = error
        self.session.commit()
        self.session.refresh(note)
        return note


class TaskRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        title: str,
        description: str | None,
        due_date: date | None,
        priority: Priority | None,
    ) -> Task:
        now = utcnow()
        task = Task(
            id=new_id("task"),
            title=title,
            description=description,
            due_date=due_date,
            priority=priority,
            status=TaskStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        self.session.add(task)
        self.session.flush()
        return task

    def get(self, task_id: str) -> Task | None:
        return self.session.get(Task, task_id)

    def list(
        self,
        *,
        status: TaskStatus | None = None,
        priority: Priority | None = None,
        due_from: date | None = None,
        due_to: date | None = None,
        query: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Task], int]:
        conditions = []
        if status is not None:
            conditions.append(Task.status == status)
        if priority is not None:
            conditions.append(Task.priority == priority)
        if due_from is not None:
            conditions.append(Task.due_date >= due_from)
        if due_to is not None:
            conditions.append(Task.due_date <= due_to)
        if query:
            conditions.append(Task.title.ilike(f"%{query}%"))

        total = self.session.scalar(select(func.count()).select_from(Task).where(*conditions))
        statement = (
            select(Task)
            .where(*conditions)
            .order_by(Task.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.scalars(statement)), int(total or 0)

    def update(self, task: Task, changes: dict) -> Task:
        for field, value in changes.items():
            setattr(task, field, value)
        task.updated_at = utcnow()
        self.session.add(task)
        self.session.flush()
        return task

    def delete(self, task: Task) -> None:
        self.session.delete(task)
        self.session.flush()

    def find_by_reference(self, reference: str) -> list[Task]:
        normalized_reference = normalize_reference(reference)
        if not normalized_reference:
            return []

        tasks = self.session.scalars(select(Task).where(Task.status != TaskStatus.CANCELLED))
        scored: list[tuple[int, Task]] = []
        reference_tokens = set(normalized_reference.split())

        for task in tasks:
            normalized_title = normalize_reference(task.title)
            if not normalized_title:
                continue

            if normalized_reference in normalized_title or normalized_title in normalized_reference:
                score = 100
            else:
                title_tokens = set(normalized_title.split())
                overlap = len(reference_tokens & title_tokens)
                score = int(100 * overlap / max(len(reference_tokens), 1))

            if score >= 50:
                scored.append((score, task))

        if not scored:
            return []

        scored.sort(key=lambda item: item[0], reverse=True)
        best_score = scored[0][0]
        return [task for score, task in scored if score == best_score]
