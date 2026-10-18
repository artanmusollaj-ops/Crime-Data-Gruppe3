"""DuckDB-Verbindungen, die S3 lesen koennen, wenn die Ablage es verlangt.

Im ``local``-Modus ist das ``duckdb.connect()`` wie bisher. In ``s3`` und
``hybrid`` werden ``httpfs`` geladen und ein **temporaeres** Secret angelegt
- es lebt nur in dieser Verbindung, nichts wird auf Platte persistiert. Die
Schluessel kommen aus der Konfiguration, nie ins Log.

Abfragen sehen danach gleich aus::

    con.execute(f"SELECT count(*) FROM read_parquet('{storage.resolve_read_path(...)}')")

**Grenzen.** Ohne ``memory_limit`` nimmt DuckDB rund 80 % des Arbeitsspeichers
der Maschine. Auf einem Rechner, der nur die Strecke faehrt, ist das richtig;
auf einer geteilten Maschine ist es die Stelle, an der ein Mehrjahreslauf
stirbt, und zwar nicht allein - er nimmt die Nachbardienste mit. ``threads``
hat denselben Charakter: Jeder Thread haelt eigene Puffer.

Beide kommen deshalb aus der Umgebung (``DUCKDB_MEMORY_LIMIT``,
``DUCKDB_THREADS``) und werden auf **jeder** Verbindung gesetzt, die dieses
Modul herstellt. Ohne Angabe bleibt DuckDBs eigene Vorgabe - der heutige
Zustand aendert sich also nicht, solange niemand etwas setzt.

Wer nur lokale Dateien liest, nimmt ``verbinde``; wer die Ablage braucht,
``connect`` mit der Konfiguration. Beide Wege setzen die Grenzen. Ein eigenes
``duckdb.connect()`` umgeht sie - genau das war bis zum 3.10.2026 an neun
Stellen der Fall.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from pathlib import Path, PurePosixPath, PureWindowsPath

import duckdb

from storage.config import Config


LOG = logging.getLogger("storage.duckdb")

#: Ob die Grenzen in diesem Prozess schon im Protokoll stehen.
#:
#: Jede Stufe oeffnet mehrere Verbindungen; dieselbe Zeile zehnmal hilft
#: niemandem. Einmal je Prozess ist genau richtig - ein Lauf ruft die Stufen
#: als eigene Prozesse auf, also steht sie je Stufe einmal da.
_gemeldet = False


class DuckDBFehler(RuntimeError):
    """Eine Extension, das Secret oder eine Grenze liess sich nicht setzen."""


# Leer heisst: nicht setzen, DuckDB entscheidet wie bisher.
VORGABE_MEMORY_LIMIT = ""
VORGABE_THREADS = ""
VORGABE_TEMP_DIRECTORY = ""


def grenzen(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """``memory_limit`` und ``threads``, soweit die Umgebung sie vorgibt.

    Nur was gesetzt ist, steht im Ergebnis. Ein leerer Wert ist keine Angabe
    und keine Null - sonst wuerde ``DUCKDB_THREADS=`` in einer ``.env`` die
    Parallelitaet abschalten, ohne dass jemand das gemeint hat.
    """
    umgebung = os.environ if env is None else env
    gesetzt: dict[str, str] = {}

    speicher = (umgebung.get("DUCKDB_MEMORY_LIMIT") or VORGABE_MEMORY_LIMIT).strip()
    if speicher:
        gesetzt["memory_limit"] = speicher

    faeden = (umgebung.get("DUCKDB_THREADS") or VORGABE_THREADS).strip()
    if faeden:
        if not faeden.isdigit() or int(faeden) < 1:
            raise DuckDBFehler(
                f"DUCKDB_THREADS={faeden!r} - erwartet ist eine ganze Zahl ab 1"
            )
        gesetzt["threads"] = faeden

    # **Wohin DuckDB auslagert, wenn der Speicher nicht reicht.**
    #
    # Am 16.10.2026 starb der Serverlauf bei ``silver crime_offense``:
    # *„could not allocate block of size 256.0 KiB (854.6 MiB/854.4 MiB
    # used)"*. Der Container hat 1'280 MiB, DuckDB nimmt sich davon einen
    # Teil - und ohne Auslagerungsverzeichnis bricht es ab, statt auf Platte
    # auszuweichen.
    #
    # **Warum ausgerechnet diese Stellschraube.** DuckDB nennt in seiner
    # eigenen Fehlermeldung drei: weniger Faeden, ``preserve_insertion_order``
    # abschalten, mehr Speicher. Die zweite scheidet hier aus: ``publish``
    # schreibt mit ``COPY {relation} TO ...`` **ohne ORDER BY**, die
    # Zeilenfolge haengt also an der Einfuegereihenfolge - und zwei Bauten
    # muessen byteweise gleich sein. Auslagern aendert am Ergebnis nichts,
    # nur an der Dauer.
    #
    # Ein absoluter Pfad ist Pflicht: Ein relativer landete im
    # Arbeitsverzeichnis des Prozesses, und das ist je nach Aufruf ein
    # anderes.
    #
    # **Absolut nach einer der beiden Konventionen, nicht nach der dieser
    # Maschine.** Der Wert kommt oft aus einer Konfiguration fuer *woanders*:
    # ``/app/data/duckdb-tmp`` steht in ``docker-compose.srv01.yml`` und gilt
    # in einem Linux-Container. ``Path`` ist auf Windows ``WindowsPath``, und
    # dort ist ``/app/...`` ohne Laufwerksbuchstaben **nicht** absolut - zwei
    # Tests ueber genau diese Compose-Datei fielen deshalb am 17.10.2026 auf
    # dem Windows-Laeufer um, obwohl der gepruefte Wert richtig ist. Gegen den
    # Fehler, den die Pruefung abwehren soll, schuetzt beides gleich gut: Ein
    # fuehrender Schraegstrich haengt auf Windows am Laufwerk, nie am
    # Verzeichnis - und ``duckdb-tmp`` ist unter beiden Konventionen relativ.
    ablage = (umgebung.get("DUCKDB_TEMP_DIRECTORY")
              or VORGABE_TEMP_DIRECTORY).strip()
    if ablage:
        if not (PurePosixPath(ablage).is_absolute()
                or PureWindowsPath(ablage).is_absolute()):
            raise DuckDBFehler(
                f"DUCKDB_TEMP_DIRECTORY={ablage!r} ist kein absoluter Pfad - "
                f"relativ haengt er am Arbeitsverzeichnis des Aufrufs.")
        gesetzt["temp_directory"] = ablage

    return gesetzt


def grenzen_setzen(con: duckdb.DuckDBPyConnection,
                   env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Setzt die Grenzen auf dieser Verbindung und gibt zurueck, was gilt.

    Ein Wert, den DuckDB ablehnt, scheitert hier laut. Eine still verworfene
    Grenze waere schlimmer als keine: Der Lauf liefe weiter, mit der Zusage im
    Protokoll und ohne sie im Prozess.
    """
    global _gemeldet

    gesetzt = grenzen(env)
    for name, wert in gesetzt.items():
        try:
            con.execute(f"SET {name}=?", [wert])
        except duckdb.Error as fehler:
            raise DuckDBFehler(
                f"{name}={wert!r} hat DuckDB nicht angenommen: {fehler}"
            ) from fehler

    # **Einmal je Prozess ins Protokoll.** Am 16.10.2026 scheiterte derselbe
    # Lauf zweimal an derselben Speichergrenze, und beide Male war unklar,
    # ob das Auslagerungsverzeichnis ueberhaupt ankam: Die Variable stand in
    # ``docker-compose.srv01.yml``, aber ob das Abbild sie kennt, sagte
    # niemand. Eine Zeile im Protokoll beantwortet das sofort - und zwar
    # auch, wenn **nichts** gesetzt ist, denn genau das ist dann die
    # Nachricht.
    if not _gemeldet:
        _gemeldet = True
        if gesetzt:
            LOG.info("DuckDB-Grenzen: %s",
                     ", ".join(f"{n}={w}" for n, w in sorted(gesetzt.items())))
        else:
            LOG.info("DuckDB-Grenzen: keine gesetzt - DuckDB rechnet mit dem "
                     "Speicher der Maschine, nicht des Containers")
    return gesetzt


