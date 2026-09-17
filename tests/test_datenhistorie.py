"""Prueft die Zahlen in ``docs/datenhistorie.md`` gegen die gepinnten Laeufe.

Das Dokument entscheidet nichts, es misst - und die Messung ist das einzige
Argument darin. Detroit hat zwei vollstaendige Schnappschuesse desselben
Bestands; alle Zahlen im Dokument stammen aus ihrem Vergleich.

Die Tests tragen ``referenzstand``: Sie haengen an genau diesen beiden
Laeufen. Waeren sie im woechentlichen Datenlauf, wuerden sie mit jedem neuen
Schnappschuss rot, ohne dass etwas kaputt ist.

**Warum das ueberhaupt geprueft wird.** Die Kernaussage des Dokuments ist ein
Verhaeltnis: 88'677 geaenderte Zeilen bei naivem Vergleich gegen 102 echte.
Stimmt eine der beiden Zahlen nicht mehr, faellt die Empfehlung in sich
zusammen - und niemand merkt es, weil beide plausibel aussehen.
"""

from __future__ import annotations

import glob
import re
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOKUMENT = PROJECT_ROOT / "docs" / "datenhistorie.md"
BRONZE = PROJECT_ROOT / "data" / "bronze" / "city=detroit"

pytestmark = pytest.mark.referenzstand


@pytest.fixture(scope="module")
def text() -> str:
    if not DOKUMENT.is_file():
        pytest.skip(f"{DOKUMENT} fehlt")
    return DOKUMENT.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def con():
    """Beide Detroit-Schnappschuesse als ``d1`` und ``d2``."""
    duckdb = pytest.importorskip("duckdb")
    laeufe = sorted(glob.glob(str(BRONZE / "**" / "part-0001.parquet"), recursive=True))
    if len(laeufe) < 2:
        pytest.skip(f"nur {len(laeufe)} Detroit-Schnappschuss/-schuesse vorhanden")
    verbindung = duckdb.connect()
    for i, pfad in enumerate(laeufe[:2], 1):
        verbindung.execute(
            f"CREATE VIEW d{i} AS SELECT attributes.* FROM read_parquet('{pfad}')"
        )
    try:
        yield verbindung
    finally:
        verbindung.close()


def zahl(text: str, muster: str) -> int:
    treffer = re.search(muster, text)
    assert treffer, f"nicht im Dokument gefunden: {muster}"
    return int(treffer.group(1).replace("'", ""))


def test_beide_schnappschuesse_haben_dieselbe_zeilenzahl(text, con):
    """Gleicher Bestand, gleicher Umfang - sonst waere der Vergleich schief."""
    a, b = con.execute(
        "SELECT (SELECT count(*) FROM d1), (SELECT count(*) FROM d2)"
    ).fetchone()
    assert a == b, f"Schnappschuesse unterschiedlich gross: {a} und {b}"
    assert zahl(text, r"in beiden Schnappschüssen \| ([\d']+) \|") == a


def test_nichts_ist_neu_und_nichts_verschwunden(text, con):
    neu, weg = con.execute("""
        SELECT (SELECT count(*) FROM (SELECT incident_entry_id FROM d2
                  EXCEPT SELECT incident_entry_id FROM d1)),
               (SELECT count(*) FROM (SELECT incident_entry_id FROM d1
                  EXCEPT SELECT incident_entry_id FROM d2))
    """).fetchone()
    assert (neu, weg) == (0, 0), f"neu {neu}, verschwunden {weg}"
    assert zahl(text, r"neu hinzugekommen \| (\d+) \|") == neu
    assert zahl(text, r"verschwunden \| (\d+) \|") == weg


def test_die_zahl_der_echten_inhaltsaenderungen_stimmt(text, con):
    """Die eine Zahl, an der die ganze Empfehlung haengt."""
    echt = con.execute("""
        SELECT count(*) FROM d1 JOIN d2 USING (incident_entry_id)
        WHERE trim(d1.offense_description) IS DISTINCT FROM trim(d2.offense_description)
           OR d1.state_offense_code IS DISTINCT FROM d2.state_offense_code
           OR d1.offense_category IS DISTINCT FROM d2.offense_category
           OR d1.case_status IS DISTINCT FROM d2.case_status
    """).fetchone()[0]
    genannt = zahl(text, r"\*\*mit echter Inhaltsänderung\*\* \| \*\*([\d']+)\*\* \|")
    assert genannt == echt, f"genannt {genannt}, gemessen {echt}"


def test_das_verhaeltnis_naiv_zu_echt_stimmt(text, con):
    """88'677 gegen 102 - das ist das Argument, nicht die Verzierung."""
    naiv = con.execute("""
        SELECT count(*) FROM d1 JOIN d2 USING (incident_entry_id)
        WHERE d1.ESRI_OID IS DISTINCT FROM d2.ESRI_OID
    """).fetchone()[0]
    assert zahl(text, r"alle Felder, wie geliefert \| ([\d']+) \|") == naiv

    faktor = re.search(r"Faktor (\d+)", text)
    assert faktor, "der Faktor fehlt im Dokument"
    echt = zahl(text, r"Text getrimmt \| \*\*([\d']+)\*\* \|")
    assert abs(int(faktor.group(1)) - round(naiv / echt)) <= 1, (
        f"Faktor genannt {faktor.group(1)}, gerechnet {naiv / echt:.0f}"
    )


