"""Exact CSV source text and import declarations, retained independently of disk files."""
import uuid
from sqlalchemy import CheckConstraint, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


class CSVPriceArtifact(Base):
    __tablename__ = "csv_price_artifacts"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingestion_runs.id"), unique=True)
    listing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("listings.id"), index=True)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_sources.id"), index=True)
    import_hash: Mapped[str] = mapped_column(String(64))
    sha256: Mapped[str] = mapped_column(String(64))
    body: Mapped[bytes] = mapped_column(LargeBinary)
    byte_count: Mapped[int] = mapped_column(Integer)
    declaration_json: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("listing_id", "source_id", "import_hash", name="uq_csv_price_import"),
        CheckConstraint("byte_count > 0", name="ck_csv_price_artifact_nonempty"),
    )
