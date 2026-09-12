"""Liest die NIBRS-Deliktkategorien aus dem User Manual und schreibt sie als CSV.

Aufruf aus dem Projekt-Root:

    python tools/build_nibrs_categories.py

**Wozu.** ``config/nibrs_offense_codes_2025.csv`` fuehrt 81 Codes, aber keine
Gruppierung. Das Projekt hat bis hierher mit den ersten beiden Zeichen des Codes
gruppiert - ``13`` fuer Koerperverletzung, ``23`` fuer Diebstahl - und das
"Deliktfamilie" genannt. Das war eine Hilfskonstruktion, und sie ist an vier
Stellen nachweislich falsch:

* ``11`` und ``36`` sind **beide** die Kategorie *Sex Offenses*
* ``58``, ``61`` und ``62`` sind **alle drei** *Commerce Violations*
* ``10`` zerfaellt in **drei** Kategorien: Kidnapping/Abduction, Treason, Espionage
* ``90`` zerfaellt in **zehn** Group-B-Kategorien; einen Sammelnamen gibt es nicht

Das User Manual fuehrt die amtliche Gliederung: 28 Group-A-Kategorien mit 71
Delikten, dazu 10 Group-B-Kategorien. Dieses Skript liest sie heraus, statt sie
abzuschreiben - eine Abschrift von Hand waere genau die gepflegte Uebersetzung,
die das Projekt an anderer Stelle schon einmal entfernt hat.

**Wie.** Gelesen wird der Abschnitt zwischen "There are 28 Group A offense
categories" und der Fussnote zu den Bundesdelikten. Darin steht je Kategorie
eine Ueberschrift und darunter ihre Delikte. Uebernommen wird nur **Code und
Kategorie**; die Bezeichnung kommt weiterhin aus der Codeliste, weil sie dort
schon gegen zwei Quellen geprueft ist.

Zwei Eigenheiten der Vorlage:

1. Lange Deliktnamen brechen um. Die Folgezeile traegt keinen Code und wird
   deshalb von selbst uebersprungen.
2. ``11B`` und ``11C`` stehen ohne Bezeichnung in einer eigenen Zeile, weil
   daneben *Converts to 11A* vermerkt ist. Sie zaehlen trotzdem zur Kategorie,
   in deren Abschnitt sie stehen.
"""

from __future__ import annotations

import csv
import re
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HANDBUCH = PROJECT_ROOT / "docs" / "nibrs-user-manual-2025-0-062625.pdf"
CODELISTE = PROJECT_ROOT / "config" / "nibrs_offense_codes_2025.csv"
ZIEL = PROJECT_ROOT / "config" / "nibrs_offense_categories_2025.csv"

QUELLE = "nibrs_user_manual_2025_0"
# Was das Handbuch ueber sich selbst sagt. Stimmen die Zahlen nach dem Lesen
# nicht, hat sich die Vorlage geaendert und das Skript liest falsch - dann soll
# es scheitern und nicht eine halbe Tabelle schreiben.
ERWARTET_A_KATEGORIEN = 28
ERWARTET_A_DELIKTE = 71
ERWARTET_B_KATEGORIEN = 10

ANFANG = "There are 28 Group A offense categories"
GRUPPE_B = "There are 10 Group B offense categories"
# Die Fussnote steht zweimal - einmal unter Group A, einmal unter Group B.
# Gelesen wird bis zur zweiten, sonst fehlt die halbe Tabelle.
ENDE = "*Denotes offenses for federal and tribal LEA reporting only"

# Ein Code steht in einer eigenen Spalte: mindestens zwei Leerzeichen davor,
# danach entweder das Zeilenende oder die naechste Spalte.
CODE = re.compile(r"(?:^|\s{2,})([0-9]{2}[A-Z0-9])(?=\s|$)")
# Eine Ueberschrift steht auf Einrueckung 2 oder 3. Das ist kein Augenmass,
# sondern gemessen: Im ganzen Abschnitt stehen dort genau 38 Zeilen ohne Code -
# 28 Group-A- und 10 Group-B-Kategorien. Umgebrochene Deliktnamen ("Acts",
# "Servitude", "Violation of National Firearm Act of") stehen auf 5 oder 6 und
# fallen damit heraus, ohne dass sie einzeln benannt werden muessten.
UEBERSCHRIFT = re.compile(r"^ {2,3}([A-Z][A-Za-z/&,' \-]{3,})\s*$")

# Zeilen des Seitenkopfs, die wie eine Ueberschrift aussehen.
KEINE_UEBERSCHRIFT = {
    "Offense", "NIBRS", "Crime", "Against", "Based on", "Code", "Group A Offenses",
    "Group B Offenses", "Offense Code", "NIBRS Offense Code", "Converts",
}


class LeseFehler(RuntimeError):
    """Die Vorlage sieht anders aus als erwartet."""


def text_aus_pdf(pfad: Path) -> list[str]:
    if not pfad.exists():
        raise LeseFehler(f"Handbuch fehlt: {pfad}")
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
    # und die Einrueckung der Folgezeile verschieben.
    return fertig.stdout.decode("utf-8", "replace").split("\n")


