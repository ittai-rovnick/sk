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

    Called after every feature mutation that changes geometry.
    Best-effort: a failure here is logged but does not propagate.
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


async def refresh_layer_bbox(
    layer_id: uuid.UUID,
    shard_db: AsyncSession,
    meta_db: AsyncSession,
) -> list[float] | None:
    """Recompute `layers.bbox` as the envelope of all active features.

    Called after every feature mutation that changes geometry.
    Best-effort: a failure here is logged but does not propagate.
    Returns [xmin, ymin, xmax, ymax] or None if no features.
    """
    try:
        row = await shard_db.execute(
            text(
                "SELECT ST_AsText(ST_Envelope(ST_Collect(geom))) AS wkt "
                "FROM features WHERE layer_id = CAST(:id AS uuid) AND deleted_at IS NULL"
            ),
            {"id": str(layer_id)},
        )
        wkt = row.scalar_one_or_none()
        if not wkt:
            await meta_db.execute(
                text("UPDATE layers SET bbox = NULL WHERE id = CAST(:id AS uuid)"),
                {"id": str(layer_id)},
            )
            await meta_db.commit()
            return None

        await meta_db.execute(
            text(
                "UPDATE layers SET bbox = ST_GeomFromText(:wkt, 4326) "
                "WHERE id = CAST(:id AS uuid)"
            ),
            {"wkt": wkt, "id": str(layer_id)},
        )
        # Extract [xmin, ymin, xmax, ymax] in the same transaction
        ext_row = await meta_db.execute(
            text(
                "SELECT ST_XMin(bbox)::float8, ST_YMin(bbox)::float8, "
                "ST_XMax(bbox)::float8, ST_YMax(bbox)::float8 "
                "FROM layers WHERE id = CAST(:id AS uuid)"
            ),
            {"id": str(layer_id)},
        )
        await meta_db.commit()
        ext = ext_row.one_or_none()
        return list(ext) if ext else None
    except Exception as exc:
        logger.warning("refresh_layer_bbox failed for layer %s: %s", layer_id, exc)
        return None


async def refresh_layer_feature_stamp(
    layer_id: uuid.UUID,
    actor_id: str,
    meta_db: AsyncSession,
) -> None:
    """Update `layers.features_updated_at` and `features_updated_by`.

    Called unconditionally after EVERY feature mutation — including property-only
    changes that don't alter geometry (those don't call refresh_layer_geometry_types).
    This is the primary signal that a layer's data has changed.
    Best-effort: a failure here is logged but does not propagate.
    """
    try:
        await meta_db.execute(
            text(
                """
                UPDATE layers
                SET features_updated_at = NOW(),
                    features_updated_by = CAST(:actor AS uuid),
                    updated_at = NOW()
                WHERE id = CAST(:id AS uuid)
                """
            ),
            {"actor": actor_id, "id": str(layer_id)},
        )
        await meta_db.commit()
    except Exception as exc:
        logger.warning(
            "refresh_layer_feature_stamp failed for layer %s: %s", layer_id, exc
        )
