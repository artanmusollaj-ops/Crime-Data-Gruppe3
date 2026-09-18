"""``docs/README.md`` muss jedes Dokument kennen - und keines erfinden.

Am 18.9.2026 lagen fuenfzehn Markdown-Dateien, zwei HTML-Seiten und 8,8 MB
amtliche PDFs flach nebeneinander in ``docs/``. Nichts daran sagte, welches
Dokument in die Abgabe gehoert und welches nur wir brauchen - die Einteilung
existierte, aber nur in unseren Koepfen.

Seither steht sie in ``docs/README.md``. Ein Wegweiser, den niemand nachfuehrt,
ist allerdings schlimmer als keiner: Er sieht nach Ordnung aus. Diese Datei
haelt ihn deshalb an drei Zusagen fest - jedes Dokument steht darin, keines
darin fehlt auf der Platte, und die Einteilung ist vollstaendig.
"""

from __future__ import annotations

from pathlib import Path
import re

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCS = PROJECT_ROOT / "docs"
WEGWEISER = DOCS / "README.md"

# Die drei Ueberschriften, unter denen ein Dokument stehen kann. Faellt eine
# weg, ist die Einteilung keine mehr.
ABSCHNITTE = (
    "## Abgabe — was zum Leistungsnachweis gehört",
    "## Intern — was wir beim Arbeiten brauchen",
    "## Erzeugt — nie von Hand ändern",
    "## Quellen — die amtlichen Unterlagen",
    "## Archiv — überholt, aber nicht gelöscht",
)


@pytest.fixture(scope="module")
def text() -> str:
    return WEGWEISER.read_text(encoding="utf-8")


def dokumente() -> list[Path]:
    """Jedes Dokument in ``docs/`` - ohne die erzeugte Code-Referenz.

    ``referenz/`` sind 37 erzeugte Seiten; sie einzeln aufzufuehren waere
    Laerm. Der Wegweiser nennt den Ordner, und das genuegt.
    """
    return sorted(p for p in DOCS.glob("*.md") if p.name != "README.md") + \
        sorted(DOCS.glob("*.html")) + sorted(DOCS.glob("archiv/*.md"))


def test_der_wegweiser_kennt_jedes_dokument(text):
    fehlend = [p.name for p in dokumente() if p.name not in text]
    assert not fehlend, (
        f"nicht im Wegweiser docs/README.md: {fehlend}. Jedes neue Dokument "
        "braucht eine Zeile - und damit die Entscheidung, ob es in die Abgabe "
        "gehoert oder nicht."
    )


def test_der_wegweiser_erfindet_kein_dokument(text):
    """Ein Verweis auf etwas, das es nicht gibt, ist die andere Richtung."""
    vorhanden = {p.name for p in DOCS.rglob("*") if p.is_file()}
    vorhanden |= {"index.html"}          # referenz/index.html
    genannt = {m for m in re.findall(r"\(([^()]+\.(?:md|html))\)", text)}
    tot = sorted(n for n in genannt
                 if Path(n).name not in vorhanden and not n.startswith("../"))
    assert not tot, f"toter Verweis im Wegweiser: {tot}"


def test_die_einteilung_ist_vollstaendig(text):
    fehlend = [a for a in ABSCHNITTE if a not in text]
    assert not fehlend, f"Abschnitt fehlt im Wegweiser: {fehlend}"


def test_jedes_dokument_steht_in_genau_einem_abschnitt(text):
    """Zweimal genannt heisst: die Einteilung ist noch nicht entschieden.

    Ausnahme ist ``feldkatalog.md``. Es ist Anhang der Abgabe **und** erzeugt -
    beides ist wahr, und beides muss man wissen. Der Wegweiser sagt es an der
    ersten Stelle ausdruecklich dazu.
    """
    # Gezaehlt wird der **Verweis**, nicht die Nennung: "ein Eintrag in
    # AENDERUNGEN.md verweist darauf" ist Fliesstext und keine Einordnung.
    grenzen = [text.index(a) for a in ABSCHNITTE] + [len(text)]
    doppelt = []
    for p in dokumente():
        treffer = [ABSCHNITTE[i] for i in range(len(ABSCHNITTE))
                   if f"]({p.name})" in text[grenzen[i]:grenzen[i + 1]]
                   or f"/{p.name})" in text[grenzen[i]:grenzen[i + 1]]]
        if len(treffer) > 1 and p.name != "feldkatalog.md":
            doppelt.append(f"{p.name}: {treffer}")
    assert not doppelt, f"in mehreren Abschnitten: {doppelt}"
    assert "**erzeugt** (siehe unten)" in text, (
        "feldkatalog.md steht in zwei Abschnitten - der erste muss sagen, warum"
    )


def test_die_quellen_liegen_im_eigenen_ordner():
    """Die 8,8 MB amtliche Unterlagen gehoeren nicht zwischen die Prosa."""
    lose = sorted(p.name for p in DOCS.glob("*")
                  if p.suffix.lower() in {".pdf", ".xlsx", ".xls", ".docx"})
    assert not lose, f"Quelldateien liegen flach in docs/: {lose}"
    quellen = sorted((DOCS / "quellen").glob("*"))
    assert len(quellen) == 7, f"sieben amtliche Unterlagen erwartet, {len(quellen)} gefunden"


