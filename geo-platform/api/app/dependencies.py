from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_meta_db, get_feature_db
from app.auth.microsoft import validate_token
from app.auth.models import RequestContext
from app.models.layers import Layer

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_meta_db),
) -> RequestContext:
    token = credentials.credentials
    context = await validate_token(token, db)
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
