#!/usr/bin/env python3
"""Erzeugt ``docs/forschungsfragen.md`` aus dem abgegebenen LN1-PDF.

Aufruf aus dem Projekt-Root:

    python tools/build_forschungsfragen.py
    python tools/build_forschungsfragen.py --pdf ... --ziel /tmp/f.md

**Warum erzeugt und nicht abgeschrieben.** Am 5.10.2026 waren drei Fassungen
der Forschungsfragen im Umlauf, und keine Pruefung hielt sie zusammen. Die
abgegebene steht im PDF, Notebook 36 zitierte eine Revision davor, und
Kapitel 3 des Konzepts trug einen als Entwurf markierten dritten Satz mit
eigenem Nummernkreis. Die Abweichung war keine Tippdifferenz: Notebook 36 hat
gemessen, dass H1 nur fuer zwei der fuenf Quellen woertlich gilt, die Abgabe
hat diese Einschraenkung in die Hypothese aufgenommen - und das Notebook
zitierte weiter die Fassung ohne sie.

Abschreiben haette eine vierte Fassung erzeugt. Ein Generator erzeugt
dieselbe, und wer das PDF hat, kann sie nachweisen.

**Die Quelle liegt nicht im Repository.** Dieselbe Lage wie bei
``tools/build_platzbedarf.py``, dort die gemessene Belegung unter ``data/``:
Der Generator laeuft, wo die Quelle liegt, das erzeugte Dokument ist die
versionierte Fassung, und der Reproduktionswaechter ueberspringt sauber, wenn
die Quelle fehlt (Entscheid vom 5.10.2026, ``.gitignore``). Die Pruefungen,
die **immer** laufen, sind die, die Notebook 36 und ``docs/ln2_konzept.md``
gegen das erzeugte Dokument halten - sie haetten die H1-Abweichung gefangen.

**Gelesen wird ueber ``pdftotext -layout``**, wie in
``tools/build_nibrs_categories.py`` und ``tools/extend_micr_arrest_charges.py``
auch. Das Werkzeug kommt mit poppler; fehlt es, bricht der Lauf mit einem
Grund ab statt mit einem Traceback. Die Tabellen aus Kapitel 3 und 11 stehen
im Layout-Modus als drei Spalten nebeneinander - Marke, Frage, Hypothese -,
und die Spalten werden **je Zeile mit Marke neu gemessen**: Beim Seitenwechsel
innerhalb der Tabelle verschiebt poppler sie um vier Zeichen, und eine fest
verdrahtete Spaltenlage haette F3 bis F6 verloren.

**Kein Erzeugungszeitstempel.** Wie in ``tools/build_platzbedarf.py`` und
``serving.build_einstieg``: Ein ``date.today()`` in der Datei hiesse, dass
ein zweiter Lauf eine andere Datei liefert, und der Waechter darauf koennte
nie gruen sein. Genannt wird deshalb der **Stand der Quelle** - das
Erstellungsdatum des PDF und sein SHA-256. Beides steht in der Quelle und ist
beim zweiten Lauf dasselbe.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

PROJEKT = Path(__file__).resolve().parents[1]
QUELLE = PROJEKT / "docs" / "Leistungsnachweis_1_Konzept_Gruppe_3.pdf"
ZIEL = PROJEKT / "docs" / "forschungsfragen.md"
WERKZEUG = "tools/build_forschungsfragen.py"

#: Die Marken, die vollstaendig dastehen muessen. Weniger heisst: Die Vorlage
#: sieht anders aus als erwartet, und dann soll nichts geschrieben werden.
FRAGEN = tuple(f"F{n}" for n in range(1, 7))
HYPOTHESEN = tuple(f"H{n}" for n in range(1, 7))

#: Die Breite, auf die die Zitate umgebrochen werden. Fest, weil ein zweiter
#: Lauf dieselbe Datei liefern muss.
BREITE = 76


class LeseFehler(RuntimeError):
    """Die Vorlage sieht anders aus als erwartet."""


@dataclass(frozen=True)
class Reihe:
    """Eine Tabellenzeile der Vorlage: Marke und ihre zwei Spalten."""

    marke: str
    links: str
    rechts: str


# --------------------------------------------------------------------------
# Die Vorlage lesen
# --------------------------------------------------------------------------

#: Ein zusammenhaengender Textblock einer Layout-Zeile, mit seiner Spalte.
#: Getrennt wird an zwei Leerzeichen - so setzt ``pdftotext -layout`` die
#: Spalten einer Tabelle.
BLOCK = re.compile(r"\S(?:.*?\S)?(?=\s{2,}|$)")

#: Wie weit eine Fortsetzungszeile von ihrer Spalte abweichen darf. Vier
#: Zeichen: Innerhalb einer Seite stehen die Spalten auf dem Zeichen genau,
#: und die Seitenzahl in der Tabellenmitte liegt neunzehn Zeichen daneben -
#: sie faellt damit heraus, ohne dass sie benannt werden muss.
SPIEL = 4


def text_aus_pdf(pfad: Path) -> list[str]:
    """Die Vorlage als Layout-Text, Zeile fuer Zeile."""
    if not pfad.is_file():
        raise LeseFehler(
            f"die abgegebene Fassung fehlt: {pfad}. Sie liegt bewusst nicht "
            "im Repository (.gitignore); ohne sie laesst sich das Dokument "
            "nicht erzeugen - die Vergleiche gegen das abgelegte Dokument "
            "laufen trotzdem"
        )
    try:
        fertig = subprocess.run(
            ["pdftotext", "-layout", str(pfad), "-"],
            capture_output=True, check=True,
        )
    except FileNotFoundError as fehler:
        raise LeseFehler(
            "pdftotext nicht gefunden - es kommt mit poppler"
        ) from fehler
    except subprocess.CalledProcessError as fehler:
        raise LeseFehler(f"pdftotext scheiterte: {fehler}") from fehler
    # Nicht splitlines: Der Seitenvorschub \x0c wuerde als Zeilenende zaehlen
    # und die Einrueckung der Folgezeile verschieben - dieselbe Lehre wie in
    # tools/build_nibrs_categories.py. \r muss weg, weil pdftotext unter
    # Windows \r\n schreibt und die Spaltenrechnung daran haengt.
    return [z.rstrip("\r") for z in
            fertig.stdout.decode("utf-8", "replace").split("\n")]


def bloecke(zeile: str) -> list[tuple[int, str]]:
    return [(t.start(), t.group()) for t in BLOCK.finditer(zeile)]


def reihen(zeilen: list[str], kopf: tuple[str, str],
           marke: re.Pattern[str]) -> list[Reihe]:
    """Die Zeilen einer dreispaltigen Tabelle, ab ihrer Kopfzeile.

    Gefunden wird die Tabelle ueber ihre **Kopfzeile** - genau die zwei
    Spaltennamen und nichts sonst. Das Dokument fuehrt drei Tabellen mit dem
    Wort *Hypothese* im Kopf; nur eine traegt daneben *Frage*.

    Die Spaltenlage wird aus jeder Zeile mit Marke neu genommen. Beim
    Seitenwechsel verschiebt poppler sie (39/81 auf Seite 6, 43/87 auf
    Seite 7); wer sie aus der Kopfzeile verdrahtet, verliert alles nach dem
    Seitenumbruch.

    Die Tabelle endet, wo in der Markenspalte etwas steht, das keine Marke
    ist - der Fliesstext unter der Tabelle beginnt am Zeilenanfang.
    """
    try:
        anfang = next(i for i, z in enumerate(zeilen)
                      if [t for _, t in bloecke(z)] == list(kopf))
    except StopIteration as fehler:
        raise LeseFehler(
            f"die Kopfzeile '{kopf[0]} | {kopf[1]}' steht nicht in der "
            "Vorlage - das Kapitel ist umgebaut oder anders gesetzt"
        ) from fehler

    gefunden: list[Reihe] = []
    teile: list[list[str]] = []
    spalten: list[int] = []
    for zeile in zeilen[anfang + 1:]:
        aktuell = bloecke(zeile)
        if not aktuell:
            continue
        if marke.fullmatch(aktuell[0][1]) and len(aktuell) == 3:
            # Eine Zeile mit Marke traegt alle drei Spalten und setzt damit
            # die Lage fuer ihre Fortsetzungszeilen.
            spalten = [spalte for spalte, _ in aktuell]
            teile.append([aktuell[0][1], aktuell[1][1], aktuell[2][1]])
            continue
        if not spalten:
            continue
        passend = []
        for spalte, inhalt in aktuell:
            naechste = min(spalten, key=lambda s: abs(s - spalte))
            if abs(naechste - spalte) <= SPIEL:
                passend.append((spalten.index(naechste), inhalt))
        if passend and passend[0][0] == 0:
            # In der Markenspalte steht Fliesstext: Die Tabelle ist zu Ende.
            break
        for welche, inhalt in passend:
            teile[-1][welche] += " " + inhalt

    gefunden = [Reihe(m, satz(li), satz(re_)) for m, li, re_ in teile]
    return gefunden


def satz(text: str) -> str:
    """Ein Zellinhalt als ein Satz - Umbrueche weg, Trennstriche zusammen."""
    text = re.sub(r"\s+", " ", text).strip()
    # "Batch -Datenplattform" zurueck zu "Batch-Datenplattform": Word setzt in
    # manchen Zellen einen bedingten Trennstrich, den poppler als eigenen
    # Block liest. Nur zwischen zwei Wortzeichen, damit der Gedankenstrich in
    # "nachgewiesen wird - nicht, welche Stadt" unberuehrt bleibt.
    return re.sub(r"(\w)\s+-(\w)", r"\1-\2", text)


def absatz(zeilen: list[str], anfang: str) -> str:
    """Der Absatz, der mit ``anfang`` beginnt - bis zur naechsten Leerzeile."""
    try:
        erste = next(i for i, z in enumerate(zeilen) if z.startswith(anfang))
    except StopIteration as fehler:
        raise LeseFehler(
            f"der Absatz '{anfang}...' steht nicht in der Vorlage"
        ) from fehler
    gesammelt = []
    for zeile in zeilen[erste:]:
        if not zeile.strip():
            break
        gesammelt.append(zeile.strip())
    return satz(" ".join(gesammelt))


def uebergeordnete_frage(zeilen: list[str]) -> str:
    """Die eine Frage ueber den sechs - sie steht im Fliesstext, nicht in der
    Tabelle, und endet am ersten Fragezeichen."""
    marke = "Die übergeordnete Forschungsfrage lautet:"
    text = absatz(zeilen, marke)[len(marke):].strip()
    if "?" not in text:
        raise LeseFehler(
            "die uebergeordnete Forschungsfrage endet nicht mit einem "
            f"Fragezeichen: {text[:120]!r}"
        )
    return text[:text.index("?") + 1]


def paare(zeilen: list[str]) -> list[Reihe]:
    """Die sechs Teilfragen mit ihren Hypothesen, aus Kapitel 3."""
    gefunden = reihen(zeilen, ("Frage", "Hypothese"), re.compile(r"F\d+"))
    pruefe_vollstaendig(gefunden, FRAGEN, "Kapitel 3")
    ohne = [r.marke for r in gefunden if not r.links.endswith("?")]
    if ohne:
        raise LeseFehler(
            f"diese Fragen enden nicht mit einem Fragezeichen: {ohne}. Das "
            "Fragezeichen trennt Frage von Hypothese; ohne es ist nicht "
            "entscheidbar, was zitiert wird"
        )
    leer = [r.marke for r in gefunden if not r.rechts]
    if leer:
        raise LeseFehler(f"diese Fragen stehen ohne Hypothese da: {leer}")
    return gefunden


def befunde(zeilen: list[str]) -> list[Reihe]:
    """Die Beantwortung aus Kapitel 11 - je Hypothese ihr Ergebnis."""
    gefunden = reihen(zeilen, ("Hypothese", "Ergebnis"), re.compile(r"H\d+"))
    pruefe_vollstaendig(gefunden, HYPOTHESEN, "Kapitel 11")
    return gefunden


def pruefe_vollstaendig(gefunden: list[Reihe], erwartet: tuple[str, ...],
                        wo: str) -> None:
    """Nennt, **welche** fehlen - nicht nur, dass es zu wenige sind."""
    da = [r.marke for r in gefunden]
    fehlend = [m for m in erwartet if m not in da]
    ueberzaehlig = [m for m in da if m not in erwartet]
    if fehlend or ueberzaehlig:
        raise LeseFehler(
            f"{wo}: {len(gefunden)} von {len(erwartet)} Zeilen gelesen"
            + (f", es fehlen {fehlend}" if fehlend else "")
            + (f", zusaetzlich gelesen {ueberzaehlig}" if ueberzaehlig else "")
            + ". Entweder hat sich die Vorlage geaendert oder das Layout - "
            "beides heisst, dass hier nichts geschrieben werden darf"
        )


def stand_der_quelle(pfad: Path) -> tuple[str, str]:
    """Erstellungsdatum und SHA-256 der Vorlage - statt eines Laufdatums.

    Das Datum wird aus den PDF-Bytes gelesen und nicht ueber ``pdfinfo``:
    Dessen Ausgabe haengt an der Zeitzone des Rechners, und damit haette der
    Reproduktionswaechter zwei Fassungen je Standort.
    """
    rohdaten = pfad.read_bytes()
    treffer = re.search(rb"/CreationDate\s*\(D:(\d{14})", rohdaten)
    if treffer is None:
        raise LeseFehler(
            f"{pfad.name} nennt kein Erstellungsdatum - ohne es haette das "
            "erzeugte Dokument keinen Stand, und ein Laufdatum darf es nicht "
            "tragen"
        )
    ziffern = treffer.group(1).decode()
    datum = f"{ziffern[6:8]}.{ziffern[4:6]}.{ziffern[0:4]}"
    return datum, hashlib.sha256(rohdaten).hexdigest()


# --------------------------------------------------------------------------
# Das Dokument setzen
# --------------------------------------------------------------------------


def zitat(marke: str, text: str) -> list[str]:
    """Ein Zitat als Blockzitat, auf feste Breite umgebrochen.

    Dieselbe Form wie in ``notebooks/36_hypothesen.ipynb`` - ``> **F1:** ...``
    -, damit ein Leser beide nebeneinander lesen kann und der Waechter beide
    mit demselben Leser einliest.
    """
    # break_on_hyphens=False, sonst bricht textwrap am Trennstrich um:
    # "Identifikator-" am Zeilenende und "Menge" in der naechsten. Beim
    # Wiedereinlesen steht dann "Identifikator- Menge" da, und der Vergleich
    # gegen die Vorlage scheitert an einem Leerzeichen, das das Setzen
    # eingefuehrt hat. Der Selbsttest in ``baue`` hat genau das gefangen.
    gebrochen = textwrap.wrap(f"**{marke}:** {text}", width=BREITE - 2,
                              break_on_hyphens=False, break_long_words=False)
    return [f"> {z}" for z in gebrochen]


def kopf(datum: str, pruefsumme: str) -> list[str]:
    return [
        "# Die abgegebenen Forschungsfragen und Hypothesen",
        "",
        "**Erzeugt, nicht geschrieben.** Der Wortlaut hier ist aus der "
        "eingereichten Fassung gezogen —",
        f"[`{WERKZEUG}`](../{WERKZEUG}) liest Kapitel 3 und Kapitel 11 des "
        "abgegebenen PDF",
        f"(`{QUELLE.name}`, erstellt am {datum}).",
        "",
        "```bash",
        "python tools/build_forschungsfragen.py",
        "```",
        "",
        "**Der Wortlaut ist Beleg, nicht Entwurf.** Diese sechs Fragen und "
        "sechs Hypothesen wurden",
        "eingereicht und bewertet; sie werden hier nicht umformuliert, "
        "gekürzt oder verbessert.",
        "Wer eine Formulierung ändern will, ändert sie in einer neuen "
        "Abgabe — nicht hier.",
        "",
        "**Warum diese Datei im Repository liegt und das PDF nicht.** Das "
        "abgegebene PDF bleibt",
        "ungetrackt (`.gitignore`, Entscheid vom 5.10.2026). Damit ist die "
        "Lage dieselbe wie bei",
        "[`intern/platzbedarf.md`](intern/platzbedarf.md): Der Generator "
        "läuft dort, wo die Quelle",
        "liegt, das erzeugte Dokument ist die versionierte Fassung, und der "
        "Reproduktionswächter",
        "in `tests/test_forschungsfragen.py` überspringt sauber, wenn die "
        "Quelle fehlt. Was **immer**",
        "läuft, sind die Vergleiche gegen dieses Dokument: Notebook 36 und "
        "Kapitel 3 von",
        "[`ln2_konzept.md`](ln2_konzept.md) müssen es wörtlich zitieren.",
        "",
        "**Stand der Quelle.** Erstellt am " + datum + ", SHA-256 "
        f"`{pruefsumme}`.",
        "Ein Erzeugungsdatum steht hier bewusst nicht: Es hiesse, dass ein "
        "zweiter Lauf eine andere",
        "Datei liefert, und der Wächter darauf könnte nie grün sein.",
        "",
    ]


def frageteil(frage: str, gelesen: list[Reihe]) -> list[str]:
    zeilen = [
        "## 1 Die übergeordnete Forschungsfrage",
        "",
        *zitat("Übergeordnete Frage", frage),
        "",
        "## 2 Die sechs Teilfragen und ihre Hypothesen",
        "",
        "Je Frage eine Hypothese, beide im Wortlaut der Abgabe. Die Nummern "
        "`F1`–`F6` und `H1`–`H6`",
        "sind die der Abgabe und gelten im ganzen Repository.",
        "",
    ]
    for reihe in gelesen:
        nummer = reihe.marke[1:]
        zeilen += [
            f"### {reihe.marke}",
            "",
            *zitat(reihe.marke, reihe.links),
            ">",
            *zitat(f"H{nummer}", reihe.rechts),
            "",
        ]
    return zeilen


def grenzteil(grenze: str) -> list[str]:
    return [
        "## 3 Die Grenze des Nachweises",
        "",
        "Sie steht in Kapitel 3 direkt unter der Tabelle und gehört zu F1:",
        "",
        *zitat("Grenze", grenze),
        "",
    ]


def befundteil(gelesen: list[Reihe]) -> list[str]:
    zeilen = [
        "## 4 Die Beantwortung aus Kapitel 11",
        "",
        "Was die Abgabe als Ergebnis je Hypothese ausweist. Der Rechenweg "
        "dazu steht in",
        "[`../notebooks/36_hypothesen.ipynb`](../notebooks/36_hypothesen.ipynb); "
        "dieses Dokument",
        "hält fest, was **abgegeben** wurde, nicht was heute gemessen wird.",
        "",
        "| | Hypothese | Ergebnis |",
        "| --- | --- | --- |",
    ]
    for reihe in gelesen:
        zeilen.append(f"| **{reihe.marke}** | {reihe.links} | {reihe.rechts} |")
    return zeilen + [""]


def schluss() -> list[str]:
    return [
        "## 5 Nachziehen",
        "",
        "```bash",
        "python tools/build_forschungsfragen.py",
        "python -m pytest tests/test_forschungsfragen.py "
        "tests/test_notebook_hypothesen.py",
        "```",
        "",
        "Die Wächter halten drei Stellen zusammen: dieses Dokument, "
        "Kapitel 3 von",
        "[`ln2_konzept.md`](ln2_konzept.md) und die Zitate in Notebook 36. "
        "Weicht eine ab, nennt",
        "der Wächter die Hypothese und beide Fassungen — genau die Prüfung, "
        "die bis zum",
        "5.10.2026 fehlte und deshalb drei Fassungen nebeneinander stehen "
        "liess.",
    ]


def baue(pdf: Path = QUELLE) -> str:
    zeilen = text_aus_pdf(pdf)
    datum, pruefsumme = stand_der_quelle(pdf)
    gelesen = paare(zeilen)
    teile = (kopf(datum, pruefsumme)
             + frageteil(uebergeordnete_frage(zeilen), gelesen)
             + grenzteil(absatz(zeilen, "Die Grenze des Nachweises"))
             + befundteil(befunde(zeilen))
             + schluss())
    text = "\n".join(teile).rstrip("\n") + "\n"
    pruefe_satz(gelesen, text)
    return text


def pruefe_satz(gelesen: list[Reihe], text: str) -> None:
    """Steht im Dokument, was gelesen wurde - nach dem Umbruch noch?

    Das Setzen darf den Wortlaut nicht anfassen. Der erste Entwurf tat es
    trotzdem: ``textwrap`` brach "Identifikator-Menge" am Trennstrich um, und
    wieder eingelesen stand dort "Identifikator- Menge". Geprueft wird
    deshalb, was ein Leser aus dem fertigen Dokument holt.
    """
    wieder = zitate_aus(text)
    soll = {r.marke: ohne_auszeichnung(r.links) for r in gelesen}
    soll |= {f"H{r.marke[1:]}": ohne_auszeichnung(r.rechts) for r in gelesen}
    abweichend = {m: (s, wieder.get(m)) for m, s in soll.items()
                  if wieder.get(m) != s}
    if abweichend:
        raise LeseFehler(
            "das Setzen hat den Wortlaut verändert:\n  " + "\n  ".join(
                f"{m}\n    Vorlage:  {s}\n    Dokument: {w}"
                for m, (s, w) in sorted(abweichend.items())))


# --------------------------------------------------------------------------
# Wieder einlesen - der Leser, den die Waechter teilen
# --------------------------------------------------------------------------

#: Ein Zitat im Blockzitat: ``> **H1:** ...``. Dieselbe Form in diesem
#: Dokument und in Notebook 36.
ZITAT = re.compile(r"^>\s*\*\*([FH]\d+):\*\*\s*(.*)$")
#: Eine Zeile einer Markdown-Tabelle, deren erste Zelle eine Marke ist.
TABELLE = re.compile(r"^\|\s*\**([FH]\d+)\**\s*\|(.*)\|\s*$")


def ohne_auszeichnung(text: str) -> str:
    """Fettung und Umbrueche weg - verglichen wird der Wortlaut.

    Dass ein Dokument ein Wort hervorhebt oder eine Zeile anders umbricht,
    ist keine Abweichung. Dass es ein Wort austauscht, ist eine.
    """
    text = text.replace("**", "").replace("`", "")
    return re.sub(r"\s+", " ", text).strip()


def zitate_aus(text: str) -> dict[str, str]:
    """Je Marke ihr Blockzitat - ``> **H1:** ...``, auch ueber mehrere Zeilen.

    Diese Form steht in diesem Dokument und in Notebook 36. Fuer die Tabelle
    in Kapitel 3 des Konzepts gibt es ``tabellenzitate_aus``; getrennt, weil
    ein Leser fuer beide Formen in derselben Datei stillschweigend
    aneinanderhaengt, was er findet - das abgegebene Zitat und das Kurzwort
    aus der Beantwortung standen so als ein Satz da.
    """
    gefunden: dict[str, list[str]] = {}
    offen: str | None = None
    for zeile in text.splitlines():
        if (treffer := ZITAT.match(zeile)) is not None:
            offen = treffer.group(1)
            gefunden.setdefault(offen, []).append(treffer.group(2))
            continue
        if offen is not None:
            if zeile.startswith(">"):
                if (rest := zeile[1:].strip()):
                    gefunden[offen].append(rest)
                continue
            offen = None
    return {marke: ohne_auszeichnung(" ".join(stuecke))
            for marke, stuecke in gefunden.items()}


def tabellenzitate_aus(text: str) -> dict[str, str]:
    """Je Marke die **erste** Zelle hinter ihr.

    Kapitel 3 des Konzepts fuehrt die Fragen und die Hypothesen als Tabelle.
    Was hinter der ersten Zelle steht - Verfahren, Stand, Ergebnis -, ist
    Bewertung und nicht Zitat; verglichen wird nur die erste.
    """
    gefunden: dict[str, str] = {}
    for zeile in text.splitlines():
        if (treffer := TABELLE.match(zeile)) is not None:
            zellen = treffer.group(2).split("|")
            gefunden[treffer.group(1)] = ohne_auszeichnung(
                zellen[0] if zellen else "")
    return gefunden


def massgeblich(ziel: Path = ZIEL) -> dict[str, str]:
    """Der abgegebene Wortlaut, aus dem abgelegten Dokument."""
    if not ziel.is_file():
        raise LeseFehler(f"{ziel} fehlt - python {WERKZEUG}")
    gelesen = zitate_aus(ziel.read_text(encoding="utf-8"))
    return {marke: gelesen[marke] for marke in FRAGEN + HYPOTHESEN
            if marke in gelesen}


# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    zerleger = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # --ziel nach dem Muster von tools/build_platzbedarf.py, damit der
    # Waechter zweimal nach tmp bauen kann, ohne die abgelegte Datei
    # anzufassen.
    zerleger.add_argument("--pdf", type=Path, default=QUELLE)
    zerleger.add_argument("--ziel", type=Path, default=ZIEL)
    args = zerleger.parse_args(argv)

    try:
        text = baue(args.pdf)
    except LeseFehler as fehler:
        print(f"FEHLER: {fehler}", file=sys.stderr)
        return 1

    args.ziel.parent.mkdir(parents=True, exist_ok=True)
    args.ziel.write_text(text, encoding="utf-8")
    try:
        name = args.ziel.relative_to(PROJEKT)
    except ValueError:
        name = args.ziel
    gelesen = zitate_aus(text)
    print(f"{name} geschrieben ({len(FRAGEN)} Fragen, "
          f"{len([m for m in gelesen if m.startswith('H')])} Hypothesen, "
          f"{args.ziel.stat().st_size} Bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
