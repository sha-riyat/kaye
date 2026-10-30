"""Cloudflare R2 (S3-compatible) storage for logos, receipts and merchant media.

The bucket stays private: WhatsApp fetches receipt images through short-lived presigned URLs.
boto3 is synchronous, so calls run in a worker thread.
"""

import asyncio
import uuid
from functools import cached_property

import boto3
from botocore.config import Config

from app.config import Settings

EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "audio/ogg": "ogg",
    "audio/wav": "wav",
    "application/pdf": "pdf",
}


def media_key(shop_id: int, kind: str, mime_type: str) -> str:
    """`shops/12/receipt/3f2a....png`: grouped by shop so a merchant's files can be listed or wiped."""
    ext = EXTENSIONS.get(mime_type.split(";")[0].strip(), "bin")
    return f"shops/{shop_id}/{kind}/{uuid.uuid4().hex}.{ext}"


class Storage:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.bucket = settings.r2_bucket

    @cached_property
    def _s3(self):
        return boto3.client(
            "s3",
            endpoint_url=f"https://{self._settings.r2_account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=self._settings.r2_access_key_id,
            aws_secret_access_key=self._settings.r2_secret_access_key,
            region_name="auto",
            config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
        )

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self._s3.put_object, Bucket=self.bucket, Key=key, Body=data, ContentType=content_type
        )

    async def get(self, key: str) -> bytes:
        response = await asyncio.to_thread(self._s3.get_object, Bucket=self.bucket, Key=key)
        return await asyncio.to_thread(response["Body"].read)

    def presigned_url(self, key: str, expires_in: int = 3600) -> str:
        return self._s3.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires_in
        )
