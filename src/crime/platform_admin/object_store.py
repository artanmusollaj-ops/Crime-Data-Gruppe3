"""SeaweedFS/S3 durability, conditional active pointer and recoverable backups.

One host owns the control database. Never place SQLite on an S3/FUSE mount.
No remote candidate is active until every release object is verified.
"""

import hashlib
from datetime import datetime, timezone
import json
import os
import sqlite3
import tarfile
import tempfile
import uuid
from pathlib import Path

from .store import AdminError, encode, now
from .runtime import secret


class Objects:
    def __init__(self):
        import boto3
        from botocore.config import Config

        endpoint = os.getenv("ADMIN_S3_ENDPOINT") or os.getenv("S3_ENDPOINT", "")
        if endpoint and "://" not in endpoint:
            endpoint = ("https://" if os.getenv("S3_USE_SSL", "true").lower() == "true" else "http://") + endpoint
        self.bucket = os.getenv("S3_BUCKET", "")
        if not endpoint or not self.bucket:
            raise AdminError("ADMIN_S3_ENDPOINT und S3_BUCKET erforderlich")
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=secret("S3_ACCESS_KEY"),
            aws_secret_access_key=secret("S3_SECRET_KEY"),
            region_name="us-east-1",
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                connect_timeout=10,
                read_timeout=60,
            ),
        )

    def read(self, key):
        from botocore.exceptions import ClientError

        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read(), response["ETag"]
        except ClientError as exc:
            if exc.response["Error"]["Code"] in {"NoSuchKey", "404", "NotFound"}:
                return None, None
            raise

    def immutable(self, path, key):
        from botocore.exceptions import ClientError
        from .candidates import file_hash

        expected = file_hash(path)
        try:
            old = self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if exc.response["Error"]["Code"] not in {"NoSuchKey", "404", "NotFound"}:
                raise
            old = None
        if old:
            if old.get("Metadata", {}).get("sha256") != expected:
                raise AdminError("Objektkonflikt: " + key)
        else:
            # Multipart transfer supports releases larger than a single S3 PUT.
            self.client.upload_file(
                str(path), self.bucket, key, ExtraArgs={"Metadata": {"sha256": expected}}
            )
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        digest = hashlib.sha256()
        try:
            for block in iter(lambda: response["Body"].read(1 << 20), b""):
                digest.update(block)
        finally:
            response["Body"].close()
        if digest.hexdigest() != expected:
            raise AdminError("S3-Pruefsumme abweichend: " + key)

    def pointer(self, key, body, etag):
        condition = {"IfMatch": etag} if etag else {"IfNoneMatch": "*"}
        self.client.put_object(
            Bucket=self.bucket, Key=key, Body=body, ContentType="application/json", **condition
        )


def publish_release(store, target, baseline, objects=None):
    from .candidates import verify_release
    from storage.release import zeiger

    objects = objects or Objects()
    manifest = verify_release(target)
    current, etag = objects.read("releases/AKTUELL.json")
    remote = json.loads(current)["release_id"] if current else None
    if remote not in {baseline, manifest["release_id"]}:
        raise AdminError("SeaweedFS-Releasebasis weicht ab; keine Ueberschreibung")
    prefix = "releases/" + target.name + "/"
    for rel in sorted(manifest["files"]):
        objects.immutable(target / rel, prefix + rel)
    objects.immutable(target / "release.json", prefix + "release.json")
    if remote != manifest["release_id"]:
        objects.pointer("releases/AKTUELL.json", encode(zeiger(manifest)).encode(), etag)


def archive_inputs(store, objects=None):
    """Archive completed Raw/Bronze runs; do not publish working Silver/Gold."""
    objects = objects or Objects()
    for layer in ("raw", "bronze"):
        root = store.data / layer
        for manifest in sorted(root.rglob("manifest.json")):
            try:
                complete = json.loads(manifest.read_text())["status"] in {"complete", "success"}
            except (ValueError, KeyError):
                complete = False
            if not complete:
                continue
            files = [
                p
                for p in manifest.parent.rglob("*")
                if p.is_file() and p != manifest and not p.name.endswith(".part")
            ]
            for p in sorted(files) + [manifest]:
                if p.is_symlink():
                    raise AdminError("Symlink im Quelldatenlauf")
                objects.immutable(p, p.relative_to(store.data).as_posix())


def backup(store, objects=None):
    """Consistent SQLite online backup plus all candidate/audit recovery files.

    Caller holds writer_lock. Web submissions may continue: SQLite's snapshot
    defines the cut. Extra files are harmless; no mutable pipeline writes run.
    """
    from .operations import record_status
    from .candidates import file_hash

    if objects is None and os.getenv("ADMIN_OBJECT_STORE", "local") == "local":
        from .candidates import file_hash
        import shutil

        class LocalBackup:
            def immutable(self, source, key):
                target = store.data / key
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists() and file_hash(target) != file_hash(source):
                    raise AdminError("Lokaler Backupkonflikt")
                shutil.copyfile(source, target)

        objects = LocalBackup()
    objects = objects or Objects()
    stamp = now().replace(":", "-") + "-" + uuid.uuid4().hex[:8]
    with tempfile.TemporaryDirectory(dir=store.root) as tmp:
        tmp = Path(tmp)
        dbfile = tmp / "control.sqlite"
        source = sqlite3.connect(store.path)
        destination = sqlite3.connect(dbfile)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        path = tmp / "control.tar.gz"
        with tarfile.open(path, "w:gz") as archive:
            archive.add(dbfile, arcname="admin/control.sqlite")
            for folder in ("jobs", "config_versions", "impact_archive", "serving"):
                if (store.root / folder).exists():
                    archive.add(store.root / folder, arcname="admin/" + folder)
            if (store.root / "managed.json").exists():
                archive.add(store.root / "managed.json", arcname="admin/managed.json")
            # lokal mit Absicht: the console keeps its releases on the worker host;
            # object_store.publish_release mirrors them to S3 and never removes the local copy.
            releases = store.data / "releases"
            if releases.exists():
                archive.add(releases, arcname="releases")
        key = "backups/control/" + stamp + ".tar.gz"
        objects.immutable(path, key)
        info = {
            "key": key,
            "created_at": now(),
            "data_root": str(store.data),
            "sha256": file_hash(path),
            "weekly": datetime.now(timezone.utc).weekday() == 6,
        }
        metadata = tmp / "backup.json"
        metadata.write_text(encode(info))
        objects.immutable(metadata, "backups/control/" + stamp + ".json")
    record_status(store, "backup", info)
    return info


def restore_archive(archive_path, destination):
    """Offline restore into EMPTY destination. Keep original /data path in Compose."""
    destination = Path(destination)
    if destination.exists() and any(destination.iterdir()):
        raise AdminError("Restore-Ziel muss leer sein")
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive.getmembers():
            path = (destination / member.name).resolve()
            if (
                not path.is_relative_to(destination.resolve())
                or member.issym()
                or member.islnk()
                or not (member.isfile() or member.isdir())
            ):
                raise AdminError("Unsicherer Backup-Eintrag")
        archive.extractall(destination, filter="data")
    db = sqlite3.connect(destination / "admin/control.sqlite")
    try:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise AdminError("Wiederhergestellte Kontrolldatenbank ist beschaedigt")
    finally:
        db.close()
    return str(destination)
