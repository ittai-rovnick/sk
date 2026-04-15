from jose import jwt, JWTError
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.config import settings
from app.auth.models import RequestContext
from app.models.users import User
import uuid

MICROSOFT_KEYS_URL = (
    f"https://login.microsoftonline.com/{settings.ms_tenant_id}/discovery/v2.0/keys"
)
_keys_cache = None


async def get_microsoft_keys() -> dict:
    global _keys_cache
    if _keys_cache is None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(MICROSOFT_KEYS_URL)
            resp.raise_for_status()
            _keys_cache = resp.json()
    return _keys_cache


async def validate_token(token: str, db: AsyncSession) -> RequestContext | None:
    try:
        keys = await get_microsoft_keys()
        claims = jwt.decode(
            token,
            keys,
            algorithms=["RS256"],
            audience=settings.ms_client_id,
        )
        ms_object_id: str = claims["oid"]
        ms_group_ids: list[str] = claims.get("groups", [])

        # Handle Microsoft 200-group overage claim
        if "_claim_names" in claims and "groups" in claims["_claim_names"]:
            ms_group_ids = await fetch_groups_from_graph(token)

        user = await upsert_user(
            db,
            ms_object_id,
            claims.get("email") or claims.get("preferred_username", ""),
            claims.get("name", ""),
        )

        return RequestContext(
            ms_object_id=ms_object_id,
            ms_group_ids=ms_group_ids,
            user_id=str(user.id),
            is_superadmin=user.is_superadmin,
        )
    except JWTError:
        return None


async def fetch_groups_from_graph(token: str) -> list[str]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://graph.microsoft.com/v1.0/me/memberOf",
            headers={"Authorization": f"Bearer {token}"},
        )
        data = resp.json()
        return [g["id"] for g in data.get("value", [])]


async def upsert_user(
    db: AsyncSession,
    ms_object_id: str,
    email: str,
    display_name: str,
) -> User:
    from datetime import datetime, timezone

    result = await db.execute(
        select(User).where(User.ms_object_id == ms_object_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            ms_object_id=ms_object_id,
            email=email,
            display_name=display_name,
        )
        db.add(user)
    else:
        user.email = email
        user.display_name = display_name
        user.last_seen_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(user)
    return user
