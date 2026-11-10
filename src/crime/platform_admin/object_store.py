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

    def metadata(self, key):
        """User metadata of an object, or None if it does not exist.

        A plain GET whose body is closed unread - not HEAD, and not a ranged
        GET. s3.datenwerft.ch sits behind Cloudflare, and for suffixes
        Cloudflare treats as static files (.gz, .tar, .zip, .csv, .pdf, ...)
        a signed HEAD came back 403 and a signed ranged GET
        SignatureDoesNotMatch, while a plain signed GET answered correctly
        (measured on srv01, 31.10.2026). The control backup is a .tar.gz, and
        every worker tick failed on it.
        """
        from botocore.exceptions import ClientError

        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if exc.response["Error"]["Code"] in {"NoSuchKey", "404", "NotFound"}:
                return None
            raise
        response["Body"].close()
        return response.get("Metadata", {})

    def immutable(self, path, key):
        from .candidates import file_hash

        expected = file_hash(path)
        old = self.metadata(key)
        if old is not None:
            if old.get("sha256") != expected:
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

    def holds(self, key, body):
        """True if ``key`` exists in the bucket with exactly these bytes."""
        current, _ = self.read(key)
        return current == body

    def keys(self, prefix):
        """Every key under ``prefix`` that has any version, delete markers included."""
        found = set()
        for page in self.client.get_paginator("list_object_versions").paginate(
            Bucket=self.bucket, Prefix=prefix
        ):
            for entry in page.get("Versions", []) + page.get("DeleteMarkers", []):
                found.add(entry["Key"])
        return sorted(found)

    def remove(self, key):
        """Delete every version of ``key`` for good.

        The bucket on srv01 is versioned: a plain delete only sets a marker and
        the bytes stay. Only deleting each version frees space (see
        storage.backend.Fassung).
        """
        versions = []
        for page in self.client.get_paginator("list_object_versions").paginate(
            Bucket=self.bucket, Prefix=key
        ):
            for entry in page.get("Versions", []) + page.get("DeleteMarkers", []):
                if entry["Key"] == key:
                    versions.append(entry.get("VersionId"))
        for version in versions:
            if version and version != "null":
                self.client.delete_object(Bucket=self.bucket, Key=key, VersionId=version)
            else:
                self.client.delete_object(Bucket=self.bucket, Key=key)


BACKUP_PREFIX = "backups/control/"
# Each worker tick backs up once a day. Seven keeps a week of control states;
# older ones are removed with all their versions after a new one is verified.
BACKUP_KEEP = 7


def backup_keep():
    value = int(os.getenv("ADMIN_BACKUP_KEEP", str(BACKUP_KEEP)))
    if value < 1:
        raise AdminError("ADMIN_BACKUP_KEEP muss mindestens 1 sein")
    return value


def prune_backups(objects, keep, current):
    """Remove all but the ``keep`` newest backups; never the one just written.

    A backup is the pair ``<stamp>.tar.gz`` and ``<stamp>.json``. The stamp
    starts with an ISO time in UTC, so its sort order is its age. Keys under
    the prefix that do not look like such a pair are left alone.
    """
    stamps = {}
    for key in objects.keys(BACKUP_PREFIX):
        name = key[len(BACKUP_PREFIX):]
        for suffix in (".tar.gz", ".json"):
            if name.endswith(suffix) and "/" not in name:
                stamps.setdefault(name[: -len(suffix)], []).append(key)
    ordered = sorted(stamps)
    removed = []
    for stamp in ordered[: max(len(ordered) - keep, 0)]:
        if stamp == current:
            continue
        for key in sorted(stamps[stamp]):
            objects.remove(key)
            removed.append(key)
    return removed


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

    A local release goes into the archive only if the object store does not
    already hold it. Until 10.11.2026 every release went in: each daily archive
    had grown to 1.74 GB, twelve of them filled 11.2 GB of the bucket, the
    bucket went over its quota and turned read-only, and the full data run of
    that day failed on it. The releases were already in the bucket under
    releases/ - release.json goes up last, so a stored release.json with the
    same bytes means the whole release is there. After the new backup is
    verified, only the newest ADMIN_BACKUP_KEEP backups are kept.
    """
    from .operations import record_status
    from .candidates import file_hash

    if objects is None and os.getenv("ADMIN_OBJECT_STORE", "local") == "local":
        import shutil

        class LocalBackup:
            def immutable(self, source, key):
                target = store.data / key
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists() and file_hash(target) != file_hash(source):
                    raise AdminError("Lokaler Backupkonflikt")
                shutil.copyfile(source, target)

            def holds(self, key, body):
                # Locally there is no second copy of a release: always archive it.
                return False

            def keys(self, prefix):
                # ADMIN_OBJECT_STORE=local keeps its backups as files under the data root.
                folder = store.data / prefix
                if not folder.is_dir():
                    return []
                return sorted(prefix + p.name for p in folder.iterdir() if p.is_file())

            def remove(self, key):
                (store.data / key).unlink(missing_ok=True)

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
            archived, in_bucket = [], []
            if releases.is_dir():
                for entry in sorted(releases.iterdir()):
                    manifest = entry / "release.json"
                    if entry.is_dir() and manifest.is_file() and objects.holds(
                        "releases/" + entry.name + "/release.json", manifest.read_bytes()
                    ):
                        in_bucket.append(entry.name)
                        continue
                    archive.add(entry, arcname="releases/" + entry.name)
                    if entry.is_dir():
                        archived.append(entry.name)
        key = BACKUP_PREFIX + stamp + ".tar.gz"
        objects.immutable(path, key)
        info = {
            "key": key,
            "created_at": now(),
            "data_root": str(store.data),
            "sha256": file_hash(path),
            "bytes": path.stat().st_size,
            "weekly": datetime.now(timezone.utc).weekday() == 6,
            # Restore fetches these from releases/ in the bucket (storage.release).
            "releases_in_bucket": in_bucket,
            "releases_archived": archived,
        }
        metadata = tmp / "backup.json"
        metadata.write_text(encode(info))
        objects.immutable(metadata, BACKUP_PREFIX + stamp + ".json")
    info["removed"] = prune_backups(objects, backup_keep(), stamp)
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
