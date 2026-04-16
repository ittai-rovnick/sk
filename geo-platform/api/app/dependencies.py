from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from app.db.session import get_meta_db, get_feature_db
from app.auth.local import validate_token
from app.auth.models import RequestContext
from app.models.layers import Layer
from app.config import settings

security = HTTPBearer(auto_error=False)

# Fixed dev user identity — consistent across all requests in dev mode
_DEV_CONTEXT = RequestContext(
    ms_object_id="dev-superadmin",
    ms_group_ids=[],
    user_id="00000000-0000-0000-0000-000000000001",
    is_superadmin=True,
)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_meta_db),
) -> RequestContext:
    if settings.dev_mode:
        return _DEV_CONTEXT

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
        )

    context = await validate_token(credentials.credentials, db)
    if not context:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return context


async def get_layer_feature_db(
    layer_id: str,
    db: AsyncSession = Depends(get_meta_db),
) -> AsyncSession:
    """Return the correct feature-shard session for the given layer_id."""
    result = await db.execute(select(Layer).where(Layer.id == layer_id))
    layer = result.scalar_one_or_none()
    if not layer:
        raise HTTPException(status_code=404, detail="Layer not found")
    async for session in get_feature_db(layer.shard_id):
        return session
