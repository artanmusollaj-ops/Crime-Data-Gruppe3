"""Schliesst Detroits Arrest Charge Codes an config/micr_nibrs_mapping.csv an.

Das Problem
-----------
MICR fuehrt **zwei** Codelisten, nicht eine. Die *Offense File Class* sagt, was
passiert ist (``09001`` Murder/Non-Negligent Manslaughter); der *Arrest Charge*
(Data Element #46 des Handbuchs) sagt, womit jemand beschuldigt wird (``0901``
Family, Gun). Das Handbuch gliedert die 833 Arrest Charges unter die 104 File
Classes.

Detroit veroeffentlicht beide in **einem** vierstelligen Feld,
``state_offense_code``. File Classes sind fuenfstellig und werden auf vier
gekuerzt (``13001`` wird ``1301``), Arrest Charges sind von Haus aus
vierstellig. Beide landen im selben Namensraum, und 54 Kuerzel sind dadurch
doppeldeutig: ``0901`` ist sowohl die gekuerzte File Class ``09001`` als auch
der Arrest Charge "Family, Gun".

Fuer diese 54 ist geprueft, welche Lesart Detroits eigene
``offense_description`` stuetzt: 34 eindeutig File Class, **keine einzige**
Arrest Charge, der Rest unentscheidbar, weil beide Bezeichnungen gleich lauten.
Die Tabelle liest sie deshalb als File Class, und das bleibt so.

Offen waren die 23 Codes, die **nur** Arrest Charge sind und keine
File-Class-Bedeutung haben - 4'467 Faelle oder 5,04 % des Jahrgangs 2024. Fuer
sie findet die Tabelle nichts, weil sie eine File-Class-Tabelle ist.

Der Weg
-------
Arrest Charge -> zugehoerige File Class -> NIBRS. Die erste Stufe steht im
Handbuch, die zweite in der Tabelle selbst. Geraten wird nichts.

Was **nicht** angeschlossen wird
--------------------------------
Drei Codes, bei denen Detroits eigene Beschreibung dem Handbuch widerspricht.
Sie bleiben offen und tragen den Widerspruch als Notiz - lieber eine benannte
Luecke als eine erfundene Zuordnung. Beim Chicago-Crosswalk hat uns genau
diese Versuchung 106 falsche Zeilen gekostet.

Aufruf aus dem Projekt-Root::

    python tools/extend_micr_arrest_charges.py

Das Skript braucht ``pdftotext`` und liest ``docs/quellen/micr_manual_1110_2024.pdf``.
Es ist idempotent: ein zweiter Lauf aendert nichts.
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAPPING = PROJECT_ROOT / "config" / "micr_nibrs_mapping.csv"
MANUAL = PROJECT_ROOT / "docs" / "quellen" / "micr_manual_1110_2024.pdf"

# Herkunft der neuen Zeilen. Sie unterscheidet sich bewusst von
# micr_manual_1110_2024: jene Zeilen stehen direkt in der File-Class-Liste,
# diese sind ueber die Arrest-Charge-Liste hergeleitet.
HERKUNFT = "micr_arrest_charge_1110_2024"

SPALTEN = [
    "micr_code",
    "micr_code_type",
    "micr_file_class",
    "micr_description",
    "nibrs_group",
    "nibrs_code",
    "nibrs_description",
    "hierarchy",
    "match",
    "mapped",
    "seen_in_detroit_2024",
    "note",
]

# Drei Codes, bei denen Detroits Verwendung dem Handbuch widerspricht.
#
# Sie standen lange unzugeordnet, mit der Notiz "nur Detroit kann das
# aufloesen". Detroit loest es - in zwei Feldern, die wir bis dahin nicht
# gelesen hatten. Zu jeder dieser Zeilen liefert die Quelle selbst
#
#   arrest_charge       die fuenfstellige MICR File Class
#   charge_description  deren Bezeichnung im Klartext
#
# und beide sind ueber alle betroffenen Zeilen eindeutig. Die genannte File
# Class traegt im Handbuch genau den Namen, den Detroit in charge_description
# schreibt. Damit sagen zwei unabhaengige Spalten dasselbe, und der Weg zum
# NIBRS-Code ist derselbe wie bei jeder anderen Arrest Charge: ueber die File
# Class.
#
# Die Herkunft heisst deshalb nicht wie beim Handbuch. Beleg ist hier die
# Quelle, nicht das Dokument - nachgerechnet in
# notebooks/11_detroit_source.ipynb, Abschnitt 7.1.
HERKUNFT_DETROIT = "detroit_charge_file_class"

DETROIT_ENTSCHEIDET = {
    "3072": (
        "30002",
        "Das Handbuch fuehrt 3072 als Retail Fraud Misrepresentation 2nd "
        "Degree unter File Class 30001; das waere 26A False Pretenses. Detroit "
        "liefert zu allen 1447 Zeilen arrest_charge 30002 und "
        "charge_description 'RETAIL FRAUD - THEFT' - den Namen, den 30002 im "
        "Handbuch traegt. Detroit benutzt daneben 3002, dieselbe File Class",
    ),
    "5421": (
        "54001",
        "Das Handbuch fuehrt 5421 als Operating ORV Under the Influence unter "
        "File Class 54002. Detroit liefert zu allen 100 Zeilen arrest_charge "
        "54001 und charge_description 'ACCIDENT, HIT & RUN' - den Namen, den "
        "54001 im Handbuch traegt",
    ),
    "5422": (
        "54001",
        "Das Handbuch fuehrt 5422 als Permitted Person Under the Influence to "
        "Operate unter File Class 54002. Detroit liefert zu allen 100 Zeilen "
        "arrest_charge 54001 und charge_description 'ACCIDENT, HIT & RUN' - "
        "den Namen, den 54001 im Handbuch traegt; gleiche Lage wie bei 5421",
    ),
}

# Der NIBRS-Code, der aus der File Class folgt, ist beim FBI zurueckgezogen.
# Die Zuordnung bleibt richtig, der Hinweis gehoert trotzdem dazu.
ZURUECKGEZOGEN = {"90A", "90E", "90H", "90I"}

# Die Bezeichnungen der noch nicht zugeordneten Zeilen stammten aus dem Feld
# ``offense_description`` der Detroit-Daten. Das ist die Einstufung des
# *Vorfalls*, nicht der Anklage, und sie schwankt innerhalb desselben Codes.
# Bei den meisten Codes traf sie trotzdem - Detroit schreibt dort den Namen der
# File Class. Bei einem nicht.
#
# Gefunden hat das Artan mit der Frage, wie man von "Diebstahl" auf ein anderes
# Delikt kommt. Die Zuordnung war richtig; die Bezeichnung war es nicht.
BEZEICHNUNG_KORRIGIERT = {
    "2501": (
        "Forgery of Checks",
        "In den Detroit-Daten stand 'LARCENY - OTHER'. Das ist weder der Name "
        "der Anklage noch der ihrer File Class: Das Handbuch fuehrt 2501 als "
        "'Forgery of Checks' unter File Class 25000 Forgery/Counterfeiting, "
        "und Detroit selbst liefert zu allen 78 Zeilen arrest_charge 25000 und "
        "charge_description 'FORGERY / COUNTERFEITING'. Die Bezeichnung kam "
        "aus einer einzelnen abweichenden Zeile",
    ),
}


def manual_text() -> list[str]:
    """Der Text des MICR-Handbuchs, Zeile fuer Zeile."""
    if not MANUAL.exists():
        raise SystemExit(f"{MANUAL} fehlt")
    if shutil.which("pdftotext") is None:
        raise SystemExit(
            "pdftotext nicht gefunden. Es gehoert zu poppler-utils; "
            "auf macOS: brew install poppler"
        )
    with tempfile.TemporaryDirectory() as tmp:
        ziel = Path(tmp) / "micr.txt"
        subprocess.run(
            ["pdftotext", "-layout", str(MANUAL), str(ziel)],
            check=True, capture_output=True,
        )
        # \r entfernen, nicht splitlines - siehe build_nibrs_categories.
        return [z.rstrip("\r") for z in
                ziel.read_text(encoding="utf-8", errors="replace").split("\n")]


def arrest_charges(zeilen: list[str]) -> dict[str, tuple[str, str]]:
    """Arrest Charge Code -> (Bezeichnung, zugehoerige File Class).

    Die Liste ist nach File Class gegliedert: eine Ueberschrift ``NNNNN -
    Bezeichnung``, darunter Zeilen ``Bezeichnung <Leerraum> NNNN``. Fortsetzungen
    ueber Seitengrenzen wiederholen die Ueberschrift, was der Aufbau von selbst
    richtig behandelt.
    """
    beginn = next(
        (i for i, z in enumerate(zeilen)
         if z.strip() == "Arrest Charge Codes" and i > 5000),
        None,
    )
    if beginn is None:
        raise SystemExit("Abschnitt 'Arrest Charge Codes' im Handbuch nicht gefunden")

    file_class: str | None = None
    treffer: dict[str, tuple[str, str]] = {}
    for zeile in zeilen[beginn:]:
        kopf = re.match(r"\s*(\d{5})\s*[–-]\s*(.+?)\s*$", zeile)
        if kopf:
            file_class = kopf.group(1)
            continue
        eintrag = re.match(r"\s*(.+?)\s{2,}(\d{4})\s*$", zeile)
        if eintrag and file_class:
            treffer.setdefault(eintrag.group(2), (eintrag.group(1).strip(), file_class))
    return treffer


def arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Quelle und Ziel lassen sich trennen.

    Das Werkzeug erweitert eine bestehende Tabelle, statt sie neu zu bauen -
    es fuellt nur Zeilen, die noch nicht zugeordnet sind. Ein Lauf auf dem
    fertigen Stand tut deshalb nichts, und ohne diese beiden Schalter liesse
    sich nicht pruefen, ob er den Anschluss noch einmal herstellen koennte.
    ``tests/config/test_micr_nibrs_mapping.py`` gibt ihm dafuer eine Fassung
    mit geloeschter Zuordnung und vergleicht das Ergebnis mit der
    versionierten Datei.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mapping", type=Path, default=MAPPING,
        help=f"Eingabe (Vorgabe: {MAPPING.relative_to(PROJECT_ROOT)})",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Ausgabe; ohne Angabe wird die Eingabe ersetzt",
    )
    args = parser.parse_args(argv)
    args.output = args.output or args.mapping
    return args


def main(argv: list[str] | None = None) -> int:
    args = arguments(argv)
    with args.mapping.open(encoding="utf-8") as datei:
        zeilen = list(csv.DictReader(datei))

    # Die Spalte micr_code_type ist neu; bestehende Zeilen sind File Classes.
    for z in zeilen:
        z.setdefault("micr_code_type", "")
        if not z["micr_code_type"]:
            z["micr_code_type"] = "file_class" if z["micr_file_class"] else ""

    nach_file_class = {
        z["micr_file_class"]: z for z in zeilen
        if z["micr_file_class"] and z["micr_code_type"] == "file_class"
    }
    charges = arrest_charges(manual_text())
    print(f"Arrest Charges im Handbuch: {len(charges)}")

    angeschlossen, ueber_detroit, unauffindbar = 0, 0, []
    korrigiert: list[tuple[str, str, str]] = []
    for z in zeilen:
        if z["mapped"] == "true":
            continue
        code = z["micr_code"]
        if code in DETROIT_ENTSCHEIDET:
            file_class, begruendung = DETROIT_ENTSCHEIDET[code]
            quelle = nach_file_class.get(file_class)
            if quelle is None or quelle["mapped"] != "true":
                unauffindbar.append(code)
                continue
            z.update({
                "micr_code_type": "arrest_charge",
                "micr_file_class": file_class,
                "nibrs_group": quelle["nibrs_group"],
                "nibrs_code": quelle["nibrs_code"],
                "nibrs_description": quelle["nibrs_description"],
                "hierarchy": quelle["hierarchy"],
                "match": HERKUNFT_DETROIT,
                "mapped": "true",
                "note": begruendung,
            })
            ueber_detroit += 1
            print(f"  {code} -> {quelle['nibrs_code']:<4} ueber File Class {file_class}"
                  f"  (aus Detroits eigenen Feldern)")
            continue

        treffer = charges.get(code)
        if treffer is None:
            unauffindbar.append(code)
            continue
        bezeichnung, file_class = treffer
        quelle = nach_file_class.get(file_class)
        if quelle is None or quelle["mapped"] != "true":
            unauffindbar.append(code)
            continue

        hinweis = (
            f"Arrest Charge '{bezeichnung}' unter File Class {file_class} "
            f"({quelle['micr_description']}); NIBRS von dort uebernommen"
        )
        neue_bezeichnung = z["micr_description"]
        if code in BEZEICHNUNG_KORRIGIERT:
            neue_bezeichnung, grund = BEZEICHNUNG_KORRIGIERT[code]
            hinweis += f"; {grund}"
            korrigiert.append((code, z["micr_description"], neue_bezeichnung))
        if quelle["nibrs_code"] in ZURUECKGEZOGEN:
            hinweis += (
                f"; NIBRS {quelle['nibrs_code']} ist beim FBI zurueckgezogen"
            )
        z.update({
            "micr_code_type": "arrest_charge",
            "micr_description": neue_bezeichnung,
            "micr_file_class": file_class,
            "nibrs_group": quelle["nibrs_group"],
            "nibrs_code": quelle["nibrs_code"],
            "nibrs_description": quelle["nibrs_description"],
            "hierarchy": quelle["hierarchy"],
            "match": HERKUNFT,
            "mapped": "true",
            "note": hinweis,
        })
        angeschlossen += 1
        print(f"  {code} -> {quelle['nibrs_code']:<4} ueber File Class {file_class}"
              f"  ({bezeichnung[:44]})")

    if unauffindbar:
        print(f"\nFEHLER: weder Arrest Charge noch File Class: {unauffindbar}",
              file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as datei:
        schreiber = csv.DictWriter(datei, fieldnames=SPALTEN)
        schreiber.writeheader()
        schreiber.writerows({s: z.get(s, "") for s in SPALTEN} for z in zeilen)

    zugeordnet = sum(1 for z in zeilen if z["mapped"] == "true")
    print(f"\n{args.output}: {len(zeilen)} Zeilen")
    for code, alt, neu in korrigiert:
        print(f"  Bezeichnung korrigiert: {code} '{alt}' -> '{neu}'")
    print(f"  ueber das Handbuch: {angeschlossen}")
    print(f"  ueber Detroits Felder: {ueber_detroit}"
          f"  ({', '.join(sorted(DETROIT_ENTSCHEIDET))})")
    print(f"  zugeordnet gesamt : {zugeordnet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
