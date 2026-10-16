"""Haelt die Kennzahlen der Dokumente gegen das aktuelle Release.

**Warum es diesen Waechter gibt.** Am 20.9.2026 wurden die Dokumente gegen
Release ``2026-09-19T23-05-26Z`` nachgerechnet. 81 Zeilen in neun Dokumenten
trugen veraltete Zahlen, und ausgerechnet die am haeufigsten wiederholten waren
die falschen - ``259'272`` stand 23-mal da, ``347'957`` und ``344'617`` je
zwoelfmal. Keine davon war je grob falsch; sie waren um Zehntelprozente daneben,
weil die Strecke seither neu gebaut wurde. Genau deshalb faellt so etwas
niemandem auf.

**Wie geprueft wird.** Nicht: "steht Zahl X an Stelle Y" - das waere eine zweite
Liste, die selbst veraltet. Sondern umgekehrt: Jede Tausenderzahl in den
Dokumenten wird gegen die **gemessenen** Kennzahlen gehalten. Ist sie einer
davon *nahe*, ohne eine zu sein, ist sie mit grosser Wahrscheinlichkeit deren
veraltete Fassung. Die Schwelle liegt bei 0,3 %; die tatsaechlich gefundenen
Abweichungen lagen zwischen 0,001 % und 0,14 %, die naechstgelegene echte
Nachbarzahl (``88'278`` gegen ``88'686``) bei 0,46 %.

**Was er nicht kann.** Eine Zahl, die zu keiner Kennzahl gehoert, sieht er
nicht. Er ersetzt das Nachrechnen nicht, er faengt das Veralten.

**Wann er laeuft.** Er traegt ``referenzstand`` und laeuft damit weder auf
Pull Requests noch im woechentlichen Datenlauf - beide haetten den falschen
Datenstand: der eine gar keinen, der andere einen frischeren als die Dokumente.
Er gehoert zu ``python -m pytest -m referenzstand`` auf dem eigenen Rechner,
gegen den gepinnten Stand, und dort vor allem vor einer Abgabe.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from gold_pipeline import einwohner_je_stadt


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATEN = PROJECT_ROOT / "data"
DOCS = PROJECT_ROOT / "docs"

pytestmark = pytest.mark.referenzstand

# Zehntelprozente trennen eine veraltete Fassung von ihrem Nachfolger. Ein
# halbes Prozent trennt zwei verschiedene Kennzahlen. Dazwischen liegt die
# Schwelle.
TOLERANZ = 0.003

# Zeilen, die einen Lauf, eine datierte Messung oder einen Verlauf festhalten.
# Ihre Zahlen sollen veraltet sein - das ist ihr Zweck.
SCHUTZ = (
    "run_2026", "1d879a0e", "1cca323d",
    "Zählung vorher", "Zählung nachher", "geladen           ",
    "geladene gegen erwartete Zeilen", "dein Lauf",
    "Detroits Bronze-Lauf", "gelesen über DuckDB",
    "Zusammen 259'356 Zeilen", "zuvor standen hier",
    "Gemessen am 13.9.2026", "Gemessen am 14.9.2026", "gemessen am 13.9.2026",
    "Beide Schnappschüsse enthalten", "in beiden Schnappschüssen",
    "Bronze, Abfrage über Detroits",
    "Nachgemessen am", "Nachgerechnet am",
    # cadvisors Speicherbelegung auf srv01 - 1'047 MiB, gemessen am Container
    # und nicht an unseren Daten. Sie sieht ``serving/rate_tract`` (1'045
    # Zeilen) nur aehnlich; die beiden haben miteinander nichts zu tun, und
    # die MiB-Zahl soll veralten, sobald jemand cadvisor deckelt.
    "Es belegt heute",
    # Die Messung vom 13.9. steht ueber zwei Zeilen; das Datum traegt die erste.
    "23,1 Sekunden",
    # Die drei Regeln der Stadtzuordnung nennen absichtlich die *verworfenen*
    # Einwohnerzahlen nebeneinander, dazu die amtliche des Zensus 2020.
    "Flächengewichtung", "Zensus 2020", "alle berührten Tracts",
    # Das Rauschen im Schnappschussvergleich: 88'677 von 88'685 Zeilen mit
    # bewegter ESRI_OID. Beide Zahlen messen das Paar vom 11./12.9.2026 und
    # sehen dem heutigen Detroit-Bestand (88'686) nur aehnlich. Sie duerfen
    # veralten - sie beschreiben zwei bestimmte Laeufe, nicht den Stand.
    "Zeilennummer der ArcGIS-Antwort",
    # platzbedarf.md zitiert die Rechnung, die es ersetzt: 1'874'417 Zeilen
    # gegen 348'341 ergaben den 5,5-Faktor. 348'341 war der Zeilenbestand, als
    # jemand das aufschrieb, und ist heute 348'329 - er *soll* veraltet sein,
    # sonst waere der Satz keine Kritik an der alten Zahl mehr.
    "war die Antwort **ein Faktor**",
    # Die Hochrechnung in platzbedarf.md rechnet mit den Zeilen, die am
    # 3.10.2026 an den beiden APIs *gemessen* wurden
    # (config/zeilen_je_jahrgang.csv), nicht mit dem gebauten Bestand. Die
    # beiden Zahlen muessen auseinanderliegen: Geladen wurde am 4.10., und der
    # laufende Jahrgang waechst taeglich - Detroit 2026 um 240 Zeilen. Waeren
    # sie gleich, waere eine der beiden abgeschrieben.
    "Zeilen × ",
)

# datenhistorie.md *ist* der Verlauf; archiv/ haelt Ueberholtes absichtlich.
AUSGENOMMEN = ("datenhistorie.md", "archiv")


def _wert(text: str) -> int:
    return int(text.replace("'", ""))


@pytest.fixture(scope="module")
def kennzahlen() -> dict[str, int]:
    """Was das aktuelle Release und die Schichten darunter wirklich sagen."""
    zeiger = DATEN / "releases" / "AKTUELL.json"
    if not zeiger.is_file():
        pytest.skip("kein Release - erst 'run_all --release' laufen lassen")
    kennung = json.loads(zeiger.read_text(encoding="utf-8"))["release_id"]
    freigabe = DATEN / "releases" / f"release={kennung}" / "release.json"
    if not freigabe.is_file():
        pytest.skip(f"Release {kennung} liegt nicht lokal")

    zahlen = {n: d["rows"] for n, d in
              json.loads(freigabe.read_text(encoding="utf-8"))["tables"].items()}

    duckdb = pytest.importorskip("duckdb")
    silber = DATEN / "silver" / "dataset=crime_offense" / "part-0001.parquet"
    tracts = DATEN / "gold" / "dataset=dim_tract" / "part-0001.parquet"
    acs = DATEN / "gold" / "dataset=dim_tract_acs" / "part-0001.parquet"
    if not silber.is_file() or not tracts.is_file():
        pytest.skip("Silver oder Gold fehlt")
    con = duckdb.connect()
    S = f"read_parquet('{silber}')"

    for stadt, zeilen, taten, faelle, ohne in con.execute(f"""
            SELECT city, count(*), count(*) FILTER (counts),
                   count(*) FILTER (counts_case),
                   count(*) FILTER (latitude IS NULL)
            FROM {S} GROUP BY 1""").fetchall():
        zahlen[f"{stadt}/anklagen"] = zeilen
        zahlen[f"{stadt}/taten"] = taten
        zahlen[f"{stadt}/faelle"] = faelle
        zahlen[f"{stadt}/ohne_koordinate"] = ohne
    zahlen["silver/crime_offense"] = con.execute(f"SELECT count(*) FROM {S}").fetchone()[0]

    for stadt, lage, n in con.execute(f"""
            SELECT reporting_city, geo_status, count(*)
            FROM read_parquet('{DATEN}/gold/dataset=fact_offense/part-0001.parquet')
            GROUP BY 1, 2""").fetchall():
        zahlen[f"{stadt}/{lage}"] = n
    for stadt, art, n in con.execute(f"""
            SELECT city, mapping_status, count(*) FROM {S}
            WHERE counts GROUP BY 1, 2""").fetchall():
        zahlen[f"{stadt}/{art}"] = n

    for stadt, ew in con.execute(einwohner_je_stadt(
            f"read_parquet('{tracts}')", f"read_parquet('{acs}')")).fetchall():
        zahlen[f"{stadt}/einwohner"] = int(ew)

    for name, muster in (("silver/tract", "dataset=tract/**/*.parquet"),
                         ("silver/place", "dataset=place/**/*.parquet"),
                         ("silver/weather_day", "dataset=weather_day/**/*.parquet")):
        dateien = [str(p) for p in (DATEN / "silver").glob(muster)]
        if dateien:
            zahlen[name] = con.execute(
                f"SELECT count(*) FROM read_parquet({dateien})").fetchone()[0]

    # Abgeleitete Zahlen, die zaehlperspektiven.md fuehrt. Sie stehen dort auf
    # der **Tatebene**, also auf den Gold-Fakten - nicht auf allen Silver-Zeilen.
    # Auf Silver gerechnet kaeme etwas anderes heraus; genau daran ist am
    # 20.9.2026 eine Korrektur dieses Dokuments zuerst gescheitert.
    con.execute(f"CREATE VIEW fakten AS SELECT * FROM read_parquet"
                f"('{DATEN}/gold/dataset=fact_offense/part-0001.parquet')")
    # ``m`` kam am 4.10.2026 dazu: Seit sechs Jahrgaengen in der Tabelle liegen
    # summieren sich auch die *Monate* nicht mehr auf die Gesamtzahl (fuenf
    # Jahreswechsel liegen jetzt innen), und zaehlperspektiven.md nennt die
    # Monatssumme als eigene Spalte. Ohne sie hier sieht sie wie eine veraltete
    # Fassung der Gesamtzahl aus - sie liegt nur neun Vorfaelle daneben.
    for stadt, vorfaelle, mehrfach, summiert, tage, monate in con.execute("""
            WITH v AS (SELECT reporting_city AS city, event_id,
                              count(DISTINCT nibrs_family) AS fam
                       FROM fakten GROUP BY 1, 2),
                 f AS (SELECT reporting_city AS city, nibrs_family AS g,
                              count(DISTINCT event_id) AS n FROM fakten GROUP BY 1, 2),
                 t AS (SELECT reporting_city AS city, date AS d,
                              count(DISTINCT event_id) AS n FROM fakten GROUP BY 1, 2),
                 m AS (SELECT reporting_city AS city,
                              date_trunc('month', date) AS d,
                              count(DISTINCT event_id) AS n FROM fakten GROUP BY 1, 2)
            SELECT v.city, count(*), count(*) FILTER (fam > 1),
                   (SELECT sum(n) FROM f WHERE f.city = v.city),
                   (SELECT sum(n) FROM t WHERE t.city = v.city),
                   (SELECT sum(n) FROM m WHERE m.city = v.city)
            FROM v GROUP BY 1""").fetchall():
        zahlen[f"{stadt}/vorfaelle"] = vorfaelle
        zahlen[f"{stadt}/vorfaelle_mehrfamilie"] = mehrfach
        zahlen[f"{stadt}/vorfaelle_je_familie"] = int(summiert)
        zahlen[f"{stadt}/vorfaelle_je_tag"] = int(tage)
        zahlen[f"{stadt}/vorfaelle_je_monat"] = int(monate)

    # Die blinde Stunde wird gemessen, nicht abgezogen. Bis zum 4.10.2026 stand
    # hier das Literal 30 - die Zahl eines Jahrgangs. Ueber sechs Jahrgaenge
    # sind es sechs solche Stunden und 118 Zeilen, und zaehlperspektiven.md
    # nennt die Gegenzahl ("faellt trotzdem 491'607-fach auf"). Mit dem Literal
    # haette der Waechter sie als veraltete Fassung von detroit/anklagen
    # beanstandet.
    blinde_stunde = con.execute(f"""
        SELECT count(*) FILTER (occurred_at_local IS NOT DISTINCT FROM
                   CAST(timezone('America/Chicago',
                        occurred_at_utc AT TIME ZONE 'UTC') AS TIMESTAMP))
        FROM {S} WHERE city = 'detroit'
    """).fetchone()[0]
    zahlen["detroit/blinde_stunde"] = blinde_stunde
    zahlen["detroit/ohne_blinde_stunde"] = (
        zahlen["detroit/anklagen"] - blinde_stunde)
    zahlen["auffang_90Z"] = con.execute(
        f"SELECT count(*) FROM {S} WHERE counts AND nibrs_code = '90Z'").fetchone()[0]
    con.close()
    return zahlen


@pytest.fixture(scope="module")
def fundstellen() -> list[tuple[str, int, str]]:
    """Jede Tausenderzahl in den Dokumenten, mit Herkunft."""
    dateien = sorted(DOCS.rglob("*.md")) + [PROJECT_ROOT / "README.md",
                                            DOCS / "architektur-einseiter.html"]
    gefunden: list[tuple[str, int, str]] = []
    for pfad in dateien:
        if not pfad.is_file() or any(a in str(pfad) for a in AUSGENOMMEN):
            continue
        text = pfad.read_text(encoding="utf-8")
        if pfad.name == "AENDERUNGEN.md":
            # Nur die Kopftabelle behauptet den Ist-Zustand; der Rest ist Verlauf.
            anfang = text.find("## Der Stand in Zahlen")
            if anfang < 0:
                continue
            versatz = text[:anfang].count("\n")
            text = text[anfang:text.index("## Vertragsversionen", anfang)]
        else:
            versatz = 0
        for i, zeile in enumerate(text.splitlines(), 1):
            if any(s in zeile for s in SCHUTZ):
                continue
            for treffer in re.finditer(r"\b\d{1,3}(?:'\d{3})+\b", zeile):
                roh = treffer.group()
                if roh.endswith("'000"):      # "rund 348'000" ist eine Naeherung
                    continue
                gefunden.append((str(pfad.relative_to(PROJECT_ROOT)),
                                 i + versatz, roh))
    return gefunden


def test_der_waechter_findet_ueberhaupt_zahlen(fundstellen):
    """Ein Sammler, der nichts findet, prueft nichts."""
    assert len(fundstellen) > 150, f"nur {len(fundstellen)} Zahlen gesammelt"


def test_die_kennzahlen_sind_gemessen_worden(kennzahlen):
    for pflicht in ("gold/fact_offense", "silver/crime_offense",
                    "chicago/taten", "detroit/taten", "chicago/einwohner"):
        assert pflicht in kennzahlen, f"{pflicht} fehlt in der Messung"


@pytest.fixture(scope="module")
def testzahlen() -> set[int]:
    """Die Testzahlen dieses Laufs - gesammelt, nicht getippt.

    **Warum sie hier gebraucht werden.** Dieser Waechter sucht Zahlen, die
    einer Kennzahl *aehnlich* sind, und haelt sie fuer deren veraltete
    Fassung. Am 17.10.2026 traf das die Testzahl selbst: **2'100 Tests** liegt
    drei Zeilen neben ``gold/dim_date`` = 2'103, und die Toleranz ist drei
    Promille. Die Dokumente waren richtig, der Waechter nicht.

    ``SCHUTZ`` waere die falsche Antwort: Dort stehen Zahlen, die veralten
    *sollen*. Eine Testzahl soll das nicht - sie hat eigene Waechter
    (``test_readme_nennt_die_testzahl``, ``test_der_kopf_nennt_die_testzahl``,
    ``test_die_testzahl_in_der_tabelle_stimmt``). Sie ist keine Kennzahl der
    Daten, und eine Zahl, die *heute* die richtige Testzahl ist, kann keine
    veraltete Fassung von irgendetwas sein.

    Gesammelt in einem eigenen Prozess, wie in ``test_referenzstand_marker``:
    pytest laesst sich nicht in sich selbst starten.
    """
    # Der Pfad, damit es *eine* Fassung des Sammellaufs gibt und nicht zwei:
    # ``tests/`` liegt nicht auf ``sys.path``, die Nachbardatei haelt die
    # Feinheiten (kein zweites ``-q``, kein ``.pytest_cache``).
    import sys

    if str(Path(__file__).parent) not in sys.path:
        sys.path.insert(0, str(Path(__file__).parent))
    from test_referenzstand_marker import sammle

    ausgewaehlt, abgewaehlt = sammle()
    return {ausgewaehlt, abgewaehlt, ausgewaehlt + abgewaehlt}


def test_keine_dokumentzahl_ist_eine_veraltete_kennzahl(
        kennzahlen, fundstellen, testzahlen):
    """Nahe an einer Kennzahl, aber keine - das ist ihre veraltete Fassung."""
    gueltig = set(kennzahlen.values()) | testzahlen
    beanstandet: list[str] = []
    for datei, zeile, roh in fundstellen:
        wert = _wert(roh)
        if wert in gueltig:
            continue
        for name, kennzahl in sorted(kennzahlen.items()):
            if kennzahl and abs(wert - kennzahl) / kennzahl <= TOLERANZ:
                beanstandet.append(
                    f"{datei}:{zeile}  {roh} sieht aus wie eine veraltete Fassung "
                    f"von {name} = {kennzahl:,}".replace(",", "'"))
                break
    assert not beanstandet, (
        "Veraltete Kennzahlen in den Dokumenten:\n  " + "\n  ".join(beanstandet)
        + "\n\nStimmt die Zahl doch, gehoert ihre Zeile in SCHUTZ - "
          "und dann mit einer Begruendung, warum sie veralten darf."
    )


def test_die_wichtigsten_kennzahlen_stehen_auch_irgendwo(kennzahlen, fundstellen):
    """Eine Zahl loeschen ist der andere Weg, einen Widerspruch aufzuloesen."""
    vorhanden = {_wert(roh) for _, _, roh in fundstellen}
    fehlend = [name for name in ("gold/fact_offense", "silver/crime_offense",
                                 "chicago/taten", "detroit/taten",
                                 "chicago/einwohner", "detroit/einwohner")
               if kennzahlen[name] not in vorhanden]
    assert not fehlend, f"diese Kennzahlen nennt kein Dokument mehr: {fehlend}"
