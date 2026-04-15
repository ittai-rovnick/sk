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


async def upload_lyrx(layer_id: str, file_bytes: bytes, filename: str) -> str:
    """Upload .lyrx file. Returns S3 key."""
    key = f"layers/{layer_id}/{filename}"
    get_client().put_object(
        Bucket=settings.storage_bucket_styles,
        Key=key,
        Body=file_bytes,
    )
    return key


async def get_signed_url(bucket: str, key: str, expires_in: int = 3600) -> str:
    """Generate a pre-signed URL that expires after expires_in seconds."""
    return get_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_in,
    )


async def ensure_buckets_exist() -> None:
    """Run on startup — create buckets if they don't exist."""
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
