from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.domain import Intent, Priority, TaskStatus
from app.errors import IntentExtractionError, LLMUnavailableError
from app.schemas.intents import LLMIntent
from app.services.intent import (
    OpenAICompatibleIntentExtractor,
    build_system_prompt,
    extract_json_object,
)
from app.services.llm import OpenAICompatibleClient


def test_llm_client_requires_explicit_configuration():
    client = OpenAICompatibleClient(Settings(llm_base_url="", llm_model="", llm_api_key=""))

    with pytest.raises(LLMUnavailableError, match="not configured"):
        client.complete_json([{"role": "user", "content": "hello"}])


def test_extract_json_object_handles_plain_and_fenced_json():
    assert extract_json_object('{"intent": "GENERAL_NOTE"}') == {"intent": "GENERAL_NOTE"}
    assert extract_json_object('```json\n{"intent": "GENERAL_NOTE"}\n```') == {
        "intent": "GENERAL_NOTE"
    }
    assert extract_json_object('Here is the result: {"intent": "GENERAL_NOTE"} Thanks') == {
        "intent": "GENERAL_NOTE"
    }


def test_extract_json_object_rejects_non_object():
    with pytest.raises(ValueError):
        extract_json_object("not json")


def test_system_prompt_contains_dynamic_calendar_context():
    now = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)

    prompt = build_system_prompt(now)

    assert "2026-10-22" in prompt
    assert "2026-10-23" in prompt
    assert "2026-10-19" in prompt
    assert "2026-10-25" in prompt


def test_intent_payload_validation():
    with pytest.raises(ValidationError):
        LLMIntent.model_validate({"intent": "CREATE_TASK"})

    with pytest.raises(ValidationError):
        LLMIntent.model_validate(
            {
                "intent": "GENERAL_NOTE",
                "task": {"title": "Should not be here"},
            }
        )

    query = LLMIntent.model_validate({"intent": "QUERY_TASKS"})
    assert query.query is not None
    assert query.query.status is None


def test_query_fields_reject_inverted_dates():
    with pytest.raises(ValidationError):
        LLMIntent.model_validate(
            {
                "intent": "QUERY_TASKS",
                "query": {"due_from": "2026-02-01", "due_to": "2026-01-01"},
            }
        )


class StubLLMClient:
    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)
        self.calls: list[list[dict]] = []

    def complete_json(self, messages) -> str:
        self.calls.append(list(messages))
        return self.responses.pop(0)


def test_extractor_retries_after_invalid_output():
    client = StubLLMClient(
        "this is not json",
        '{"intent":"GENERAL_NOTE","task":null,"update":null,"query":null}',
    )
    extractor = OpenAICompatibleIntentExtractor(client, max_attempts=2)

    result = extractor.extract("An idea", datetime.now(UTC))

    assert result.intent == Intent.GENERAL_NOTE
    assert len(client.calls) == 2
    assert "previous output was invalid" in client.calls[1][-1]["content"]


def test_extractor_raises_after_exhausting_attempts():
    client = StubLLMClient("not json", "still not json")
    extractor = OpenAICompatibleIntentExtractor(client, max_attempts=2)

    with pytest.raises(IntentExtractionError):
        extractor.extract("An idea", datetime.now(UTC))

    assert len(client.calls) == 2


def test_create_task_intent_parses_normalized_values():
    result = LLMIntent.model_validate(
        {
            "intent": "CREATE_TASK",
            "task": {
                "title": "Review the PR",
                "due_date": "2026-10-23",
                "priority": "HIGH",
            },
        }
    )

    assert result.task is not None
    assert result.task.due_date == date(2026, 10, 23)
    assert result.task.priority == Priority.HIGH


def test_update_task_intent_parses_status():
    result = LLMIntent.model_validate(
        {
            "intent": "UPDATE_TASK_STATUS",
            "update": {"task_identifier": "login bug", "new_status": "COMPLETED"},
        }
    )

    assert result.update is not None
    assert result.update.new_status == TaskStatus.COMPLETED
