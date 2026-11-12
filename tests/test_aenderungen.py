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
from gold_pipeline import RATENJAHR, raten_je_stadt


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


def gemessene_raten():
    """Delikte, Faelle, Einwohner und beide Raten je Stadt - fuer ein Jahr.

    Aus ``gold_pipeline.raten_je_stadt``. Der Jahresfilter steckt darin, und
    er muss es: Seit dem Mehrjahresbau vom 4.10.2026 traegt ``fact_offense``
    sechs Jahrgaenge, und derselbe Quotient ergibt dann 500,7 je 1'000 fuer
    Chicago - sechs Jahre Zaehler auf einem Jahr Nenner.
    """
    duckdb = pytest.importorskip("duckdb")
    tract = PROJECT_ROOT / "data" / "gold" / "dataset=dim_tract" / "part-0001.parquet"
    acs = PROJECT_ROOT / "data" / "gold" / "dataset=dim_tract_acs" / "part-0001.parquet"
    if not (GOLD.exists() and tract.exists() and acs.exists()):
        pytest.skip("Gold nicht gebaut")
    con = duckdb.connect()
    try:
        return {
            z[0]: (z[1], z[2], z[3], z[4], z[5])
            for z in con.execute(raten_je_stadt(
                f"read_parquet('{GOLD}')", f"read_parquet('{tract}')",
                f"read_parquet('{acs}')")).fetchall()
        }
    finally:
        con.close()


@pytest.mark.referenzstand
def test_der_kopf_nennt_die_raten(stand):
    """Die Rate je 1'000 Einwohner - was am ehesten auf eine Folie kommt.

    Geprueft wird dazu, dass die Kopftabelle ihren **Jahrgang** nennt: Eine
    Rate ohne Zeitraum ist keine, und der Driftbericht liest genau diese
    Zeilen (``orchestration.drift``). Stuende dort eine kumulierte Zahl,
    waere der woechentliche Datenlauf dauerhaft rot.
    """
    echt = gemessene_raten()
    assert str(RATENJAHR) in stand, (
        f"der Kopfabschnitt nennt den Jahrgang {RATENJAHR} nicht - die Raten "
        "darin gelten fuer ein Jahr, nicht fuer den ganzen Bestand"
    )
    # Seit dem 12.11.2026 (E-2) traegt die Stadtzeile die Fallrate; die
    # Tatrate steht in der Zeile "Tatebene" darunter.
    for stadt in ("Chicago", "Detroit"):
        treffer = re.search(
            rf"\| {stadt} \|.*?\*\*([0-9]+,[0-9])\*\* je 1'000", stand
        )
        assert treffer, f"Rate fuer {stadt} nicht im Kopfabschnitt gefunden"
        genannt = float(treffer.group(1).replace(",", "."))
        rate = echt[stadt.lower()][4]
        assert genannt == pytest.approx(rate, abs=0.05), (
            f"{stadt}: genannt {genannt}, tatsaechlich {rate} (Fallebene)"
        )
        tat = re.search(
            rf"\| Tatebene.*?je 1'000:.*?{stadt} \*\*([0-9]+,[0-9])\*\*", stand
        )
        assert tat, f"Tatrate fuer {stadt} nicht im Kopfabschnitt gefunden"
        assert float(tat.group(1).replace(",", ".")) == pytest.approx(
            echt[stadt.lower()][3], abs=0.05), f"{stadt}: Tatrate"



#: Die Herkunft einer Eintragsueberschrift in Klammern. Seit dem 11.10.2026
#: darf sie **mehrere** Nummern nennen: An jenem Tag ging eine
#: zusammenhaengende Arbeit in zwei Pull Requests hinaus (#144 brachte den
#: Betriebsstand, #145 die Waechter ueber den Serverlauf), und der Eintrag
#: wurde erweitert statt gespalten - zwei Eintraege fuer einen Vorgang waeren
#: schlechter zu lesen gewesen. Eine erfundene Nummer bleibt schlimmer als
#: keine, deshalb muss jede genannte auch nachschlagbar sein.
HERKUNFT = r"\(#[0-9]+(?:,\s*#[0-9]+)*\)"

