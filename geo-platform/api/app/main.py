import asyncio
import sys
import uuid

# psycopg3 async requires SelectorEventLoop on Windows (uvicorn uses ProactorEventLoop by default)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.config import settings
from app.services.storage_service import ensure_buckets_exist
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

_DEV_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


async def _ensure_dev_user() -> None:
    from app.db.session import get_meta_db
    from app.models.users import User
    async for db in get_meta_db():
        result = await db.execute(select(User).where(User.id == _DEV_USER_ID))
        if not result.scalar_one_or_none():
            db.add(User(
                id=_DEV_USER_ID,
                email="dev@local",
                display_name="Dev Superadmin",
                is_superadmin=True,
                is_active=True,
            ))
            await db.commit()
        break


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.dev_mode:
        await _ensure_dev_user()
    await ensure_buckets_exist()
    yield


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
