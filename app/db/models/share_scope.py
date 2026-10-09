"""Explicit, evidence-backed mapping of company-wide shares to one common security."""
import uuid
from datetime import date, datetime
from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


class CompanyShareScope(Base):
    __tablename__ = "company_share_scopes"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    security_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("securities.id"), index=True)
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date] = mapped_column(Date)
    known_date: Mapped[date] = mapped_column(Date)
    evidence_url: Mapped[str] = mapped_column(Text)
    evidence_note: Mapped[str] = mapped_column(Text)
    scope_type: Mapped[str] = mapped_column(String(30), server_default="single_common_class")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        UniqueConstraint("company_id", "valid_from", "valid_to", name="uq_company_share_scope_period"),
        CheckConstraint("valid_to >= valid_from", name="ck_share_scope_period"),
        CheckConstraint("known_date >= valid_from", name="ck_share_scope_known_date"),
        CheckConstraint("scope_type = 'single_common_class'", name="ck_share_scope_type"),
    )
