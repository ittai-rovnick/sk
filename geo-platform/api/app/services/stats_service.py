"""Per-layer attribute statistics. Cached 60s in Redis under stats:{layer_id}."""
import logging
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import cache_get, cache_set

logger = logging.getLogger(__name__)


async def get_layer_stats(
    shard_db: AsyncSession,
    layer_id: uuid.UUID,
    json_schema: dict | None,
) -> dict[str, Any]:
    cache_key = f"stats:{layer_id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    # ── Total count + geometry types
    count_row = await shard_db.execute(
        text("""
            SELECT COUNT(*)::int AS cnt
            FROM features
            WHERE layer_id = CAST(:lid AS uuid) AND deleted_at IS NULL
        """),
        {"lid": str(layer_id)},
    )
    total = int(count_row.scalar_one())

    geom_breakdown: dict[str, int] = {}
    if total > 0:
        geom_rows = await shard_db.execute(
            text("""
                SELECT REPLACE(ST_GeometryType(geom), 'ST_', '') AS gt, COUNT(*)::int
                FROM features
                WHERE layer_id = CAST(:lid AS uuid) AND deleted_at IS NULL
                GROUP BY gt
            """),
            {"lid": str(layer_id)},
        )
        for r in geom_rows.all():
            geom_breakdown[r[0]] = int(r[1])

    # ── Bbox envelope
    bbox: list[float] | None = None
    if total > 0:
        bbox_row = await shard_db.execute(
            text("""
                SELECT ST_XMin(env)::float8, ST_YMin(env)::float8,
                       ST_XMax(env)::float8, ST_YMax(env)::float8
                FROM (
                    SELECT ST_Envelope(ST_Collect(geom)) AS env
                    FROM features
                    WHERE layer_id = CAST(:lid AS uuid) AND deleted_at IS NULL
                ) sub
                WHERE env IS NOT NULL
            """),
            {"lid": str(layer_id)},
        )
        ext = bbox_row.one_or_none()
        bbox = list(ext) if ext else None

    # ── Per-field stats from json_schema
    field_stats: dict[str, Any] = {}
    fields = (json_schema or {}).get("fields", []) if json_schema else []
    for f in fields:
        if not isinstance(f, dict) or "name" not in f:
            continue
        name = f["name"]
        ftype = f.get("type", "string")
        try:
            if ftype == "number":
                row = await shard_db.execute(
                    text("""
                        SELECT
                            MIN((properties->>:f)::numeric)::float8 AS mn,
                            MAX((properties->>:f)::numeric)::float8 AS mx,
                            AVG((properties->>:f)::numeric)::float8 AS avg,
                            COUNT(*) FILTER (WHERE properties->>:f IS NULL OR properties->>:f = '')::int AS nulls
                        FROM features
                        WHERE layer_id = CAST(:lid AS uuid) AND deleted_at IS NULL
                    """),
                    {"f": name, "lid": str(layer_id)},
                )
                mn, mx, avg, nulls = row.one()
                field_stats[name] = {
                    "type": "number",
                    "min": mn, "max": mx, "avg": avg,
                    "null_count": int(nulls or 0),
                }
            elif ftype == "boolean":
                row = await shard_db.execute(
                    text("""
                        SELECT
                            COUNT(*) FILTER (WHERE properties->>:f = 'true')::int  AS tc,
                            COUNT(*) FILTER (WHERE properties->>:f = 'false')::int AS fc,
                            COUNT(*) FILTER (WHERE properties->>:f IS NULL)::int   AS nc
                        FROM features
                        WHERE layer_id = CAST(:lid AS uuid) AND deleted_at IS NULL
                    """),
                    {"f": name, "lid": str(layer_id)},
                )
                tc, fc, nc = row.one()
                field_stats[name] = {
                    "type": "boolean",
                    "true_count": int(tc or 0),
                    "false_count": int(fc or 0),
                    "null_count": int(nc or 0),
                }
            else:
                # string, date, etc.
                row = await shard_db.execute(
                    text("""
                        SELECT
                            COUNT(*) FILTER (WHERE properties->>:f IS NULL)::int AS nulls,
                            COUNT(DISTINCT properties->>:f)::int AS uniq
                        FROM features
                        WHERE layer_id = CAST(:lid AS uuid) AND deleted_at IS NULL
                    """),
                    {"f": name, "lid": str(layer_id)},
                )
                nulls, uniq = row.one()
                top = await shard_db.execute(
                    text("""
                        SELECT properties->>:f AS val, COUNT(*)::int AS cnt
                        FROM features
                        WHERE layer_id = CAST(:lid AS uuid)
                          AND deleted_at IS NULL
                          AND properties->>:f IS NOT NULL
                        GROUP BY val
                        ORDER BY cnt DESC, val
                        LIMIT 10
                    """),
                    {"f": name, "lid": str(layer_id)},
                )
                top_values = [{"value": r[0], "count": int(r[1])} for r in top.all()]
                field_stats[name] = {
                    "type": "string",
                    "null_count": int(nulls or 0),
                    "unique_count": int(uniq or 0),
                    "top_values": top_values,
                }
        except Exception as exc:
            logger.warning("stats for field %s failed: %s", name, exc)
            field_stats[name] = {"type": ftype, "error": str(exc)}

    stats = {
        "layer_id": str(layer_id),
        "total_count": total,
        "geometry_type_counts": geom_breakdown,
        "bbox": bbox,
        "field_stats": field_stats,
    }
    await cache_set(cache_key, stats, ttl=60)
    return stats
