"""Schreibt die Tract-Umrisse als GeoJSON fuer eine Karte.

Aufruf aus dem Projekt-Root::

    python -m serving.export_geojson

Ergebnis: ``data/serving/tracts.geojson`` mit den 1'055 Tracts der beiden
Studienstaedte, dazu ``tracts.manifest.json`` mit der Herkunft.

**Warum es diese Datei braucht.** Eine Choroplethenkarte faerbt Flaechen ein,
also braucht sie Polygone. ``gold/dim_tract`` fuehrt aber nur Zentroide - die
Umrisse liegen in ``silver/tract`` als WKB, ein Format, das kein Browser liest.
Diese Datei schlaegt die Bruecke, einmal beim Bauen statt bei jeder Abfrage.

**Warum die Geometrie nicht einfach nach Gold wandert.** ``dim_tract`` deckt
beide Countys ab, nicht nur die Staedte; mit Geometrie waere die Dimension
26 MB statt 0,4 MB, und jedes ``SELECT *`` darauf wuerde sie mitschleppen. Gold
soll klein und schnell bleiben. Die Karte braucht ausserdem GeoJSON und nicht
WKB - eine Spalte in der Dimension haette das Problem nur verschoben.

**Was in den Eigenschaften steht - und was bewusst nicht.** Je Flaeche nur
``geoid``, ``city`` und ``tract_name``, also die Identitaet. **Keine
Einwohnerzahl, keine Rate, keine Fallzahl.** Wer faerben will, verbindet ueber
``geoid`` mit ``dim_tract`` und ``fact_offense``. Eine Kennzahl auch hier
abzulegen waere eine zweite Wahrheit, die veralten kann, ohne dass man es ihr
ansieht - genau der Grund, aus dem die Auswertungsdatenbank Sichten haelt und
keine Kopien (siehe Modulkopf von ``serving``).

**Vereinfachung.** Die Umrisse kommen mit voller TIGER-Genauigkeit und ergaeben
eine Datei von 2,94 MB. Douglas-Peucker mit 0,00002 Grad - rund **zwei Meter** -
macht daraus 0,55 MB. Gemessen kostet das:

====================  ==========  ================  ===================
Toleranz              Datei       Flaeche je Tract  Stadtflaeche gesamt
====================  ==========  ================  ===================
keine                   2,94 MB              -                -
0,00002  (~2 m)         0,55 MB        -0,0002 %         -0,011 %
0,0001   (~11 m)        0,42 MB        -0,0008 %         -0,055 %
0,0005   (~56 m)        0,37 MB        -0,0826 %            -
====================  ==========  ================  ===================

**Der ganze Gewinn liegt in den ersten zwei Metern** - 2,94 auf 0,55 MB. Wer
weiter vereinfacht, spart noch 0,13 MB und wird dafuer fuenfmal ungenauer; das
ist kein Handel. Was die Datei jenseits der Geometrie kostet, ist der
GeoJSON-Rahmen selbst: 0,39 MB Umrisse, der Rest sind ``Feature``-Huellen und
Eigenschaften.

Die dritte Spalte misst die Flaeche je Tract, die vierte die Vereinigung aller
Tracts einer Stadt. Die vierte ist die interessantere: Sie zeigt, ob zwischen
Nachbarflaechen Luecken aufreissen, wenn eine gemeinsame Grenze zweimal
unabhaengig vereinfacht wird. Tun sie kaum - 0,011 % der Stadtflaeche
entspricht einem Saum von wenigen Zentimetern, auf einer Stadtkarte
unsichtbar.

**Was das Bild belegt.** Die 1'055 Flaechen einmal gezeichnet, zeigen zwei
Dinge, die keine Zahl so deutlich sagt:

* **Detroit hat zwei Loecher** - Hamtramck und Highland Park, zwei
  eigenstaendige Staedte, die vollstaendig von Detroit umschlossen sind. Sie
  fehlen zu Recht: 14 Tracts dort tragen keine Stadtzuordnung, weil die
  Mehrheitsregel sie einer anderen Gemeinde zuschlaegt. Waeren sie dabei,
  waere Detroits Nenner zu gross und die Rate zu niedrig.
* **Chicagos abgetrennter Block im Nordwesten** ist O'Hare. Tract 9800 hat
  dort **null Einwohner** - der Flughafen. Genau fuer solche Flaechen ist die
  Rate ``NULL`` und nicht null; sonst leuchtete der Flughafen als sicherste
  Gegend der Stadt.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from gold_pipeline.build_gold import VEREINFACHUNG_GRAD
from serving import SERVING_LAYER
from storage import for_root
from storage import duckdb as storage_duckdb


LOG = logging.getLogger("export_geojson")

GEOJSON_NAME = "tracts.geojson"
MANIFEST_NAME = "tracts.manifest.json"
PARQUET_FILE = "part-0001.parquet"

# Zwei Meter. Warum gerade die, steht im Modulkopf.
#
# Gelesen und nicht getippt: Seit dem 14.10.2026 vereinfacht auch Gold
# (``dim_tract_geo``, fuer die Karte in Kibana). Zwei Toleranzen nebeneinander
# hiessen, dass die Karte dort und die Karte im Browser verschieden genaue
# Umrisse zeigen, ohne dass es jemandem auffiele.
TOLERANZ = VEREINFACHUNG_GRAD

# Nur die Identitaet. Kennzahlen kommen ueber geoid aus dim_tract.
EIGENSCHAFTEN = ("geoid", "city", "tract_name")


def quellen(data_root: Path) -> tuple[str, str]:
    """Die Umrisse aus Silver, die Stadtzuordnung aus Gold - lokal oder s3://."""
    ablage = for_root(data_root)
    tract = ablage.list_files("silver/dataset=tract", f"**/{PARQUET_FILE}")
    dim = f"gold/dataset=dim_tract/{PARQUET_FILE}"
    if not tract:
        raise RuntimeError(
            f"Keine Tract-Geometrie unter {data_root}/silver/dataset=tract. "
            "Zuerst 'python -m silver_pipeline.build_tract'."
        )
    if not ablage.exists(dim):
        raise RuntimeError(
            f"{ablage.local_path(dim)} fehlt - ohne sie ist nicht bekannt, welcher "
            "Tract zu welcher Stadt gehoert. Zuerst 'python -m gold_pipeline.build_gold'."
        )
    return ablage.resolve_read_path(tract[-1]), ablage.resolve_read_path(dim)