def secret_sql(config: Config, name: str = "seaweedfs") -> str:
    """Das CREATE SECRET - ohne PERSISTENT, also nur fuer diese Sitzung."""
    def q(text: str) -> str:
        return text.replace("'", "''")

    return (
        f"CREATE OR REPLACE SECRET {name} ("
        f"TYPE S3, KEY_ID '{q(config.s3_access_key)}', "
        f"SECRET '{q(config.s3_secret_key)}', "
        f"ENDPOINT '{q(config.s3_endpoint)}', URL_STYLE 'path', "
        f"USE_SSL {'true' if config.s3_use_ssl else 'false'})"
    )


def s3_einrichten(con: duckdb.DuckDBPyConnection, config: Config) -> None:
    try:
        con.execute("INSTALL httpfs")
        con.execute("LOAD httpfs")
    except duckdb.Error as error:
        raise DuckDBFehler(f"httpfs-Extension nicht verfuegbar: {error}") from error
    try:
        con.execute(secret_sql(config))
    except duckdb.Error as error:
        # Die Fehlermeldung von DuckDB koennte das SQL samt Schluessel zitieren.
        raise DuckDBFehler(
            f"S3-Secret konnte nicht angelegt werden ({type(error).__name__})"
        ) from None


def verbinde(database: str | Path = ":memory:", *,
             read_only: bool = False,
             env: Mapping[str, str] | None = None) -> duckdb.DuckDBPyConnection:
    """Eine Verbindung ohne S3, aber mit den Grenzen.

    Fuer die Stellen, die nur lokale Dateien lesen oder eine Datenbank
    schreiben. Wer die Ablage braucht, nimmt ``connect``.
    """
    con = duckdb.connect(str(database), read_only=read_only)
    try:
        grenzen_setzen(con, env)
    except DuckDBFehler:
        con.close()
        raise
    return con


def connect(config: Config, database: str | Path = ":memory:", *,
            read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Eine Verbindung, die die Ablage lesen kann - lokal oder S3."""
    con = verbinde(database, read_only=read_only)
    if config.remote:
        try:
            s3_einrichten(con, config)
        except DuckDBFehler:
            con.close()
            raise
    return con
