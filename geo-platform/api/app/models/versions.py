import uuid
from datetime import datetime
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, ARRAY, func, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
import enum


class ResourceTypeEnum(str, enum.Enum):
    layer = "layer"
    map = "map"


class ResourceVersion(Base):
    __tablename__ = "resource_versions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    resource_type: Mapped[ResourceTypeEnum] = mapped_column(
        Enum(ResourceTypeEnum, name="resource_type"), nullable=False
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    changed_fields: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    message: Mapped[str | None] = mapped_column(String)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
