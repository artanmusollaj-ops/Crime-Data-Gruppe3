"""Prueft die Zahlen in ``docs/zaehlperspektiven.md`` gegen die gebauten Schichten.

Das Dokument hat genau einen Zweck: jemanden davon abzuhalten, Zahlen zu
addieren, die sich nicht addieren lassen. Sein Argument sind vier
Gegenueberstellungen - vier Perspektiven, Familien gegen Gesamtzahl, Tage gegen
Monate, volle Woche gegen Teilwoche. Stimmt eine davon nicht mehr, ist das
Dokument nicht ungenau, sondern falsch: Es warnt dann vor einer Abweichung, die
es nicht mehr gibt, oder verschweigt eine, die groesser geworden ist.

Die Tests tragen ``referenzstand``. Sie haengen an genau diesem Datenstand;
im woechentlichen Datenlauf wuerden sie mit jedem neuen Schnappschuss rot, ohne
dass etwas kaputt waere.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOKUMENT = PROJECT_ROOT / "docs" / "zaehlperspektiven.md"
SILBER = PROJECT_ROOT / "data" / "silver" / "dataset=crime_offense" / "part-0001.parquet"
GOLD = PROJECT_ROOT / "data" / "gold" / "dataset=fact_offense" / "part-0001.parquet"

pytestmark = pytest.mark.referenzstand


@pytest.fixture(scope="module")
def text() -> str:
    if not DOKUMENT.is_file():
        pytest.skip(f"{DOKUMENT} fehlt")
    return DOKUMENT.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def con():
    """``s`` ist Silver, ``f`` sind die Gold-Fakten."""
    duckdb = pytest.importorskip("duckdb")
    if not (SILBER.is_file() and GOLD.is_file()):
        pytest.skip("silver oder gold nicht gebaut")
    verbindung = duckdb.connect()
    verbindung.execute(f"CREATE VIEW s AS SELECT * FROM read_parquet('{SILBER}')")
    verbindung.execute(f"CREATE VIEW f AS SELECT * FROM read_parquet('{GOLD}')")
    try:
        yield verbindung
    finally:
        verbindung.close()


def zahl(text: str, muster: str) -> int:
    treffer = re.search(muster, text)
    assert treffer, f"nicht im Dokument gefunden: {muster}"
    return int(treffer.group(1).replace("'", ""))


def zeile(text: str, praefix: str) -> list[int]:
    """Die Zahlen der ersten Tabellenzeile, die mit ``praefix`` beginnt.

    Gebunden an den Zeilenanfang, nicht an ein Vorkommen irgendwo: Sonst
    trifft ``| Chicago |`` die Kopfzeile der ersten Tabelle, und die traegt
    keine Zahlen.
    """
    for z in text.splitlines():
        if z.startswith(praefix):
            return [int(t.replace("'", "")) for t in re.findall(r"\b\d[\d']*\b", z)]
    raise AssertionError(f"keine Tabellenzeile, die mit {praefix!r} beginnt")


# --------------------------------------------------------------------------
# 1 - Die vier Perspektiven
# --------------------------------------------------------------------------


def test_die_vier_perspektiven_stimmen(text, con):
    """Die Tabelle, von der alles Uebrige abhaengt."""
    erwartet = {
        "| **Anklagen**": "TRUE",
        "| **Taten**": "counts",
        "| **Fälle**": "counts_case",
    }
    for beschriftung, wo in erwartet.items():
        chi, det = con.execute(
            f"SELECT count(*) FILTER (city = 'chicago'), "
            f"count(*) FILTER (city = 'detroit') FROM s WHERE {wo}"
        ).fetchone()
        genannt = zeile(text, beschriftung)
        assert genannt[:2] == [chi, det], (
            f"{beschriftung}: genannt {genannt[:2]}, gemessen [{chi}, {det}]"
        )


def test_die_vorfaelle_decken_sich_mit_den_faellen(text, con):
    """Keine Beobachtung, sondern eine Zusage - reconcile bricht sonst ab."""
    chi, det = con.execute(
        "SELECT count(DISTINCT event_id) FILTER (city = 'chicago' AND counts), "
        "count(DISTINCT event_id) FILTER (city = 'detroit' AND counts) FROM s"
    ).fetchone()
    assert zeile(text, "| **Vorfälle**")[:2] == [chi, det]
    assert zeile(text, "| **Fälle**")[:2] == [chi, det], (
        "Faelle und Vorfaelle muessen uebereinstimmen, sonst ist die Aussage "
        "des Abschnitts hinfaellig"
    )


def test_die_gold_zeilenzahl_ist_die_tatebene(text, con):
    taten = con.execute("SELECT count(*) FROM f").fetchone()[0]
    assert zahl(text, r"\*\*([\d']+) Taten\*\*") == taten


# --------------------------------------------------------------------------
# 2 - Was sich nicht addieren laesst
# --------------------------------------------------------------------------


def test_die_mehrfamilien_vorfaelle_stimmen(text, con):
    """Der Kern des Dokuments: 5,2 % der Detroiter Vorfaelle."""
    gemessen = {
        stadt: (vorfaelle, mehrere, summe)
        for stadt, vorfaelle, mehrere, summe in con.execute("""
            SELECT f.reporting_city,
                   count(DISTINCT f.event_id),
                   count(DISTINCT f.event_id) FILTER (f.event_id IN (
                       SELECT event_id FROM f GROUP BY event_id
                       HAVING count(DISTINCT nibrs_family) > 1)),
                   (SELECT sum(n) FROM (
                       SELECT count(DISTINCT event_id) AS n FROM f AS g
                       WHERE g.reporting_city = f.reporting_city
                       GROUP BY g.nibrs_family))
            FROM f GROUP BY 1
        """).fetchall()
    }
    for stadt, beschriftung in (("chicago", "| Chicago |"), ("detroit", "| Detroit |")):
        vorfaelle, mehrere, summe = gemessen[stadt]
        genannt = zeile(text, beschriftung)
        assert genannt[0] == vorfaelle, f"{stadt}: Vorfaelle {genannt[0]} statt {vorfaelle}"
        assert mehrere in genannt, f"{stadt}: {mehrere} Mehrfamilien-Vorfaelle fehlen"
        assert summe in genannt, f"{stadt}: Summe je Familie {summe} fehlt"

    zuviel = gemessen["detroit"][2] - gemessen["detroit"][0]
    assert zahl(text, r"\*\*([\d']+) zu viel") == zuviel


def test_tage_summieren_sich_nicht_zu_monaten(text, con):
    """Vier und zwei Vorfaelle - klein genug, um unbemerkt zu bleiben."""
    for stadt in ("chicago", "detroit"):
        tage, monate, jahr = con.execute(f"""
            SELECT (SELECT sum(n) FROM (SELECT count(DISTINCT event_id) AS n
                        FROM f WHERE reporting_city = '{stadt}' GROUP BY date)),
                   (SELECT sum(n) FROM (SELECT count(DISTINCT event_id) AS n
                        FROM f WHERE reporting_city = '{stadt}'
                        GROUP BY date_trunc('month', date))),
                   (SELECT count(DISTINCT event_id) FROM f
                        WHERE reporting_city = '{stadt}')
        """).fetchone()
        assert monate == jahr, (
            f"{stadt}: Monate summieren sich nicht mehr zum Jahr - dann stimmt "
            "die Aussage des Abschnitts nicht mehr"
        )
        beschriftung = f"| {stadt.capitalize()} | {tage:,}".replace(",", "'")
        assert beschriftung in text, (
            f"{stadt}: die Zeile mit {tage} Tagen summiert fehlt im Dokument"
        )


def test_die_teilwoche_am_jahresende_stimmt(text, con):
    """Ohne diese Zahl liest sich der Jahresausklang wie ein Einbruch."""
    erste, letzte = con.execute("""
        SELECT (SELECT count(*) FROM f
                WHERE date_trunc('week', date) = (SELECT min(date_trunc('week', date)) FROM f)),
               (SELECT count(*) FROM f
                WHERE date_trunc('week', date) = (SELECT max(date_trunc('week', date)) FROM f))
    """).fetchone()
    assert zahl(text, r"vollständig: ([\d']+) Taten") == erste
    assert zahl(text, r"\*\*zwei Tage\*\*: ([\d']+) Taten") == letzte


# --------------------------------------------------------------------------
# 3 - Was die Pruefungen nicht beweisen
# --------------------------------------------------------------------------


def test_die_zuordnungsquoten_stimmen(text, con):
    """Sie stehen da, um zu zeigen, was sie **nicht** aussagen."""
    for stadt, spalte in (("chicago", "| Chicago |"), ("detroit", "| Detroit |")):
        gemessen = dict(con.execute(
            f"SELECT mapping_status, count(*) FROM f "
            f"WHERE reporting_city = '{stadt}' GROUP BY 1"
        ).fetchall())
        # Die Statuszeile steht im dritten Tabellenblock; gesucht wird die
        # Zeile, die alle vier Werte traegt.
        kandidaten = [z for z in text.splitlines()
                      if z.startswith(spalte)
                      and len(re.findall(r"\b\d[\d']*\b", z)) == 4]
        assert kandidaten, f"{stadt}: keine Statuszeile mit vier Zahlen gefunden"
        genannt = [int(t.replace("'", ""))
                   for t in re.findall(r"\b\d[\d']*\b", kandidaten[-1])]
        erwartet = [gemessen.get(s, 0) for s in
                    ("exact", "ambiguous", "fallback_90Z", "unmapped")]
        assert genannt == erwartet, (
            f"{stadt}: genannt {genannt}, gemessen {erwartet}"
        )


def test_die_blinde_stunde_ist_richtig_beziffert(text, con):
    """Die Grenze der Zeitpruefung - sie gehoert genannt, also auch geprueft."""
    zusammen, gesamt = con.execute("""
        SELECT count(*) FILTER (occurred_at_local IS NOT DISTINCT FROM
                   CAST(timezone('America/Chicago',
                        occurred_at_utc AT TIME ZONE 'UTC') AS TIMESTAMP)),
               count(*)
        FROM s WHERE city = 'detroit'
    """).fetchone()
    assert zahl(text, r"(\d+) der ([\d']+) Detroiter Zeilen") == zusammen
    assert zahl(text, r"\d+ der ([\d']+) Detroiter Zeilen") == gesamt
    assert zahl(text, r"trotzdem ([\d']+)-fach auf") == gesamt - zusammen


def test_die_mehrdeutigen_ortszeiten_stimmen(text, con):
    mehrdeutig = con.execute(
        "SELECT count(*) FROM s WHERE local_time_ambiguous"
    ).fetchone()[0]
    assert zahl(text, r"Die (\d+) Zeilen in der doppelten Stunde") == mehrdeutig


def test_die_event_id_falle_nennt_den_richtigen_ausdruck(text, con):
    """Der Hinweis nuetzt nur, wenn er den Ausdruck nennt, den der Bau benutzt."""
    assert "count(DISTINCT coalesce(event_id, offense_id))" in text, (
        "das Dokument sagt nicht, wie man je Vorfall richtig zaehlt"
    )
    ohne = con.execute(
        "SELECT count(*) FROM s WHERE event_id IS NULL OR trim(event_id) = ''"
    ).fetchone()[0]
    assert ohne == 0, (
        f"{ohne} Zeilen ohne event_id - das Dokument sagt 'keine einzige Zeile'"
    )
    assert "keine einzige Zeile" in text


def test_die_mehrdeutigen_beschreibungen_stimmen(text, con):
    """Der Punkt, der vorher gar keine Zahl hatte.

    Bis zum 17.9.2026 stand hier nur "Gleiche Beschreibung heisst nicht
    gleiches Delikt. Textvarianten sind Kandidaten fuer ein Review, keine
    Regel zum Zusammenlegen." Die Ueberschrift sagte das eine, der Satz das
    Gegenteil, und belegt war keines von beidem. Gemessen ist der Befund
    deutlich staerker, als der Satz vermuten liess.
    """
    # Chicago hatte den Befund bis zum 19.9.2026: Silver fuehrte nur die zweite
    # IUCR-Haelfte, und 23,3 % der Zeilen trugen damit eine fuer sich genommen
    # mehrdeutige Beschreibung. Seit Vertrag 3 stehen beide Haelften da, und der
    # Anteil ist null. Geprueft wird deshalb die Null - nicht mehr die alte
    # Quote, die im Dokument nur noch als Vorgeschichte steht.
    chi_zeilen = con.execute("""
        WITH je AS (SELECT source_offense_description AS t
                    FROM s WHERE city = 'chicago'
                    GROUP BY 1 HAVING count(DISTINCT nibrs_code) > 1)
        SELECT count(*) FROM s WHERE city = 'chicago'
          AND source_offense_description IN (SELECT t FROM je)
    """).fetchone()[0]
    assert chi_zeilen == 0, (
        f"{chi_zeilen} Chicagoer Zeilen tragen wieder eine mehrdeutige "
        "Beschreibung - dann stimmt der Silver-Vertrag 3 nicht mehr"
    )
    assert "ist damit **null**" in " ".join(text.split()), (
        "das Dokument nennt die Null nicht mehr"
    )

    det = con.execute("""
        SELECT count(*) FROM (SELECT source_offense_description FROM s
            WHERE city = 'detroit' AND source_offense_description IS NOT NULL
            GROUP BY 1 HAVING count(DISTINCT nibrs_code) > 1)
    """).fetchone()[0]
    assert zahl(text, r"Dort\nsind es (\d+)\nBeschreibungen") == det


def test_der_groesste_detroiter_fall_stimmt(text, con):
    """Eine Beschreibung ueber 26 NIBRS-Codes - das ist das Argument."""
    codes, zeilen = con.execute("""
        SELECT count(DISTINCT nibrs_code), count(*) FROM s
        WHERE city = 'detroit'
          AND source_offense_description = 'ASSAULT AND BATTERY/SIMPLE ASSAULT'
    """).fetchone()
    assert zahl(text, r"\*\*(\d+) verschiedene") == codes
    assert zahl(text, r"über ([\d']+) Zeilen ab") == zeilen


def test_die_umkehrung_stimmt_auch(text, con):
    """Verschiedene Texte, gleicher Code - die andere Haelfte des Befunds."""
    for stadt, muster in (("chicago", r"\*\*(\d+) der (\d+)\*\* Chicagoer"),
                          ("detroit", r"\*\*(\d+) der (\d+)\*\* Detroiter")):
        mehrfach, codes = con.execute(f"""
            WITH je AS (SELECT nibrs_code, count(DISTINCT source_offense_description) AS n
                        FROM s WHERE city = '{stadt}' AND nibrs_code IS NOT NULL GROUP BY 1)
            SELECT count(*) FILTER (n > 1), count(*) FROM je
        """).fetchone()
        treffer = re.search(muster, " ".join(text.split()))
        assert treffer, f"{stadt}: die Umkehrung fehlt im Dokument"
        assert (int(treffer.group(1)), int(treffer.group(2))) == (mehrfach, codes), (
            f"{stadt}: genannt {treffer.groups()}, gemessen ({mehrfach}, {codes})"
        )


def test_die_ambiguous_zuordnungen_stimmen(text, con):
    """20 im Crosswalk, 17 in den Daten - der Unterschied war vorher unterschlagen."""
    im_crosswalk = sum(
        con.execute(
            f"SELECT count(*) FROM read_csv('{PROJECT_ROOT / 'config' / datei}', "
            f"header = true, all_varchar = true) "
            f"WHERE mapped = 'true' AND match IN ({herkuenfte})"
        ).fetchone()[0]
        for datei, herkuenfte in (("iucr_nibrs_mapping.csv", "'nibrs_ermessen'"),
                                  ("micr_nibrs_mapping.csv", "'detroit_charge_file_class'"))
    )
    codes, zeilen = con.execute(
        "SELECT count(DISTINCT source_offense_code), count(*) FROM s "
        "WHERE mapping_status = 'ambiguous'"
    ).fetchone()
    ohne_umbrueche = " ".join(text.split())
    assert f"**{im_crosswalk} in den Crosswalks, davon {codes} mit Zeilen" in ohne_umbrueche, (
        f"gemessen {im_crosswalk} im Crosswalk und {codes} in den Daten"
    )
    assert f"({zeilen:,} Zeilen)".replace(",", "'") in ohne_umbrueche, (
        f"die Zeilenzahl der ambiguous-Zuordnungen ist {zeilen}"
    )
    assert im_crosswalk - codes == 3, (
        f"{im_crosswalk - codes} Zuordnungen ohne Zeilen im Jahrgang - "
        "das Dokument sagt drei"
    )
    assert "übrigen drei" in ohne_umbrueche


def test_die_bronze_only_felder_fehlen_wirklich(text, con):
    """Der Absatz nennt Spalten - Spaltennamen veralten am schnellsten.

    Ein erster Entwurf sagte hier ausserdem, das Manifest nenne den
    Bronze-Lauf, aus dem eine Zeile stammt. Das tut es nicht: Es nennt alle
    Laeufe, aus denen die Tabelle entstand. Fuer Detroit gibt es den einen
    Lauf gar nicht, weil beide Schnappschuesse alle Zeilen enthalten.
    """
    vorhanden = {r[0] for r in con.execute("DESCRIBE SELECT * FROM s").fetchall()}
    assert len(vorhanden) == 28, f"Silver hat {len(vorhanden)} Spalten, nicht 28"
    assert re.search(r"Silver führt 28\s+Spalten", text), (
        "die genannte Spaltenzahl stimmt nicht"
    )

    for spalte in ("charge_description", "arrest_charge", "offense_category",
                   "primary_type", "fbi_code", "updated_on", "updated_at"):
        assert spalte not in vorhanden, (
            f"{spalte} steht inzwischen in Silver - der Absatz behauptet das "
            "Gegenteil"
        )
        assert f"`{spalte}`" in text, f"{spalte} wird im Absatz nicht genannt"

    assert "run" not in vorhanden and "run_id" not in vorhanden, (
        "Silver fuehrt jetzt eine Zeilen-Herkunft - der Absatz sagt, es tue es nicht"
    )


def test_der_manifesteintrag_nennt_die_zahl_der_laeufe(text):
    """Acht und acht - beides steht im Manifest der gebauten Tabelle.

    Bis zum 20.9.2026 standen hier drei und zwei, bis zum 3.10. sieben und
    acht; der zweite Chicago-Vollabzug machte daraus acht und acht. Beide
    Staedte laden Deltas, die Zahl waechst mit jedem Lauf, und das Dokument
    muss mit.

    Die erwartete Paarung steht hier von Hand und nicht im Dokument gelesen -
    das ist die schwache Stelle dieses Waechters: Er faengt eine Abweichung,
    nennt aber nicht die Stelle im Text, die nachzuziehen ist (es ist der
    Abschnitt zu den Delta-Laeufen).
    """
    manifest = PROJECT_ROOT / "data" / "silver" / "dataset=crime_offense" / "manifest.json"
    if not manifest.is_file():
        pytest.skip("silver nicht gebaut")
    herkunft = json.loads(manifest.read_text(encoding="utf-8"))["derived_from"]
    chi = len(herkunft["chicago_bronze_runs"])
    det = len(herkunft["detroit_bronze_runs"])
    assert (chi, det) == (8, 8), (
        f"das Dokument nennt acht Chicago- und acht Detroit-Laeufe, "
        f"das Manifest hat {chi} und {det}"
    )


def test_alle_detroit_zeilen_stehen_in_beiden_schnappschuessen(text, con):
    """Die Zahl, die den Rueckgriff auf einen einzelnen Lauf unmoeglich macht."""
    zeilen = con.execute("SELECT count(*) FROM s WHERE city = 'detroit'").fetchone()[0]
    assert zahl(text, r"\*\*alle ([\d']+) Zeilen\*\*") == zeilen


def test_die_angekuendigten_sieben_punkte_sind_sieben(text):
    """Der Uebergang nennt eine Zahl - dann muss sie auch stimmen.

    Ein frueherer Uebergang lautete nur "Auch die 28 beweisen weniger, als
    ihre Zahl vermuten laesst". Direkt hinter einem Absatz, der 31 auf 28
    herunterrechnet, las sich das wie die Fortsetzung dieser Rechnung statt
    wie die Aussage des Abschnitts. Seither nennt der Uebergang die Zahl der
    Punkte - und diese Zahl kann veralten.
    """
    anfang = text.index("## 3 · Was die Prüfungen nicht beweisen")
    ende = text.index("## Wo das weiterführt")
    abschnitt = text[anfang:ende]
    # Ein Punkt ist ein fetter Vorspann am Zeilenanfang, der einen ganzen
    # Satz bildet - erkennbar am Punkt vor den Sternen. Fette Hervorhebungen
    # im Fliesstext ("**42 Kontrollen**") tun das nicht.
    punkte = [p for p in re.findall(r"^\*\*[^*]+\*\*", abschnitt, re.M)
              if p.endswith(".**")]
    zahlwort = {"drei": 3, "vier": 4, "fünf": 5, "sechs": 6, "sieben": 7,
                "acht": 8, "neun": 9, "zehn": 10}
    treffer = re.search(r"folgenden (\w+) Punkte", text)
    assert treffer, "der Übergang kündigt keine Zahl von Punkten an"
    genannt = zahlwort[treffer.group(1)]
    assert genannt == len(punkte), (
        f"der Übergang kündigt {genannt} Punkte an, der Abschnitt hat "
        f"{len(punkte)}: {punkte}"
    )


def test_der_uebergang_sagt_was_eine_gruene_pruefung_bedeutet(text):
    """Die Kernaussage des Abschnitts, nicht nur seine sieben Beispiele.

    Ohne sie ist der Abschnitt eine Liste von Eigenheiten; mit ihr ist er ein
    Argument.
    """
    ohne_umbrueche = " ".join(text.split())
    assert "zeigt, dass der Bau getan hat, was ihm aufgetragen wurde" in ohne_umbrueche
    assert "nicht, dass das Ergebnis die Wirklichkeit richtig beschreibt" in ohne_umbrueche


def test_das_dokument_nennt_seine_herkunft(text):
    """Die Gliederung ist Artans Arbeit - das gehoert dahin, wo sie steht."""
    assert "sql_check_scripts" in text
    assert "Referenzstand neu gemessen" in text


def test_jeder_abschnitt_sagt_was_er_fuer_eine_auswertung_heisst(text):
    """Ein Katalog von Eigenheiten ohne Konsequenz ist Trivia."""
    assert "Was das für eine Auswertung heisst" in text
    assert "nie addiert" in text