#: Eine Eintragsueberschrift mit ihren Nummern.
UEBERSCHRIFT = re.compile(r"^## [0-9.]+ · .*?\((#[0-9]+(?:,\s*#[0-9]+)*)\)$",
                          re.M)


def pr_nummern(text: str) -> set[int]:
    """Jede Pull-Request-Nummer, die eine Eintragsueberschrift nennt."""
    return {int(n) for gruppe in UEBERSCHRIFT.findall(text)
            for n in re.findall(r"#([0-9]+)", gruppe)}


def test_jeder_eintrag_nennt_seine_herkunft(text):
    """Ohne den Verweis laesst sich die Begruendung nicht nachlesen.

    Bis zum 20.9.2026 war das immer eine PR-Nummer. Seit PR #121 gemergt und
    sein Branch geloescht ist, entsteht Arbeit auch direkt auf ``main`` - dann
    ist der Commit der Verweis, und der Eintrag sagt ``(direkt auf main)``.

    Seit dem 3.10.2026 kommt eine dritte Form dazu: ``(Branch `name`)``, fuer
    Arbeit, die auf einem Branch entsteht und ohne Pull Request gemergt wird.
    Die beiden alten Formen deckten das nicht ab - eine PR-Nummer gibt es
    nicht, und ``direkt auf main`` waere falsch. Eine erfundene Nummer ist
    schlimmer als keine: Sie sieht nachschlagbar aus und fuehrt ins Leere.

    Verlangt bleibt, dass jeder Eintrag *irgendeine* nachschlagbare Herkunft
    nennt; was nicht geht, ist gar keine.
    """
    eintraege = re.findall(r"^## ([0-9]{2}\.[0-9]{2}\.[0-9]{4}.*)$", text, re.M)
    assert len(eintraege) >= 8, f"nur {len(eintraege)} Eintraege gefunden"
    ohne = [e for e in eintraege
            if not re.search(HERKUNFT, e)
            and "(direkt auf main)" not in e
            and not re.search(r"\(Branch `[^`]+`\)", e)]
    assert not ohne, f"Eintraege ohne nachschlagbare Herkunft: {ohne}"


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
    eintraege = pr_nummern(text)
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
    eintraege = pr_nummern(text)
    anfang = text.index("## Bewusst ohne Eintrag")
    ausgelassen = {int(n) for n in re.findall(r"^\| #([0-9]+) \|", text[anfang:], re.M)}
    doppelt = sorted(eintraege & ausgelassen)
    assert not doppelt, f"gleichzeitig Eintrag und ausgelassen: {doppelt}"


@pytest.mark.referenzstand
def test_der_kopf_nennt_faelle_und_taten(stand):
    """Beide Zaehlweisen, seit #66 - vorn die Faelle, seit E-2 (12.11.2026).

    Die Stadtzeile nennt die Faelle neben der Fallrate, die Zeile "Tatebene"
    die Taten neben der Tatrate - je Zeile ein Zeitraum und eine Grundmenge.
    """
    echt = gemessene_raten()
    for stadt in ("Chicago", "Detroit"):
        faelle = zahl(stand, rf"\| {stadt} \| ([0-9']+) Fälle")
        assert faelle == echt[stadt.lower()][1], (
            f"Faelle {stadt}: genannt {faelle:,}, tatsaechlich {echt[stadt.lower()][1]:,}"
        )
        taten = zahl(stand, rf"\| Tatebene.*?{stadt} ([0-9']+)")
        assert taten == echt[stadt.lower()][0], (
            f"Taten {stadt}: genannt {taten:,}, tatsaechlich {echt[stadt.lower()][0]:,}"
        )
