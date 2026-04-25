"""Pydantic schemas for maps, map groups, map layers, and the /open tree response."""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel


# ── Map ────────────────────────────────────────────────────────────────────────

class MapCreate(BaseModel):
    database_id: uuid.UUID
    name: str
    description: str | None = None


class MapUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class MapResponse(BaseModel):
    id: uuid.UUID
    database_id: uuid.UUID
    name: str
    description: str | None
    extent: list[float] | None = None  # [lon_min, lat_min, lon_max, lat_max]
    content_version: int
    content_updated_at: datetime
    content_updated_by: uuid.UUID | None
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Map Group ──────────────────────────────────────────────────────────────────

class MapGroupCreate(BaseModel):
    name: str
    parent_id: uuid.UUID | None = None
    embedded_map_id: uuid.UUID | None = None
    sort_order: int = 0


class MapGroupUpdate(BaseModel):
    name: str | None = None
    parent_id: uuid.UUID | None = None
    sort_order: int | None = None
    is_expanded: bool | None = None


class MapGroupResponse(BaseModel):
    id: uuid.UUID
    map_id: uuid.UUID
    parent_id: uuid.UUID | None
    embedded_map_id: uuid.UUID | None
    name: str
    sort_order: int
    is_expanded: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Map Layer ──────────────────────────────────────────────────────────────────

class MapLayerAdd(BaseModel):
    layer_id: uuid.UUID
    group_id: uuid.UUID | None = None
    sort_order: int = 0
    filter_expression: dict | None = None


class MapLayerUpdate(BaseModel):
    group_id: uuid.UUID | None = None
    sort_order: int | None = None
    is_visible: bool | None = None
    filter_expression: dict | None = None


class MapLayerResponse(BaseModel):
    id: uuid.UUID
    map_id: uuid.UUID
    layer_id: uuid.UUID
    group_id: uuid.UUID | None
    sort_order: int
    is_visible: bool
    filter_expression: dict | None
    added_at: datetime

    model_config = {"from_attributes": True}


# ── Tree nodes for /open ───────────────────────────────────────────────────────

class MapLayerNode(BaseModel):
    type: Literal["layer"] = "layer"
    map_layer_id: uuid.UUID
    layer_id: uuid.UUID
    name: str
    group_id: uuid.UUID | None
    sort_order: int
    is_visible: bool
    srid: int
    geometry_types: list[str]
    bbox: list[float] | None
    filter_expression: dict | None
    effective_role: str | None = None


class MapGroupNode(BaseModel):
    type: Literal["group"] = "group"
    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    sort_order: int
    is_expanded: bool
    embedded_map_id: uuid.UUID | None
    children: list["MapGroupNode | MapLayerNode"] = []


MapGroupNode.model_rebuild()


class MapOpenResponse(BaseModel):
    map: MapResponse
    tree: list[MapGroupNode | MapLayerNode]


# ── Freshness ──────────────────────────────────────────────────────────────────

class MapFreshnessChangedLayer(BaseModel):
    layer_id: uuid.UUID
    name: str
    features_updated_at: datetime | None
    features_updated_by: uuid.UUID | None


class MapFreshnessResponse(BaseModel):
    map_id: uuid.UUID
    content_version: int
    content_updated_at: datetime
    any_change_since: bool
    changed_layers: list[MapFreshnessChangedLayer]


# ── Bulk group permission grant ────────────────────────────────────────────────

class GroupPermissionGrantRequest(BaseModel):
    ms_user_id: str | None = None
    ms_group_id: str | None = None
    role_id: uuid.UUID
    allow: bool = True


class GroupPermissionGrantResponse(BaseModel):
    granted: int
    layer_ids: list[uuid.UUID]
