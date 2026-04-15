import uuid
from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, ARRAY, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from geoalchemy2 import Geometry
from app.db.base import Base


class RasterCatalog(Base):
    __tablename__ = "raster_catalog"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    database_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("geo_databases.id", ondelete="CASCADE")
    )
    group_layer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("group_layers.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    s3_key: Mapped[str] = mapped_column(String, nullable=False)
    format: Mapped[str] = mapped_column(String, nullable=False, default="COG")
    srid: Mapped[int] = mapped_column(Integer, nullable=False, default=4326)
    resolution_m: Mapped[float | None] = mapped_column(Float)
    band_count: Mapped[int | None] = mapped_column(Integer)
    bbox: Mapped[None] = mapped_column(Geometry("POLYGON", srid=4326), nullable=True)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    status: Mapped[str] = mapped_column(String, nullable=False, default="ready")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
