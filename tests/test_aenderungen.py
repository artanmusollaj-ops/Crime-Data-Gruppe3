"""Prueft, dass ``docs/intern/AENDERUNGEN.md`` nicht still veraltet.

Die Datei haelt fest, was sich an den Zahlen geaendert hat und warum - sie ist
die Uebergabe von Silver und Gold an Dokumentation und Praesentation. Genau
solche Dateien veralten unbemerkt: Niemand merkt, dass die Kopfzahlen nicht
mehr stimmen, bis jemand sie in eine Folie uebernimmt.

Geprueft werden deshalb die Zahlen im Abschnitt "Der Stand in Zahlen" gegen das,
was tatsaechlich da ist. Der Fliesstext bleibt ungeprueft - er beschreibt
Vergangenes und soll sich nicht aendern.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AENDERUNGEN = PROJECT_ROOT / "docs" / "intern" / "AENDERUNGEN.md"
SILVER = PROJECT_ROOT / "data" / "silver" / "dataset=crime_offense" / "part-0001.parquet"
GOLD = PROJECT_ROOT / "data" / "gold" / "dataset=fact_offense" / "part-0001.parquet"


@pytest.fixture(scope="module")
def text() -> str:
    return AENDERUNGEN.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def stand(text) -> str:
    """Nur der Kopfabschnitt mit den aktuellen Zahlen."""
    anfang = text.index("## Der Stand in Zahlen")
    ende = text.index("## ", anfang + 10)
    return text[anfang:ende]


def zahl(stand: str, muster: str) -> int:
    """Eine Zahl aus dem Kopfabschnitt, mit Apostroph als Tausendertrenner."""
    treffer = re.search(muster, stand)
    assert treffer, f"nicht gefunden im Kopfabschnitt: {muster}"
    return int(treffer.group(1).replace("'", "").replace(",", ""))


def test_datei_existiert():
    assert AENDERUNGEN.exists(), (
        f"{AENDERUNGEN} fehlt - sie ist die Uebergabe an die Dokumentation"
    )


def test_der_kopf_nennt_die_testzahl(stand):
    """Die Zahl, die in jeder Abgabe zitiert wird.

    Gezaehlt wird nicht gegen eine Konstante, sondern gegen das, was pytest
    gerade sammelt - eine fest verdrahtete Zahl waere selbst wieder etwas, das
    veraltet.

    Gesammelt wird in einem eigenen Prozess mit ``--collect-only``. Die Tests
    laufen dabei nicht; ein Zaehler, der nur Funktionsnamen liest, uebersaehe
    parametrisierte Tests und ``TestCase``-Methoden - genau 73 Stueck, wie ein
    erster Versuch zeigte.
    """
    genannt = zahl(stand, r"\| Tests \| \*\*([0-9']+)\*\* \|")
    # -o addopts= schaltet die Vorgaben aus pyproject.toml ab. Sie enthalten
    # -q, und damit druckt pytest die Summenzeile nicht, sondern nur die
    # Zahlen je Datei - die Regex unten faende nichts und der Test wuerde sich
    # stillschweigend ueberspringen.
    fertig = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only",
         "-o", "addopts=", "-p", "no:cacheprovider"],
        capture_output=True, text=True, cwd=PROJECT_ROOT,
    )
    treffer = re.search(r"([0-9]+) tests? collected", fertig.stdout)
    if treffer is None:
        pytest.skip(f"Sammellauf lieferte keine Zahl: {fertig.stdout[-200:]}")
    gesammelt = int(treffer.group(1))
    assert genannt == gesammelt, (
        f"AENDERUNGEN.md nennt {genannt} Tests, gesammelt werden {gesammelt}. "
        "Beim naechsten Eintrag die Kopfzahl mitziehen."
    )


@pytest.mark.referenzstand
def test_der_kopf_nennt_die_zeilenzahlen(stand):
    """Silver und Gold - die beiden Zahlen, die die Granularität unterscheiden."""
    duckdb = pytest.importorskip("duckdb")
    if not (SILVER.exists() and GOLD.exists()):
        pytest.skip("Silver oder Gold nicht gebaut")
    con = duckdb.connect()
    try:
        for pfad, muster, name in (
            (SILVER, r"`silver/crime_offense` \| ([0-9']+) Zeilen", "silver"),
            (GOLD, r"`gold/fact_offense` \| \*\*([0-9']+)\*\* Zeilen", "gold"),
        ):
            genannt = zahl(stand, muster)
            echt = con.execute(f"SELECT count(*) FROM read_parquet('{pfad}')").fetchone()[0]
            assert genannt == echt, f"{name}: genannt {genannt:,}, tatsaechlich {echt:,}"
    finally:
        con.close()


@pytest.mark.referenzstand
def test_der_kopf_nennt_die_raten(stand):
    """Die Rate je 1'000 Einwohner - was am ehesten auf eine Folie kommt."""
    duckdb = pytest.importorskip("duckdb")
    tract = PROJECT_ROOT / "data" / "gold" / "dataset=dim_tract" / "part-0001.parquet"
    if not (GOLD.exists() and tract.exists()):
        pytest.skip("Gold nicht gebaut")
    con = duckdb.connect()
    try:
        echt = dict(con.execute(f"""
            WITH e AS (
                SELECT city, sum(population) AS n
                FROM read_parquet('{tract}') WHERE city IS NOT NULL GROUP BY 1
            )
            SELECT t.city, round(count(*) * 1000.0 / any_value(e.n), 1)
            FROM read_parquet('{GOLD}') f
            JOIN read_parquet('{tract}') t ON t.geoid = f.tract_geoid
            JOIN e ON e.city = t.city
            WHERE t.city IS NOT NULL GROUP BY 1
        """).fetchall())
    finally:
        con.close()
    for stadt in ("Chicago", "Detroit"):
        treffer = re.search(
            rf"\| {stadt} \|.*?\*\*([0-9]+,[0-9])\*\* je 1'000", stand
        )
        assert treffer, f"Rate fuer {stadt} nicht im Kopfabschnitt gefunden"
        genannt = float(treffer.group(1).replace(",", "."))
        assert genannt == pytest.approx(echt[stadt.lower()], abs=0.05), (
            f"{stadt}: genannt {genannt}, tatsaechlich {echt[stadt.lower()]}"
        )


