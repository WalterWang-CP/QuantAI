import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from app.db.database import Base


class RetrievalJob(Base):
    __tablename__ = "retrieval_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    tracking_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tracking_runs.id"),
        nullable=False,
        index=True,
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )

    listing_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("listings.id"),
        nullable=False,
        index=True,
    )

    provider_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    dataset_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    required_start_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    required_end_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    full_history: Mapped[bool] = mapped_column(
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
        index=True,
    )

    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    ingestion_run_id: Mapped[
        uuid.UUID | None
    ] = mapped_column(
        ForeignKey("ingestion_runs.id"),
        nullable=True,
    )

    error_message: Mapped[
        str | None
    ] = mapped_column(
        Text,
        nullable=True,
    )

    last_error_type: Mapped[
        str | None
    ] = mapped_column(
        String(50),
        nullable=True,
    )

    last_attempt_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    next_retry_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    started_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "tracking_run_id",
            "listing_id",
            "provider_name",
            "dataset_name",
            "required_start_date",
            "required_end_date",
            name="uq_retrieval_job_requirement",
        ),
    )


class RetrievalBatchRun(Base):
    __tablename__ = "retrieval_batch_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    tracking_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tracking_runs.id"),
        nullable=False,
        index=True,
    )

    provider_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    requested_limit: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="running",
        index=True,
    )

    attempts_started: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    jobs_completed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    retry_scheduled: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    jobs_failed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    paused_until: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    stop_reason: Mapped[
        str | None
    ] = mapped_column(
        Text,
        nullable=True,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    completed_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class RetrievalJobAttempt(Base):
    __tablename__ = "retrieval_job_attempts"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("retrieval_jobs.id"),
        nullable=False,
        index=True,
    )

    batch_run_id: Mapped[
        uuid.UUID | None
    ] = mapped_column(
        ForeignKey("retrieval_batch_runs.id"),
        nullable=True,
        index=True,
    )

    attempt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    error_type: Mapped[
        str | None
    ] = mapped_column(
        String(50),
        nullable=True,
    )

    error_message: Mapped[
        str | None
    ] = mapped_column(
        Text,
        nullable=True,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    completed_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "job_id",
            "attempt_number",
            name="uq_retrieval_job_attempt",
        ),
    )


class ProviderThrottleState(Base):
    __tablename__ = "provider_throttle_states"

    provider_name: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
    )

    quota_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    requests_today: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    last_request_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    blocked_until: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    block_reason: Mapped[
        str | None
    ] = mapped_column(
        Text,
        nullable=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )