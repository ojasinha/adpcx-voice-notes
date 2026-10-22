from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UTCDateTime
from app.domain import Intent, Priority, Source, TaskStatus


def utcnow() -> datetime:
    return datetime.now(UTC)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(
            TaskStatus,
            native_enum=False,
            values_callable=lambda enum: [member.value for member in enum],
            validate_strings=True,
            length=20,
        ),
        nullable=False,
        default=TaskStatus.PENDING,
        index=True,
    )
    priority: Mapped[Priority | None] = mapped_column(
        SAEnum(
            Priority,
            native_enum=False,
            values_callable=lambda enum: [member.value for member in enum],
            validate_strings=True,
            length=20,
        ),
        nullable=True,
        index=True,
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow, onupdate=utcnow
    )

    notes: Mapped[list[Note]] = relationship(back_populates="task", passive_deletes=True)


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    raw_transcript: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow, index=True
    )
    source: Mapped[Source] = mapped_column(
        SAEnum(
            Source,
            native_enum=False,
            values_callable=lambda enum: [member.value for member in enum],
            validate_strings=True,
            length=10,
        ),
        nullable=False,
        index=True,
    )
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    intent: Mapped[Intent | None] = mapped_column(
        SAEnum(
            Intent,
            native_enum=False,
            values_callable=lambda enum: [member.value for member in enum],
            validate_strings=True,
            length=30,
        ),
        nullable=True,
    )
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    task: Mapped[Task | None] = relationship(back_populates="notes")
