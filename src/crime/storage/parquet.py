"""Was wirklich in einer Parquet-Datei steht - und was DuckDB dazuerfindet.

**Die Falle.** Liegt eine Datei unter einem Pfad im Hive-Muster, etwa
``dataset=fact_offense/release=2026-09-21T12-55-05Z/part-0001.parquet``, dann
leitet DuckDB aus den Verzeichnisnamen Spalten ab - hier ``dataset`` und
``release``. ``DESCRIBE SELECT * FROM read_parquet(...)`` nennt sie mit,
obwohl in keiner Datei eine solche Spalte steht, und zwar mit einer Dateiliste
genauso wie mit einem einzelnen Pfad.

Dreimal in zwei Wochen hat das etwas kaputt gemacht: ``load_elasticsearch``
haette zwei Felder zu viel abgebildet, die Einstiegsseite zeigte je Datensatz
zwei Spalten zu viel - 24 statt 22 -, und beim Anhaengen in
``build_source_change`` passten die Spaltenzahlen nicht mehr zusammen. Jedes
Mal wurde es an seiner Stelle behoben, mit demselben Kommentar daneben.

Deshalb eine Stelle statt drei: Wer die Spalten einer Datei braucht, fragt das
Parquet-Schema, nicht eine Abfrage darueber. Fuer eine Relation mit
ausgeschriebenen Spalten bleibt ``DESCRIBE`` richtig - die Falle hat nur
``SELECT *`` ueber einem Hive-Pfad.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.fs as pafs
import pyarrow.parquet as pq

S3_PRAEFIX = "s3://"


def _ablage(pfad: str) -> tuple[pafs.FileSystem | None, str]:
    """Dateisystem und Pfad fuer ``pq.ParquetFile`` - lokal oder auf S3.

    **Warum das hier sein muss.** Dieses Modul nahm den Pfad, wie er kam, und
    gab ihn an pyarrow. Bei einem lokalen Pfad geht das; bei
    ``s3://urban-crime/...`` loest pyarrow die Adresse ueber seine eigene
    S3-Erkennung auf - ohne Endpunkt, ohne Schluessel - und meldete auf
    ``srv01`` am 16.10.2026 *"Bucket 'urban-crime' not found"*. Der Lauf brach
    bei ``silver source_change`` ab, also an der Stufe, die zwei Tage vorher
    ueberhaupt erst in den Bauplan kam.

    Dieselbe Krankheit wie bei den Regeln 2 und 4 von ``orchestration.aufraeumen``
    (#158): ein Modul, das an der Ablage vorbei liest, laeuft nur im
    ``local``-Modus. ``AGENTS.md`` nennt es unter "Conventions": Dateizugriff
    ueber ``storage``, nie ueber offene Pfade.

    Die Parameter spiegeln ``storage.duckdb.secret_sql``: derselbe Endpunkt,
    dieselben Schluessel, **Pfadstil** - SeaweedFS kennt keine
    Bucket-Subdomains. Weicht das eine vom anderen ab, liest DuckDB etwas
    anderes als dieses Modul, und das waere schlimmer als ein Fehler.
    """
    if not pfad.startswith(S3_PRAEFIX):
        return None, pfad
    # Spaet importiert: ``storage/__init__`` holt dieses Modul herein.
    from storage import get_storage

    config = get_storage().config
    system = pafs.S3FileSystem(
        access_key=config.s3_access_key,
        secret_key=config.s3_secret_key,
        endpoint_override=config.endpoint_url,
        scheme="https" if config.s3_use_ssl else "http",
        # Pfadstil, wie im DuckDB-Secret (URL_STYLE 'path').
        force_virtual_addressing=False,
    )
    return system, pfad[len(S3_PRAEFIX):]


def schema(datei: Path | str) -> pa.Schema:
    """Das Arrow-Schema der Datei: genau die Spalten, die darin stehen."""
    system, pfad = _ablage(str(datei))
    if system is None:
        return pq.ParquetFile(pfad).schema_arrow
    return pq.ParquetFile(pfad, filesystem=system).schema_arrow


def spalten(datei: Path | str) -> tuple[str, ...]:
    """Die Spaltennamen der Datei, in der Reihenfolge der Datei."""
    return tuple(feld.name for feld in schema(datei))
