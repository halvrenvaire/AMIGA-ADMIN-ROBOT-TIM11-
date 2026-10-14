"""Penyimpanan file PDF invoice (dan nanti voucher): folder lokal atau bucket S3."""
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import BACKEND_DIR, settings


class StorageError(Exception):
    pass


def _local_path(key: str) -> Path:
    base = (BACKEND_DIR / settings.local_storage_dir).resolve()
    path = (base / key).resolve()
    if base not in path.parents:
        raise StorageError("Lokasi file tidak valid")
    return path


def _s3():
    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key or None,
        aws_secret_access_key=settings.aws_secret_access_key or None,
    )


def save(key: str, data: bytes, content_type: str = "application/pdf") -> None:
    if settings.storage_backend == "s3":
        try:
            _s3().put_object(Bucket=settings.aws_bucket, Key=key, Body=data, ContentType=content_type)
        except (BotoCoreError, ClientError) as e:
            raise StorageError(f"Gagal menyimpan ke S3: {e}") from e
        return
    path = _local_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def load(key: str) -> bytes:
    if settings.storage_backend == "s3":
        try:
            return _s3().get_object(Bucket=settings.aws_bucket, Key=key)["Body"].read()
        except (BotoCoreError, ClientError) as e:
            raise StorageError(f"Gagal membaca dari S3: {e}") from e
    try:
        return _local_path(key).read_bytes()
    except FileNotFoundError as e:
        raise StorageError(f"File tidak ditemukan: {key}") from e
