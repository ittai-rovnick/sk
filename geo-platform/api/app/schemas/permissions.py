import uuid
from datetime import datetime
from pydantic import BaseModel, model_validator


class PermissionGrant(BaseModel):
    ms_user_id: str | None = None
    ms_group_id: str | None = None
    database_id: uuid.UUID | None = None
    group_layer_id: uuid.UUID | None = None
    layer_id: uuid.UUID | None = None
    role_id: uuid.UUID
    allow: bool = True

    @model_validator(mode="after")
    def check_principal_and_resource(self) -> "PermissionGrant":
        principals = [self.ms_user_id, self.ms_group_id]
        if sum(p is not None for p in principals) != 1:
            raise ValueError("Exactly one of ms_user_id or ms_group_id must be set")
        resources = [self.database_id, self.group_layer_id, self.layer_id]
        if sum(r is not None for r in resources) != 1:
            raise ValueError("Exactly one of database_id, group_layer_id, or layer_id must be set")
        return self


class PermissionResponse(BaseModel):
    id: uuid.UUID
    ms_user_id: str | None
    ms_group_id: str | None
    database_id: uuid.UUID | None
    group_layer_id: uuid.UUID | None
    layer_id: uuid.UUID | None
    role_id: uuid.UUID
    allow: bool
    granted_at: datetime

    model_config = {"from_attributes": True}
