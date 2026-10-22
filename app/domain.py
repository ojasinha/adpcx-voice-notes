from __future__ import annotations

from enum import StrEnum
from uuid import uuid4


class Source(StrEnum):
    VOICE = "voice"
    TEXT = "text"


class Intent(StrEnum):
    CREATE_TASK = "CREATE_TASK"
    UPDATE_TASK_STATUS = "UPDATE_TASK_STATUS"
    QUERY_TASKS = "QUERY_TASKS"
    GENERAL_NOTE = "GENERAL_NOTE"


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class Priority(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"
