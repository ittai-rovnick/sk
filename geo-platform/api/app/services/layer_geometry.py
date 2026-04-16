import logging
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def refresh_layer_geometry_types(
    layer_id: uuid.UUID,
    shard_db: AsyncSession,
    meta_db: AsyncSession,
) -> list[str]:
    """Recompute `layers.geometry_types` from the current active features.

    Called after every feature mutation (create / update-with-geom / delete / sync push).
    Best-effort: a failure here is logged but does not propagate, so the feature write stays committed.
    """
    try:
        row = await shard_db.execute(
            text(
                """
                SELECT COALESCE(
                    array_agg(DISTINCT UPPER(REPLACE(ST_GeometryType(geom), 'ST_', ''))),
                    ARRAY[]::text[]
                ) AS types
                FROM features
                WHERE layer_id = CAST(:layer_id AS uuid) AND deleted_at IS NULL
                """
            ),
            {"layer_id": str(layer_id)},
        )
        types = row.scalar_one()
        await meta_db.execute(
            text(
                "UPDATE layers SET geometry_types = :types, updated_at = NOW() "
                "WHERE id = CAST(:id AS uuid)"
            ),
            {"types": types, "id": str(layer_id)},
        )
        await meta_db.commit()
        return types
    except Exception as exc:
        logger.warning(
            "refresh_layer_geometry_types failed for layer %s: %s",
            layer_id, exc,
        )
        return []
