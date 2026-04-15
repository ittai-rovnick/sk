import uuid
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel


class SnapshotRequest(BaseModel):
    layer_ids: list[uuid.UUID]
    device_id: str


class SnapshotResponse(BaseModel):
    snapshots: list[dict[str, Any]]
    features_by_layer: dict[str, list[dict[str, Any]]]


class DeltaResponse(BaseModel):
    updated: list[dict[str, Any]]
    deleted: list[int]


class SyncEdit(BaseModel):
    feature_id: int
    layer_id: uuid.UUID
    operation: Literal["create", "update", "delete"]
    version: int
    geom: dict[str, Any] | None = None
    properties: dict[str, Any] | None = None


class PushRequest(BaseModel):
    device_id: str
    edits: list[SyncEdit]


class ConflictInfo(BaseModel):
    feature_id: int
    server_version: int
    client_version: int


class FailedInfo(BaseModel):
    feature_id: int
    reason: str


class PushResponse(BaseModel):
    succeeded: list[int]
    conflicts: list[ConflictInfo]
    failed: list[FailedInfo]


class SyncStatusResponse(BaseModel):
    snapshot_age_hours: float
    is_expired: bool
    server_updated_at: datetime | None
    local_snapshotted_at: datetime
    pending_conflicts: int
