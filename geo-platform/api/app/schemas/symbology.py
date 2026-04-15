import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel


class StyleCreate(BaseModel):
    name: str = "default"
    renderer: dict[str, Any] = {}
    label_config: dict[str, Any] | None = None
    popup_config: dict[str, Any] | None = None
    is_default: bool = False


class StyleUpdate(BaseModel):
    renderer: dict[str, Any] | None = None
    label_config: dict[str, Any] | None = None
    popup_config: dict[str, Any] | None = None
    is_default: bool | None = None


class StyleResponse(BaseModel):
    id: uuid.UUID
    layer_id: uuid.UUID
    name: str
    renderer: dict[str, Any]
    label_config: dict[str, Any] | None
    popup_config: dict[str, Any] | None
    is_default: bool
    lyrx_s3_key: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
