"""
Object storage client (MinIO, S3-compatible).

All large binary artifacts (uploaded datasets, results, previews) live in an
object store instead of the API's local filesystem. This is what lets a job be
processed by a temporary worker container on a different machine: the worker
only needs the object key and the store's network address, not a shared disk.

The API keeps a local cache of files it has recently read (for fast slice
serving), but the object store is always the source of truth. Swapping MinIO
for real AWS S3 later only requires changing the endpoint/credentials env vars,
since both speak the same S3 API.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from minio import Minio
from minio.error import S3Error

load_dotenv()

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "beadbuddy")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=MINIO_SECURE,
)


def ensure_bucket() -> None:
    """Create the working bucket if it does not exist yet. Safe to call often."""
    if not _client.bucket_exists(MINIO_BUCKET):
        _client.make_bucket(MINIO_BUCKET)


def upload_path(local_path: Path, object_key: str) -> str:
    """Upload a local file to the store and return the object key it was stored under."""
    ensure_bucket()
    _client.fput_object(MINIO_BUCKET, object_key, str(local_path))
    return object_key


def download_to_path(object_key: str, destination: Path) -> Path:
    """Download an object to a local path, creating parent directories as needed."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    _client.fget_object(MINIO_BUCKET, object_key, str(destination))
    return destination


def object_exists(object_key: str) -> bool:
    try:
        _client.stat_object(MINIO_BUCKET, object_key)
        return True
    except S3Error:
        return False


def ensure_local_copy(object_key: str, cache_path: Path) -> Path:
    """Return a local path for an object, downloading it only if not already cached."""
    if not cache_path.exists():
        download_to_path(object_key, cache_path)
    return cache_path
