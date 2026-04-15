from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.auth.models import RequestContext


async def can_user_do(
    db: AsyncSession,
    ctx: RequestContext,
    layer_id: str,
    operation: str,
) -> bool:
    """
    Call the can_user_do() PostgreSQL function.
    Returns True if the user (or any of their groups) has permission.
    Superadmins bypass all checks.
    """
    if ctx.is_superadmin:
        return True

    result = await db.execute(
        text(
            "SELECT can_user_do(:ms_object_id, :ms_group_ids, :layer_id::uuid, :operation)"
        ),
        {
            "ms_object_id": ctx.ms_object_id,
            "ms_group_ids": ctx.ms_group_ids,
            "layer_id": layer_id,
            "operation": operation,
        },
    )
    return bool(result.scalar())
