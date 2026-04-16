import uuid
import json
from datetime import datetime, timezone, timedelta
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.dependencies import get_meta_db, get_current_user
from app.auth.models import RequestContext
from app.auth.permissions import can_user_do
from app.models.layers import Layer
from app.models.audit import SyncSnapshot, SyncConflict, FailedSync
from app.schemas.sync import (
    SnapshotRequest, SnapshotResponse,
    DeltaResponse,
    PushRequest, PushResponse, ConflictInfo, FailedInfo,
    SyncStatusResponse,
)
from app.db.session import shard_sessions

router = APIRouter(prefix="/sync", tags=["sync"])

SNAPSHOT_TTL_HOURS = 72


async def _get_layer(db: AsyncSession, layer_id: uuid.UUID) -> Layer:
    result = await db.execute(
        select(Layer).where(Layer.id == layer_id, Layer.deleted_at.is_(None))
    )
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Layer not found")
    return obj


@router.post("/snapshot", response_model=SnapshotResponse)
async def create_snapshot(
    body: SnapshotRequest,
    meta_db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    snapshots = []
    features_by_layer: dict[str, list[dict[str, Any]]] = {}
    expires_at = datetime.now(timezone.utc) + timedelta(hours=SNAPSHOT_TTL_HOURS)

    for layer_id in body.layer_ids:
        layer = await _get_layer(meta_db, layer_id)
        if not await can_user_do(meta_db, ctx, str(layer_id), "read"):
            continue

        sql = text("""
            SELECT id, layer_id, ST_AsGeoJSON(geom)::jsonb AS geom,
                   properties, version, created_by, updated_by, created_at, updated_at
            FROM features
            WHERE layer_id = CAST(:layer_id AS uuid) AND deleted_at IS NULL
        """)

        async with shard_sessions[layer.shard_id]() as shard_db:
            result = await shard_db.execute(sql, {"layer_id": str(layer_id)})
            rows = result.mappings().all()

        feature_list = []
        for r in rows:
            feature_list.append({
                "id": r["id"],
                "layer_id": str(r["layer_id"]),
                "geom": r["geom"] if isinstance(r["geom"], dict) else json.loads(r["geom"]),
                "properties": r["properties"],
                "version": r["version"],
                "created_by": r["created_by"],
                "updated_by": r["updated_by"],
                "created_at": r["created_at"].isoformat(),
                "updated_at": r["updated_at"].isoformat(),
            })
        features_by_layer[str(layer_id)] = feature_list

        # Record snapshot
        snap = SyncSnapshot(
            layer_id=layer_id,
            user_id=uuid.UUID(ctx.user_id),
            device_id=body.device_id,
            expires_at=expires_at,
            feature_count=len(feature_list),
        )
        meta_db.add(snap)
        snapshots.append({
            "layer_id": str(layer_id),
            "snapshotted_at": snap.snapshotted_at,
            "feature_count": len(feature_list),
            "expires_at": expires_at.isoformat(),
        })

    await meta_db.commit()
    return SnapshotResponse(snapshots=snapshots, features_by_layer=features_by_layer)


@router.get("/delta/{layer_id}", response_model=DeltaResponse)
async def get_delta(
    layer_id: uuid.UUID,
    device_id: str,
    meta_db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    layer = await _get_layer(meta_db, layer_id)
    if not await can_user_do(meta_db, ctx, str(layer_id), "read"):
        raise HTTPException(status_code=403, detail="Read permission required")

    # Find most recent snapshot for this device + layer
    result = await meta_db.execute(
        select(SyncSnapshot)
        .where(
            SyncSnapshot.layer_id == layer_id,
            SyncSnapshot.user_id == uuid.UUID(ctx.user_id),
            SyncSnapshot.device_id == device_id,
        )
        .order_by(SyncSnapshot.snapshotted_at.desc())
        .limit(1)
    )
    snap = result.scalar_one_or_none()
    if not snap:
        raise HTTPException(status_code=404, detail="No snapshot found for this device and layer")
    if snap.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Snapshot expired — request a new snapshot")

    updated_sql = text("""
        SELECT id, layer_id, ST_AsGeoJSON(geom)::jsonb AS geom,
               properties, version, created_by, updated_by, created_at, updated_at
        FROM features
        WHERE layer_id = CAST(:layer_id AS uuid)
          AND deleted_at IS NULL
          AND updated_at > :since
    """)
    deleted_sql = text("""
        SELECT id FROM features
        WHERE layer_id = CAST(:layer_id AS uuid)
          AND deleted_at IS NOT NULL
          AND deleted_at > :since
    """)
    params = {"layer_id": str(layer_id), "since": snap.snapshotted_at}

    async with shard_sessions[layer.shard_id]() as shard_db:
        updated_rows = (await shard_db.execute(updated_sql, params)).mappings().all()
        deleted_rows = (await shard_db.execute(deleted_sql, params)).mappings().all()

    updated = []
    for r in updated_rows:
        updated.append({
            "id": r["id"],
            "layer_id": str(r["layer_id"]),
            "geom": r["geom"] if isinstance(r["geom"], dict) else json.loads(r["geom"]),
            "properties": r["properties"],
            "version": r["version"],
            "updated_at": r["updated_at"].isoformat(),
        })

    return DeltaResponse(
        updated=updated,
        deleted=[r["id"] for r in deleted_rows],
    )


@router.post("/push", response_model=PushResponse)
async def push_edits(
    body: PushRequest,
    meta_db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    succeeded: list[int] = []
    conflicts: list[ConflictInfo] = []
    failed: list[FailedInfo] = []

    # Group edits by layer to minimise shard lookups
    edits_by_layer: dict[uuid.UUID, list] = {}
    for edit in body.edits:
        edits_by_layer.setdefault(edit.layer_id, []).append(edit)

    for layer_id, edits in edits_by_layer.items():
        try:
            layer = await _get_layer(meta_db, layer_id)
        except HTTPException:
            for edit in edits:
                failed.append(FailedInfo(feature_id=edit.feature_id, reason="Layer not found"))
            continue

        if not await can_user_do(meta_db, ctx, str(layer_id), "write"):
            for edit in edits:
                failed.append(FailedInfo(feature_id=edit.feature_id, reason="Write permission denied"))
            continue

        if layer.is_locked:
            for edit in edits:
                failed.append(FailedInfo(feature_id=edit.feature_id, reason="Layer is locked"))
            continue

        async with shard_sessions[layer.shard_id]() as shard_db:
            for edit in edits:
                try:
                    if edit.operation == "create":
                        sql = text("""
                            INSERT INTO features
                                (layer_id, geom, properties, version, created_by, updated_by, created_at, updated_at)
                            VALUES (
                                CAST(:layer_id AS uuid),
                                ST_SetSRID(ST_MakeValid(ST_GeomFromGeoJSON(:geom)), 4326),
                                :properties, 1, :actor, :actor, NOW(), NOW()
                            )
                            RETURNING id
                        """)
                        r = await shard_db.execute(sql, {
                            "layer_id": str(layer_id),
                            "geom": json.dumps(edit.geom or {}),
                            "properties": json.dumps(edit.properties or {}),
                            "actor": ctx.ms_object_id,
                        })
                        succeeded.append(r.scalar_one())

                    elif edit.operation == "update":
                        set_parts = ["version = version + 1", "updated_by = :actor", "updated_at = NOW()"]
                        params: dict[str, Any] = {
                            "id": edit.feature_id,
                            "layer_id": str(layer_id),
                            "expected_version": edit.version,
                            "actor": ctx.ms_object_id,
                        }
                        if edit.geom is not None:
                            set_parts.append("geom = ST_SetSRID(ST_MakeValid(ST_GeomFromGeoJSON(:geom)), 4326)")
                            params["geom"] = json.dumps(edit.geom)
                        if edit.properties is not None:
                            set_parts.append("properties = :properties")
                            params["properties"] = json.dumps(edit.properties)

                        r = await shard_db.execute(text(f"""
                            UPDATE features SET {', '.join(set_parts)}
                            WHERE id = :id AND layer_id = CAST(:layer_id AS uuid)
                              AND version = :expected_version AND deleted_at IS NULL
                            RETURNING id
                        """), params)
                        row = r.scalar_one_or_none()
                        if row is None:
                            # Check if feature exists at all (to distinguish conflict vs missing)
                            check = await shard_db.execute(
                                text("SELECT version FROM features WHERE id = :id AND layer_id = CAST(:layer_id AS uuid) AND deleted_at IS NULL"),
                                {"id": edit.feature_id, "layer_id": str(layer_id)},
                            )
                            server_row = check.one_or_none()
                            if server_row:
                                conflict = SyncConflict(
                                    layer_id=layer_id,
                                    feature_id=edit.feature_id,
                                    user_id=uuid.UUID(ctx.user_id),
                                    device_id=body.device_id,
                                    client_payload={"geom": edit.geom, "properties": edit.properties},
                                    server_version=server_row[0],
                                    client_version=edit.version,
                                )
                                meta_db.add(conflict)
                                conflicts.append(ConflictInfo(
                                    feature_id=edit.feature_id,
                                    server_version=server_row[0],
                                    client_version=edit.version,
                                ))
                            else:
                                failed.append(FailedInfo(feature_id=edit.feature_id, reason="Feature not found"))
                        else:
                            succeeded.append(row)

                    elif edit.operation == "delete":
                        r = await shard_db.execute(text("""
                            UPDATE features SET deleted_at = NOW(), deleted_by = :actor
                            WHERE id = :id AND layer_id = CAST(:layer_id AS uuid) AND deleted_at IS NULL
                            RETURNING id
                        """), {"id": edit.feature_id, "layer_id": str(layer_id), "actor": ctx.ms_object_id})
                        row = r.scalar_one_or_none()
                        if row is None:
                            failed.append(FailedInfo(feature_id=edit.feature_id, reason="Feature not found"))
                        else:
                            succeeded.append(row)

                except Exception as exc:
                    failed.append(FailedInfo(feature_id=edit.feature_id, reason=str(exc)))

            await shard_db.commit()

    await meta_db.commit()
    return PushResponse(succeeded=succeeded, conflicts=conflicts, failed=failed)


@router.get("/status/{layer_id}", response_model=SyncStatusResponse)
async def get_sync_status(
    layer_id: uuid.UUID,
    device_id: str,
    meta_db: AsyncSession = Depends(get_meta_db),
    ctx: RequestContext = Depends(get_current_user),
):
    await _get_layer(meta_db, layer_id)

    result = await meta_db.execute(
        select(SyncSnapshot)
        .where(
            SyncSnapshot.layer_id == layer_id,
            SyncSnapshot.user_id == uuid.UUID(ctx.user_id),
            SyncSnapshot.device_id == device_id,
        )
        .order_by(SyncSnapshot.snapshotted_at.desc())
        .limit(1)
    )
    snap = result.scalar_one_or_none()
    if not snap:
        raise HTTPException(status_code=404, detail="No snapshot found for this device and layer")

    now = datetime.now(timezone.utc)
    age_hours = (now - snap.snapshotted_at).total_seconds() / 3600

    pending_conflicts_result = await meta_db.execute(
        select(SyncConflict)
        .where(
            SyncConflict.layer_id == layer_id,
            SyncConflict.user_id == uuid.UUID(ctx.user_id),
            SyncConflict.device_id == device_id,
            SyncConflict.resolution == "pending",
        )
    )
    pending_conflicts = len(pending_conflicts_result.scalars().all())

    layer_result = await meta_db.execute(
        select(Layer).where(Layer.id == layer_id)
    )
    layer = layer_result.scalar_one_or_none()

    return SyncStatusResponse(
        snapshot_age_hours=age_hours,
        is_expired=snap.expires_at < now,
        server_updated_at=layer.updated_at if layer else None,
        local_snapshotted_at=snap.snapshotted_at,
        pending_conflicts=pending_conflicts,
    )
