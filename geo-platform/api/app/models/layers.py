import uuid
from datetime import datetime
from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, String, ARRAY, Text, func, text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from geoalchemy2 import Geometry
from app.db.base import Base


class GroupLayer(Base):
    __tablename__ = "group_layers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    database_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("geo_databases.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("group_layers.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Layer(Base):
    __tablename__ = "layers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    database_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("geo_databases.id", ondelete="CASCADE"), nullable=False
    )
    group_layer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("group_layers.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String)
    geometry_types: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default=text("'{}'")
    )
    srid: Mapped[int] = mapped_column(Integer, nullable=False, default=4326)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    status: Mapped[str] = mapped_column(String, nullable=False, default="draft")
    health: Mapped[str] = mapped_column(String, nullable=False, default="ok")
    shard_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    locked_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lock_reason: Mapped[str | None] = mapped_column(Text)
    bbox: Mapped[None] = mapped_column(Geometry("POLYGON", srid=4326), nullable=True)
    lyrx_s3_key: Mapped[str | None] = mapped_column(String)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class LayerOwner(Base):
    __tablename__ = "layer_owners"

    layer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("layers.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )


class LayerSchema(Base):
    __tablename__ = "layer_schema"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    layer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("layers.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    json_schema: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
