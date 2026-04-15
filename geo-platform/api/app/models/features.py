# Features live in the features database, not the metadata database.
# This module exists for import completeness; the actual table is partitioned
# and managed via raw SQL / the features Alembic migration.
# The Feature class below mirrors that table for type-hinting purposes only
# and is NOT used with the meta engine.

import uuid
from datetime import datetime
from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from geoalchemy2 import Geometry
from app.db.base import Base


class Feature(Base):
    __tablename__ = "features"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    layer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, primary_key=True)
    geom: Mapped[None] = mapped_column(Geometry("GEOMETRY"), nullable=False)
    properties: Mapped[dict] = mapped_column(nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[str | None] = mapped_column(String)
    updated_by: Mapped[str | None] = mapped_column(String)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = {"extend_existing": True}
