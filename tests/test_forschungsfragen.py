"""Haelt die drei Fassungen der Forschungsfragen gegen die **abgegebene**.

**Warum es diesen Waechter gibt.** Am 5.10.2026 waren drei Fassungen im
Umlauf. Das eingereichte LN1 fuehrt sechs Fragen F1 bis F6 mit je einer
Hypothese. ``notebooks/36_hypothesen.ipynb`` zitierte dieselben sechs - aber
eine Revision aelter: Sein H1 sagte *"die Menge der gelieferten technischen
IDs"*, das abgegebene *"die gelieferte Menge ... bei Quellen ohne
Identifikator-Menge tritt ein gleichwertiger Nachweis an ihre Stelle"*. Das
war keine Tippdifferenz, sondern genau die Einschraenkung, die das Notebook
selbst gemessen und in Prosa erklaert hatte und die in der Abgabe in die
Hypothese wanderte. Und Kapitel 3 von ``ln2_konzept.md`` trug einen dritten,
als Entwurf markierten Satz mit eigenem Nummernkreis.

``tests/test_notebook_hypothesen.py`` prueft seit dem 20.9.2026, dass das
Notebook seine sechs woertlich festhaelt - aber gegen **nichts**, weil die
massgebliche Fassung nicht im Repository lag.

**Was hier geprueft wird, und wann.**

* **Immer**: dass das abgelegte ``docs/forschungsfragen.md`` sechs Paare
  fuehrt, und dass Kapitel 3 des Konzepts dieselbe Menge im selben Wortlaut
  traegt. Dafuer braucht es die Quelle nicht.
* **Nur mit der Quelle**: dass ein frischer Bau dieselbe Datei liefert. Das
  abgegebene PDF liegt bewusst nicht im Repository (``.gitignore``), also
  ueberspringt diese Pruefung in einem frischen Klon - dieselbe Lage wie bei
  ``tests/test_platzbedarf_dokumente.py``, dessen Quelle ``data/`` ist.

Der Wert liegt deshalb weniger im Beweis gegen das PDF als im **Vergleich der
drei Fassungen gegeneinander**, und der laeuft immer.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

PROJEKT = Path(__file__).resolve().parents[1]
WERKZEUGE = PROJEKT / "tools"
if str(WERKZEUGE) not in sys.path:
    sys.path.insert(0, str(WERKZEUGE))

import build_forschungsfragen as bf  # noqa: E402

WERKZEUG = WERKZEUGE / "build_forschungsfragen.py"
DOKUMENT = PROJEKT / "docs" / "forschungsfragen.md"
KONZEPT = PROJEKT / "docs" / "ln2_konzept.md"

ALLE = bf.FRAGEN + bf.HYPOTHESEN


@pytest.fixture(scope="module")
def massgeblich() -> dict[str, str]:
    """Der abgegebene Wortlaut - aus dem abgelegten Dokument, nicht dem PDF."""
    if not DOKUMENT.is_file():
        pytest.fail(f"{DOKUMENT} fehlt - python tools/build_forschungsfragen.py")
    return bf.massgeblich(DOKUMENT)


def baue_nach(ziel: Path, pdf: Path | None = None) -> subprocess.CompletedProcess:
    """Ein Bau in einem **eigenen** Prozess.

    Nie im selben: Zwei Bauten darin teilen den Hash-Seed und koennen nicht
    abweichen - der Waechter waere gruen und wertlos (AGENTS.md).
    """
    befehl = [sys.executable, str(WERKZEUG), "--ziel", str(ziel)]
    if pdf is not None:
        befehl += ["--pdf", str(pdf)]
    return subprocess.run(befehl, capture_output=True, text=True, cwd=PROJEKT)


# --------------------------------------------------------------------------
# Das abgelegte Dokument - laeuft immer
# --------------------------------------------------------------------------


def test_das_dokument_liegt_im_repository():
    assert DOKUMENT.is_file(), (
        "docs/forschungsfragen.md fehlt - python tools/build_forschungsfragen.py. "
        "Ohne das Dokument haengen Notebook 36 und Kapitel 3 des Konzepts an "
        "nichts, und genau das war der Zustand bis zum 5.10.2026"
    )


def test_das_dokument_fuehrt_genau_sechs_paare(massgeblich):
    fehlend = [m for m in ALLE if m not in massgeblich]
    assert not fehlend, f"im Dokument fehlen: {fehlend}"
    leer = [m for m, text in massgeblich.items() if len(text) < 20]
    assert not leer, f"ohne Wortlaut: {leer}"


def test_jede_frage_endet_mit_einem_fragezeichen(massgeblich):
    """Das Fragezeichen trennt Frage von Hypothese - in der Vorlage wie hier."""
    ohne = [m for m in bf.FRAGEN if not massgeblich[m].endswith("?")]
    assert not ohne, f"keine Frage: {ohne}"


def test_das_dokument_nennt_seine_herkunft():
    """Ein erzeugtes Dokument ohne Herkunft laedt zur Handaenderung ein."""
    text = DOKUMENT.read_text(encoding="utf-8")
    for erwartet in ("Leistungsnachweis_1_Konzept_Gruppe_3.pdf",
                     "Kapitel 3", "tools/build_forschungsfragen.py",
                     "SHA-256", ".gitignore"):
        assert erwartet in text, f"das Dokument nennt {erwartet!r} nicht"


def test_das_dokument_sagt_dass_der_wortlaut_beleg_ist():
    """Die Zusage, die den ganzen Umbau tragt - als Satz, nicht als Absicht."""
    text = DOKUMENT.read_text(encoding="utf-8")
    assert "Beleg, nicht Entwurf" in text
    assert "nicht umformuliert" in text


def test_das_dokument_traegt_kein_erzeugungsdatum():
    """Sonst koennte der Reproduktionswaechter nie gruen sein.

    Dieselbe Lehre wie in ``serving.build_einstieg`` und
    ``tools/build_platzbedarf.py``: Der Stand kommt aus der **Quelle** - hier
    das Erstellungsdatum des PDF und sein SHA-256.
    """
    text = DOKUMENT.read_text(encoding="utf-8")
    assert "Stand der Quelle" in text
    # Ein Erzeugungsdatum waere ein Datum, das keines der genannten ist. Statt
    # danach zu suchen, wird die Zusage selbst geprueft: Das Dokument sagt,
    # dass es keines traegt - und test_ein_zweiter_lauf_liefert_dieselbe_datei
    # haelt die Zusage.
    assert "Ein Erzeugungsdatum steht hier bewusst nicht" in text


# --------------------------------------------------------------------------
# Kapitel 3 des Konzepts gegen das Dokument - laeuft immer
# --------------------------------------------------------------------------


def kapitel_drei() -> str:
    text = KONZEPT.read_text(encoding="utf-8")
    anfang = text.index("## 3 · Forschungsfragen und Hypothesen")
    return text[anfang:text.index("## 4 · ", anfang)]


def test_das_konzept_fuehrt_dieselbe_menge(massgeblich):
    """Kein zweiter Nummernkreis mehr.

    Bis zum 5.10.2026 fuehrte Kapitel 3 FF1 bis FF3 mit H1 bis H8 - andere
    Fragen, andere Hypothesen, als Entwurf markiert. Wer die Nummern
    verglich, ohne das zu wissen, verglich Verschiedenes.
    """
    kapitel = kapitel_drei()
    gelesen = bf.tabellenzitate_aus(kapitel)
    fehlend = [m for m in ALLE if m not in gelesen]
    assert not fehlend, (
        f"Kapitel 3 fuehrt diese Marken nicht (mehr): {fehlend}. Massgeblich "
        "ist docs/forschungsfragen.md; die Abgabe wurde mit F1 bis F6 "
        "eingereicht und bewertet."
    )
    ueberzaehlig = sorted(m for m in gelesen if m not in ALLE)
    assert not ueberzaehlig, (
        f"Kapitel 3 fuehrt Marken, die die Abgabe nicht kennt: "
        f"{ueberzaehlig}. Ein zweiter Nummernkreis im selben Kapitel war der "
        "Grund fuer diesen Waechter."
    )
    assert "FF1" not in kapitel, (
        "Kapitel 3 traegt wieder FF1 - der Entwurfssatz. Seine gemessenen "
        "Befunde gehoeren in den Analyseteil, nicht in die Hypothesentabelle."
    )


def test_das_konzept_zitiert_woertlich(massgeblich):
    """Jede Abweichung mit Marke und **beiden** Fassungen."""
    gelesen = bf.tabellenzitate_aus(kapitel_drei())
    abweichend = [
        f"{m}\n    abgegeben: {massgeblich[m]}\n    Kapitel 3:  {gelesen[m]}"
        for m in ALLE if m in gelesen and gelesen[m] != massgeblich[m]
    ]
    assert not abweichend, (
        "Kapitel 3 von docs/ln2_konzept.md weicht vom abgegebenen Wortlaut "
        "ab:\n  " + "\n  ".join(abweichend)
        + "\n\nMassgeblich ist docs/forschungsfragen.md - es ist aus der "
        "eingereichten Fassung erzeugt."
    )


def test_das_konzept_verweist_auf_das_erzeugte_dokument():
    """Eine Tabelle ohne ihre Quelle laedt zur Handaenderung ein."""
    assert "forschungsfragen.md" in kapitel_drei(), (
        "Kapitel 3 nennt docs/forschungsfragen.md nicht - dann weiss niemand, "
        "woher der Wortlaut kommt und womit er nachgezogen wird"
    )


def test_die_befunde_des_entwurfs_sind_nicht_verloren():
    """Gemessen ist gemessen - auch wenn die Hypothese daneben wegfaellt.

    Der alte Entwurf hatte zwei Befunde, die wirklich gerechnet wurden: die
    fehlenden Koordinaten nach Delikttyp (Chi-Quadrat, beide Staedte) und der
    falsifizierte raeumliche Join gegen Detroits eigene Tract-Angabe. Sie
    stehen seit dem 5.10.2026 als **Befunde** im Analyseteil.
    """
    text = KONZEPT.read_text(encoding="utf-8")
    analyse = text[text.index("## 8 · Transformation Teil 1"):
                   text.index("## 9 · Grenzen")]
    for erwartet in ("Chi-Quadrat", "räumliche", "Delikttyp"):
        assert erwartet in analyse, (
            f"der Befund zu {erwartet!r} steht nicht mehr im Analyseteil - "
            "er ist gemessen und darf mit dem Entwurf nicht verschwinden"
        )


# --------------------------------------------------------------------------
# Die Abbruchfaelle - ohne die Quelle pruefbar
# --------------------------------------------------------------------------


def test_eine_fehlende_frage_bricht_den_bau_ab():
    """Der Fall aus der Matrix: Vorlage geaendert oder Layout anders.

    Geprueft auf einer gestellten Vorlage und nicht am PDF - das PDF wird
    nicht veraendert. Die Spaltenlage ist dieselbe wie bei ``pdftotext
    -layout``: Marke, Frage, Hypothese, getrennt durch zwei Leerzeichen.
    """
    vorlage = [
        "              Frage                      Hypothese",
        " F1           Geht das?                  Ja.",
        " F2           Und das?                   Auch.",
    ]
    with pytest.raises(bf.LeseFehler) as fehler:
        bf.paare(vorlage)
    text = str(fehler.value)
    assert "F3" in text and "F6" in text, (
        f"der Abbruch nennt nicht, welche fehlen: {text}")
    assert "2 von 6" in text


def test_eine_frage_ohne_fragezeichen_bricht_den_bau_ab():
    """Das Fragezeichen trennt Frage von Hypothese; ohne es wird geraten."""
    vorlage = ["              Frage                      Hypothese"]
    for n in range(1, 7):
        vorlage.append(f" F{n}           Geht das{'?' if n != 4 else '.'}"
                       f"                  Ja.")
    with pytest.raises(bf.LeseFehler) as fehler:
        bf.paare(vorlage)
    assert "F4" in str(fehler.value)


def test_eine_fehlende_kopfzeile_bricht_den_bau_ab():
    with pytest.raises(bf.LeseFehler) as fehler:
        bf.paare([" F1    Geht das?    Ja."])
    assert "Kopfzeile" in str(fehler.value)


def test_der_bau_ueberlebt_den_seitenwechsel_in_der_tabelle():
    """Die Spalten verschieben sich dort - gemessen am abgegebenen PDF.

    Auf Seite 6 stehen sie auf 39 und 81, auf Seite 7 auf 43 und 87. Eine aus
    der Kopfzeile verdrahtete Lage haette F3 bis F6 verloren, und zwar still:
    Die Fortsetzungszeilen waeren einfach nicht angekommen.
    """
    vorlage = ["                     Frage                 Hypothese",
               " F1                  Geht das?             Ja, und zwar",
               "                                           gruendlich."]
    # Dieselbe Tabelle, vier Zeichen nach rechts - wie nach einem Seitenumbruch.
    vorlage += ["     F2                  Und das?              Auch, und",
                "                                               wie."]
    gelesen = bf.reihen(vorlage, ("Frage", "Hypothese"), re.compile(r"F\d+"))
    assert [r.marke for r in gelesen] == ["F1", "F2"]
    assert gelesen[0].rechts == "Ja, und zwar gruendlich."
    assert gelesen[1].rechts == "Auch, und wie."


def test_ohne_die_quelle_bricht_der_generator_mit_grund_ab(tmp_path):
    """Kein Traceback, sondern ein Satz - und nichts geschrieben."""
    ziel = tmp_path / "fehlschlag.md"
    fertig = baue_nach(ziel, pdf=tmp_path / "gibtsnicht.pdf")
    assert fertig.returncode == 1, fertig.stdout + fertig.stderr
    assert "Traceback" not in fertig.stderr, fertig.stderr
    assert "FEHLER" in fertig.stderr and "gibtsnicht.pdf" in fertig.stderr
    assert not ziel.exists(), (
        "der gescheiterte Lauf hat trotzdem geschrieben - am 17.9.2026 ist "
        "der Feldkatalog genau so zweimal in einen Commit geraten")


# --------------------------------------------------------------------------
# Reproduktion - braucht die Quelle und ueberspringt ohne sie
# --------------------------------------------------------------------------


def test_ein_zweiter_lauf_liefert_dieselbe_datei(tmp_path):
    """Zwei Laeufe, **zwei Prozesse** - und dieselbe Datei.

    Ueberspringt ohne das abgegebene PDF: Es liegt bewusst nicht im
    Repository, und in einem frischen Klon waere der Test sonst dauerhaft
    rot. Gebaut wird nach ``tmp_path``, damit ein Fehlschlag das abgelegte
    Dokument nicht veraendert.
    """
    if not bf.QUELLE.is_file():
        pytest.skip(f"{bf.QUELLE.name} liegt nicht hier (bewusst ungetrackt)")
    gebaut = []
    for n in range(2):
        ziel = tmp_path / f"lauf{n}.md"
        fertig = baue_nach(ziel)
        if fertig.returncode != 0 and "pdftotext nicht gefunden" in fertig.stderr:
            pytest.skip("pdftotext nicht verfuegbar - es kommt mit poppler")
        assert fertig.returncode == 0, fertig.stderr[-1500:]
        gebaut.append(ziel.read_text(encoding="utf-8"))

    assert gebaut[0] == gebaut[1], (
        "zwei Laeufe liefern verschiedene Dateien - irgendwo steckt etwas "
        "Veraenderliches darin, vermutlich ein Datum")
    assert DOKUMENT.read_text(encoding="utf-8") == gebaut[0], (
        "docs/forschungsfragen.md ist aelter als die abgegebene Fassung. "
        "python tools/build_forschungsfragen.py")
