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


@asynccontextmanager
async def lifespan(app: FastAPI):
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
