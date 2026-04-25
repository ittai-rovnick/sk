"""Version history service — full snapshots, race-condition-free counter.

`record_version()` MUST be called inside the same DB transaction as the UPDATE it
records. Commit once, after both the UPDATE and the INSERT into resource_versions.
"""
import logging
import uuid
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.layers import Layer
from app.models.maps import Map
from app.models.versions import ResourceVersion

logger = logging.getLogger(__name__)


async def record_version(
    db: AsyncSession,
    resource_type: str,
    resource_id: uuid.UUID,
    snapshot: dict[str, Any],
    changed_fields: list[str],
    actor_id: str | None,
    message: str | None = None,
) -> int:
    """Record a snapshot at the next version number, in the caller's transaction.

    Returns the assigned version number. The caller must commit; this function
    does NOT commit on its own.
    """
    if resource_type not in ("layer", "map"):
        raise ValueError(f"Unknown resource_type: {resource_type}")

    # Acquire next version (FOR UPDATE inside the same tx)
    next_v = await db.execute(
        text("SELECT next_resource_version(CAST(:rt AS resource_type), CAST(:rid AS uuid))"),
        {"rt": resource_type, "rid": str(resource_id)},
    )
    version = int(next_v.scalar_one())

    await db.execute(
        text("""
            INSERT INTO resource_versions
                (resource_type, resource_id, version, snapshot, changed_fields, message, changed_by)
            VALUES (
                CAST(:rt AS resource_type),
                CAST(:rid AS uuid),
                :version,
                CAST(:snapshot AS jsonb),
                CAST(:changed_fields AS text[]),
                :message,
                CAST(:actor AS uuid)
            )
        """),
        {
            "rt": resource_type,
            "rid": str(resource_id),
            "version": version,
            "snapshot": _json_safe(snapshot),
            "changed_fields": changed_fields,
            "message": message,
            "actor": actor_id,
        },
    )
    return version


async def get_versions(
    db: AsyncSession,
    resource_type: str,
    resource_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    result = await db.execute(
        text("""
            SELECT id, version, changed_fields, changed_by, changed_at, message
            FROM resource_versions
            WHERE resource_type = CAST(:rt AS resource_type)
              AND resource_id  = CAST(:rid AS uuid)
            ORDER BY version DESC
            LIMIT :limit OFFSET :offset
        """),
        {"rt": resource_type, "rid": str(resource_id), "limit": limit, "offset": offset},
    )
    return [dict(r) for r in result.mappings().all()]


async def get_version(
    db: AsyncSession,
    resource_type: str,
    resource_id: uuid.UUID,
    version: int,
) -> dict | None:
    result = await db.execute(
        text("""
            SELECT id, version, snapshot, changed_fields, changed_by, changed_at, message
            FROM resource_versions
            WHERE resource_type = CAST(:rt AS resource_type)
              AND resource_id  = CAST(:rid AS uuid)
              AND version = :v
        """),
        {"rt": resource_type, "rid": str(resource_id), "v": version},
    )
    row = result.mappings().one_or_none()
    return dict(row) if row else None


async def restore_version(
    db: AsyncSession,
    resource_type: str,
    resource_id: uuid.UUID,
    version: int,
    actor_id: str,
) -> dict:
    """Restore the resource's persisted fields from snapshot[version].

    Records a new version capturing the pre-restore snapshot, with message
    'Restored from v{version}'. Returns {version: <new_version>, message: ...}.
    """
    snap_row = await get_version(db, resource_type, resource_id, version)
    if not snap_row:
        raise ValueError("Version not found")

    snapshot = snap_row["snapshot"]

    if resource_type == "layer":
        result = await db.execute(select(Layer).where(Layer.id == resource_id))
        obj = result.scalar_one_or_none()
        if not obj:
            raise ValueError("Layer not found")
        before_snapshot = _layer_snapshot(obj)
        for field in LAYER_VERSION_FIELDS:
            if field in snapshot:
                setattr(obj, field, snapshot[field])
        obj.updated_by = uuid.UUID(actor_id)
    else:  # map
        result = await db.execute(select(Map).where(Map.id == resource_id))
        obj = result.scalar_one_or_none()
        if not obj:
            raise ValueError("Map not found")
        before_snapshot = _map_snapshot(obj)
        for field in MAP_VERSION_FIELDS:
            if field in snapshot:
                setattr(obj, field, snapshot[field])
        obj.updated_by = uuid.UUID(actor_id)

    new_version = await record_version(
        db,
        resource_type,
        resource_id,
        before_snapshot,
        list(snapshot.keys()),
        actor_id,
        message=f"Restored from v{version}",
    )
    await db.commit()
    return {"version": new_version, "message": f"Restored from v{version}"}


# ── Snapshot field whitelists ──────────────────────────────────────────────────

LAYER_VERSION_FIELDS = ["name", "description", "status", "srid", "tags", "sort_order", "group_layer_id"]
MAP_VERSION_FIELDS = ["name", "description"]


def _layer_snapshot(layer: Layer) -> dict[str, Any]:
    return {f: getattr(layer, f) for f in LAYER_VERSION_FIELDS}


def _map_snapshot(m: Map) -> dict[str, Any]:
    return {f: getattr(m, f) for f in MAP_VERSION_FIELDS}


def _json_safe(d: dict[str, Any]) -> str:
    """Serialize snapshot to JSON; UUIDs and dates → strings."""
    import json
    return json.dumps(d, default=str)
