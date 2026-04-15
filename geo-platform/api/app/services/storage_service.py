import asyncio
import boto3
from app.config import settings

_client = None


def get_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=settings.storage_endpoint,
            aws_access_key_id=settings.storage_access_key,
            aws_secret_access_key=settings.storage_secret_key,
        )
    return _client


def _upload_lyrx_sync(layer_id: str, file_bytes: bytes, filename: str) -> str:
    key = f"layers/{layer_id}/{filename}"
    get_client().put_object(
        Bucket=settings.storage_bucket_styles,
        Key=key,
        Body=file_bytes,
    )
    return key


def _get_signed_url_sync(bucket: str, key: str, expires_in: int) -> str:
    return get_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_in,
    )


def _ensure_buckets_sync() -> None:
    client = get_client()
    for bucket in [
        settings.storage_bucket_styles,
        settings.storage_bucket_rasters,
        settings.storage_bucket_exports,
    ]:
        try:
            client.head_bucket(Bucket=bucket)
        except Exception:
            client.create_bucket(Bucket=bucket)


async def upload_lyrx(layer_id: str, file_bytes: bytes, filename: str) -> str:
    """Upload .lyrx file. Returns S3 key."""
    return await asyncio.to_thread(_upload_lyrx_sync, layer_id, file_bytes, filename)


async def get_signed_url(bucket: str, key: str, expires_in: int = 3600) -> str:
    """Generate a pre-signed URL that expires after expires_in seconds."""
    return await asyncio.to_thread(_get_signed_url_sync, bucket, key, expires_in)


async def ensure_buckets_exist() -> None:
    """Run on startup — create buckets if they don't exist."""
    await asyncio.to_thread(_ensure_buckets_sync)
