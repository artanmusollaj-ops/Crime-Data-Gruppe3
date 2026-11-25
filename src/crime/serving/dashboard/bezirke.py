"""Die Polizeibezirke im Speicher: Umrisse, Einwohner je Vintage.

Seit dem 25.11.2026 (Gold-Vertrag 11). Das Brett »Geografie« zeigt damit
neben der Rate je Tract die Rate und die Festnahmequote je Bezirk.

**Einwohner je Bezirk** sind die Summe ueber ``bridge_tract_police_area``:
Einwohner eines Stadt-Tracts mal seinem Flaechenanteil am Bezirk, je
Vintage. Die Anteile eines Tracts summieren sich in Gold auf 1, die Bezirke
einer Stadt ergeben also ihre Einwohner. Gezaehlt werden nur Bezirke mit
``within_city`` - Chicagos District 31 (Norridge und Harwood Heights) nicht.

Ein aelteres Release fuehrt beide Tabellen nicht. Dann gibt ``lade_bezirke``
``None`` zurueck, und das Brett sagt, warum es keine Bezirke zeigt, statt
dass das ganze Dashboard nicht laedt.
"""

from __future__ import annotations

from typing import Any


def lade_bezirke(con: Any, ablage: Any, release: str, acs: str) -> dict[str, Any] | None:
    """Legt ``bezirk`` und ``bezirk_einwohner`` an; die Umrisse als Kartenpfade."""
    from serving.dashboard.geografie import pfade

    pfade_je = {}
    for tabelle in ("dim_police_area", "bridge_tract_police_area"):
        rel = f"{release}/gold/dataset={tabelle}"
        if not ablage.exists(rel, "manifest.json"):
            return None
        pfade_je[tabelle] = ablage.resolve_read_path(rel, "part-0001.parquet")
    bezirke = f"read_parquet('{pfade_je['dim_police_area']}', hive_partitioning=false)"
    bruecke = f"read_parquet('{pfade_je['bridge_tract_police_area']}', hive_partitioning=false)"
    con.execute(f"""
        CREATE TABLE bezirk AS
        SELECT city AS stadt, TRY_CAST(area_id AS UTINYINT) AS nr, area_name AS name,
               within_city AS zaehlt, boundary_wkt
        FROM {bezirke}""")
    con.execute(f"""
        CREATE TABLE bezirk_einwohner AS
        SELECT b.city AS stadt, TRY_CAST(b.area_id AS UTINYINT) AS nr, a.vintage,
               sum(a.population * b.tract_share) AS population
        FROM {bruecke} b
        JOIN read_parquet('{acs}', hive_partitioning=false) a USING (geoid)
        GROUP BY ALL""")
    karten = pfade(con.execute("""
        SELECT CAST(nr AS VARCHAR), stadt, name, boundary_wkt
        FROM bezirk WHERE zaehlt ORDER BY stadt, nr""").fetchall())
    con.execute("ALTER TABLE bezirk DROP COLUMN boundary_wkt")
    return karten
