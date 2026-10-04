"""Prueft, dass ``docs/eine-zahl.md`` nicht still veraltet.

Das Dokument rollt die Rate 94,5 rueckwaerts bis zur API-Antwort auf. Es ist
damit die ausfuehrlichste Sammlung gemessener Zahlen im Projekt - und genau
deshalb die Datei, die beim naechsten Neubau als erste unbemerkt falsch wird.
Jede Zahl darin wird hier gegen die gebauten Daten gehalten.

Die Tests tragen ``referenzstand``, weil sie am gepinnten Stand haengen und
nicht am woechentlichen Datenlauf: Neue Daten duerfen die Zahlen aendern, ohne
dass der Lauf rot wird. Wer neu baut, zieht das Dokument mit.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from gold_pipeline import einwohner_je_stadt


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOKUMENT = PROJECT_ROOT / "docs" / "eine-zahl.md"
DATA = PROJECT_ROOT / "data"
GOLD = DATA / "gold" / "dataset=fact_offense" / "part-0001.parquet"
TRACT = DATA / "gold" / "dataset=dim_tract" / "part-0001.parquet"
# Seit Vertrag 6 liegt der Nenner je Vintage in einer eigenen Tabelle.
ACS = DATA / "gold" / "dataset=dim_tract_acs" / "part-0001.parquet"
NENNER = einwohner_je_stadt(f"read_parquet('{TRACT}')",
                            f"read_parquet('{ACS}')")
SILVER = DATA / "silver" / "dataset=crime_offense" / "part-0001.parquet"
LAUF = "run_20260905T174633859259Z"
BRONZE = DATA / "bronze" / "city=chicago" / "ingest_date=2026-09-05" / LAUF
RAW = DATA / "raw" / "city=chicago" / "ingest_date=2026-09-05" / LAUF

pytestmark = pytest.mark.referenzstand


@pytest.fixture(scope="module")
def text() -> str:
    return DOKUMENT.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def con():
    duckdb = pytest.importorskip("duckdb")
    for pfad in (GOLD, TRACT, SILVER):
        if not pfad.exists():
            pytest.skip(f"nicht gebaut: {pfad}")
    verbindung = duckdb.connect()
    try:
        yield verbindung
    finally:
        verbindung.close()


def zahlen(text: str) -> set[int]:
    """Alle ganzen Zahlen im Dokument, Apostroph als Tausendertrenner.

    Geprueft wird gegen diese Menge statt gegen je eine eigene Regex. Eine
    Regex je Zahl bricht, sobald jemand eine Tabelle umbaut - und bricht dann
    stillschweigend, weil ``re.search`` nichts findet und der Test sich
    ueberspringt. Die Menge haelt auch nach einem Umbau.
    """
    return {int(t.replace("'", "")) for t in re.findall(r"\b\d[\d']*\b", text)}


def steht_drin(text: str, wert: int) -> bool:
    return wert in zahlen(text)


def test_das_dokument_existiert():
    assert DOKUMENT.exists(), f"{DOKUMENT} fehlt"


def test_die_ueberschrift_nennt_die_zahl(text, con):
    """94,5 steht im Titel - sie ist der Aufhaenger des ganzen Dokuments."""
    assert text.startswith("# 94,5"), "der Titel nennt die Zahl nicht mehr"
    echt = con.execute(f"""
        WITH e AS ({NENNER})
        SELECT round(count(*) * 1000.0 / any_value(e.n), 1)
        FROM read_parquet('{GOLD}') f
        JOIN read_parquet('{TRACT}') t ON t.geoid = f.tract_geoid
        JOIN e ON e.city = t.city
        WHERE t.city = 'chicago'
    """).fetchone()[0]
    assert echt == pytest.approx(94.5, abs=0.05), (
        f"Chicago liegt jetzt bei {echt} - Titel und Stufe 0 mitziehen"
    )


def test_die_rechnung_geht_auf(text, con):
    """Zaehler, Nenner und Ergebnis der Stufe 1 - alle drei gemessen."""
    zaehler, nenner = con.execute(f"""
        SELECT count(*), any_value(e.n)
        FROM read_parquet('{GOLD}') f
        JOIN read_parquet('{TRACT}') t ON t.geoid = f.tract_geoid
        JOIN ({NENNER}) e ON e.city = t.city
        WHERE t.city = 'chicago'
    """).fetchone()
    formel = re.search(
        r"([\d']+) Delikte\s+/\s+([\d']+) Einwohner\s+×\s+1000\s+=\s+([\d,]+)",
        text,
    )
    assert formel, "die Formelzeile in Stufe 1 ist nicht mehr lesbar"
    genannt_zaehler, genannt_nenner = (
        int(formel.group(i).replace("'", "")) for i in (1, 2)
    )
    assert genannt_zaehler == zaehler, (
        f"Zaehler: genannt {genannt_zaehler:,}, echt {zaehler:,}"
    )
    assert genannt_nenner == nenner, (
        f"Nenner: genannt {genannt_nenner:,}, echt {nenner:,}"
    )
    genannt_ergebnis = float(formel.group(3).replace(",", "."))
    assert genannt_ergebnis == pytest.approx(
        zaehler * 1000.0 / nenner, abs=0.005
    ), f"das Ergebnis {genannt_ergebnis} passt nicht zu den beiden Zahlen"


def test_der_nenner_stimmt(text, con):
    """Stufe 2 - Anzahl Tracts, Flaechenanteil, Randtracts, Nullbevoelkerung."""
    anzahl, kleinster = con.execute(f"""
        SELECT count(*), min(city_area_share) FROM read_parquet('{TRACT}')
        WHERE city = 'chicago'
    """).fetchone()
    assert steht_drin(text, anzahl), f"{anzahl} Chicago-Tracts fehlen"
    assert f"{kleinster:.3f}".replace(".", ",") in text, (
        f"kleinster Flaechenanteil ist {kleinster:.4f} - Stufe 2 mitziehen"
    )

    rand = con.execute(f"""
        SELECT count(*) FROM read_parquet('{TRACT}')
        WHERE city IS NULL AND city_area_share > 0
    """).fetchone()[0]
    assert re.search(rf"\*\*{rand} Tracts berühren", text), (
        f"{rand} Randtracts - die Zahl in Stufe 2 stimmt nicht mehr"
    )

    leer = con.execute(f"""
        SELECT count(*) FROM read_parquet('{TRACT}') d
        JOIN read_parquet('{ACS}') a
          ON a.geoid = d.geoid AND a.vintage = d.reference_vintage
        WHERE d.city = 'chicago' AND a.population = 0
    """).fetchone()[0]
    wort = {1: "Ein", 2: "Zwei", 3: "Drei", 4: "Vier", 5: "Fuenf"}.get(leer)
    assert wort and f"**{wort}**" in text.replace("Fünf", "Fuenf"), (
        f"{leer} Tracts ohne Einwohner - Stufe 2 mitziehen"
    )


def test_der_zaehler_ist_vollstaendig_aufgeteilt(text, con):
    """Stufe 3 - die geo_status-Tabelle muss auf die Gesamtzahl aufgehen.

    Das ist die inhaltliche Aussage des Abschnitts: Was nicht in die Rate
    geht, wird benannt statt weggelassen. Ein Dokument, dessen Tabelle sich
    nicht mehr aufsummiert, behauptet etwas Falsches.
    """
    zeilen = dict(con.execute(f"""
        SELECT geo_status, count(*) FROM read_parquet('{GOLD}')
        WHERE reporting_city = 'chicago' GROUP BY 1
    """).fetchall())
    for status, anzahl in zeilen.items():
        assert re.search(rf"\| `{status}` \| ([\d']+) \|", text), (
            f"geo_status {status} fehlt in der Tabelle"
        )
        genannt = int(re.search(rf"\| `{status}` \| ([\d']+) \|",
                                text).group(1).replace("'", ""))
        assert genannt == anzahl, f"{status}: genannt {genannt:,}, echt {anzahl:,}"

    summe = sum(zeilen.values())
    genannt = int(re.search(r"\| \*\*Summe\*\* \| \*\*([\d']+)\*\* \|",
                            text).group(1).replace("'", ""))
    assert genannt == summe, f"Summenzeile {genannt:,}, echt {summe:,}"


def test_die_guete_der_zuordnung_stimmt(text, con):
    """Stufe 3 - die mapping_status-Tabelle."""
    for status, anzahl in con.execute(f"""
        SELECT mapping_status, count(*) FROM read_parquet('{GOLD}')
        WHERE reporting_city = 'chicago' GROUP BY 1
    """).fetchall():
        treffer = re.search(rf"\| `{status}` \| ([\d']+) \|", text)
        assert treffer, f"mapping_status {status} fehlt in der Tabelle"
        genannt = int(treffer.group(1).replace("'", ""))
        assert genannt == anzahl, f"{status}: genannt {genannt:,}, echt {anzahl:,}"


def test_die_granularitaet_stimmt(text, con):
    """Stufe 4 - Tat- und Fallebene, Zeilen wie Raten."""
    for stadt, zeilen, faelle in con.execute(f"""
        SELECT reporting_city, count(*), count(*) FILTER (counts_case)
        FROM read_parquet('{GOLD}') GROUP BY 1
    """).fetchall():
        assert steht_drin(text, zeilen), f"{stadt}: {zeilen:,} Zeilen fehlen"
        assert steht_drin(text, faelle), f"{stadt}: {faelle:,} Faelle fehlen"

    silver_detroit = con.execute(
        f"SELECT count(*) FROM read_parquet('{SILVER}') WHERE city = 'detroit'"
    ).fetchone()[0]
    assert steht_drin(text, silver_detroit), (
        f"Detroits {silver_detroit:,} Silver-Zeilen fehlen in Stufe 4"
    )

    mehrzeilig = con.execute(f"""
        SELECT count(*) FROM (
            SELECT event_id FROM read_parquet('{SILVER}')
            WHERE city = 'chicago' GROUP BY 1 HAVING count(*) > 1
        )
    """).fetchone()[0]
    assert re.search(rf"\*\*{mehrzeilig}\s*\n?Chicagoer Fälle\*\*|\*\*{mehrzeilig} Chicagoer", text), (
        f"{mehrzeilig} mehrzeilige Faelle - Stufe 4 mitziehen"
    )

    raten = dict(con.execute(f"""
        WITH e AS ({NENNER})
        SELECT t.city, list_value(
            round(count(*) * 1000.0 / any_value(e.n), 1),
            round(count(*) FILTER (f.counts_case) * 1000.0 / any_value(e.n), 1))
        FROM read_parquet('{GOLD}') f
        JOIN read_parquet('{TRACT}') t ON t.geoid = f.tract_geoid
        JOIN e ON e.city = t.city
        WHERE t.city IS NOT NULL GROUP BY 1
    """).fetchall())
    for stadt, (tat, fall) in raten.items():
        zeile = re.search(rf"\| {stadt.capitalize()} \| \*\*([\d,]+)\*\* \| ([\d,]+) \|", text)
        assert zeile, f"Ratenzeile fuer {stadt} fehlt in Stufe 4"
        assert float(zeile.group(1).replace(",", ".")) == pytest.approx(tat, abs=0.05)
        assert float(zeile.group(2).replace(",", ".")) == pytest.approx(fall, abs=0.05)


def test_die_herkunftskette_nennt_die_echten_laeufe(text):
    """Stufe 5 - jeder Lauf und jede Pruefsumme im Diagramm steht im Manifest.

    Geprueft wird in diese Richtung: Was im Dokument steht, muss im Manifest
    vorkommen. Ein erfundener oder veralteter Lauf faellt damit auf; ein neu
    hinzugekommener nicht - der wird von ``test_vertragsversionen`` erfasst.
    """
    manifest = GOLD.parent / "manifest.json"
    if not manifest.exists():
        pytest.skip("Gold-Manifest fehlt")
    roh = manifest.read_text(encoding="utf-8")
    m = json.loads(roh)

    anfang = text.index("## Stufe 5")
    block = text[anfang:text.index("## Stufe 6")]

    for lauf in re.findall(r"\brun_\d{8}T\d{15}Z\b", block):
        assert lauf in roh, f"{lauf} steht im Dokument, aber nicht im Manifest"

    for abdruck in re.findall(r"\b([0-9a-f]{8})…", block):
        assert abdruck in roh, (
            f"Abdruck {abdruck}… steht im Dokument, aber nicht im Manifest"
        )

    assert str(m["contract_version"]) in block, "die Vertragsversion stimmt nicht"


def test_der_vollstaendigkeitsnachweis_stimmt(text):
    """Stufe 6 - die Zahlen aus dem Bronze-Manifest."""
    manifest = BRONZE / "manifest.json"
    if not manifest.exists():
        pytest.skip(f"{manifest} fehlt")
    m = json.loads(manifest.read_text(encoding="utf-8"))

    anfang = text.index("## Stufe 6")
    block = text[anfang:text.index("## Stufe 7")]

    assert m["run_id"] in block, "der Lauf in Stufe 6 stimmt nicht"
    assert m["mode"] in block, "der Modus in Stufe 6 stimmt nicht"
    v = m["completeness"]
    assert v["verified"] is True, "der Lauf ist nicht mehr verified"
    for schluessel in ("source_count_before", "source_count_after", "downloaded_rows"):
        assert steht_drin(block, v[schluessel]), (
            f"{schluessel} = {v[schluessel]:,} fehlt in Stufe 6"
        )
    assert v["snapshot_sha256"][:8] in block, "der id-Abdruck fehlt"
    assert m["source_schema"]["fingerprint"][:8] in block, "der Schemaabdruck fehlt"
    assert steht_drin(block, len(m["source_schema"]["fields"])), (
        f"die Feldzahl {len(m['source_schema']['fields'])} fehlt in Stufe 6"
    )


def test_das_beweisstueck_stimmt(text):
    """Stufe 7 - so viele Antwortdateien, wie das Manifest auffuehrt."""
    manifest = RAW / "manifest.json"
    if not manifest.exists():
        pytest.skip(f"{manifest} fehlt")
    m = json.loads(manifest.read_text(encoding="utf-8"))

    anfang = text.index("## Stufe 7")
    block = text[anfang:text.index("---", anfang)]

    seiten = [d for d in m["files"] if d["path"].endswith(".json.gz")]
    assert re.search(rf"\*\*{len(seiten)} Antworten", block), (
        f"{len(seiten)} Antwortdateien - Stufe 7 mitziehen"
    )
    erste = seiten[0]
    assert steht_drin(block, erste["size_bytes"]), (
        f"die Groesse der ersten Antwort ({erste['size_bytes']:,}) fehlt"
    )
    assert erste["sha256"][:8] in block, "die Pruefsumme der ersten Antwort fehlt"


def test_der_einzelfall_stimmt(text, con):
    """Der durchgerechnete Fall - er traegt vier Entscheidungen auf einmal.

    Wenn dieser Fall nicht mehr stimmt, ist das Herzstueck des Dokuments
    falsch: Es ist die einzige Stelle, an der ein Leser die ganze Kette an
    einer einzigen Zeile nachvollziehen kann.
    """
    zeilen = con.execute(f"""
        SELECT offense_id, occurred_at_local, occurred_at_utc, hour_of_day,
               source_offense_code, nibrs_code, mapping_status, tract_geoid,
               geo_status, counts_case
        FROM read_parquet('{GOLD}')
        WHERE event_id = 'JH100028' ORDER BY occurred_at_local
    """).fetchall()
    assert len(zeilen) == 2, (
        f"JH100028 hat jetzt {len(zeilen)} Zeilen statt 2 - der Abschnitt "
        "lebt davon, dass es genau zwei sind"
    )

    for (oid, lokal, utc, stunde, iucr, nibrs, mapping,
         tract, geo, fall) in zeilen:
        assert f"`offense_id` {oid}" in text, f"offense_id {oid} fehlt"
        for zeitpunkt in (lokal, utc):
            assert zeitpunkt.strftime("%Y-%m-%d %H:%M") in text, (
                f"Zeitpunkt {zeitpunkt} fehlt in der Fall-Tabelle"
            )
        assert steht_drin(text, stunde), f"hour_of_day {stunde} fehlt"
        assert f"`{iucr}`" in text and f"`{nibrs}`" in text
        assert f"`{mapping}`" in text and f"`{geo}`" in text
        assert tract in text, f"Tract {tract} fehlt"

    assert zeilen[0][-1] is True and zeilen[1][-1] is False, (
        "die erste Zeile zaehlt als Fall, die zweite nicht - genau das ist "
        "der Punkt des Abschnitts"
    )


def test_der_tract_des_einzelfalls_stimmt(text, con):
    """Die 197,6 am Schluss - die Zahl, die zeigt, wie stark Tracts streuen."""
    tract = "17031690400"
    delikte = con.execute(
        f"SELECT count(*) FROM read_parquet('{GOLD}') WHERE tract_geoid = '{tract}'"
    ).fetchone()[0]
    bevoelkerung, anteil = con.execute(
        f"SELECT a.population, d.city_area_share "
        f"FROM read_parquet('{TRACT}') d "
        f"JOIN read_parquet('{ACS}') a "
        f"  ON a.geoid = d.geoid AND a.vintage = d.reference_vintage "
        f"WHERE d.geoid = '{tract}'"
    ).fetchone()

    assert steht_drin(text, delikte), f"{delikte} Delikte im Tract fehlen"
    assert steht_drin(text, bevoelkerung), f"{bevoelkerung:,} Einwohner fehlen"
    assert anteil == pytest.approx(1.0, abs=0.0005), (
        "der Tract liegt nicht mehr ganz in Chicago"
    )

    rate = delikte * 1000.0 / bevoelkerung
    genannt = float(re.search(r"\*\*([\d]+,[\d])\s*je\n?\s*1'000\*\*", text)
                    .group(1).replace(",", "."))
    assert genannt == pytest.approx(rate, abs=0.05), (
        f"Tractrate: genannt {genannt}, echt {rate:.1f}"
    )


def test_jede_stufe_ist_da(text):
    """Die Kette darf keine Luecke haben - sonst bricht die Argumentation."""
    fehlend = [n for n in range(8) if f"## Stufe {n} ·" not in text]
    assert not fehlend, f"diese Stufen fehlen: {fehlend}"
