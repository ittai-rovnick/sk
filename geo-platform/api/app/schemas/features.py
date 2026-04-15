import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel


class FeatureCreate(BaseModel):
    geom: dict[str, Any]      # GeoJSON geometry object
    properties: dict[str, Any] = {}


class FeatureUpdate(BaseModel):
    geom: dict[str, Any] | None = None
    properties: dict[str, Any] | None = None
    version: int              # Required for optimistic locking


class FeatureResponse(BaseModel):
    id: int
    layer_id: uuid.UUID
    geom: dict[str, Any]
    properties: dict[str, Any]
    version: int
    created_by: str | None
    updated_by: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BboxQuery(BaseModel):
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float
    limit: int = 1000
    offset: int = 0
