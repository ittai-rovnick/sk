from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Import all models here so Alembic and relationship resolution can find them.
# Add each new model file as it is created.
from app.models import (  # noqa: F401, E402
    users,
    groups,
    databases,
    layers,
    features,
    permissions,
    symbology,
    rasters,
    audit,
)