def sammle(
    con: duckdb.DuckDBPyConnection,
    tract: Path,
    dim: Path,
    *,
    toleranz: float,
    alle: bool,
) -> list[dict]:
    """Liest die Umrisse und gibt sie als GeoJSON-Features zurueck.

    ``ST_Simplify`` kann eine Flaeche unguelig machen oder ganz verschwinden
    lassen, wenn die Toleranz groesser ist als die Flaeche selbst. Beides waere
    ein Loch in der Karte, das niemandem auffiele - deshalb wird es hier
    geprueft und nicht gehofft.
    """
    stadtfilter = "" if alle else "AND d.city IS NOT NULL"
    geom = (
        "ST_GeomFromWKB(t.geometry)" if toleranz <= 0
        else f"ST_Simplify(ST_GeomFromWKB(t.geometry), {toleranz})"
    )
    zeilen = con.execute(f"""
        SELECT d.geoid, d.city, d.tract_name,
               ST_AsGeoJSON({geom})    AS geometrie,
               ST_IsValid({geom})      AS gueltig,
               ST_IsEmpty({geom})      AS leer
        FROM read_parquet('{tract}') t
        JOIN read_parquet('{dim}') d ON d.geoid = t.geoid
        WHERE t.geometry IS NOT NULL {stadtfilter}
        ORDER BY d.geoid
    """).fetchall()

    if not zeilen:
        raise RuntimeError(
            "Keine Flaeche gefunden. Ohne --alle werden nur Tracts der beiden "
            "Studienstaedte ausgegeben; ist dim_tract.city ueberall NULL, "
            "wurde Gold ohne die Ortsgrenzen gebaut."
        )

    kaputt = [z[0] for z in zeilen if not z[4] or z[5]]
    if kaputt:
        raise RuntimeError(
            f"{len(kaputt)} Flaechen sind nach dem Vereinfachen ungueltig oder "
            f"leer, zuerst {kaputt[:5]}. Mit --toleranz 0 laesst sich das "
            "Vereinfachen abschalten."
        )

    return [
        {
            "type": "Feature",
            "id": geoid,
            "properties": {"geoid": geoid, "city": city, "tract_name": name},
            "geometry": json.loads(geometrie),
        }
        for geoid, city, name, geometrie, _, _ in zeilen
    ]


