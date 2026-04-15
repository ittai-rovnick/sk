from fastapi import APIRouter
from sqlalchemy import text
from app.db.session import MetaSessionLocal

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """No auth required — used by load balancers and Docker healthchecks."""
    async with MetaSessionLocal() as db:
        await db.execute(text("SELECT 1"))
    return {"status": "ok"}
