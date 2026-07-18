"""Save and load ZIP files (local disk or S3/MinIO)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import urlparse

import boto3
from botocore.client import Config

from app.config import get_settings


def _local_path(key: str) -> Path:
    settings = get_settings()
    path = Path(settings.media_root) / "uploads" / key
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _s3():
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.aws_s3_endpoint_url,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_s3_region_name,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def ensure_bucket() -> None:
    settings = get_settings()
    if settings.use_local_storage:
        Path(settings.media_root).mkdir(parents=True, exist_ok=True)
        return
    client = _s3()
    bucket = settings.aws_storage_bucket_name
    try:
        client.head_bucket(Bucket=bucket)
    except Exception:
        client.create_bucket(Bucket=bucket)


def save_bytes(key: str, data: bytes, content_type: str = "application/zip") -> None:
    settings = get_settings()
    if settings.use_local_storage:
        path = _local_path(key)
        path.write_bytes(data)
        return
    ensure_bucket()
    _s3().put_object(
        Bucket=settings.aws_storage_bucket_name,
        Key=key,
        Body=data,
        ContentType=content_type,
    )


def download_to(key: str, dest: Path) -> Path:
    settings = get_settings()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if settings.use_local_storage:
        dest.write_bytes(_local_path(key).read_bytes())
        return dest
    _s3().download_file(settings.aws_storage_bucket_name, key, str(dest))
    return dest


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_join(root: Path, name: str) -> Path | None:
    cleaned = name.replace("\\", "/").lstrip("/")
    if ".." in Path(cleaned).parts:
        return None
    full = (root / cleaned).resolve()
    try:
        full.relative_to(root.resolve())
    except ValueError:
        return None
    return full
