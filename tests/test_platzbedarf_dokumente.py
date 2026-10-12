"""Haelt die Schichtentabelle in **beiden** Dokumenten gegen eine frische Messung.

**Warum es diesen Waechter gibt.** Am 4.10.2026 nannte
``docs/architektur-ist-und-ziel.md`` fuer ``releases/`` 121 MB, gemessen waren
254,1 MB - mehr als das Doppelte. Dieselbe Tabelle steht ein zweites Mal als
SVG-Text in ``docs/architektur-einseiter.html``, und dort stand sie
**unbewacht**: ``tests/test_dokumentzahlen.py`` sammelt nur tausendergetrennte
Ganzzahlen (``\\b\\d{1,3}(?:'\\d{3})+\\b``) und sieht eine MB-Angabe gar nicht.
Bewacht war bis dahin keine einzige Groessenangabe im Projekt.

Deshalb zwei Dinge, und beide stehen in AGENTS.md als Lehre:

* **Steht dieselbe Tabelle in zwei Dokumenten, muss der Waechter beide
  erfassen.** Sonst veraltet das unbewachte genauso - einmal mit acht
  ueberholten Aussagen auf einmal. Darum laeuft jede Pruefung hier ueber beide
  Fundstellen, und ``test_beide_dokumente_tragen_die_tabelle`` faellt, wenn
  eine davon verschwindet.
* **Reproduzierbarkeit nie in einem Prozess pruefen.** Der zweite Bau von
  ``tools/build_platzbedarf.py`` laeuft per ``subprocess``; zwei Bauten im
  selben Prozess teilen den Hash-Seed und koennen nicht abweichen.

**Was er nicht prueft.** Nicht alle 261 Groessenangaben des Projekts - nur die
Schichtentabelle und die Groesse je Release. Die uebrigen stehen in Prosa ueber
Dinge, die sich nicht aus ``data/`` messen lassen.

**Wann er laeuft.** Er traegt ``referenzstand``: Die gemessenen Groessen
bewegen sich mit jedem Lauf, und auf einem Pull Request ohne Daten waere er
nur rot. Er gehoert zu ``python -m pytest -m referenzstand`` auf dem eigenen
Rechner - und dort vor allem nach einem Neubau und vor einer Abgabe.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from orchestration import platzbedarf as pb


PROJEKT = Path(__file__).resolve().parents[1]
DATEN = PROJEKT / "data"
WERKZEUG = PROJEKT / "tools" / "build_platzbedarf.py"
DOKUMENT = PROJEKT / "docs" / "intern" / "platzbedarf.md"

MARKDOWN = PROJEKT / "docs" / "architektur-ist-und-ziel.md"
EINSEITER = PROJEKT / "docs" / "architektur-einseiter.html"
BEIDE = (MARKDOWN, EINSEITER)

pytestmark = pytest.mark.referenzstand

# Eine MB- oder GB-Angabe mit Schweizer Trenner und Dezimalkomma: "0,9 MB",
# "254,1 MB", "1'831,1 MB", "2,73 GB". Genau die Form, die der
# Ganzzahl-Sammler in test_dokumentzahlen.py nicht sieht.
GROESSE = re.compile(r"(\d{1,3}(?:'\d{3})*(?:,\d+)?)\s*(MB|GB)")

# Dateigroessen bewegen sich weniger als Zeilenzahlen: Ein Neubau derselben
# Daten aendert ein Parquet um Promille. Ein Prozent trennt deshalb sicher
# "nachgezogen" von "veraltet" - die Abweichung, die diesen Waechter
# ausgeloest hat, lag bei 110 %.
TOLERANZ = 0.01

# Dazu die Rundung der Darstellung: Die Dokumente schreiben eine Stelle nach
# dem Komma, und "0,9 MB" fuer 0,923 MB ist nicht veraltet, sondern gerundet.
# Ohne diesen Spielraum waere jede kleine Schicht dauerhaft rot - 2,5 %
# Rundungsfehler bei einer Toleranz von 1 %.
RUNDUNG = 0.05


def mb(bytes_: int) -> float:
    return bytes_ / 1e6


@pytest.fixture(scope="module")
def gemessen() -> dict[str, int]:
    """Die Belegung je Schicht, frisch gemessen - lokal, wie das Dokument.

    ``nur_lokal`` und nicht die Ablage aus der Umgebung: Mit
    ``STORAGE_BACKEND=hybrid`` zaehlte die Messung den gemeinsamen Bestand auf
    SeaweedFS mit, und dann haengt der Waechter daran, wer ihn laufen laesst.
    """
    ablage = pb.nur_lokal(DATEN)
    schichten = pb.belegung(ablage)
    if not any(s.dateien for s in schichten):
        pytest.skip("kein gebautes data/ - erst 'run_all' laufen lassen")
    return {s.name: s.bytes for s in schichten}


@pytest.fixture(scope="module")
def release_bytes() -> int:
    """Die Groesse eines Release-Standes - der groesste, wie in der Rechnung."""
    ablage = pb.nur_lokal(DATEN)
    staende: dict[str, int] = {}
    for rel, groesse in ablage.groessen_unter("releases").items():
        teile = rel.split("/")
        if len(teile) > 2 and teile[1].startswith("release="):
            staende[teile[1]] = staende.get(teile[1], 0) + groesse
    if not staende:
        pytest.skip("kein Release liegt lokal")
    return max(staende.values())


def fundstellen(pfad: Path) -> list[tuple[int, str, float]]:
    """Jede MB-/GB-Angabe einer Datei, mit Zeilennummer - in MB gerechnet."""
    gefunden = []
    for nummer, zeile in enumerate(pfad.read_text(encoding="utf-8").splitlines(), 1):
        for treffer in GROESSE.finditer(zeile):
            wert = float(treffer.group(1).replace("'", "").replace(",", "."))
            gefunden.append((nummer, treffer.group(0),
                             wert * (1000 if treffer.group(2) == "GB" else 1)))
    return gefunden


def nahe(wert: float, soll: float) -> bool:
    return soll > 0 and abs(wert - soll) <= max(soll * TOLERANZ, RUNDUNG)


# Ein ``<text>`` des Einseiters, mit seiner x-Position. Die Schichtentabelle
# steht dort als Band: Name und Groesse einer Schicht teilen dieselbe
# x-Position, nicht dieselbe Zeile.
SVG_TEXT = re.compile(r'<text x="(\d+)"[^>]*>([^<]*)</text>')


def schichtentabelle(pfad: Path, schichten: tuple[str, ...]
                     ) -> dict[str, tuple[int, str, float]]:
    """Je Schicht **ihre** Fundstelle, nicht irgendeine der Datei.

    Die erste Fassung dieses Waechters suchte die gemessene Zahl irgendwo im
    Dokument. Das ging fuer vier der sechs Schichten gut und fuer zwei nicht:
    ``143,5 MB`` steht in ``architektur-ist-und-ziel.md`` auch im Satz ueber
    die Trennung von raw und bronze, ``15,3 MB`` auch im Abschnitt ueber
    Elasticsearch. Wer die Tabellenzelle von raw oder gold auf Unsinn setzte,
    blieb gruen - der Zwilling im Fliesstext deckte ihn. Gebunden wird deshalb
    an die **Zeile der Schicht**:

    * Markdown: die Tabellenzeile, die mit ``| **<schicht>** |`` beginnt; es
      zaehlt die letzte Groessenangabe darin.
    * Einseiter: die ``<text>``-Elemente an derselben **x-Position** wie der
      Schichtname. Nicht ueber ``y``, damit ein verschobenes Band den Waechter
      nicht gleich mit verschiebt.
    """
    text = pfad.read_text(encoding="utf-8")
    gefunden: dict[str, tuple[int, str, float]] = {}

    if pfad.suffix == ".md":
        for nummer, zeile in enumerate(text.splitlines(), 1):
            for schicht in schichten:
                if not zeile.startswith(f"| **{schicht}**"):
                    continue
                treffer = list(GROESSE.finditer(zeile))
                if treffer:
                    gefunden[schicht] = (nummer, treffer[-1].group(0),
                                         _mb_aus(treffer[-1]))
        return gefunden

    je_x: dict[int, list[tuple[int, str]]] = {}
    for nummer, zeile in enumerate(text.splitlines(), 1):
        for treffer in SVG_TEXT.finditer(zeile):
            je_x.setdefault(int(treffer.group(1)), []).append(
                (nummer, treffer.group(2)))
    for schicht in schichten:
        for texte in je_x.values():
            if not any(inhalt.strip() == schicht for _, inhalt in texte):
                continue
            for nummer, inhalt in texte:
                if (treffer := GROESSE.search(inhalt)) is not None:
                    gefunden[schicht] = (nummer, treffer.group(0),
                                         _mb_aus(treffer))
                    break
    return gefunden


def _mb_aus(treffer: re.Match) -> float:
    wert = float(treffer.group(1).replace("'", "").replace(",", "."))
    return wert * (1000 if treffer.group(2) == "GB" else 1)


# --------------------------------------------------------------------------
# Der Sammler selbst
# --------------------------------------------------------------------------


def test_der_sammler_findet_ueberhaupt_groessen():
    """Ein Sammler, der nichts findet, prueft nichts.

    Genau das war der Zustand vorher: Der Ganzzahl-Sammler in
    test_dokumentzahlen.py sieht '254,1 MB' nicht, und niemand hat es bemerkt.
    """
    for pfad in BEIDE:
        assert len(fundstellen(pfad)) >= 6, (
            f"{pfad.name}: nur {len(fundstellen(pfad))} Groessenangaben "
            "gefunden - das Muster passt nicht mehr auf das Dokument")


@pytest.mark.parametrize("text, erwartet", [
    ("0,9 MB", 0.9), ("254,1 MB", 254.1), ("1'831,1 MB", 1831.1),
    ("2,73 GB", 2730.0), ("42 MB", 42.0),
])
def test_der_sammler_versteht_beide_einheiten(tmp_path, text, erwartet):
    pfad = tmp_path / "x.md"
    pfad.write_text(f"irgendwas {text} dahinter\n", encoding="utf-8")
    assert fundstellen(pfad)[0][2] == pytest.approx(erwartet)


def test_beide_dokumente_tragen_die_tabelle():
    """Verschwindet eine Fundstelle, soll das auffallen und nicht beruhigen."""
    for pfad in BEIDE:
        werte = {f"{w:.1f}" for _, _, w in fundstellen(pfad)}
        assert len(werte) >= 5, (
            f"{pfad.name} nennt die Schichtgroessen nicht mehr - dann prueft "
            "dieser Waechter dort nichts, und das ist schlimmer als rot")


# --------------------------------------------------------------------------
# Die Schichtentabelle, in beiden Dokumenten
# --------------------------------------------------------------------------


@pytest.mark.parametrize("pfad", BEIDE, ids=lambda p: p.name)
def test_jede_schicht_steht_mit_ihrer_gemessenen_groesse_da(pfad, gemessen):
    """Je Schicht **eine** Fundstelle, die die Messung trifft.

    Geprueft wird in dieser Richtung - von der Messung zum Dokument -, weil
    die andere Richtung eine zweite Liste waere, die selbst veraltet.

    **Warum nicht die Umkehrung wie in ``test_dokumentzahlen.py``** ("nahe an
    einer Kennzahl, aber keine, also deren veraltete Fassung")? Weil ihre
    Voraussetzung hier nicht gilt. Zeilenzahlen wandern um Zehntelprozente;
    Bytes wandern weit - ``releases/`` hat sich zwischen zwei Messungen von
    121 auf 254 MB mehr als verdoppelt. Ein Naehe-Fenster, das 121 noch als
    veraltete Fassung von 254 erkennt, haelt jede zweite Groesse des Dokuments
    fuer eine veraltete Schichtgroesse. Verlaesslich ist hier die **fehlende
    richtige** Zahl, nicht die vorhandene falsche.
    """
    gebunden = schichtentabelle(pfad, tuple(gemessen))
    beanstandet = []
    for name, bytes_ in gemessen.items():
        if not bytes_:
            continue
        soll = mb(bytes_)
        if name not in gebunden:
            beanstandet.append(
                f"{name} ist gemessen {soll:.1f} MB - "
                f"{pfad.relative_to(PROJEKT)} hat fuer diese Schicht gar "
                f"keine Zeile mehr")
            continue
        nummer, roh, wert = gebunden[name]
        if not nahe(wert, soll):
            beanstandet.append(
                f"{name} ist gemessen {soll:.1f} MB - "
                f"{pfad.relative_to(PROJEKT)}:{nummer} steht '{roh}'")
    assert not beanstandet, (
        f"{pfad.relative_to(PROJEKT)} nennt diese gemessenen Groessen nicht "
        f"(mehr):\n  " + "\n  ".join(beanstandet)
        + "\n\nNachziehen: python tools/build_platzbedarf.py, dann die Tabelle "
        "in beiden Dokumenten aus docs/intern/platzbedarf.md uebernehmen."
    )


@pytest.mark.parametrize("pfad", BEIDE, ids=lambda p: p.name)
def test_die_groesse_eines_release_steht_richtig_da(pfad, release_bytes):
    """Die zweite bewachte Zahl: was ein Stand kostet.

    Sie traegt die Releases-Regel der Hochrechnung (``RELEASES_N`` Staende) und
    steht in beiden Dokumenten - im Markdown in B.6, im Einseiter in der
    Querschnittszeile.
    """
    soll = mb(release_bytes)
    werte = [w for _, _, w in fundstellen(pfad)]
    # 5 % statt 1 %: Hier steht eine gerundete Angabe ("rund 42 MB"), und
    # Releases unterscheiden sich untereinander um Zehntel-MB.
    assert any(abs(w - soll) / soll <= 0.05 for w in werte), (
        f"{pfad.relative_to(PROJEKT)} nennt die Groesse eines Release-Standes "
        f"nicht ({soll:.1f} MB). Gefunden: "
        f"{', '.join(f'{w:.1f}' for w in sorted(werte))}"
    )


@pytest.mark.parametrize("pfad", BEIDE, ids=lambda p: p.name)
def test_beide_dokumente_verweisen_auf_die_hochrechnung(pfad):
    """Eine Tabelle ohne ihren Generator laedt zur Handaenderung ein."""
    assert "platzbedarf" in pfad.read_text(encoding="utf-8"), (
        f"{pfad.relative_to(PROJEKT)} verweist nicht auf "
        "docs/intern/platzbedarf.md - dann weiss niemand, woher die Zahlen "
        "kommen und womit sie nachgezogen werden")


# --------------------------------------------------------------------------
# Das erzeugte Dokument
# --------------------------------------------------------------------------


def test_das_erzeugte_dokument_liegt_im_repository():
    assert DOKUMENT.is_file(), (
        "docs/intern/platzbedarf.md fehlt - python tools/build_platzbedarf.py")


def test_das_erzeugte_dokument_traegt_die_gemessene_tabelle(gemessen):
    werte = [w for _, _, w in fundstellen(DOKUMENT)]
    fehlend = [name for name, b in gemessen.items()
               if b and not any(nahe(w, mb(b)) for w in werte)]
    assert not fehlend, (
        f"platzbedarf.md ist aelter als die Daten ({', '.join(fehlend)}) - "
        "python tools/build_platzbedarf.py")


def test_ein_zweiter_lauf_liefert_dieselbe_datei(tmp_path, gemessen):
    """Zwei Laeufe, **zwei Prozesse** - und dieselbe Datei.

    ``gemessen`` steht hier nur fuer seinen Sprung: Ohne gebautes ``data/``
    beschreibt die abgelegte Datei einen Stand, den es hier nicht gibt, und
    ein Vergleich waere eine Aussage ueber den fremden Rechner.

    Im selben Prozess waere der Test gruen und wertlos: Zwei Bauten teilen
    dann den Hash-Seed und koennen nicht abweichen (AGENTS.md). Gebaut wird
    nach ``tmp_path``, damit ein Fehlschlag die abgelegte Datei nicht
    veraendert - am 17.9.2026 ist der Feldkatalog genau so zweimal in einen
    Commit geraten.
    """
    gebaut = []
    for n in range(2):
        ziel = tmp_path / f"lauf{n}.md"
        fertig = subprocess.run(
            [sys.executable, str(WERKZEUG), "--data-root", str(DATEN),
             "--ziel", str(ziel)],
            capture_output=True, text=True, cwd=PROJEKT)
        assert fertig.returncode == 0, fertig.stderr[-1500:]
        gebaut.append(ziel.read_text(encoding="utf-8"))

    assert gebaut[0] == gebaut[1], (
        "zwei Laeufe liefern verschiedene Dateien - irgendwo steckt etwas "
        "Veraenderliches darin, vermutlich ein Datum oder eine Menge")
    assert DOKUMENT.read_text(encoding="utf-8") == gebaut[0], (
        "docs/intern/platzbedarf.md ist aelter als data/. "
        "python tools/build_platzbedarf.py")


def test_das_dokument_nennt_den_stand_der_daten_statt_eines_datums():
    """Das Messdatum ist der **Stand der Daten**, kein ``date.today()``.

    Ein Erzeugungszeitstempel haette den Waechter darueber unmoeglich gemacht:
    Ein zweiter Lauf am naechsten Tag liefert dann eine andere Datei.
    ``serving.build_einstieg`` laesst ihn aus demselben Grund weg. Genannt
    wird deshalb die Kennung des juengsten Release - sie steht in den Daten
    und ist bei einem zweiten Lauf dieselbe.
    """
    text = DOKUMENT.read_text(encoding="utf-8")
    assert "Stand der Daten:" in text
    ablage = pb.nur_lokal(DATEN)
    kennungen = sorted(
        teile[1].removeprefix("release=")
        for rel in ablage.groessen_unter("releases")
        if len(teile := rel.split("/")) > 2 and teile[1].startswith("release=")
    )
    if not kennungen:
        pytest.skip("kein Release liegt lokal")
    assert kennungen[-1] in text, (
        f"das Dokument nennt nicht das juengste Release ({kennungen[-1]}) - "
        "python tools/build_platzbedarf.py")