def test_jeder_eintrag_nennt_seine_herkunft(text):
    """Ohne den Verweis laesst sich die Begruendung nicht nachlesen.

    Bis zum 20.9.2026 war das immer eine PR-Nummer. Seit PR #121 gemergt und
    sein Branch geloescht ist, entsteht Arbeit auch direkt auf ``main`` - dann
    ist der Commit der Verweis, und der Eintrag sagt ``(direkt auf main)``.
    Verlangt bleibt, dass jeder Eintrag *irgendeine* nachschlagbare Herkunft
    nennt; was nicht geht, ist gar keine.
    """
    eintraege = re.findall(r"^## ([0-9]{2}\.[0-9]{2}\.[0-9]{4}.*)$", text, re.M)
    assert len(eintraege) >= 8, f"nur {len(eintraege)} Eintraege gefunden"
    ohne = [e for e in eintraege
            if not re.search(r"\(#[0-9]+\)", e) and "(direkt auf main)" not in e]
    assert not ohne, f"Eintraege ohne PR-Nummer oder Herkunftsvermerk: {ohne}"


def test_die_eintraege_stehen_neueste_zuerst(text):
    """Sonst liest niemand den obersten und glaubt, er sei aktuell."""
    daten = re.findall(r"^## ([0-9]{2})\.([0-9]{2})\.([0-9]{4})", text, re.M)
    schluessel = [(j, m, t) for t, m, j in daten]
    assert schluessel == sorted(schluessel, reverse=True), (
        f"Reihenfolge stimmt nicht: {daten}"
    )


def test_keine_pull_request_nummer_faellt_durch(text):
    """Jede Nummer ab #24 ist entweder ein Eintrag oder bewusst ausgelassen.

    Das ist die Pruefung, die vier Monate zu spaet kam: #25, #28, #31 und #37
    waren gemergt und hatten keinen Eintrag. Aufgefallen ist es nur, weil
    jemand gefragt hat, ob die Datei nachgefuehrt sei.

    Ohne Netz geht das so: Die Nummern muessen **luckenlos** sein. Faellt eine
    heraus, ist sie entweder vergessen oder gehoert unter "Bewusst ohne
    Eintrag" - beides will man wissen. Ein neuer Pull Request laesst den Test
    fallen, bis er eingeordnet ist; genau das ist der Zweck.
    """
    eintraege = {int(n) for n in re.findall(r"^## [0-9.]+ · .*?\(#([0-9]+)\)$",
                                            text, re.M)}
    assert eintraege, "keine Eintraege mit PR-Nummer gefunden"

    anfang = text.index("## Bewusst ohne Eintrag")
    ausgelassen = {int(n) for n in re.findall(r"^\| #([0-9]+) \|", text[anfang:], re.M)}
    assert ausgelassen, "der Abschnitt 'Bewusst ohne Eintrag' ist leer"

    bekannt = eintraege | ausgelassen
    fehlend = sorted(set(range(min(bekannt), max(bekannt) + 1)) - bekannt)
    assert not fehlend, (
        f"Diese Pull Requests sind weder Eintrag noch ausgelassen: {fehlend}. "
        "Entweder einen Eintrag schreiben oder unter 'Bewusst ohne Eintrag' "
        "mit Begruendung eintragen."
    )


def test_die_eintraege_und_die_ausgelassenen_ueberschneiden_sich_nicht(text):
    """Sonst stuende dieselbe Nummer als erledigt und als ausgelassen da."""
    eintraege = {int(n) for n in re.findall(r"^## [0-9.]+ · .*?\(#([0-9]+)\)$",
                                            text, re.M)}
    anfang = text.index("## Bewusst ohne Eintrag")
    ausgelassen = {int(n) for n in re.findall(r"^\| #([0-9]+) \|", text[anfang:], re.M)}
    doppelt = sorted(eintraege & ausgelassen)
    assert not doppelt, f"gleichzeitig Eintrag und ausgelassen: {doppelt}"


@pytest.mark.referenzstand
def test_der_kopf_nennt_das_fallebene(stand):
    """Die zweite Zaehlweise, seit #66 - je Fall eine Zeile, beide Staedte gleich."""
    duckdb = pytest.importorskip("duckdb")
    if not GOLD.exists():
        pytest.skip("Gold nicht gebaut")
    con = duckdb.connect()
    try:
        echt = dict(con.execute(
            f"SELECT reporting_city, count(*) FILTER (counts_case) "
            f"FROM read_parquet('{GOLD}') GROUP BY 1"
        ).fetchall())
    finally:
        con.close()
    for stadt in ("Chicago", "Detroit"):
        genannt = zahl(stand, rf"\| Fallebene.*?{stadt} ([0-9']+)")
        assert genannt == echt[stadt.lower()], (
            f"Fallebene {stadt}: genannt {genannt:,}, tatsaechlich {echt[stadt.lower()]:,}"
        )
