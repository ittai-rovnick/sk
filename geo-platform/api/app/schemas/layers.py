import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel


class GroupLayerCreate(BaseModel):
    database_id: uuid.UUID
    parent_id: uuid.UUID | None = None
    name: str
    description: str | None = None
    tags: list[str] = []
    sort_order: int = 0


class GroupLayerUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    sort_order: int | None = None
    parent_id: uuid.UUID | None = None


class GroupLayerResponse(BaseModel):
    id: uuid.UUID
    database_id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str
    description: str | None
    tags: list[str]
    sort_order: int
    created_at: datetime

    model_config = {"from_attributes": True}


class LayerCreate(BaseModel):
    database_id: uuid.UUID
    group_layer_id: uuid.UUID | None = None
    name: str
    description: str | None = None
    geometry_type: str
    srid: int = 4326
    tags: list[str] = []
    sort_order: int = 0


class LayerUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    group_layer_id: uuid.UUID | None = None
    tags: list[str] | None = None
    status: str | None = None
    sort_order: int | None = None


class LayerResponse(BaseModel):
    id: uuid.UUID
    database_id: uuid.UUID
    group_layer_id: uuid.UUID | None
    name: str
    description: str | None
    geometry_type: str
    srid: int
    tags: list[str]
    status: str
    health: str
    shard_id: int
    is_locked: bool
    lock_reason: str | None
    locked_at: datetime | None
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LockRequest(BaseModel):
    reason: str | None = None


class LayerSchemaUpdate(BaseModel):
    json_schema: dict[str, Any]
