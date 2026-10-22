from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain import Intent, Source
from app.schemas.tasks import TaskOut


class NoteCreate(BaseModel):
    text: str = Field(min_length=1, max_length=10_000)

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text must not be blank")
        return value


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    raw_transcript: str
    created_at: datetime
    source: Source
    task_id: str | None = None
    intent: Intent | None = None
    processing_error: str | None = None


class NoteDetailOut(NoteOut):
    task: TaskOut | None = None


class ActionOut(BaseModel):
    type: Literal["task_created", "task_updated", "tasks_listed", "note_saved"]
    task: TaskOut | None = None
    tasks: list[TaskOut] | None = None
    total: int | None = None


class NoteProcessResponse(BaseModel):
    note: NoteOut
    intent: Intent
    action: ActionOut
