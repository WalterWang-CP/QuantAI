"""Versioned USD SEC market-cap calculations with captured input manifests."""
import uuid
from datetime import date, datetime
from sqlalchemy import Date, DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


class SECMarketCapSnapshot(Base):
    __tablename__ = "sec_market_cap_snapshots"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    listing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("listings.id"), index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    valuation_date: Mapped[date] = mapped_column(Date, index=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    manifest_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("listing_id", "valuation_date", "input_hash", name="uq_sec_market_cap_inputs"),)
