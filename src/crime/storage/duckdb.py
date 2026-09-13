"""DuckDB-Verbindungen, die S3 lesen koennen, wenn die Ablage es verlangt.

Im ``local``-Modus ist das ``duckdb.connect()`` wie bisher. In ``s3`` und
``hybrid`` werden ``httpfs`` geladen und ein **temporaeres** Secret angelegt
- es lebt nur in dieser Verbindung, nichts wird auf Platte persistiert. Die
Schluessel kommen aus der Konfiguration, nie ins Log.

Abfragen sehen danach gleich aus::

    con.execute(f"SELECT count(*) FROM read_parquet('{storage.resolve_read_path(...)}')")
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from storage.config import Config


class DuckDBFehler(RuntimeError):
    """Eine Extension oder das Secret liess sich nicht einrichten."""


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


def connect(config: Config, database: str | Path = ":memory:", *,
            read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Eine Verbindung, die die Ablage lesen kann - lokal oder S3."""
    con = duckdb.connect(str(database), read_only=read_only)
    if config.remote:
        s3_einrichten(con, config)
    return con