def abschnitt(text: str, von: str, bis: str | None) -> str:
    anfang = text.index(von)
    return text[anfang:text.index(bis)] if bis else text[anfang:]


def verlinkte_dokumente(text: str) -> set[str]:
    return {m for m in re.findall(r"\]\(([\w.-]+\.(?:md|html))\)", text)}


def test_wegweiser_und_konzept_teilen_dieselbe_einteilung():
    """Zwei Orte, eine Wahrheit - sonst driften sie auseinander.

    ``docs/README.md`` teilt die Dokumente in Abgabe und intern; Kapitel 11.3
    und 11.5 des Konzepts tun dasselbe noch einmal, weil die Abgabe ihre
    eigenen Anhaenge nennen muss. Am 18.9.2026 stimmten sie *nicht* ueberein:
    Das Konzept verlinkte ``leistungsnachweise.md`` mitten im Kapitel ueber
    die Hypothesen - ein Dokument, das ausdruecklich nicht zur Abgabe gehoert
    und Luecken auflistet -, und vier fuer den LN geschriebene Dokumente
    kamen darin ueberhaupt nicht vor.
    """
    wegweiser = WEGWEISER.read_text(encoding="utf-8")
    konzept = (DOCS / "ln1_konzept.md").read_text(encoding="utf-8")

    w_abgabe = verlinkte_dokumente(abschnitt(wegweiser, ABSCHNITTE[0], ABSCHNITTE[1]))
    w_intern = verlinkte_dokumente(abschnitt(wegweiser, ABSCHNITTE[1], ABSCHNITTE[2]))
    k_abgabe = verlinkte_dokumente(
        abschnitt(konzept, "### 11.3 Anhang zu diesem Leistungsnachweis",
                  "### 11.4 Amtliche Quellen"))
    k_intern = verlinkte_dokumente(
        abschnitt(konzept, "### 11.5 Interne Arbeitsgrundlagen", "Die Einteilung dieses"))

    # Das Konzept selbst steht im Wegweiser, nennt sich aber nicht im Anhang.
    w_abgabe.discard("ln1_konzept.md")
    assert w_abgabe == k_abgabe, (
        f"Anhang weicht ab.\n  nur im Wegweiser: {sorted(w_abgabe - k_abgabe)}"
        f"\n  nur im Konzept 11.3: {sorted(k_abgabe - w_abgabe)}"
    )
    assert w_intern == k_intern, (
        f"intern weicht ab.\n  nur im Wegweiser: {sorted(w_intern - k_intern)}"
        f"\n  nur im Konzept 11.5: {sorted(k_intern - w_intern)}"
    )


# Diese internen Dokumente duerfen im Fliesstext der Abgabe nicht auftauchen.
# ``AENDERUNGEN.md`` steht bewusst **nicht** darin: Kapitel 5.2 verweist in
# einer Selbstkorrektur darauf ("hier stand bis heute ..."), und das ist ein
# Beleg, kein Eingestaendnis - der Aenderungsnachweis traegt die Begruendung,
# die der Satz behauptet. Die drei hier dagegen fuehren offene Entscheide und
# Luecken; ein Verweis darauf mitten in der Argumentation zeigt auf das, was
# noch fehlt.
NICHT_IM_FLIESSTEXT = ("leistungsnachweise.md", "projektabsprache.md",
                       "datenhistorie.md")


def test_das_konzept_verlinkt_keine_maengelliste_im_fliesstext():
    """Der Fehler, der den Umbau ausgeloest hat.

    In Kapitel 3 - Forschungsfragen und Hypothesen, dem Kern der Abgabe -
    stand *"der Entscheid ist offen; siehe leistungsnachweise.md Abschnitt
    2.3"*. Wer dem folgte, landete in "Anforderungen, Stand, Luecken". In
    Kapitel 11.5 duerfen diese Dokumente stehen, dort ist der Vorbehalt dabei;
    im Fliesstext davor nicht.
    """
    konzept = (DOCS / "ln1_konzept.md").read_text(encoding="utf-8")
    davor = konzept[:konzept.index("## 11 · Wo was liegt")]
    # Der Vorspann vor Kapitel 1 nennt die Arbeitsgrundlagen ausdruecklich als
    # solche - das ist gewollt und gehoert nicht in die Pruefung.
    haupttext = davor[davor.index("## 1 "):] if "## 1 " in davor else davor
    gefunden = sorted(n for n in NICHT_IM_FLIESSTEXT if f"]({n})" in haupttext)
    assert not gefunden, (
        f"internes Dokument im Fliesstext der Abgabe verlinkt: {gefunden}. "
        "In Kapitel 11.5 gehoert es hin, davor nicht."
    )


def test_das_projekt_readme_fuehrt_zum_wegweiser():
    """Sonst findet ihn nur, wer ihn schon kennt."""
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/README.md" in readme, (
        "das README im Projekt-Root muss auf docs/README.md verweisen"
    )
