import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)


from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class RankingSnapshot(Base):
    __tablename__ = "ranking_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    ranking_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    effective_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    ranking_metric: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="market_cap_usd",
    )

    base_currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="USD",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="legacy",
        index=True,
    )

    candidate_count: Mapped[
        int | None
    ] = mapped_column(
        Integer,
        nullable=True,
    )

    ranked_company_count: Mapped[
        int | None
    ] = mapped_column(
        Integer,
        nullable=True,
    )

    minimum_required_candidates: Mapped[
        int | None
    ] = mapped_column(
        Integer,
        nullable=True,
    )

    approved_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    approval_note: Mapped[
        str | None
    ] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    rankings: Mapped[list["CompanyRanking"]] = relationship(
        back_populates="snapshot",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "effective_date >= ranking_date",
            name="ck_ranking_snapshot_dates",
        ),
    )

    CheckConstraint(
    "status IN "
    "('legacy', 'draft', 'approved', 'rejected')",
    name="ck_ranking_snapshot_status",
    ),

class CompanyRanking(Base):
    __tablename__ = "company_rankings"

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

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )

    rank: Mapped[int] = mapped_column(
        nullable=False,
    )

    market_cap_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(30, 2),
        nullable=True,
    )

    snapshot: Mapped["RankingSnapshot"] = relationship(
        back_populates="rankings",
    )

    __table_args__ = (
        CheckConstraint(
            "rank > 0",
            name="ck_company_ranking_positive_rank",
        ),
        UniqueConstraint(
            "snapshot_id",
            "company_id",
            name="uq_snapshot_company",
        ),
        UniqueConstraint(
            "snapshot_id",
            "rank",
            name="uq_snapshot_rank",
        ),
    )