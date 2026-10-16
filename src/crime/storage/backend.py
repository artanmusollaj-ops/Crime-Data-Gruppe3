"""Die Ablage: lokal, SeaweedFS ueber S3, oder beides (hybrid).

Lesen im Hybridmodus: **lokal zuerst, sonst S3.** Schreiben: **lokal,
pruefen, dann publizieren.** Kein Dual-Write, keine Synchronisation in beide
Richtungen. Das lokale Verzeichnis ist Arbeitskopie und Cache; SeaweedFS ist
der gemeinsame veroeffentlichte Bestand.

**Geholt** wird seit dem 17.9.2026, was unveraenderlich ist: Raw- und
Bronze-Laeufe (``hole_fehlende_laeufe``) und Releases (``storage.release``).
Silver und Gold werden weiterhin gelesen, nicht kopiert - ein stiller Cache
waere eine zweite Wahrheit mit eigenem Alter.

Publizieren ist gezielt: die Dateien **eines** Laufs oder **einer** Tabelle,
``manifest.json`` zuletzt - so ist das Manifest auf S3 das Zeichen, dass ein
Lauf vollstaendig oben ist, genau wie das Umbenennen lokal.

Zwei Sorten Ziele:

* **Unveraenderliche Laeufe** (``run_<id>``): existiert ein Objekt schon und
  ist identisch, wird es uebersprungen; existiert es mit anderem Inhalt,
  ist das ein Fehler. Nichts wird still ueberschrieben.
* **Abgeleitete Tabellen** (``silver/dataset=...``, ``gold/dataset=...``):
  lokal werden sie ersetzt, nicht angehaeuft (siehe ``silver_pipeline``).
  Auf S3 gilt dasselbe - **sie werden ueberschrieben.** Das Manifest nennt die
  Bronze-Laeufe, aus denen der Stand entstand.

Nach jedem Upload wird das Objekt zurueckgelesen: Existenz und Groesse
immer, die MD5-Pruefsumme gegen das ETag, wo der Dienst eines liefert.

**Der veraltete lokale Stand.** Die Regel "lokal zuerst" hat eine scharfe
Kante: Wer eine Silver- oder Gold-Tabelle von letzter Woche herumliegen hat,
liest sie - auch wenn auf SeaweedFS eine neuere liegt, und ohne es zu merken.
Und veroeffentlicht er sie, verdraengt sein alter Stand den neuen. Deshalb
vergleicht die Ablage bei abgeleiteten Tabellen beide Manifeste:

* **Beim Lesen** eine Warnung, wenn die lokale aelter ist - gelesen wird
  trotzdem lokal, denn das ist die Regel.
* **Beim Publizieren** eine Absage, wenn der eigene Stand aelter ist oder auf
  weniger Bronze-Laeufen ruht. Wer wirklich zurueckdrehen will, sagt
  ``erzwingen=True``.

Verglichen wird ``built_at_utc`` (tragen alle neun Tabellen) und die
Lauf-Kennungen aus ``derived_from``. Gold nennt dort Silver-Tabellen statt
Laeufe; fuer Gold zaehlt deshalb nur der Zeitpunkt.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import time
from collections.abc import Iterable
from datetime import datetime, timezone
from fnmatch import translate as glob_translate
from pathlib import Path
from typing import Any, NamedTuple, Protocol

from manifeste import (
    FERTIG,
    MANIFEST,
    Lauf,
    Tabelle,
    fertige_laeufe,
    read_manifest,
    tabellen,
)
from storage import paths
from storage.config import Config


LOG = logging.getLogger("storage")

MD5 = re.compile(r"^[0-9a-f]{32}$")

# Schichten, die ersetzt statt angehaeuft werden - nur fuer sie ist die Frage
# "wessen Stand ist neuer?" ueberhaupt sinnvoll. Laeufe sind unveraenderlich.
ABGELEITET = ("silver", "gold")

# Die Schichten der Strecke, in der Reihenfolge, in der sie entstehen - die
# kanonische Liste. Bis zum 4.10.2026 stand sie dreimal im Projekt und keine
# zwei Fassungen waren gleich: ``storage/__main__.py`` kannte ``raw`` und
# ``bronze``, ``serving/build_analysis_db.py`` und ``tools/build_feldkatalog.py``
# kannten ``silver``, ``gold`` und ``serving``. Keine davon war falsch - jede
# war der Ausschnitt, den ihr Aufrufer braucht -, aber keine liess sich fragen,
# *welche* Schichten es gibt. Genau das braucht ``orchestration.platzbedarf``,
# um die Belegung je Schicht zu messen. Die drei Ausschnitte stehen weiter bei
# ihren Benutzern, aber als Auswahl aus dieser Liste.
SCHICHTEN = ("raw", "bronze", "silver", "gold", "serving", "releases")

#: Die Schichten, die aus unveraenderlichen Laeufen bestehen und anhaeufen.
LAUFSCHICHTEN = ("raw", "bronze")

#: Die Schichten, die Tabellen fuehren - ersetzt, nicht angehaeuft. ``serving``
#: steht dabei, obwohl es nichts entwertet: Es traegt die vier
#: Vergleichstabellen aus ``build_comparison``, und sie sind Tabellen wie jede
#: andere. ``ABGELEITET`` ist die engere Menge - nur dort ist der
#: Standvergleich sinnvoll.
TABELLENSCHICHTEN = ("silver", "gold", "serving")


class StorageError(RuntimeError):
    """Die Ablage ist nicht erreichbar oder lehnt ab - ohne Traceback aus boto3."""


class PublishError(StorageError):
    """Etwas konnte nicht nach SeaweedFS - oder liegt dort schon anders."""


class Objekt(NamedTuple):
    key: str
    size: int
    etag: str


class S3Client(Protocol):
    """Das Wenige, das die Ablage von S3 braucht."""

    def head(self, key: str) -> Objekt | None: ...
    def get(self, key: str) -> bytes: ...
    def put(self, key: str, daten: bytes) -> None: ...
    def list(self, prefix: str) -> list[Objekt]: ...
    def delete(self, key: str) -> None: ...


# Vor dem ersten Nachpublizieren antwortete SeaweedFS auf ein HEAD einmal mit
# 403 - und Sekunden spaeter auf denselben Schluessel mit 404. Solche Aussetzer
# (403, 5xx, Verbindungsabbruch) werden ein paarmal mit Pause wiederholt, bevor
# sie ein Fehler sind. boto3 wiederholt 403 von sich aus nicht.
VERSUCHE = 4
PAUSEN = (1.0, 3.0, 8.0)
VORUEBERGEHEND = {"403", "AccessDenied", "500", "502", "503", "504",
                  "InternalError", "ServiceUnavailable", "SlowDown", "RequestTimeout"}


def fehlerkennung(fehler: Exception) -> str:
    """Wie ein Transportfehler im Protokoll heisst - der Code, nicht die Klasse.

    Bis zum 5.10.2026 schrieb die Wiederholungswarnung
    ``type(fehler).__name__``, also "ClientError" - und so heisst *jeder*
    abgelehnte boto-Aufruf. Damit war die Drosselung des Endpunkts (403 auf
    einen vorhandenen, aber dicht abgefragten Schluessel) nicht von einem
    fehlenden Schluessel zu unterscheiden, und die Fehlersuche am 5.10.2026
    lief zweimal in die falsche Richtung, bevor eine Messung die Drosselung
    zeigte. Seither nennt die Warnung den Code und, wo boto einen mitgibt,
    den HTTP-Status.
    """
    from botocore.exceptions import ClientError

    if isinstance(fehler, ClientError):
        antwort = fehler.response or {}
        code = str(antwort.get("Error", {}).get("Code", "")) or "ohne Code"
        status = (antwort.get("ResponseMetadata") or {}).get("HTTPStatusCode")
        return f"{code} (HTTP {status})" if status else code
    return type(fehler).__name__


class Boto3Client:
    """S3 ueber boto3, path-style, gegen den konfigurierten Endpoint."""

    def __init__(self, config: Config) -> None:
        import boto3
        from botocore.config import Config as BotoConfig

        self.bucket = config.s3_bucket
        self.endpoint_url = config.endpoint_url
        self._client = boto3.client(
            "s3",
            endpoint_url=config.endpoint_url,
            aws_access_key_id=config.s3_access_key,
            aws_secret_access_key=config.s3_secret_key,
            region_name="us-east-1",
            config=BotoConfig(
                s3={"addressing_style": "path"}, signature_version="s3v4",
                retries={"max_attempts": 4, "mode": "standard"},
            ),
        )

    def _mit_wiederholung(self, was: str, aufruf):
        """Fuehrt ``aufruf()`` aus; voruebergehende Fehler werden wiederholt."""
        from botocore.exceptions import BotoCoreError, ClientError

        for versuch in range(VERSUCHE):
            try:
                return aufruf()
            except ClientError as fehler:
                code = str(fehler.response.get("Error", {}).get("Code", ""))
                if code in ("404", "NoSuchKey", "NotFound"):
                    raise
                letzter = fehler
                if code not in VORUEBERGEHEND:
                    break
            except BotoCoreError as fehler:
                letzter = fehler
            if versuch < VERSUCHE - 1:
                LOG.warning("SeaweedFS: %s bei %s - Versuch %d von %d, Pause %.0f s",
                            fehlerkennung(letzter), was, versuch + 1, VERSUCHE, PAUSEN[versuch])
                time.sleep(PAUSEN[versuch])
        raise self._uebersetzt(letzter, was) from letzter

    def _uebersetzt(self, fehler: Exception, was: str) -> StorageError:
        """Ein boto-Fehler als ein Satz - Endpoint und Ursache, keine Schluessel."""
        from botocore.exceptions import ClientError, EndpointConnectionError

        if isinstance(fehler, EndpointConnectionError):
            return StorageError(
                f"SeaweedFS nicht erreichbar: {self.endpoint_url} ({was}). "
                "Stimmt S3_ENDPOINT, und loest der Hostname auf? "
                "'python -m storage' prueft die Verbindung."
            )
        if isinstance(fehler, ClientError):
            code = str(fehler.response.get("Error", {}).get("Code", "?"))
            return StorageError(
                f"SeaweedFS lehnt ab: {code} bei {was} auf {self.endpoint_url}, "
                f"Bucket {self.bucket!r}. Bei AccessDenied/InvalidAccessKeyId/"
                "SignatureDoesNotMatch die Schluessel pruefen, bei NoSuchBucket den Bucket."
            )
        return StorageError(f"SeaweedFS: {type(fehler).__name__} bei {was}: {fehler}")

    def head(self, key: str) -> Objekt | None:
        from botocore.exceptions import ClientError

        try:
            antwort = self._mit_wiederholung(
                f"HEAD {key}", lambda: self._client.head_object(Bucket=self.bucket, Key=key))
        except ClientError as fehler:
            code = str(fehler.response.get("Error", {}).get("Code", ""))
            if code in ("404", "NoSuchKey", "NotFound"):
                return None
            raise self._uebersetzt(fehler, f"HEAD {key}") from fehler
        return Objekt(key, int(antwort["ContentLength"]), antwort.get("ETag", ""))

    def get(self, key: str) -> bytes:
        from botocore.exceptions import ClientError

        try:
            return self._mit_wiederholung(
                f"GET {key}",
                lambda: self._client.get_object(Bucket=self.bucket, Key=key)["Body"].read())
        except ClientError as fehler:
            raise self._uebersetzt(fehler, f"GET {key}") from fehler

    def put(self, key: str, daten: bytes) -> None:
        self._mit_wiederholung(
            f"PUT {key}",
            lambda: self._client.put_object(Bucket=self.bucket, Key=key, Body=daten))

    def list(self, prefix: str) -> list[Objekt]:
        def alle() -> list[Objekt]:
            gefunden: list[Objekt] = []
            paginator = self._client.get_paginator("list_objects_v2")
            for seite in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                for eintrag in seite.get("Contents", []):
                    gefunden.append(Objekt(eintrag["Key"], int(eintrag["Size"]),
                                           eintrag.get("ETag", "")))
            return gefunden

        return self._mit_wiederholung(f"LIST {prefix}", alle)

    def delete(self, key: str) -> None:
        # S3 antwortet auf DELETE eines fehlenden Schluessels mit 204, nicht
        # mit 404 - loeschen ist damit wiederholbar. Das traegt
        # ``Storage.entferne_oben``: Ein Abbruch mitten im Praefix laesst sich
        # durch einen zweiten Lauf zu Ende bringen.
        self._mit_wiederholung(
            f"DELETE {key}",
            lambda: self._client.delete_object(Bucket=self.bucket, Key=key))


class FakeS3Client:
    """Ein S3 im Speicher - fuer Tests, ohne Netz und ohne SeaweedFS.

    ``anfragen`` haelt jede gestellte Anfrage in der Reihenfolge, in der sie
    gestellt wurde (``"HEAD <key>"``, ``"LIST <prefix>"``, ``"GET <key>"``,
    ``"PUT <key>"``, ``"DELETE <key>"``). Damit laesst sich **zaehlen**, nicht
    nur pruefen - genau das brauchte der Nachweis, dass ``publish_files`` ein
    ``list`` je Praefix stellt und kein ``HEAD`` je Datei.
    """

    def __init__(self) -> None:
        self.objekte: dict[str, bytes] = {}
        self.uploads: list[str] = []
        self.geloescht: list[str] = []
        self.anfragen: list[str] = []

    def _objekt(self, key: str) -> Objekt | None:
        """Die Auskunft zu einem Schluessel - dieselbe fuer ``head`` und ``list``.

        Beide Wege sagen dasselbe ueber dasselbe Objekt, so wie bei S3:
        ``ListObjectsV2`` nennt ``Size`` und ``ETag`` je Eintrag, und es sind
        dieselben Werte, die ein ``HeadObject`` liefert. Wer im Test ein
        eigenwilliges ETag braucht, ueberschreibt deshalb **diese** Stelle -
        nicht ``head``, sonst zeigten die beiden Wege Verschiedenes.
        """
        if key not in self.objekte:
            return None
        daten = self.objekte[key]
        return Objekt(key, len(daten), '"' + hashlib.md5(daten).hexdigest() + '"')

    def head(self, key: str) -> Objekt | None:
        self.anfragen.append(f"HEAD {key}")
        return self._objekt(key)

    def get(self, key: str) -> bytes:
        self.anfragen.append(f"GET {key}")
        return self.objekte[key]

    def put(self, key: str, daten: bytes) -> None:
        self.anfragen.append(f"PUT {key}")
        self.objekte[key] = bytes(daten)
        self.uploads.append(key)

    def list(self, prefix: str) -> list[Objekt]:
        # Eine Anfrage, wie bei ``Boto3Client.list`` - kein ``HEAD`` je Eintrag.
        self.anfragen.append(f"LIST {prefix}")
        return [self._objekt(k) for k in sorted(self.objekte) if k.startswith(prefix)]  # type: ignore[misc]

    def delete(self, key: str) -> None:
        # Wie S3: ein fehlender Schluessel ist kein Fehler.
        self.anfragen.append(f"DELETE {key}")
        self.objekte.pop(key, None)
        self.geloescht.append(key)


def zeitpunkt(manifest: dict[str, Any]) -> datetime | None:
    """Wann diese Tabelle gebaut wurde. Alle neun tragen ``built_at_utc``."""
    roh = manifest.get("built_at_utc") or manifest.get("completed_at_utc")
    if not roh:
        return None
    try:
        wann = datetime.fromisoformat(str(roh).replace("Z", "+00:00"))
    except ValueError:
        return None
    return wann if wann.tzinfo else wann.replace(tzinfo=timezone.utc)


def eingaben(manifest: dict[str, Any]) -> frozenset[str]:
    """Die Bronze-Laufkennungen, auf denen eine Tabelle ruht.

    Drei Formen, gewachsen und bewusst nicht angeglichen: ``crime_offense``
    fuehrt Listen je Stadt (``chicago_bronze_runs``), die uebrigen
    Silver-Tabellen eine Liste von Eintraegen mit ``run_id``, und Gold nennt
    Silver-Tabellen statt Laeufe - dort bleibt die Menge leer, und es zaehlt
    allein der Zeitpunkt.
    """
    herkunft = manifest.get("derived_from")
    gefunden: set[str] = set()
    if isinstance(herkunft, dict):
        for schluessel, wert in herkunft.items():
            if schluessel.endswith("_runs") and isinstance(wert, list):
                gefunden.update(str(v) for v in wert)
    elif isinstance(herkunft, list):
        for eintrag in herkunft:
            if isinstance(eintrag, dict) and eintrag.get("run_id"):
                gefunden.add(str(eintrag["run_id"]))
    return frozenset(gefunden)


class Standvergleich(NamedTuple):
    """Der eigene Stand einer abgeleiteten Tabelle gegen den auf SeaweedFS."""

    tabelle: str
    hier: datetime | None
    dort: datetime | None
    fehlende_eingaben: frozenset[str]

    @property
    def aelter(self) -> bool:
        return self.hier is not None and self.dort is not None and self.hier < self.dort

    @property
    def veraltet(self) -> bool:
        """Aelter gebaut, oder auf Laeufen, die hier gar nicht erreichbar sind.

        ``fehlende_eingaben`` sind **nicht** einfach die Laeufe, die der Stand
        oben nennt und der hiesige nicht - das waere zu streng. Siehe
        ``Storage.vergleiche_stand``.
        """
        return self.aelter or bool(self.fehlende_eingaben)

    def satz(self) -> str:
        teile = []
        if self.hier and self.dort:
            teile.append(f"hier gebaut {self.hier:%d.%m.%Y %H:%M} UTC, "
                         f"auf SeaweedFS {self.dort:%d.%m.%Y %H:%M} UTC")
        if self.fehlende_eingaben:
            namen = ", ".join(sorted(self.fehlende_eingaben)[:3])
            mehr = "" if len(self.fehlende_eingaben) <= 3 else f" und {len(self.fehlende_eingaben) - 3} weitere"
            teile.append(f"dort stecken {len(self.fehlende_eingaben)} Bronze-Lauf/Laeufe, "
                         f"die hier fehlen ({namen}{mehr})")
        return f"{self.tabelle}: " + "; ".join(teile)


def etag_md5(etag: str) -> str | None:
    """Das ETag als MD5, wenn es eines ist (bei mehrteiligen Uploads nicht)."""
    wert = etag.strip().strip('"').lower()
    return wert if MD5.match(wert) else None


class Storage:
    """Eine Ablage mit Wurzel, Backend und - falls noetig - S3-Client."""

    def __init__(self, config: Config, client: S3Client | None = None) -> None:
        self.config = config
        self._client = client
        self._entfernte_manifeste: dict[str, dict[str, Any] | None] = {}
        self._verfuegbar: dict[str, frozenset[str]] = {}
        self._gewarnt: set[str] = set()

    # -- Aufbau --------------------------------------------------------------

    @property
    def backend(self) -> str:
        return self.config.backend

    @property
    def local_root(self) -> Path:
        return self.config.local_root

    @property
    def client(self) -> S3Client:
        if self._client is None:
            if not self.config.remote:
                raise PublishError("STORAGE_BACKEND=local kennt kein S3")
            self._client = Boto3Client(self.config)
        return self._client

    def mit_wurzel(self, local_root: Path) -> Storage:
        """Dieselbe Ablage mit anderer lokaler Wurzel (``--data-root``)."""
        from dataclasses import replace

        if Path(local_root) == self.local_root:
            return self
        return Storage(replace(self.config, local_root=Path(local_root)), self._client)

    # -- Wessen Stand ist neuer? --------------------------------------------

    def tabellenverzeichnis(self, rel: str) -> str:
        """Das Verzeichnis, in dem das Manifest liegt - aus Datei oder Ordner."""
        letzter = rel.rsplit("/", 1)[-1]
        return rel.rsplit("/", 1)[0] if "." in letzter else rel

    def entfernter_stand(self, verzeichnis: str, *, frisch: bool = False) -> dict[str, Any] | None:
        """Das Manifest dieser Tabelle auf SeaweedFS, oder None."""
        if not self.config.remote:
            return None
        if not frisch and verzeichnis in self._entfernte_manifeste:
            return self._entfernte_manifeste[verzeichnis]
        schluessel = f"{verzeichnis}/{MANIFEST}"
        manifest = None
        if self.client.head(schluessel) is not None:
            try:
                manifest = json.loads(self.client.get(schluessel).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                LOG.warning("Manifest auf SeaweedFS nicht lesbar: %s", schluessel)
        self._entfernte_manifeste[verzeichnis] = manifest
        return manifest

    def verfuegbare_laeufe(self, schicht: str = "bronze") -> frozenset[str]:
        """Jede Laufkennung, die hier erreichbar ist - lokal oder auf S3.

        Gelesen werden die Manifeste, nicht die Verzeichnisnamen: Detroit
        nennt seine Kennung ``pipeline_run_id``, die uebrigen ``run_id``.
        Einmal je Ablage ermittelt; ``hole_lauf`` verwirft den Zwischenstand,
        weil danach mehr da ist.
        """
        if schicht not in self._verfuegbar:
            self._verfuegbar[schicht] = frozenset(
                lauf.run_id for lauf in self.laeufe(schicht, "**/manifest.json",
                                                    streng=False)
            )
        return self._verfuegbar[schicht]

    def vergleiche_stand(self, verzeichnis: str, lokal: dict[str, Any] | None = None, *,
                         frisch: bool = False) -> Standvergleich | None:
        """Vergleicht die lokale Tabelle mit der auf SeaweedFS.

        ``None``, wenn nichts zu vergleichen ist: keine der beiden Seiten da,
        oder eine Schicht, in der Staende einander nicht verdraengen.

        **Was als fehlend zaehlt.** Bis zum 17.9.2026 galt jeder Lauf als
        fehlend, den der Stand oben nennt und der hiesige nicht. Das war zu
        streng, und es hat an diesem Abend einen Gesamtlauf abgebrochen:

            silver/dataset=weather_day: hier gebaut 19:30 UTC, auf SeaweedFS
            16:05 UTC; dort stecken 1 Bronze-Lauf/Laeufe, die hier fehlen
            (run_20260908T201217784384Z)

        Der hiesige Stand war **neuer** und ruhte auf einem **neueren**
        NOAA-Lauf. NOAA liefert Vollschnappschuesse, und
        ``build_weather_day`` nimmt deshalb nur den juengsten - der Lauf vom
        8.9. war nicht verloren, sondern abgeloest. Er lag die ganze Zeit
        unter ``data/bronze``.

        Deshalb zaehlt jetzt, ob ein Lauf hier **erreichbar** ist, nicht ob
        der Bau ihn benutzt hat. Die Absicht der Regel bleibt: Wer einen Lauf
        geloescht oder nie geholt hat und daraus neu baut, verdraengt einen
        reicheren Stand - und genau dann ist der Lauf auch nicht erreichbar.
        Bei Chicagos Deltas aendert sich nichts: ``crime_offense`` liest alle
        Laeufe, ein erreichbarer taucht dort immer auch in der Herkunft auf.
        """
        if verzeichnis.split("/")[0] not in ABGELEITET or not self.config.remote:
            return None
        if lokal is None:
            pfad = self.local_path(verzeichnis, MANIFEST)
            if not pfad.exists():
                return None
            manifest = read_manifest(pfad, streng=False)
            if manifest is None:
                return None
            lokal = manifest
        dort = self.entfernter_stand(verzeichnis, frisch=frisch)
        if dort is None:
            return None
        return Standvergleich(
            verzeichnis, zeitpunkt(lokal), zeitpunkt(dort),
            eingaben(dort) - eingaben(lokal) - self.verfuegbare_laeufe(),
        )

    def _warne_wenn_veraltet(self, rel: str) -> None:
        """Beim Lesen: sagen, dass die lokale Fassung nicht die neueste ist.

        Eine Warnung, keine Absage - "lokal zuerst" bleibt die Regel. Faellt
        dabei SeaweedFS aus, bleibt es still: Ein lokaler Lesezugriff soll
        nicht daran scheitern, dass das Netz weg ist.
        """
        verzeichnis = self.tabellenverzeichnis(rel)
        if verzeichnis in self._gewarnt or verzeichnis.split("/")[0] not in ABGELEITET:
            return
        self._gewarnt.add(verzeichnis)
        try:
            befund = self.vergleiche_stand(verzeichnis)
        except StorageError as fehler:
            LOG.debug("Stand nicht vergleichbar (%s): %s", verzeichnis, fehler)
            return
        if befund is not None and befund.veraltet:
            LOG.warning(
                "Lokaler Stand ist aelter als der auf SeaweedFS - %s. Gelesen wird "
                "trotzdem die lokale Fassung. Neu bauen mit "
                "'python -m orchestration.run_all --ohne-ingestion'.",
                befund.satz(),
            )

    # -- Pfade ---------------------------------------------------------------

    def storage_path(self, *teile: str | Path) -> str:
        """Der relative Ablagepfad - die Adresse, die alle Backends verstehen."""
        return paths.relativ(*teile)

    def local_path(self, *teile: str | Path) -> Path:
        rel = paths.relativ(*teile)
        return self.local_root / rel if rel else self.local_root

    def s3_path(self, *teile: str | Path) -> str:
        return paths.s3_url(self.config.s3_bucket, paths.relativ(*teile))

    def relativ(self, pfad: Path) -> str | None:
        """Der Ablagepfad eines lokalen Pfads, oder None ausserhalb der Wurzel."""
        return paths.unter_wurzel(self.local_root, Path(pfad))

    def resolve_read_path(self, *teile: str | Path) -> str:
        """Woher gelesen wird - als Zeichenkette, die DuckDB versteht.

        local: immer lokal. s3: immer S3. hybrid: lokal, wenn die Datei da
        ist, sonst S3 - und das steht im Log.
        """
        rel = paths.relativ(*teile)
        if self.backend == "local":
            return str(self.local_path(rel))
        if self.backend == "s3":
            return self.s3_path(rel)
        lokal = self.local_path(rel)
        if lokal.exists():
            self._warne_wenn_veraltet(rel)
            LOG.debug("Reading local: %s", lokal)
            return str(lokal)
        LOG.info("Local file missing, falling back to S3: %s", self.s3_path(rel))
        return self.s3_path(rel)

    def exists(self, *teile: str | Path) -> bool:
        rel = paths.relativ(*teile)
        if self.config.liest_lokal and self.local_path(rel).exists():
            return True
        if self.config.remote:
            return self.client.head(rel) is not None
        return False

    def read_text(self, *teile: str | Path) -> str:
        rel = paths.relativ(*teile)
        lokal = self.local_path(rel)
        if self.config.liest_lokal and lokal.exists():
            return lokal.read_text(encoding="utf-8")
        if self.config.remote:
            return self.client.get(rel).decode("utf-8")
        raise FileNotFoundError(str(lokal))

    def write_text(self, text: str, *teile: str | Path) -> Path:
        """Schreibt lokal; im s3-Modus ausserdem sofort nach S3.

        Fuer Laeufe und Tabellen ist das der falsche Weg - die gehen ueber
        ``publish_run``/``publish_table`` nach der Pruefung. Das hier ist fuer
        kleine Protokolle, die keine Pruefung haben.
        """
        rel = paths.relativ(*teile)
        lokal = self.local_path(rel)
        lokal.parent.mkdir(parents=True, exist_ok=True)
        lokal.write_text(text, encoding="utf-8")
        if self.backend == "s3":
            self.publish_files([rel], ueberschreiben=True)
        return lokal

    # -- Suchen --------------------------------------------------------------

    def list_files(self, prefix: str | Path, muster: str = "**/*") -> list[str]:
        """Dateien unter ``prefix``, als relative Ablagepfade, sortiert.

        ``muster`` gilt relativ zu ``prefix`` und wie bei ``Path.glob``:
        ``**/`` deckt auch null Verzeichnisebenen ab. Versteckte Teile
        (``.part``, ``.partial``) zaehlen nie. hybrid: lokal und S3 vereint,
        lokal gewinnt bei gleichem Pfad.
        """
        praefix = paths.relativ(prefix)
        gefunden: set[str] = set()
        if self.config.liest_lokal:
            wurzel = self.local_path(praefix)
            if wurzel.exists():
                for pfad in wurzel.glob(muster):
                    if pfad.is_file():
                        rel = pfad.relative_to(wurzel).as_posix()
                        if not paths.versteckt(rel):
                            gefunden.add(paths.relativ(praefix, rel))
        if self.config.remote:
            for objekt in self.client.list(praefix + "/" if praefix else ""):
                rel = objekt.key[len(praefix) + 1:] if praefix else objekt.key
                if paths.versteckt(rel) or not passt(rel, muster):
                    continue
                gefunden.add(paths.relativ(praefix, rel))
        return sorted(gefunden)

    def groessen_unter(self, prefix: str | Path, muster: str = "**/*", *,
                       lokal: bool = False) -> dict[str, int]:
        """Jede Datei unter ``prefix`` mit ihrer Groesse in Bytes.

        Dieselbe Auswahl wie ``list_files`` und darum dieselben Regeln:
        Versteckte Teile (``.part``, ``.partial``) zaehlen nie, und im
        Hybridmodus gewinnt die lokale Datei - dieselbe Datei wird **einmal**
        gezaehlt, nicht zweimal. Gemessen wird lokal mit ``st_size``, auf S3
        mit ``Objekt.size``; S3 wird zuerst gelesen, damit die lokale Groesse
        sie ueberschreibt.

        ``lokal=True`` misst nur die Arbeitskopie auf dieser Platte, auch im
        ``s3``-Modus, in dem die Ablage sonst gar nicht lokal liest. Das ist
        die Frage, die ``aufraeumen`` stellt (was gibt das Loeschen frei?) und
        die ``python -m storage publizieren`` stellt (was ist noch
        hochzuladen?) - beide meinen Bytes auf der Platte, nicht den
        gemeinsamen Bestand.
        """
        praefix = paths.relativ(prefix)
        gefunden: dict[str, int] = {}
        if self.config.remote and not lokal:
            for objekt in self.client.list(praefix + "/" if praefix else ""):
                rel = objekt.key[len(praefix) + 1:] if praefix else objekt.key
                if paths.versteckt(rel) or not passt(rel, muster):
                    continue
                gefunden[paths.relativ(praefix, rel)] = objekt.size
        if self.config.liest_lokal or lokal:
            wurzel = self.local_path(praefix)
            if wurzel.exists():
                for pfad in wurzel.glob(muster):
                    if not pfad.is_file():
                        continue
                    rel = pfad.relative_to(wurzel).as_posix()
                    if not paths.versteckt(rel):
                        gefunden[paths.relativ(praefix, rel)] = pfad.stat().st_size
        return dict(sorted(gefunden.items()))

    def bytes_unter(self, prefix: str | Path, muster: str = "**/*", *,
                    lokal: bool = False) -> int:
        """Die Belegung unter ``prefix`` in Bytes - **die** Byte-Summe.

        Sie stand bis zum 4.10.2026 dreimal ausgeschrieben im Projekt
        (``storage/__main__.py``, ``orchestration.aufraeumen``,
        ``tools/build_referenz.py``), jedes Mal als ``sum(p.stat().st_size for
        p in ...rglob("*"))`` - und damit jedes Mal nur im ``local``-Modus
        richtig, jedes Mal mit den ``.part``-Verzeichnissen drin, und einmal
        geteilt durch 1'048'576, wo alle anderen durch 1e6 teilten. Ein fehlendes
        Praefix ist kein Fehler, sondern 0 Bytes: Eine Schicht, die es noch
        nicht gibt, belegt nichts.

        Unberuehrt bleibt die Summe in ``storage.release``: Sie zaehlt die
        Dateien **eines** Release-Manifests, steht in unveraenderlichen
        Manifesten und darf sich nie anders rechnen als damals.
        """
        return sum(self.groessen_unter(prefix, muster, lokal=lokal).values())

    def laeufe(self, prefix: str | Path, muster: str = f"**/run_*/{MANIFEST}", *,
               status: frozenset[str] = FERTIG, streng: bool = False,
               fehler: type[Exception] = PublishError) -> list[Lauf]:
        """Fertige Laeufe unter ``prefix`` - lokal, auf S3 oder beides.

        Jeder ``Lauf`` traegt seinen relativen Ablagepfad in ``relativ``;
        ``verzeichnis`` ist der lokale Pfad, der bei einem S3-Lauf nicht
        existieren muss. Ein Lauf, dessen Manifest nicht fertig sagt, gilt
        nicht - auch nicht, wenn er lokal liegt und S3 einen fertigen hat.
        """
        praefix = paths.relativ(prefix)
        gefunden: dict[str, Lauf] = {}
        if self.config.liest_lokal:
            wurzel = self.local_path(praefix)
            for lauf in fertige_laeufe(wurzel, muster, streng=streng, fehler=fehler,
                                       status=status):
                rel = paths.relativ(praefix, lauf.verzeichnis.relative_to(wurzel).as_posix())
                gefunden[rel] = Lauf(lauf.verzeichnis, lauf.manifest, rel)
        if self.config.remote:
            for objekt in self.client.list(praefix + "/" if praefix else ""):
                if not objekt.key.endswith("/" + MANIFEST):
                    continue
                rel = objekt.key[len(praefix) + 1:] if praefix else objekt.key
                if paths.versteckt(rel) or not passt(rel, muster):
                    continue
                rel_dir = objekt.key[: -len("/" + MANIFEST)]
                if rel_dir in gefunden:
                    continue
                try:
                    manifest = json.loads(self.client.get(objekt.key).decode("utf-8"))
                except (OSError, ValueError) as error:
                    raise fehler(f"Invalid manifest: {self.s3_path(objekt.key)}") from error
                if str(manifest.get("status", "")).lower() not in status:
                    LOG.warning("Lauf uebersprungen, nicht fertig: %s", self.s3_path(rel_dir))
                    continue
                gefunden[rel_dir] = Lauf(self.local_path(rel_dir), manifest, rel_dir)
        return [gefunden[k] for k in sorted(gefunden)]

    def tabellen(self, schichten: tuple[str, ...] = ("silver", "gold")) -> list[Tabelle]:
        """Fertige Silver- und Gold-Tabellen, mit relativem Ablagepfad.

        *Fertig* heisst hier dasselbe wie bei ``laeufe``: Das Manifest sagt es.
        Bis zum 15.9.2026 galt jede Tabelle mit Manifest als gebaut, egal was
        darin stand - eine Tabelle mitten im Publizieren also auch. Damit half
        der Status niemandem: Er wurde gesetzt und nie gelesen.
        """
        gefunden: dict[str, Tabelle] = {}
        if self.config.liest_lokal:
            for t in tabellen(self.local_root, schichten):
                rel = self.relativ(t.verzeichnis) or t.verzeichnis.as_posix()
                gefunden[rel] = Tabelle(t.schicht, t.name, t.verzeichnis, t.manifest, rel)
        if self.config.remote:
            for schicht in schichten:
                for objekt in self.client.list(schicht + "/dataset="):
                    if not objekt.key.endswith("/" + MANIFEST):
                        continue
                    rel_dir = objekt.key[: -len("/" + MANIFEST)]
                    if rel_dir in gefunden or paths.versteckt(rel_dir):
                        continue
                    name = next(t for t in rel_dir.split("/")
                                if t.startswith("dataset=")).removeprefix("dataset=")
                    manifest = json.loads(self.client.get(objekt.key).decode("utf-8"))
                    gefunden[rel_dir] = Tabelle(schicht, name, self.local_path(rel_dir),
                                                manifest, rel_dir)
        fertig = {}
        for rel, tabelle in gefunden.items():
            status = str((tabelle.manifest or {}).get("status", "")).lower()
            if status in FERTIG:
                fertig[rel] = tabelle
            else:
                LOG.warning("Tabelle uebersprungen, nicht fertig (%s): %s", status or "ohne Status", rel)
        return sorted(fertig.values(), key=lambda t: (t.schicht, t.name))

    # -- Publizieren ---------------------------------------------------------

    def publish_files(self, dateien: Iterable[str], *, ueberschreiben: bool = False) -> list[str]:
        """Laedt lokale Dateien nach S3, ``manifest.json`` zuletzt.

        Gibt zurueck, was jetzt oben liegt. Ohne S3 im Backend passiert
        nichts; im Hybridmodus mit ``HYBRID_PUBLISH_AFTER_WRITE=false`` auch
        nicht - dann steht es im Log.

        Was oben schon liegt, wird **einmal je Praefix** aufgelistet, nicht je
        Datei mit ``HEAD`` erfragt (siehe ``_bestand_oben``). Jede Entscheidung
        bleibt dieselbe: identisch oben wird uebersprungen, abweichend oben ist
        ohne ``ueberschreiben`` ein Fehler, und ``_ist_identisch`` entscheidet
        allein, was "gleich" heisst.
        """
        liste = [paths.relativ(d) for d in dateien]
        if not liste:
            return []
        if not self.config.publiziert:
            if self.backend == "hybrid":
                LOG.info("Not published (HYBRID_PUBLISH_AFTER_WRITE=false): %d file(s)", len(liste))
            return []

        reihenfolge = sorted(liste, key=lambda r: (r.rsplit("/", 1)[-1] == MANIFEST, r))
        bestand = self._bestand_oben(reihenfolge)
        oben: list[str] = []
        for rel in reihenfolge:
            lokal = self.local_path(rel)
            daten = lokal.read_bytes()
            md5 = hashlib.md5(daten).hexdigest()

            vorhanden = bestand.get(rel)
            if vorhanden is not None:
                if self._ist_identisch(rel, vorhanden, daten, md5):
                    LOG.info("Already published, identical: %s", rel)
                    oben.append(rel)
                    continue
                if not ueberschreiben:
                    raise PublishError(
                        f"{self.s3_path(rel)} existiert bereits mit anderem Inhalt "
                        f"({vorhanden.size} Bytes, lokal {len(daten)}). Laeufe sind "
                        "unveraenderlich; nichts wird still ueberschrieben."
                    )
                LOG.info("Replacing published table file: %s", rel)

            try:
                self.client.put(rel, daten)
            except Exception as error:  # noqa: BLE001 - jede Transportstoerung ist hier gleich
                raise PublishError(f"Upload fehlgeschlagen: {self.s3_path(rel)}: {error}") from error

            nachher = self.client.head(rel)
            if nachher is None or nachher.size != len(daten):
                raise PublishError(
                    f"Upload nicht bestaetigt: {self.s3_path(rel)} "
                    f"({'fehlt' if nachher is None else f'{nachher.size} statt {len(daten)} Bytes'})"
                )
            if not self._ist_identisch(rel, nachher, daten, md5):
                raise PublishError(f"Pruefsumme nach Upload weicht ab: {self.s3_path(rel)}")
            LOG.info("Published: %s", rel)
            oben.append(rel)
        return oben

    def _bestand_oben(self, dateien: list[str]) -> dict[str, Objekt]:
        """Was von ``dateien`` schon oben liegt - **ein** ``list`` je Praefix.

        Bis zum 5.10.2026 fragte ``publish_files`` je Datei mit ``HEAD``, ob
        oben schon etwas liegt. Beim Publizieren der sechs Jahrgaenge waren das
        446 Anfragen in Folge, und der Endpunkt drosselte 350 davon: Unter
        dichter Anfragefolge antwortet er auf einen fehlenden Schluessel mit
        403 statt 404. Gemessen am 5.10.2026 - 120 Anfragen in 8,5 s ergaben
        120 x 403, derselbe fehlende Schluessel einzeln abgefragt 403 einmal
        und 404 viermal. ``403`` steht in ``VORUEBERGEHEND``, also holte
        ``_mit_wiederholung`` nach einer Sekunde das ehrliche 404 - das
        Ergebnis stimmte, der Upload dauerte doppelt so lang.

        Ein ``list`` beantwortet dieselbe Frage fuer alle Dateien eines
        Verzeichnisses: ``Objekt`` traegt ``key``, ``size`` und ``etag``, und
        genau das - und nichts darueber hinaus - braucht ``_ist_identisch``.
        Die Zahl der Anfragen fuer die Vorabpruefung faellt damit von N auf
        eins je Verzeichnis.

        Aufgelistet wird je **Praefix**, nicht einmal fuer alles: Ein Release
        traegt Dateien unter ``gold/dataset=...`` und ``serving/dataset=...``,
        und ein ``list`` auf den gemeinsamen Stamm brachte jedes andere
        Release mit.
        """
        gesucht: dict[str, set[str]] = {}
        for rel in dateien:
            verzeichnis = rel.rpartition("/")[0]
            # Ein Schluessel ohne Verzeichnis (``write_text`` kann einen
            # anlegen) wird mit sich selbst als Praefix aufgelistet: ``list("")``
            # waere der ganze Bucket. Nachgeschlagen wird ohnehin exakt.
            gesucht.setdefault(verzeichnis + "/" if verzeichnis else rel, set()).add(rel)
        bestand: dict[str, Objekt] = {}
        for praefix, schluessel in gesucht.items():
            for objekt in self.client.list(praefix):
                if objekt.key in schluessel:
                    bestand[objekt.key] = objekt
        return bestand

    def _ist_identisch(self, rel: str, oben: Objekt, daten: bytes, md5: str) -> bool:
        """Ob das Objekt oben byteweise dasselbe ist wie ``daten``.

        **Gleiche Groesse ist kein Beweis.** Genau das stand hier bis zum
        15.9.2026: Liess sich das ETag nicht als MD5 lesen, genuegte die
        Byteanzahl - und drei Bytes ``NEU`` galten als identisch mit drei
        Bytes ``ALT``. Der Upload unterblieb, und die Zusage unveraenderlicher
        Laeufe ruhte auf einem Zufall.

        Ein ETag ist nicht immer eine Pruefsumme: Bei mehrteiligen Uploads
        setzt S3 einen Hash ueber die Teil-Hashes mit angehaengtem ``-N``.
        Dann bleibt nur, den Inhalt zu holen und zu vergleichen. Das kostet
        einen Download - aber nur dann, wenn die Groessen ohnehin gleich sind
        und die Pruefsumme nichts hergibt.
        """
        if oben.size != len(daten):
            return False
        bekannt = etag_md5(oben.etag)
        if bekannt is not None:
            return bekannt == md5
        LOG.info("ETag ist keine Pruefsumme (%s), Inhalt wird geholt: %s",
                 oben.etag, self.s3_path(rel))
        try:
            return self.client.get(rel) == daten
        except Exception as fehler:  # noqa: BLE001 - jede Transportstoerung ist hier gleich
            raise PublishError(
                f"Inhalt nicht pruefbar: {self.s3_path(rel)}: {fehler}. Das ETag "
                "ist keine Pruefsumme, und der Vergleichsdownload scheiterte - "
                "gleiche Groesse allein gilt nicht als gleicher Inhalt."
            ) from fehler

    def _dateien_unter(self, rel_dir: str) -> list[str]:
        wurzel = self.local_path(rel_dir)
        if not wurzel.is_dir():
            raise PublishError(f"Nichts zu publizieren, kein Verzeichnis: {wurzel}")
        return [
            paths.relativ(rel_dir, p.relative_to(wurzel).as_posix())
            for p in sorted(wurzel.rglob("*"))
            if p.is_file() and not paths.versteckt(p.relative_to(wurzel).as_posix())
        ]

    def _rel_dir(self, ziel: str | Path) -> str | None:
        if isinstance(ziel, Path):
            rel = self.relativ(ziel)
            if rel is None:
                LOG.warning("Not published, outside LOCAL_DATA_ROOT (%s): %s",
                            self.local_root, ziel)
            return rel
        return paths.relativ(ziel)

    def tabellen_manifest(self, ziel: str | Path) -> dict[str, Any]:
        """Das Manifest einer **publizierten** Tabelle - lokal oder oben.

        **Warum es das gibt.** ``publish_table`` entfernt im s3-Modus die
        lokale Arbeitskopie; der Pfad, den ``build`` zurueckgibt, zeigt
        danach ins Leere. Jedes Stufenmodul las ihn trotzdem, um seinen
        Schlussbericht zu schreiben - und jeder Lauf endete dort mit
        *„Invalid manifest"* und Exitcode 1, **obwohl die Tabelle sauber
        publiziert war**. Fuer ``orchestration.run_all`` war das ein
        gescheiterter Lauf; der Serverlauf vom 12.10.2026 starb genau so bei
        ``silver tract_2021``, der vom 15.10. wieder.

        Vier Module hatten denselben Fehler (``build_tract``,
        ``build_place``, ``build_weather_day``, ``build_gold``). Deshalb
        steht die Antwort hier und nicht viermal dort: Wer eine Tabelle
        publiziert, fragt die Ablage nach ihrem Manifest, nicht das
        Dateisystem.
        """
        rel = self._rel_dir(ziel)
        if rel is None:
            raise StorageError(
                f"{ziel} liegt ausserhalb von LOCAL_DATA_ROOT "
                f"({self.local_root}) - dafuer gibt es keinen Ablagepfad.")
        return json.loads(self.read_text(rel, "manifest.json"))

    def publish_run(self, lauf: str | Path) -> list[str]:
        """Einen fertigen, unveraenderlichen Lauf publizieren - alles darin,
        Manifest zuletzt. Im s3-Modus verschwindet die lokale Kopie danach."""
        rel = self._rel_dir(lauf)
        if rel is None:
            return []
        oben = self.publish_files(self._dateien_unter(rel), ueberschreiben=False)
        self._lokal_entfernen_falls_s3(rel)
        return oben

    def publish_table(self, tabelle: str | Path, *, erzwingen: bool = False) -> list[str]:
        """Eine abgeleitete Tabelle publizieren. **Ueberschreibt** auf S3 -
        lokal wird sie ebenso ersetzt, nicht angehaeuft.

        Nicht aber, wenn der eigene Stand aelter ist als der dort oder auf
        weniger Bronze-Laeufen ruht: Dann verdraengte er einen neueren, und
        niemand saehe es ihm an. ``erzwingen=True`` dreht bewusst zurueck.
        """
        rel = self._rel_dir(tabelle)
        if rel is None:
            return []
        if self.config.publiziert and not erzwingen:
            befund = self.vergleiche_stand(rel, frisch=True)
            if befund is not None and befund.veraltet:
                raise PublishError(
                    f"Nicht publiziert, das waere ein Rueckschritt - {befund.satz()}. "
                    "Erst neu bauen ('python -m orchestration.run_all --ohne-ingestion'), "
                    "dann publizieren. Wer wirklich zurueckdrehen will: "
                    "publish_table(..., erzwingen=True)."
                )
        self._entwerte_entferntes_manifest(rel)
        oben = self.publish_files(self._dateien_unter(rel), ueberschreiben=True)
        self._entfernte_manifeste.pop(rel, None)
        self._lokal_entfernen_falls_s3(rel, aufschiebbar=True)
        return oben

    def _entwerte_entferntes_manifest(self, rel: str) -> None:
        """Das entfernte Manifest auf ``publishing`` setzen, bevor Daten fallen.

        **Warum das noetig ist.** ``manifest.json`` zuletzt zu schreiben
        schuetzt einen *neuen* Lauf: Ohne Manifest gilt er nicht. Eine
        *bestehende* Tabelle schuetzt es nicht. Wird ihre Parquet-Datei
        ueberschrieben und bricht danach der Manifest-Upload ab, liegt oben
        der neue Inhalt unter dem alten Manifest - und das sagt weiterhin
        ``complete``. Genau das war am 15.9.2026 in einer Gegenprobe zu sehen:
        neue Daten, Bauzeitpunkt vom 1. August, Status ``complete``.

        Deshalb faellt zuerst der Status. Ein Leser sieht danach der Reihe nach
        den vollstaendigen alten Stand, dann *keinen* (``publishing`` zaehlt
        nicht als fertig, siehe ``tabellen``), dann den vollstaendigen neuen.
        Ein Abbruch dazwischen laesst die Tabelle unbrauchbar zurueck, nicht
        falsch - und der naechste Lauf stellt sie her.

        Was das **nicht** loest: Die fuenf Gold-Tabellen werden weiterhin
        nacheinander publiziert. Ein gemeinsamer, konsistenter Stand ueber
        alle Tabellen braucht Versionspfade und einen Verweis, der umgelegt
        wird; das steht im Ausblick.
        """
        if not self.config.publiziert:
            return
        schluessel = paths.relativ(rel, MANIFEST)
        oben = self.client.head(schluessel)
        if oben is None:
            return
        try:
            manifest = json.loads(self.client.get(schluessel).decode("utf-8"))
        except (OSError, ValueError) as fehler:
            raise PublishError(
                f"Entferntes Manifest nicht lesbar: {self.s3_path(schluessel)}: {fehler}"
            ) from fehler
        if str(manifest.get("status", "")).lower() not in FERTIG:
            return
        manifest["status"] = "publishing"
        manifest["superseded_at_utc"] = datetime.now(timezone.utc).isoformat(
            timespec="seconds").replace("+00:00", "Z")
        try:
            self.client.put(schluessel, json.dumps(manifest, indent=2).encode("utf-8"))
        except Exception as fehler:  # noqa: BLE001 - jede Transportstoerung ist hier gleich
            raise PublishError(
                f"Tabelle nicht entwertet, nichts angefasst: "
                f"{self.s3_path(schluessel)}: {fehler}"
            ) from fehler
        LOG.info("Entferntes Manifest auf 'publishing' gesetzt: %s", schluessel)

    # -- Holen ---------------------------------------------------------------
    #
    # Bis zum 17.9.2026 galt: kein automatisches Herunterladen - was lokal
    # fehlt, wird von S3 gelesen, nicht kopiert. Das bleibt fuer Silver und
    # Gold richtig (Abschnitt 8 der Storage-Architektur: ein stiller Cache
    # waere eine zweite Wahrheit mit eigenem Alter). Fuer Raw und Bronze gilt
    # es nicht: Laeufe sind unveraenderlich, eine Kopie kann nicht veralten,
    # und jeder Rechner soll den ganzen Bestand haben - Christian, 17.9.2026.
    # Releases sind ebenso unveraenderlich; sie werden mit ``storage.release``
    # geholt, ueber dieselben Bausteine hier.

    def hole(self, rel: str | Path) -> Path:
        """Ein Objekt von S3 in die lokale Wurzel - geprueft und unteilbar.

        Liegt es lokal schon identisch, passiert nichts. Geschrieben wird in
        eine ``.part``-Datei daneben, verglichen (Groesse, dann MD5 gegen das
        ETag, wo der Dienst eines liefert), dann umbenannt.
        """
        rel = paths.relativ(rel)
        if not self.config.remote:
            raise PublishError(f"STORAGE_BACKEND={self.backend} kennt kein S3 - nichts zu holen")
        oben = self.client.head(rel)
        if oben is None:
            raise StorageError(f"nicht auf SeaweedFS: {self.s3_path(rel)}")
        ziel = self.local_path(rel)
        if ziel.is_file() and ziel.stat().st_size == oben.size:
            bekannt = etag_md5(oben.etag)
            if bekannt is None or bekannt == hashlib.md5(ziel.read_bytes()).hexdigest():
                LOG.debug("Already local, identical: %s", rel)
                return ziel
        try:
            daten = self.client.get(rel)
        except Exception as fehler:  # noqa: BLE001 - jede Transportstoerung ist hier gleich
            raise StorageError(f"Download fehlgeschlagen: {self.s3_path(rel)}: {fehler}") from fehler
        if len(daten) != oben.size:
            raise StorageError(
                f"Download unvollstaendig: {self.s3_path(rel)} "
                f"({len(daten)} statt {oben.size} Bytes)"
            )
        bekannt = etag_md5(oben.etag)
        if bekannt is not None and bekannt != hashlib.md5(daten).hexdigest():
            raise StorageError(f"Pruefsumme nach Download weicht ab: {self.s3_path(rel)}")
        ziel.parent.mkdir(parents=True, exist_ok=True)
        arbeit = ziel.with_name(f".{ziel.name}.{id(self) & 0xffff:x}.part")
        arbeit.write_bytes(daten)
        arbeit.replace(ziel)
        LOG.info("Fetched: %s", rel)
        return ziel

    def hole_lauf(self, rel_dir: str | Path) -> list[Path]:
        """Einen Lauf ganz holen - alle Objekte darunter, ``manifest.json`` zuletzt.

        Wie beim Publizieren ist das Manifest das Zeichen, dass der Lauf ganz
        da ist: Bricht der Download davor ab, liegt lokal ein Verzeichnis ohne
        Manifest, und das gilt nirgends als Lauf.
        """
        rel_dir = paths.relativ(rel_dir)
        objekte = [o.key for o in self.client.list(rel_dir + "/")
                   if not paths.versteckt(o.key[len(rel_dir) + 1:])]
        if not objekte:
            raise StorageError(f"kein Lauf unter {self.s3_path(rel_dir)}")
        reihenfolge = sorted(objekte, key=lambda k: (k.rsplit("/", 1)[-1] == MANIFEST, k))
        geholt = [self.hole(k) for k in reihenfolge]
        self._verfuegbar.clear()   # jetzt ist hier mehr erreichbar als vorher
        return geholt

    def fehlende_laeufe(self, schichten: tuple[str, ...] = ("raw", "bronze")) -> list[str]:
        """Laeufe, die oben liegen und lokal fehlen - als relative Verzeichnisse.

        *Fehlt* heisst: kein lokales Manifest. Ein lokaler Lauf ohne Manifest
        ist ein abgebrochener Download oder Bau und wird erneut geholt.
        """
        if not self.config.remote:
            return []
        fehlend: list[str] = []
        for schicht in schichten:   # in dieser Reihenfolge: Raw vor Bronze
            je_schicht = []
            for objekt in self.client.list(schicht + "/"):
                if not objekt.key.endswith("/" + MANIFEST):
                    continue
                rel_dir = objekt.key[: -len("/" + MANIFEST)]
                if paths.versteckt(rel_dir):
                    continue
                if not (self.local_path(rel_dir) / MANIFEST).is_file():
                    je_schicht.append(rel_dir)
            fehlend += sorted(je_schicht)
        return fehlend

    def hole_fehlende_laeufe(self, schichten: tuple[str, ...] = ("raw", "bronze")) -> list[str]:
        """Holt jeden Lauf, der oben liegt und lokal fehlt. Raw vor Bronze."""
        geholt = []
        for rel_dir in self.fehlende_laeufe(schichten):
            self.hole_lauf(rel_dir)
            geholt.append(rel_dir)
        if geholt:
            LOG.info("%d Lauf/Laeufe geholt: %s", len(geholt), ", ".join(geholt))
        return geholt

    # -- Entfernen -----------------------------------------------------------

    def entferne_oben(self, prefix: str | Path, *, zuletzt: str | None = None) -> list[str]:
        """Entfernt auf SeaweedFS jedes Objekt unter ``prefix``. Lokal bleibt alles.

        ``prefix`` ist ein **Verzeichnis**: Es wird mit ``/`` abgeschlossen,
        bevor aufgezaehlt wird. Sonst traefe ``releases/release=2026-10-03``
        auch ``releases/release=2026-10-03T19-53-12Z/...`` - ein Praefix, das
        nur fast passt, loescht hier ein ganzes Release zu viel.

        ``zuletzt`` ist der Dateiname, der **ganz am Ende** weggeht - das
        Spiegelbild von "``release.json`` geht zuletzt hoch" in
        ``storage.release``. Ohne das loescht die sortierte Aufzaehlung
        ``release.json`` mitten im Praefix (``gold/`` < ``release.json`` <
        ``serving/``), und ein Abbruch danach macht das Release **unsichtbar**:
        ``release.liste`` erkennt es nur an einem Schluessel, der auf
        ``/release.json`` endet, und die 26,5 MB grosse ``analyse.duckdb``
        laege fuer immer unauffindbar oben. Solange das Manifest steht, findet
        ein zweiter Lauf den Rest.

        Aufgezaehlt wird ueber ``list``, nicht geraten: Weg ist nur, was
        wirklich oben liegt. Ein fehlgeschlagenes ``delete`` **bricht ab** und
        laesst den Rest stehen - die bis dahin entfernten Objekte bleiben
        entfernt. Ein zweiter Lauf bringt es zu Ende, weil S3 das Loeschen
        eines fehlenden Schluessels nicht als Fehler behandelt.

        Dass es diese Methode ueberhaupt gibt, ist eine Entscheidung vom
        4.10.2026: ``orchestration.aufraeumen`` raeumt seither auch Releases,
        und die liegen oben als der gemeinsame Stand
        (``docs/intern/datenhistorie.md`` 5.5). Fuer Laeufe und Tabellen gilt
        sie nicht - die bleiben unveraenderlich.
        """
        rel = paths.relativ(prefix)
        if not rel:
            raise PublishError(
                "entferne_oben braucht ein Praefix - ohne eines waere es der "
                "ganze Bucket."
            )
        schluessel = [o.key for o in self.client.list(rel + "/")]
        if zuletzt:
            spaet = [k for k in schluessel if k == f"{rel}/{zuletzt}"]
            schluessel = [k for k in schluessel if k not in spaet] + spaet
        geloescht: list[str] = []
        for key in schluessel:
            self.client.delete(key)
            geloescht.append(key)
            LOG.info("Removed from S3: %s", key)
        return geloescht

    def _lokal_entfernen_falls_s3(self, rel: str, *,
                                  aufschiebbar: bool = False) -> None:
        """``aufschiebbar`` gilt nur fuer **Tabellen**, nie fuer Laeufe.

        Ein Lauf ist unveraenderlich und laesst sich jederzeit wieder holen;
        ihn lokal zu behalten haeuft nur an - 141 Bronze-Laeufe waren am
        16.10.2026 der Grund, warum der Silver-Bau erstickte. Eine Tabelle
        dagegen braucht das Release, und das wird aus dem lokalen Stand
        gebildet. Deshalb entscheidet nicht der Schalter allein, sondern auch,
        **was** publiziert wurde: Ein global gesetztes
        ``STORAGE_KEEP_LOCAL`` kann Raw und Bronze nicht lokal halten.
        """
        if self.backend != "s3":
            return
        if aufschiebbar and self.config.keep_local:
            # Aufgeschoben, nicht aufgehoben: ``orchestration.run_all``
            # entfernt die Kopien nach dem Release in einem Zug. Begruendung
            # an ``Config.keep_local``.
            LOG.info("Local working copy kept (STORAGE_KEEP_LOCAL): %s", rel)
            return
        shutil.rmtree(self.local_path(rel), ignore_errors=True)
        LOG.info("Local working copy removed (STORAGE_BACKEND=s3): %s", rel)

    def arbeitskopien_entfernen(
        self, schichten: tuple[str, ...] = ("silver", "gold", "serving")
    ) -> list[str]:
        """Die lokalen Arbeitskopien publizierter Tabellen entfernen.

        Das Gegenstueck zu ``keep_local``: Was die Stufen behalten haben,
        damit das Release es findet, geht hier weg - **nachdem** das Release
        gebildet ist.

        **Entfernt wird nur, was oben wirklich liegt.** Je Tabelle wird das
        entfernte Manifest gefragt; fehlt es, bleibt die Kopie. Sonst wuerde
        eine Tabelle, deren Upload scheiterte, hier verschwinden - und waere
        nirgends mehr. Das ist der Unterschied zwischen Aufraeumen und
        Datenverlust, und er kostet eine Abfrage je Tabelle.

        Ausserhalb von ``s3`` tut die Methode nichts: In ``local`` gibt es
        kein Oben, in ``hybrid`` ist die lokale Kopie der Bestand.
        """
        if self.backend != "s3":
            return []
        weg: list[str] = []
        for schicht in schichten:
            wurzel = self.local_path(schicht)
            if not wurzel.is_dir():
                continue
            for manifest in sorted(wurzel.rglob(MANIFEST)):
                verzeichnis = manifest.parent
                rel = self.relativ(verzeichnis)
                if rel is None:
                    continue
                if not self.exists(rel, MANIFEST):
                    LOG.warning(
                        "Nicht oben, lokale Kopie bleibt: %s", rel)
                    continue
                shutil.rmtree(verzeichnis, ignore_errors=True)
                LOG.info("Local working copy removed after release: %s", rel)
                weg.append(rel)
        return weg


#: ``fnmatch.translate`` haengt ans Ende jedes Musters einen Anker fuer das
#: Stringende: bis Python 3.13 ``\Z``, seit 3.14 ``\z``. Ein Segment ist aber
#: nur ein Stueck Pfad, also muss der Anker weg - sonst steht ein Stringende
#: mitten im Muster und ``station=*/run_*/manifest.json`` passt auf nichts mehr.
ENDANKER = re.compile(r"\\[Zz]$")


def glob_regex(muster: str) -> re.Pattern[str]:
    """``Path.glob``-Semantik als Regex: ``*`` bleibt in seiner Ebene, ``**``
    deckt null oder mehr Ebenen ab."""
    teile = muster.split("/")
    ausdruck = "^"
    for i, teil in enumerate(teile):
        letzter = i == len(teile) - 1
        if teil == "**":
            ausdruck += ".*" if letzter else "(?:[^/]+/)*"
            continue
        segment = ENDANKER.sub("", glob_translate(teil))
        ausdruck += segment.replace(".*", "[^/]*") + ("" if letzter else "/")
    return re.compile(ausdruck + "$")


def passt(rel: str, muster: str) -> bool:
    return glob_regex(muster).match(rel) is not None


def manifest_von(storage: Storage, *teile: str | Path) -> dict[str, Any]:
    """Ein Manifest lesen, woher auch immer."""
    return json.loads(storage.read_text(*teile))
