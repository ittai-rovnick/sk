import uuid
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String)
    can_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_write: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_delete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_export: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_manage_style: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_manage_perms: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_publish: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_system_role: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ms_user_id: Mapped[str | None] = mapped_column(String)
    ms_group_id: Mapped[str | None] = mapped_column(String)
    database_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("geo_databases.id", ondelete="CASCADE")
    )
    group_layer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("group_layers.id", ondelete="CASCADE")
    )
    layer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("layers.id", ondelete="CASCADE")
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False
    )
    allow: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    granted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
