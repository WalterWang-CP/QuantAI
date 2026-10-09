"""Audited company-wide shares candidates; separate from market-cap inputs."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


class NormalizedShareFact(Base):
    __tablename__ = "normalized_share_facts"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    raw_fact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("raw_financial_facts.id"))
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    observation_date: Mapped[date] = mapped_column(Date)
    known_date: Mapped[date | None] = mapped_column(Date, index=True)
    shares_text: Mapped[str | None] = mapped_column(String(26))
    status: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(255))
    rule_version: Mapped[str] = mapped_column(String(30), server_default="sec-shares-v1")
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        UniqueConstraint("raw_fact_id", name="uq_normalized_share_raw_fact"),
        CheckConstraint("status IN ('accepted', 'excluded', 'conflict')", name="ck_normalized_share_status"),
        CheckConstraint("shares_text IS NULL OR CAST(shares_text AS NUMERIC) > 0", name="ck_normalized_share_positive"),
        CheckConstraint("known_date IS NULL OR known_date >= observation_date", name="ck_normalized_share_dates"),
        CheckConstraint("status != 'accepted' OR (shares_text IS NOT NULL AND known_date IS NOT NULL)", name="ck_normalized_share_accepted"),
    )

    @property
    def shares_outstanding(self) -> Decimal | None:
        return Decimal(self.shares_text) if self.shares_text is not None else None