def kategorien(zeilen: list[str]) -> list[dict[str, str]]:
    """Je Code eine Zeile mit seiner Kategorie und seiner Gruppe."""
    try:
        von = next(i for i, z in enumerate(zeilen) if z.startswith(ANFANG))
    except StopIteration as fehler:
        raise LeseFehler(
            "Der Abschnitt mit den Deliktkategorien wurde nicht gefunden"
        ) from fehler
    enden = [i for i, z in enumerate(zeilen) if ENDE in z and i > von]
    if len(enden) < 2:
        raise LeseFehler(
            f"Die Fussnote zu den Bundesdelikten steht {len(enden)} mal statt "
            "zweimal - der Group-B-Abschnitt fehlt oder die Vorlage hat sich "
            "geaendert"
        )
    bis = enden[1]

    gruppe = "A"
    kategorie: str | None = None
    gefunden: dict[str, tuple[str, str]] = {}

    for zeile in zeilen[von : bis + 1]:
        if zeile.startswith(GRUPPE_B):
            gruppe = "B"
            kategorie = None
            continue

        codes = CODE.findall(zeile)
        if codes:
            if kategorie is None:
                raise LeseFehler(f"Code ohne Kategorie: {zeile.strip()!r}")
            for code in codes:
                # Die Spalte "Based on NCIC Offense Code" enthaelt vierstellige
                # Zahlen; die Regex trifft sie nicht, aber ein Code darf auch
                # nicht zweimal in verschiedene Kategorien fallen.
                if code in gefunden and gefunden[code][0] != kategorie:
                    raise LeseFehler(
                        f"{code} steht in zwei Kategorien: "
                        f"{gefunden[code][0]} und {kategorie}"
                    )
                gefunden[code] = (kategorie, gruppe)
            continue

        treffer = UEBERSCHRIFT.match(zeile)
        if treffer:
            name = treffer.group(1).strip()
            if name not in KEINE_UEBERSCHRIFT and not name.startswith("Denotes"):
                kategorie = name

    return [
        {
            "nibrs_code": code,
            "nibrs_category": kategorie,
            "nibrs_group": gruppe,
            "source": QUELLE,
        }
        for code, (kategorie, gruppe) in sorted(gefunden.items())
    ]


def pruefe(zeilen: list[dict[str, str]]) -> None:
    """Gegen die Zahlen, die das Handbuch selbst nennt."""
    a = [z for z in zeilen if z["nibrs_group"] == "A"]
    b = [z for z in zeilen if z["nibrs_group"] == "B"]
    kat_a = {z["nibrs_category"] for z in a}
    kat_b = {z["nibrs_category"] for z in b}

    fehler = []
    if len(kat_a) != ERWARTET_A_KATEGORIEN:
        fehler.append(f"{len(kat_a)} Group-A-Kategorien statt {ERWARTET_A_KATEGORIEN}")
    if len(a) != ERWARTET_A_DELIKTE:
        fehler.append(f"{len(a)} Group-A-Delikte statt {ERWARTET_A_DELIKTE}")
    if len(kat_b) != ERWARTET_B_KATEGORIEN:
        fehler.append(f"{len(kat_b)} Group-B-Kategorien statt {ERWARTET_B_KATEGORIEN}")
    if fehler:
        raise LeseFehler(
            "Die Vorlage liest sich anders als das Handbuch sie beschreibt: "
            + "; ".join(fehler)
        )

    with CODELISTE.open(encoding="utf-8") as datei:
        amtlich = {z["nibrs_code"]: z for z in csv.DictReader(datei)}
    gelesen = {z["nibrs_code"] for z in zeilen}
    fehlend = sorted(set(amtlich) - gelesen)
    ueberzaehlig = sorted(gelesen - set(amtlich))
    if fehlend or ueberzaehlig:
        raise LeseFehler(
            f"Deckt sich nicht mit der Codeliste - fehlend: {fehlend}, "
            f"zusaetzlich: {ueberzaehlig}"
        )

    # Die Gruppe muss zu der passen, die schon in der Codeliste steht.
    uneinig = {
        z["nibrs_code"]: (z["nibrs_group"], amtlich[z["nibrs_code"]]["nibrs_group"])
        for z in zeilen
        if z["nibrs_group"] != amtlich[z["nibrs_code"]]["nibrs_group"]
    }
    if uneinig:
        raise LeseFehler(f"Gruppe widerspricht der Codeliste: {uneinig}")


def main() -> int:
    try:
        zeilen = kategorien(text_aus_pdf(HANDBUCH))
        pruefe(zeilen)
    except LeseFehler as fehler:
        print(f"FEHLER: {fehler}", file=sys.stderr)
        return 1

    with ZIEL.open("w", newline="", encoding="utf-8") as datei:
        schreiber = csv.DictWriter(
            datei, fieldnames=["nibrs_code", "nibrs_category", "nibrs_group", "source"]
        )
        schreiber.writeheader()
        schreiber.writerows(zeilen)

    kat = {}
    for z in zeilen:
        kat.setdefault((z["nibrs_group"], z["nibrs_category"]), []).append(z["nibrs_code"])
    print(f"{ZIEL.relative_to(PROJECT_ROOT)}: {len(zeilen)} Codes")
    for (gruppe, name), codes in sorted(kat.items()):
        print(f"  [{gruppe}] {name:<42} {', '.join(sorted(codes))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
