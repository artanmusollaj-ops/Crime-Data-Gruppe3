"""The console's S3 client behind Cloudflare (srv01, 31.10.2026).

s3.datenwerft.ch is reached through Cloudflare. For suffixes Cloudflare treats
as static files (.gz, .tar, ...) a signed HEAD came back 403 and a signed
ranged GET SignatureDoesNotMatch - while a plain signed GET of the same key
answered correctly. The control backup is a .tar.gz, and it asked with HEAD
before uploading; every worker tick on srv01 failed there. Existence and
metadata are now read with a plain GET whose body is closed unread.
"""

import hashlib
import io

import pytest
from botocore.exceptions import ClientError

from platform_admin.object_store import Objects
from platform_admin.store import AdminError


def error(code, operation):
    return ClientError({"Error": {"Code": code, "Message": code}}, operation)


class BehindCloudflare:
    """HEAD and ranged GET on archive suffixes fail; plain GET and upload work."""

    def __init__(self):
        self.objects = {}
        self.uploads = []

    def head_object(self, Bucket, Key):
        if Key.endswith((".gz", ".tar", ".zip")):
            raise error("403", "HeadObject")
        raise AssertionError("HEAD is not used")

    def get_object(self, Bucket, Key, Range=None):
        if Key not in self.objects:
            raise error("NoSuchKey", "GetObject")
        if Range and Key.endswith((".gz", ".tar", ".zip")):
            raise error("SignatureDoesNotMatch", "GetObject")
        data, metadata = self.objects[Key]
        return {"Body": io.BytesIO(data), "Metadata": metadata, "ETag": '"e"'}

    def upload_file(self, path, bucket, key, ExtraArgs=None):
        with open(path, "rb") as f:
            self.objects[key] = (f.read(), (ExtraArgs or {}).get("Metadata", {}))
        self.uploads.append(key)


def objects():
    o = Objects.__new__(Objects)
    o.client, o.bucket = BehindCloudflare(), "urban-crime"
    return o


def test_a_new_archive_is_uploaded_although_head_would_fail(tmp_path):
    o = objects()
    path = tmp_path / "control.tar.gz"
    path.write_bytes(b"archive")
    o.immutable(path, "backups/control/x.tar.gz")
    assert o.client.uploads == ["backups/control/x.tar.gz"]


def test_the_same_archive_again_is_not_uploaded_twice(tmp_path):
    o = objects()
    path = tmp_path / "control.tar.gz"
    path.write_bytes(b"archive")
    o.immutable(path, "backups/control/x.tar.gz")
    o.immutable(path, "backups/control/x.tar.gz")
    assert o.client.uploads == ["backups/control/x.tar.gz"]


def test_different_bytes_under_the_same_key_are_a_conflict(tmp_path):
    o = objects()
    o.client.objects["backups/control/x.tar.gz"] = (
        b"other", {"sha256": hashlib.sha256(b"other").hexdigest()})
    path = tmp_path / "control.tar.gz"
    path.write_bytes(b"archive")
    with pytest.raises(AdminError, match="Objektkonflikt"):
        o.immutable(path, "backups/control/x.tar.gz")


def test_an_empty_existing_object_is_still_found(tmp_path):
    o = objects()
    empty = hashlib.sha256(b"").hexdigest()
    o.client.objects["backups/control/leer.tar"] = (b"", {"sha256": empty})
    path = tmp_path / "leer.tar"
    path.write_bytes(b"")
    o.immutable(path, "backups/control/leer.tar")
    assert o.client.uploads == []
