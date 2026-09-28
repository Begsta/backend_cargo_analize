import io
import json
import uuid
from pathlib import Path

import urllib3
from minio import Minio
from minio.error import S3Error

from core.config import settings

IMAGE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/pjpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
VIDEO_EXTENSIONS = {
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
}
MAX_FILE_BYTES = 30 * 1024 * 1024

_client: Minio | None = None


class StorageError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


def get_minio() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
            http_client=urllib3.PoolManager(
                timeout=urllib3.util.Timeout(connect=3.0, read=20.0),
                retries=urllib3.Retry(total=1, connect=1),
            ),
        )
    return _client


def ensure_bucket() -> None:
    client = get_minio()
    bucket = settings.MINIO_BUCKET
    try:
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{bucket}/*"],
                }
            ],
        }
        client.set_bucket_policy(bucket, json.dumps(policy))
    except S3Error as exc:
        raise StorageError("Не удалось подготовить бакет MinIO") from exc


def public_media_url(stored_name: str | None) -> str:
    if not stored_name:
        return ""
    if stored_name.startswith(("http://", "https://", "/")):
        return stored_name
    return f"{settings.MINIO_PUBLIC_BASE}/{stored_name}"


def extension_for(kind: str, content_type: str | None, filename: str | None) -> str:
    table = IMAGE_EXTENSIONS if kind == "image" else VIDEO_EXTENSIONS
    normalized = (content_type or "").split(";")[0].strip().lower()
    if normalized in table:
        return table[normalized]
    suffix = Path(filename or "").suffix.lower()
    if suffix == ".jpeg":
        suffix = ".jpg"
    if suffix in set(table.values()):
        return suffix
    title = "изображения" if kind == "image" else "видео"
    raise StorageError(f"Неподдерживаемый тип {title}")


def latin_object_name(kind: str, extension: str) -> str:
    """Имя объекта на латинице. Исходное имя файла клиента не используется."""
    object_name = f"{kind}-{uuid.uuid4().hex}{extension}"
    if not object_name.isascii():
        raise StorageError("Имя файла должно быть на латинице")
    return object_name


def upload_bytes(object_name: str, data: bytes, content_type: str) -> None:
    if not object_name.isascii():
        raise StorageError("Имя файла должно быть на латинице")
    if len(data) > MAX_FILE_BYTES:
        raise StorageError("Файл больше 30 МБ")
    ensure_bucket()
    try:
        get_minio().put_object(
            settings.MINIO_BUCKET,
            object_name,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type or "application/octet-stream",
        )
    except S3Error as exc:
        raise StorageError("Не удалось сохранить файл в MinIO") from exc
