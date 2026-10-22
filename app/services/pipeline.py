from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.domain import Intent, Priority, Source
from app.errors import AppError, IntentExtractionError, LLMUnavailableError
from app.models import Note, utcnow
from app.repositories import NoteRepository, TaskRepository
from app.schemas.intents import LLMIntent
from app.schemas.notes import ActionOut, NoteProcessResponse, ProcessedNoteOut
from app.schemas.tasks import TaskOut
from app.services.intent import IntentExtractor
from app.services.tasks import resolve_task


class NotePipeline:
    def __init__(self, session: Session, extractor: IntentExtractor) -> None:
        self.session = session
        self.notes = NoteRepository(session)
        self.tasks = TaskRepository(session)
        self.extractor = extractor

    def process(self, text: str, source: Source) -> NoteProcessResponse:
        note = self.notes.create(text, source)
        self.session.commit()
        self.session.refresh(note)
        note_id = note.id

        try:
            extracted = self.extractor.extract(text, datetime.now(UTC))
        except (IntentExtractionError, LLMUnavailableError) as exc:
            self._attach_failed_note(exc, note_id)
            raise

        try:
            action = self._execute(note, extracted)
            note.intent = extracted.intent
            note.processing_error = None
            self.session.commit()
            self.session.refresh(note)
        except AppError as exc:
            self.session.rollback()
            self._attach_failed_note(exc, note_id)
            raise
        except Exception:
            self.session.rollback()
            self.notes.mark_failed(note_id, "Internal error while executing the intent")
            raise

        return NoteProcessResponse(
            note=ProcessedNoteOut.model_validate(note),
            intent=extracted.intent,
            action=action,
        )

    def _attach_failed_note(self, exc: AppError, note_id: str) -> None:
        failed_note = self.notes.mark_failed(note_id, exc.message)
        if failed_note is not None:
            exc.extra.setdefault("note", self._note_payload(failed_note))

    @staticmethod
    def _note_payload(note: Note) -> dict[str, Any]:
        return ProcessedNoteOut.model_validate(note).model_dump(mode="json")

    def _execute(self, note: Note, extracted: LLMIntent) -> ActionOut:
        if extracted.intent == Intent.CREATE_TASK:
            assert extracted.task is not None
            task = self.tasks.create(
                title=extracted.task.title,
                description=extracted.task.description,
                due_date=extracted.task.due_date,
                priority=extracted.task.priority or Priority.MEDIUM,
            )
            note.task_id = task.id
            return ActionOut(type="task_created", task=TaskOut.model_validate(task))

        if extracted.intent == Intent.UPDATE_TASK_STATUS:
            assert extracted.update is not None
            task = resolve_task(self.tasks, extracted.update.task_identifier)
            task.status = extracted.update.new_status
            task.updated_at = utcnow()
            note.task_id = task.id
            self.session.flush()
            return ActionOut(type="task_updated", task=TaskOut.model_validate(task))

        if extracted.intent == Intent.QUERY_TASKS:
            assert extracted.query is not None
            tasks, total = self.tasks.list(
                status=extracted.query.status,
                due_from=extracted.query.due_from,
                due_to=extracted.query.due_to,
                priority=extracted.query.priority,
                limit=100,
                offset=0,
            )
            return ActionOut(
                type="tasks_listed",
                tasks=[TaskOut.model_validate(task) for task in tasks],
                total=total,
            )

        return ActionOut(type="note_saved")
