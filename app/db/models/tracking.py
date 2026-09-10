import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class TrackingRun(Base):
    __tablename__ = "tracking_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ranking_snapshots.id"),
        nullable=False,
        index=True,
    )

    policy_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    policy_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    policy_json: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
    )

    engine_version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    decisions: Mapped[list["CompanyTrackingDecision"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "policy_hash",
            "engine_version",
            name="uq_tracking_run",
        ),
    )


class CompanyTrackingDecision(Base):
    __tablename__ = "company_tracking_decisions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tracking_runs.id"),
        nullable=False,
        index=True,
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )

    rank: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    main_universe: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )

    elite_tracking: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )

    elite_triggered_now: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    first_elite_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    historical_backfill_start: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    dropout_tracking: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )

    dropout_triggered_now: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    dropout_until: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    run: Mapped["TrackingRun"] = relationship(
        back_populates="decisions",
    )

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "company_id",
            name="uq_tracking_run_company",
        ),
    )