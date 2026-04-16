from pydantic_settings import BaseSettings
from typing import Dict


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

    # Storage
    storage_endpoint: str
    storage_access_key: str
    storage_secret_key: str
    storage_bucket_styles: str = "geo-styles"
    storage_bucket_rasters: str = "geo-rasters"
    storage_bucket_exports: str = "geo-exports"

    # API
    api_secret_key: str = "dev-secret"
    api_debug: bool = False
    api_cors_origins: list[str] = ["http://localhost:5173"]

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
