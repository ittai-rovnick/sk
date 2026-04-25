import uuid
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, field_validator


ALLOWED_GEOMETRY_TYPES: frozenset[str] = frozenset({
    "POINT", "LINESTRING", "POLYGON",
    "MULTIPOINT", "MULTILINESTRING", "MULTIPOLYGON",
})

GEOJSON_GEOMETRY_TYPES: frozenset[str] = frozenset({
    "Point", "MultiPoint", "LineString", "MultiLineString",
    "Polygon", "MultiPolygon", "GeometryCollection",
})


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
    geometry_types: list[str]
    srid: int
    tags: list[str]
    status: str
    health: str
    shard_id: int
    is_locked: bool
    lock_reason: str | None
    locked_at: datetime | None
    sort_order: int
    bbox: list[float] | None = None           # [lon_min, lat_min, lon_max, lat_max]
    features_updated_at: datetime | None = None
    features_updated_by: uuid.UUID | None = None
    updated_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("bbox", mode="before")
    @classmethod
    def _coerce_bbox(cls, v):
        # geoalchemy2 returns a WKBElement here; the live extent value must be
        # populated separately by the caller (or computed via ST_X/Y queries).
        if v is None or isinstance(v, list):
            return v
        return None


class LockRequest(BaseModel):
    reason: str | None = None


class LayerSchemaUpdate(BaseModel):
    json_schema: dict[str, Any]


# ---------------------------------------------------------------- identify schemas

class LayerIdentifyRequest(BaseModel):
    database_id: uuid.UUID
    geometry: dict                            # GeoJSON geometry object


class LayerIdentifyLayerNode(BaseModel):
    type: Literal["layer"] = "layer"
    layer_id: uuid.UUID
    name: str
    feature_count_in_area: int
    geometry_types: list[str]
    bbox: list[float] | None                  # [lon_min, lat_min, lon_max, lat_max]


class LayerIdentifyGroupNode(BaseModel):
    type: Literal["group"] = "group"
    id: uuid.UUID
    name: str
    features_in_area: int
    children: list[LayerIdentifyLayerNode]


class LayerIdentifyResponse(BaseModel):
    tree: list[LayerIdentifyGroupNode | LayerIdentifyLayerNode]


# ---------------------------------------------------------------- version schemas

class VersionListItem(BaseModel):
    id: int
    version: int
    changed_fields: list[str]
    changed_by: uuid.UUID | None
    changed_at: datetime
    message: str | None

    model_config = {"from_attributes": True}


class VersionDetail(BaseModel):
    id: int
    version: int
    snapshot: dict[str, Any]
    changed_fields: list[str]
    changed_by: uuid.UUID | None
    changed_at: datetime
    message: str | None

    model_config = {"from_attributes": True}


class VersionRestoreResponse(BaseModel):
    version: int
    message: str


# ---------------------------------------------------------------- expression schemas

class ExpressionCreate(BaseModel):
    name: str
    description: str | None = None
    expression: dict[str, Any]


class ExpressionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    expression: dict[str, Any] | None = None


class ExpressionResponse(BaseModel):
    id: uuid.UUID
    layer_id: uuid.UUID
    name: str
    description: str | None
    expression: dict[str, Any]
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ExpressionListItem(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
