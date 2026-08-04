"""File storage — local filesystem in dev, S3 in prod.

Selected by STORAGE_BACKEND. Identical call signatures either way, so nothing
upstream knows which one is live:

    key = put(data, filename="plan.pdf", prefix="lifecycle")
    blob = get(key)
    href = url(key)

S3 mode writes with SSE-KMS and hands out short-lived presigned GETs — objects
are never public. Local mode writes under UPLOAD_DIR and returns a file path.
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

from app import config

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_name(filename: str) -> str:
    """Strip anything that could escape the prefix (path traversal, separators)."""
    name = os.path.basename(filename or "upload")
    name = _SAFE.sub("_", name).strip("._-") or "upload"
    return name[:200]


def build_key(filename: str, prefix: str = "") -> str:
    """A collision-proof object key that preserves the original name."""
    unique = uuid.uuid4().hex[:12]
    safe = _safe_name(filename)
    return f"{prefix.strip('/')}/{unique}-{safe}" if prefix else f"{unique}-{safe}"


def _local_path(key: str) -> Path:
    root = Path(config.UPLOAD_DIR).resolve()
    target = (root / key).resolve()
    # Refuse anything that resolves outside UPLOAD_DIR.
    if not str(target).startswith(str(root)):
        raise ValueError("Refusing to write outside UPLOAD_DIR")
    return target


def put(data: bytes, *, filename: str, prefix: str = "") -> str:
    """Store bytes; return the storage key."""
    key = build_key(filename, prefix)
    if config.STORAGE_BACKEND == "s3":
        import boto3

        # The provisioned bucket enforces default encryption (SSE-S3), so a
        # plain put is already encrypted at rest. Request SSE-KMS only when a
        # CMK is configured — sending "aws:kms" unconditionally needs KMS
        # grants the task role doesn't carry.
        extra = {}
        if config.KMS_KEY_ID:
            extra = {
                "ServerSideEncryption": "aws:kms",
                "SSEKMSKeyId": config.KMS_KEY_ID,
            }
        boto3.client("s3", region_name=config.AWS_REGION).put_object(
            Bucket=config.S3_BUCKET, Key=key, Body=data, **extra
        )
        return key

    path = _local_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return key


def get(key: str) -> bytes:
    if config.STORAGE_BACKEND == "s3":
        import boto3

        obj = boto3.client("s3", region_name=config.AWS_REGION).get_object(
            Bucket=config.S3_BUCKET, Key=key
        )
        return obj["Body"].read()
    return _local_path(key).read_bytes()


def url(key: str, *, expires_in: int = 900) -> str:
    """A presigned GET in S3 mode; a plain path in local mode."""
    if config.STORAGE_BACKEND == "s3":
        import boto3

        return boto3.client("s3", region_name=config.AWS_REGION).generate_presigned_url(
            "get_object",
            Params={"Bucket": config.S3_BUCKET, "Key": key},
            ExpiresIn=expires_in,
        )
    return str(_local_path(key))
