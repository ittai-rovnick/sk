import uuid
from datetime import datetime
from sqlalchemy import DateTime, Integer, String, ARRAY, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class GeoDatabase(Base):
    __tablename__ = "geo_databases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String)
    default_srid: Mapped[int] = mapped_column(Integer, nullable=False, default=4326)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
