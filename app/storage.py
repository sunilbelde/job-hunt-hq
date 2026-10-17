import uuid
from datetime import datetime, timezone
from typing import Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


class StorageError(Exception):
    """Raised when an upload or URL signing operation fails."""


class Storage(Protocol):
    def upload(self, content: bytes, content_type: str, extension: str) -> str:
        """Store the content and return its object key."""
        ...

    def presigned_url(self, key: str, ttl_seconds: int) -> str:
        """Return a time-limited GET URL for the key."""
        ...


def build_key(extension: str, now: datetime | None = None) -> str:
    day = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    return f"outputs/{day}/{uuid.uuid4()}.{extension}"


class R2Storage:
    def __init__(
        self, account_id: str, access_key_id: str, secret_access_key: str, bucket: str, client=None
    ):
        self._bucket = bucket
        self._client = client or boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name="auto",
            config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
        )

    def upload(self, content: bytes, content_type: str, extension: str) -> str:
        key = build_key(extension)
        try:
            self._client.put_object(
                Bucket=self._bucket, Key=key, Body=content, ContentType=content_type
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(f"upload failed: {type(exc).__name__}: {exc}") from exc
        return key

    def presigned_url(self, key: str, ttl_seconds: int) -> str:
        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=ttl_seconds,
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(f"signing failed: {type(exc).__name__}: {exc}") from exc
