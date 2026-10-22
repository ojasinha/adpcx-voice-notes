from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain import Intent, Priority, TaskStatus


class CreateTaskFields(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    due_date: date | None = None
    priority: Priority | None = None

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class UpdateStatusFields(BaseModel):
    task_identifier: str = Field(min_length=1, max_length=200)
    new_status: TaskStatus

    @field_validator("task_identifier")
    @classmethod
    def identifier_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("task_identifier must not be blank")
        return value


class QueryFields(BaseModel):
    status: TaskStatus | None = None
    due_from: date | None = None
    due_to: date | None = None
    priority: Priority | None = None

    @model_validator(mode="after")
    def validate_date_range(self) -> QueryFields:
        if self.due_from and self.due_to and self.due_from > self.due_to:
            raise ValueError("due_from must be on or before due_to")
        return self


class LLMIntent(BaseModel):
    intent: Intent
    task: CreateTaskFields | None = None
    update: UpdateStatusFields | None = None
    query: QueryFields | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> LLMIntent:
        if self.intent == Intent.CREATE_TASK:
            if self.task is None:
                raise ValueError("CREATE_TASK requires task")
            if self.update is not None or self.query is not None:
                raise ValueError("CREATE_TASK must not include update or query")
        elif self.intent == Intent.UPDATE_TASK_STATUS:
            if self.update is None:
                raise ValueError("UPDATE_TASK_STATUS requires update")
            if self.task is not None or self.query is not None:
                raise ValueError("UPDATE_TASK_STATUS must not include task or query")
        elif self.intent == Intent.QUERY_TASKS:
            if self.task is not None or self.update is not None:
                raise ValueError("QUERY_TASKS must not include task or update")
            if self.query is None:
                self.query = QueryFields()
        else:
            if self.task is not None or self.update is not None or self.query is not None:
                raise ValueError("GENERAL_NOTE must not include task, update, or query")
        return self
