import uuid
from datetime import datetime
from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class MsGroup(Base):
    __tablename__ = "ms_groups"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ms_group_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(String)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
