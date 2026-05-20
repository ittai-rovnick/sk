from pydantic_settings import BaseSettings
from pydantic import model_validator
from typing import Dict, Optional


def _psycopg_url(url: str) -> str:
    """Coerce a plain postgres:// or postgresql:// URL to postgresql+psycopg://.

    Render (and many other cloud providers) return a standard libpq URL.
    SQLAlchemy needs the driver qualifier so it uses psycopg3 (psycopg).
    """
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


class Settings(BaseSettings):
    # Dev mode — bypasses auth entirely, all requests treated as superadmin
    dev_mode: bool = False

    # Microsoft (optional in dev_mode)
    ms_tenant_id: str = "dev"
    ms_client_id: str = "dev"
    ms_client_secret: str = "dev"

    # Databases
    meta_db_url: str                      # via pgbouncer — API runtime
    meta_db_direct_url: str               # direct — Alembic migrations only
    features_shard_count: int = 1
    features_shard_0_url: str

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Storage (endpoint is optional — omit to use native AWS S3)
    storage_endpoint: Optional[str] = None
    storage_access_key: Optional[str] = None
    storage_secret_key: Optional[str] = None
    storage_bucket_styles: str = "geo-styles"
    storage_bucket_rasters: str = "geo-rasters"
    storage_bucket_exports: str = "geo-exports"

    # API
    api_secret_key: str = "dev-secret"
    api_debug: bool = False
    api_cors_origins: list[str] = ["http://localhost:5173"]

    @model_validator(mode="after")
    def _coerce_db_urls(self) -> "Settings":
        """Convert plain postgres:// URLs (e.g. from Render) to the psycopg dialect."""
        self.meta_db_url = _psycopg_url(self.meta_db_url)
        self.meta_db_direct_url = _psycopg_url(self.meta_db_direct_url)
        self.features_shard_0_url = _psycopg_url(self.features_shard_0_url)
        return self

    @property
    def shard_urls(self) -> Dict[int, str]:
        urls = {}
        for i in range(self.features_shard_count):
            url = getattr(self, f"features_shard_{i}_url")
            urls[i] = url
        return urls

    class Config:
        env_file = ".env"


settings = Settings()
