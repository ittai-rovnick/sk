import asyncio
import sys

# psycopg3 async requires SelectorEventLoop on Windows (uvicorn uses ProactorEventLoop by default)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.services.storage_service import ensure_buckets_exist
from app.db.session import MetaSessionLocal
from app.models.users import User
from app.routers import (
    health,
    auth,
    databases,
    group_layers,
    layers,
    features,
    permissions,
    symbology,
    users,
    groups,
    rasters,
    sync,
)


async def _ensure_dev_user() -> None:
    """Create seed superadmin users if they don't exist yet."""
    import uuid
    from sqlalchemy import select

    seed_users = [
        dict(
            id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            email="dev@localhost",
            display_name="Dev Superadmin",
        ),
        dict(
            id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
            email="ittai@rovnick.com",
            display_name="Ittai",
        ),
    ]

    async with MetaSessionLocal() as db:
        for u in seed_users:
            result = await db.execute(select(User).where(User.id == u["id"]))
            if result.scalar_one_or_none() is None:
                db.add(User(
                    id=u["id"],
                    email=u["email"],
                    display_name=u["display_name"],
                    is_superadmin=True,
                    is_active=True,
                ))
        await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await ensure_buckets_exist()
    if settings.dev_mode:
        await _ensure_dev_user()
    yield
    # Shutdown — nothing to do yet


app = FastAPI(
    title="Geo Platform API",
    version="0.1.0",
    debug=settings.api_debug,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(databases.router)
app.include_router(group_layers.router)
app.include_router(layers.router)
app.include_router(features.router)
app.include_router(permissions.router)
app.include_router(symbology.router)
app.include_router(users.router)
app.include_router(groups.router)
app.include_router(rasters.router)
app.include_router(sync.router)
