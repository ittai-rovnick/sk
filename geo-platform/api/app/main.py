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
    """Create a superadmin dev user if DEV_MODE is on and the user doesn't exist yet."""
    import uuid
    from sqlalchemy import select
    async with MetaSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.id == uuid.UUID("00000000-0000-0000-0000-000000000001"))
        )
        if result.scalar_one_or_none() is None:
            dev_user = User(
                id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                ms_object_id="dev-superadmin",
                email="dev@localhost",
                display_name="Dev Superadmin",
                is_superadmin=True,
                is_active=True,
            )
            db.add(dev_user)
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