def build(data_root: Path, *, toleranz: float = TOLERANZ, alle: bool = False) -> Path:
    tract, dim = quellen(data_root)
    con = storage_duckdb.connect(for_root(data_root).config)
    try:
        con.execute("INSTALL spatial")
        con.execute("LOAD spatial")
        features = sammle(con, tract, dim, toleranz=toleranz, alle=alle)
    finally:
        con.close()

    ziel = data_root / SERVING_LAYER / GEOJSON_NAME
    ziel.parent.mkdir(parents=True, exist_ok=True)

    inhalt = {"type": "FeatureCollection", "features": features}
    manifest = {
        "gebaut_am_utc": datetime.now(timezone.utc).isoformat(),
        "features": len(features),
        "toleranz_grad": toleranz,
        "toleranz_meter_etwa": round(toleranz * 111_000),
        "eigenschaften": list(EIGENSCHAFTEN),
        "nur_studienstaedte": not alle,
        "derived_from": {"silver_tract": str(tract), "gold_dim_tract": str(dim)},
        "hinweis": (
            "Nur Identitaet, keine Kennzahlen. Zum Faerben ueber geoid mit "
            "dim_tract und fact_offense verbinden."
        ),
    }

    # Wie ueberall: erst in .part, dann umbenennen. Eine halb geschriebene
    # Karte faellt sonst erst dem auf, der sie oeffnet.
    for datei, daten in ((ziel, inhalt), (ziel.with_name(MANIFEST_NAME), manifest)):
        arbeit = datei.with_name(f".{datei.name}.part")
        arbeit.write_text(json.dumps(daten, ensure_ascii=False), encoding="utf-8")
        arbeit.replace(datei)

    LOG.info("%s: %d Flaechen, %.2f MB, Toleranz %.5f Grad (~%d m)",
             ziel, len(features), ziel.stat().st_size / 1e6,
             toleranz, round(toleranz * 111_000))
    return ziel


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Schreibt die Tract-Umrisse als GeoJSON fuer eine Karte."
    )
    parser.add_argument("--data-root", type=Path, default=None,
                        help="Wurzel der Schichten (Vorgabe: LOCAL_DATA_ROOT oder data)")
    parser.add_argument(
        "--toleranz", type=float, default=TOLERANZ,
        help=f"Douglas-Peucker in Grad, 0 schaltet ab (Vorgabe {TOLERANZ}, ~2 m)",
    )
    parser.add_argument(
        "--alle", action="store_true",
        help="alle Tracts beider Countys statt nur der beiden Staedte",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = arguments()
    from storage.managed import guard
    guard(for_root(args.data_root).local_root, allow_worker=True)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    try:
        ziel = build(for_root(args.data_root).local_root,
                     toleranz=args.toleranz, alle=args.alle)
    except RuntimeError as fehler:
        LOG.error("%s", fehler)
        return 1
    print(f"\nBereit. Die Karte liest:\n  {ziel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
