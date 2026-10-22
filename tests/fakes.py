from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from app.domain import Intent, Priority, TaskStatus
from app.schemas.intents import CreateTaskFields, LLMIntent, QueryFields, UpdateStatusFields


class FakeTranscriber:
    def __init__(self, text: str = "Remind me to review the PR tomorrow") -> None:
        self.text = text
        self.error: Exception | None = None
        self.calls: list[Path] = []

    def transcribe(self, audio_path: Path) -> str:
        self.calls.append(audio_path)
        if self.error is not None:
            raise self.error
        return self.text


class FakeIntentExtractor:
    def __init__(self, *results: LLMIntent | Exception) -> None:
        self.results = list(results)
        self.calls: list[str] = []

    def extract(self, text: str, now: datetime) -> LLMIntent:
        self.calls.append(text)
        if not self.results:
            raise AssertionError("No fake intent was queued for this call")
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def create_task_intent(
    title: str = "Review the PR",
    description: str | None = None,
    due_date: date | None = None,
    priority: Priority | None = Priority.HIGH,
) -> LLMIntent:
    return LLMIntent(
        intent=Intent.CREATE_TASK,
        task=CreateTaskFields(
            title=title,
            description=description,
            due_date=due_date,
            priority=priority,
        ),
    )


def update_status_intent(
    identifier: str,
    status: TaskStatus = TaskStatus.COMPLETED,
) -> LLMIntent:
    return LLMIntent(
        intent=Intent.UPDATE_TASK_STATUS,
        update=UpdateStatusFields(task_identifier=identifier, new_status=status),
    )


def query_intent(
    status: TaskStatus | None = None,
    due_from: date | None = None,
    due_to: date | None = None,
    priority: Priority | None = None,
) -> LLMIntent:
    return LLMIntent(
        intent=Intent.QUERY_TASKS,
        query=QueryFields(
            status=status,
            due_from=due_from,
            due_to=due_to,
            priority=priority,
        ),
    )


def general_note_intent() -> LLMIntent:
    return LLMIntent(intent=Intent.GENERAL_NOTE)
