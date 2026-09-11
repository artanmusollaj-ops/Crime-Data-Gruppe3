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

Das Skript braucht ``pdftotext`` und liest ``docs/micr_manual_1110_2024.pdf``.
Es ist idempotent: ein zweiter Lauf aendert nichts.
"""

from __future__ import annotations

import csv
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAPPING = PROJECT_ROOT / "config" / "micr_nibrs_mapping.csv"
MANUAL = PROJECT_ROOT / "docs" / "micr_manual_1110_2024.pdf"

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

# Detroits Beschreibung widerspricht dem Handbuch. Nicht zuordnen.
UMSTRITTEN = {
    "3072": (
        "Detroit nennt es RETAIL FRAUD - THEFT, das Handbuch fuehrt 3072 als "
        "Retail Fraud Misrepresentation 2nd Degree unter File Class 30001. "
        "Theft waere 30002 mit den Arrest Charges 3073/3074/3078. Der "
        "Unterschied ist 26A False Pretenses gegen 23C Shoplifting. Detroit "
        "benutzt daneben auch 3002, die echte File Class fuer Retail Fraud "
        "Theft. Nur Detroit kann das aufloesen"
    ),
    "5421": (
        "Detroit nennt es ACCIDENT, HIT & RUN; das Handbuch fuehrt 5421 als "
        "Operating ORV Under the Influence of Controlled Substance unter File "
        "Class 54002. Hit & Run waere 54001, deren Arrest Charges 8011 bis "
        "8013 sind. Detroits Verwendung passt zu keiner der beiden Lesarten"
    ),
    "5422": (
        "wie 5421: Detroit nennt es ACCIDENT, HIT & RUN, das Handbuch "
        "Permitted Person Under the Influence of Controlled Substance to "
        "Operate, File Class 54002"
    ),
}

# Der NIBRS-Code, der aus der File Class folgt, ist beim FBI zurueckgezogen.
# Die Zuordnung bleibt richtig, der Hinweis gehoert trotzdem dazu.
ZURUECKGEZOGEN = {"90A", "90E", "90H", "90I"}


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
        return ziel.read_text(encoding="utf-8", errors="replace").split("\n")


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


def main() -> int:
    with MAPPING.open(encoding="utf-8") as datei:
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

    angeschlossen, offen_gelassen, unauffindbar = 0, 0, []
    for z in zeilen:
        if z["mapped"] == "true":
            continue
        code = z["micr_code"]
        if code in UMSTRITTEN:
            z["micr_code_type"] = "arrest_charge"
            z["note"] = UMSTRITTEN[code]
            offen_gelassen += 1
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
        if quelle["nibrs_code"] in ZURUECKGEZOGEN:
            hinweis += (
                f"; NIBRS {quelle['nibrs_code']} ist beim FBI zurueckgezogen"
            )
        z.update({
            "micr_code_type": "arrest_charge",
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

    with MAPPING.open("w", newline="", encoding="utf-8") as datei:
        schreiber = csv.DictWriter(datei, fieldnames=SPALTEN)
        schreiber.writeheader()
        schreiber.writerows({s: z.get(s, "") for s in SPALTEN} for z in zeilen)

    zugeordnet = sum(1 for z in zeilen if z["mapped"] == "true")
    print(f"\n{MAPPING.relative_to(PROJECT_ROOT)}: {len(zeilen)} Zeilen")
    print(f"  neu angeschlossen : {angeschlossen}")
    print(f"  bewusst offen     : {offen_gelassen}  ({', '.join(sorted(UMSTRITTEN))})")
    print(f"  zugeordnet gesamt : {zugeordnet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
