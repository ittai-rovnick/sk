from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.models import RequestContext
from app.auth.permissions import can_user_do


async def can_user_do(
    db: AsyncSession,
    ctx: RequestContext,
    layer_id: str,
    operation: str,
) -> bool:
    """Delegate to auth.permissions. Centralised so services can also call it."""
    from app.auth.permissions import can_user_do as _check
    return await _check(db, ctx, layer_id, operation)
