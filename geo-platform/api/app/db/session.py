from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings
from typing import Dict, AsyncGenerator

# Metadata DB engine
meta_engine = create_async_engine(settings.meta_db_url, echo=settings.api_debug)
MetaSessionLocal = async_sessionmaker(meta_engine, expire_on_commit=False)

# Features shard engines — one per shard
shard_engines: Dict[int, any] = {}
shard_sessions: Dict[int, async_sessionmaker] = {}

for shard_id, url in settings.shard_urls.items():
    engine = create_async_engine(url, echo=settings.api_debug)
    shard_engines[shard_id] = engine
    shard_sessions[shard_id] = async_sessionmaker(engine, expire_on_commit=False)


async def get_meta_db() -> AsyncGenerator[AsyncSession, None]:
    async with MetaSessionLocal() as session:
        yield session


async def get_feature_db(shard_id: int) -> AsyncGenerator[AsyncSession, None]:
    async with shard_sessions[shard_id]() as session:
        yield session
