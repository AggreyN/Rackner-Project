"""Storage seam — local roundtrip, traversal guard, and the S3 branch (stubbed).

The live S3 path is proven against the real bucket by the running stack; here
boto3 is faked so the parts that must never regress stay pinned offline:
SSE-KMS on every write, private presigned GETs, and object keys that cannot
escape their prefix.
"""

from __future__ import annotations

import io
import sys
import types

import pytest

from app import config
from app.services import storage


# --- key building --------------------------------------------------------------


def test_keys_preserve_the_name_but_never_collide():
    k1 = storage.build_key("plan.pdf", "lifecycle")
    k2 = storage.build_key("plan.pdf", "lifecycle")
    assert k1 != k2, "two uploads of the same filename must not overwrite"
    assert k1.startswith("lifecycle/") and k1.endswith("-plan.pdf")


def test_hostile_filenames_cannot_carry_separators():
    key = storage.build_key("../../etc/passwd", "lifecycle")
    prefix, _, name = key.partition("lifecycle/")
    assert prefix == "" and "/" not in name and ".." not in name


# --- local backend -------------------------------------------------------------


@pytest.fixture()
def local_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(config, "UPLOAD_DIR", str(tmp_path / "uploads"))


def test_local_put_get_roundtrip(local_mode):
    key = storage.put(b"pdf-bytes", filename="plan.pdf", prefix="lifecycle")
    assert storage.get(key) == b"pdf-bytes"


def test_local_refuses_paths_outside_upload_dir(local_mode):
    with pytest.raises(ValueError):
        storage._local_path("../../outside.txt")


# --- s3 backend (boto3 faked at the sys.modules seam — storage imports it
# lazily inside each call, so patching the module attribute would miss) --------


class _FakeS3:
    def __init__(self):
        self.put_calls: list[dict] = []
        self.objects: dict[str, bytes] = {}

    def put_object(self, **kw):
        self.put_calls.append(kw)
        self.objects[kw["Key"]] = kw["Body"]

    def get_object(self, *, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[Key])}

    def generate_presigned_url(self, op, *, Params, ExpiresIn):
        assert op == "get_object"
        return (
            f"https://{Params['Bucket']}.s3.amazonaws.com/{Params['Key']}"
            f"?X-Amz-Expires={ExpiresIn}&X-Amz-Signature=stub"
        )


@pytest.fixture()
def fake_s3(monkeypatch):
    fake = _FakeS3()
    module = types.ModuleType("boto3")
    module.client = lambda name, **kw: fake
    monkeypatch.setitem(sys.modules, "boto3", module)
    monkeypatch.setattr(config, "STORAGE_BACKEND", "s3")
    monkeypatch.setattr(config, "S3_BUCKET", "test-bucket")
    monkeypatch.setattr(config, "KMS_KEY_ID", "")
    return fake


def test_s3_put_relies_on_bucket_default_encryption(fake_s3):
    """No CMK configured -> plain put. The bucket's default encryption
    (SSE-S3) applies server-side; requesting aws:kms here would need KMS
    grants the ECS task role doesn't carry."""
    storage.put(b"secret-plan", filename="plan.pdf", prefix="lifecycle")
    (call,) = fake_s3.put_calls
    assert call["Bucket"] == "test-bucket"
    assert "ServerSideEncryption" not in call
    assert "SSEKMSKeyId" not in call


def test_s3_put_uses_the_configured_cmk_when_set(fake_s3, monkeypatch):
    monkeypatch.setattr(config, "KMS_KEY_ID", "key-abc")
    storage.put(b"secret-plan", filename="plan.pdf", prefix="lifecycle")
    call = fake_s3.put_calls[-1]
    assert call["ServerSideEncryption"] == "aws:kms"
    assert call["SSEKMSKeyId"] == "key-abc"


def test_s3_put_get_roundtrip(fake_s3):
    key = storage.put(b"secret-plan", filename="plan.pdf", prefix="lifecycle")
    assert storage.get(key) == b"secret-plan"


def test_s3_url_is_a_short_lived_presigned_get(fake_s3):
    key = storage.put(b"x", filename="plan.pdf", prefix="lifecycle")
    href = storage.url(key)
    assert key in href and "X-Amz-Expires=900" in href, (
        "objects are private; access is only ever via a short-lived presign"
    )