def test_die_leerraumaenderungen_sind_gezaehlt(text, con):
    """150 von 160 - ohne diese Zahl klaenge 'Beschreibung geaendert' nach Inhalt."""
    alle, nur_leerraum = con.execute("""
        SELECT count(*) FILTER (d1.offense_description
                                IS DISTINCT FROM d2.offense_description),
               count(*) FILTER (d1.offense_description
                                IS DISTINCT FROM d2.offense_description
                                AND trim(d1.offense_description)
                                IS NOT DISTINCT FROM trim(d2.offense_description))
        FROM d1 JOIN d2 USING (incident_entry_id)
    """).fetchone()
    assert zahl(text, r"`offense_description` \| (\d+) \|") == alle
    assert zahl(text, r"davon \*\*(\d+) reine Leerzeichen\*\*") == nur_leerraum


def test_die_vierzehn_codeaenderungen_stehen_vollstaendig_drin(text, con):
    """Ihr Muster ist der interessanteste Befund des Dokuments."""
    paare = con.execute("""
        SELECT d1.state_offense_code, d2.state_offense_code
        FROM d1 JOIN d2 USING (incident_entry_id)
        WHERE d1.state_offense_code IS DISTINCT FROM d2.state_offense_code
        GROUP BY 1, 2
    """).fetchall()
    assert zahl(text, r"`state_offense_code` \| (\d+) \|") == con.execute("""
        SELECT count(*) FROM d1 JOIN d2 USING (incident_entry_id)
        WHERE d1.state_offense_code IS DISTINCT FROM d2.state_offense_code
    """).fetchone()[0]
    fehlend = [f"{a} -> {b}" for a, b in paare if f"{a} -> {b}" not in text]
    assert not fehlend, f"diese Codeänderungen fehlen im Dokument: {fehlend}"


def test_der_code_3072_traegt_die_genannten_zeilen(text):
    """Der Code verbindet die Messung mit der Vergleichszahl - deshalb steht er da.

    Ein erster Entwurf nannte hier eine Gold-Zahl und schrieb Silver darueber:
    1'403 zaehlende Taten gegen 1'443 Anklagen. Der Unterschied ist Detroits
    Granularitaet, und genau die verwechselt man an dieser Stelle leicht.
    """
    duckdb = pytest.importorskip("duckdb")
    silber = PROJECT_ROOT / "data" / "silver" / "dataset=crime_offense" / "part-0001.parquet"
    gold = PROJECT_ROOT / "data" / "gold" / "dataset=fact_offense" / "part-0001.parquet"
    if not (silber.is_file() and gold.is_file()):
        pytest.skip("silver oder gold nicht gebaut")
    verbindung = duckdb.connect()
    try:
        anklagen = verbindung.execute(
            f"SELECT count(*) FROM read_parquet('{silber}') "
            f"WHERE city = 'detroit' AND source_offense_code = '3072'"
        ).fetchone()[0]
        taten = verbindung.execute(
            f"SELECT count(*) FROM read_parquet('{gold}') "
            f"WHERE reporting_city = 'detroit' AND source_offense_code = '3072' "
            f"AND mapping_status = 'ambiguous'"
        ).fetchone()[0]
    finally:
        verbindung.close()
    assert zahl(text, r"\*\*([\d']+) Anklagen\*\*") == anklagen
    assert zahl(text, r"\*\*([\d']+) zählende Taten\*\*") == taten


def test_das_dokument_nennt_seine_grenzen(text):
    """Ein Entscheidungspapier ohne Grenzen ist eine Werbung."""
    assert "Was es nicht löst" in text
    assert "beginnt mit der Beobachtung, nicht mit der Tat" in text


def test_jede_offene_entscheidung_hat_eine_empfehlung(text):
    """Fuenf Fragen, fuenf Empfehlungen - sonst ist es keine Vorlage.

    Die fuenfte kam am 17.9.2026 mit den Releases dazu: eine zweite Historie
    neben der, um die es hier geht.
    """
    fragen = re.findall(r"^### 5\.\d ", text, re.M)
    empfehlungen = re.findall(r"\*\*Empfehlung:", text)
    assert len(fragen) == 5, f"{len(fragen)} Entscheidungen gefunden"
    assert len(empfehlungen) >= 5, (
        f"nur {len(empfehlungen)} Empfehlungen zu {len(fragen)} Entscheidungen"
    )


def test_die_release_groesse_stimmt_mit_dem_ausblick_ueberein(text):
    """Dieselbe Zahl an zwei Stellen - sie darf nur einmal veralten."""
    ausblick = (PROJECT_ROOT / "docs" / "ausblick.md").read_text(encoding="utf-8")
    assert "42,3 MB" in text
    assert "26,5 MB" in text
    assert "Releases werden aufgehoben" in ausblick or "aufgehoben" in ausblick
