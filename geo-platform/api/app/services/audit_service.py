import asyncio
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.models import RequestContext
from app.models.audit import AuditLog


async def log(
    db: AsyncSession,
    ctx: RequestContext,
    action: str,
    resource_type: str,
    resource_id: str,
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
    ip_address: str | None = None,
    error_message: str | None = None,
) -> None:
    """
    Write an audit log entry. Fire-and-forget — errors are suppressed so they
    never interrupt the main request path.
    """
    async def _write() -> None:
        try:
            entry = AuditLog(
                user_id=ctx.user_id,
                ms_object_id=ctx.ms_object_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                old_value=old_value,
                new_value=new_value,
                ip_address=ip_address,
                error_message=error_message,
            )
            db.add(entry)
            await db.commit()
        except Exception:
            pass  # audit failure must never crash the API

    asyncio.create_task(_write())
