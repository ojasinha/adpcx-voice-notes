from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query

from app.api.deps import IntentExtractorDep, SessionDep
from app.domain import Source
from app.errors import InvalidRequestError, NotFoundError
from app.repositories import NoteRepository
from app.schemas.common import Page
from app.schemas.notes import NoteCreate, NoteDetailOut, NoteOut, NoteProcessResponse
from app.services.pipeline import NotePipeline

router = APIRouter(prefix="/api/notes", tags=["notes"])


@router.post("", response_model=NoteProcessResponse, status_code=201)
def create_note(
    payload: NoteCreate,
    session: SessionDep,
    extractor: IntentExtractorDep,
) -> NoteProcessResponse:
    pipeline = NotePipeline(session, extractor)
    return pipeline.process(payload.text, Source.TEXT)


@router.get("", response_model=Page[NoteOut])
def list_notes(
    session: SessionDep,
    source: Source | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    task_id: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Page[NoteOut]:
    if created_from and created_to and created_from > created_to:
        raise InvalidRequestError("created_from must be on or before created_to")

    notes, total = NoteRepository(session).list(
        source=source,
        created_from=created_from,
        created_to=created_to,
        task_id=task_id,
        limit=limit,
        offset=offset,
    )
    return Page(
        items=[NoteOut.model_validate(note) for note in notes],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{note_id}", response_model=NoteDetailOut)
def get_note(note_id: str, session: SessionDep) -> NoteDetailOut:
    note = NoteRepository(session).get(note_id, with_task=True)
    if note is None:
        raise NotFoundError(f"Note {note_id!r} not found")
    return NoteDetailOut.model_validate(note)
