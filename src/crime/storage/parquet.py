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
import pyarrow.parquet as pq


def schema(datei: Path | str) -> pa.Schema:
    """Das Arrow-Schema der Datei: genau die Spalten, die darin stehen."""
    return pq.ParquetFile(datei).schema_arrow


def spalten(datei: Path | str) -> tuple[str, ...]:
    """Die Spaltennamen der Datei, in der Reihenfolge der Datei."""
    return tuple(feld.name for feld in schema(datei))
