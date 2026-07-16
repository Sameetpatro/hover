"""Object storage helpers for MinIO / S3 / local filesystem."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import BinaryIO
from urllib.parse import urlparse

import boto3
from botocore.client import Config
from django.conf import settings


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def ensure_bucket() -> None:
    if settings.USE_LOCAL_STORAGE:
        Path(settings.MEDIA_ROOT).mkdir(parents=True, exist_ok=True)
        return
    client = get_s3_client()
    bucket = settings.AWS_STORAGE_BUCKET_NAME
    try:
        client.head_bucket(Bucket=bucket)
    except Exception:
        client.create_bucket(Bucket=bucket)


def local_path_for_key(key: str) -> Path:
    path = Path(settings.MEDIA_ROOT) / "uploads" / key
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def upload_fileobj(key: str, fileobj: BinaryIO, content_type: str = "application/zip") -> str:
    if settings.USE_LOCAL_STORAGE:
        dest = local_path_for_key(key)
        with dest.open("wb") as out:
            while True:
                chunk = fileobj.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
        return str(dest)

    ensure_bucket()
    client = get_s3_client()
    fileobj.seek(0)
    client.upload_fileobj(
        fileobj,
        settings.AWS_STORAGE_BUCKET_NAME,
        key,
        ExtraArgs={"ContentType": content_type},
    )
    return key


def download_to_path(key: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if settings.USE_LOCAL_STORAGE:
        src = local_path_for_key(key)
        dest.write_bytes(src.read_bytes())
        return dest

    client = get_s3_client()
    client.download_file(settings.AWS_STORAGE_BUCKET_NAME, key, str(dest))
    return dest


def presigned_put_url(key: str, expires: int = 3600) -> str | None:
    if settings.USE_LOCAL_STORAGE:
        return None
    ensure_bucket()
    client = get_s3_client()
    return client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
            "Key": key,
            "ContentType": "application/zip",
        },
        ExpiresIn=expires,
    )


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def rewrite_presigned_for_browser(url: str | None) -> str | None:
    """Rewrite docker-internal MinIO host so the browser can reach it."""
    if not url:
        return url
    public = getattr(settings, "AWS_S3_PUBLIC_URL", None) or None
    # Allow override via env already baked into endpoint for local
    parsed = urlparse(url)
    if parsed.hostname in {"minio", "hover-minio"}:
        public_base = "http://localhost:9000"
        return url.replace(f"{parsed.scheme}://{parsed.netloc}", public_base)
    return url
