"""Jede amtliche Unterlage muss sagen, woher sie kommt.

``docs/quellen/`` haelt die Dokumente, aus denen die Referenztabellen in
``config/`` reproduziert werden. Bis zum 19.9.2026 lagen dort sieben
Binaerdateien **ohne jeden Herkunftsnachweis** - kein Verweis, keine Fassung,
keine Pruefsumme. Wer ein Dokument neu holen wollte, musste raten.

``docs/quellen/README.md`` schliesst das. Diese Datei haelt es geschlossen:
Eine neue Unterlage ohne Eintrag laesst den Test fallen, und ein Eintrag, dessen
Datei sich geaendert hat, ebenso - denn dann belegt die Pruefsumme nichts mehr.

Warum die Pruefsumme mitgeprueft wird und nicht nur der Name: Ein Dokument
auszutauschen und den Eintrag stehen zu lassen ist der Fehler, den niemand
bemerkt. Die Referenztabellen wuerden weiterhin gegen ein Dokument gebaut, das
so nicht mehr dort liegt.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

QUELLEN = Path(__file__).resolve().parents[1] / "docs" / "quellen"
VERZEICHNIS = QUELLEN / "README.md"

BELEGSTUFEN = {"Prüfsumme", "Adresse"}


def dateien() -> list[Path]:
    """Alle Unterlagen - das Verzeichnis selbst ist keine."""
    return sorted(p for p in QUELLEN.iterdir()
                  if p.is_file() and p.name != "README.md" and not p.name.startswith("."))


def eintraege() -> dict[str, dict[str, str]]:
    """Je Ueberschrift ``### `datei` `` die Felder der darunter stehenden Tabelle."""
    text = VERZEICHNIS.read_text(encoding="utf-8")
    teile = re.split(r"^### `([^`]+)`\s*$", text, flags=re.MULTILINE)
    gefunden: dict[str, dict[str, str]] = {}
    for name, rumpf in zip(teile[1::2], teile[2::2]):
        felder: dict[str, str] = {}
        for zeile in rumpf.splitlines():
            treffer = re.match(r"\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|\s*$", zeile)
            if treffer and treffer.group(1) not in ("", "---"):
                felder[treffer.group(1)] = treffer.group(2)
        gefunden[name] = felder
    return gefunden


def test_das_verzeichnis_gibt_es():
    assert VERZEICHNIS.is_file(), f"{VERZEICHNIS} fehlt"


def test_jede_unterlage_hat_einen_eintrag():
    fehlend = sorted({p.name for p in dateien()} - set(eintraege()))
    assert not fehlend, (
        f"ohne Herkunftsnachweis in docs/quellen/README.md: {fehlend}. "
        "Eine Unterlage ohne Quellenverweis ist als Beleg wertlos."
    )


def test_kein_eintrag_zeigt_ins_leere():
    verwaist = sorted(set(eintraege()) - {p.name for p in dateien()})
    assert not verwaist, f"Eintrag ohne Datei: {verwaist}"


@pytest.mark.parametrize("pfad", dateien(), ids=lambda p: p.name)
def test_pruefsumme_und_groesse_stimmen(pfad: Path):
    felder = eintraege()[pfad.name]
    rohdaten = pfad.read_bytes()

    erwartet = felder.get("SHA-256", "").strip("`")
    assert erwartet == hashlib.sha256(rohdaten).hexdigest(), (
        f"{pfad.name}: SHA-256 im Verzeichnis passt nicht zur Datei. "
        "Entweder wurde das Dokument ausgetauscht oder der Eintrag ist alt."
    )

    genannt = int(felder.get("Grösse", "0").replace("'", "").split()[0])
    assert genannt == len(rohdaten), f"{pfad.name}: {genannt} Bytes genannt, {len(rohdaten)} gemessen"


@pytest.mark.parametrize("pfad", dateien(), ids=lambda p: p.name)
def test_jeder_eintrag_nennt_eine_adresse_und_seine_belegstufe(pfad: Path):
    felder = eintraege()[pfad.name]

    adressen = " ".join(felder.get(name, "") for name in ("Adresse", "Übersichtsseite", "Direktabruf"))
    assert "http" in adressen, f"{pfad.name}: keine Adresse - woher stammt das Dokument?"

    stufe = felder.get("belegt", "").replace("*", "").split(" (")[0].strip()
    assert stufe in BELEGSTUFEN, (
        f"{pfad.name}: 'belegt' ist {stufe!r}, erwartet eine von {sorted(BELEGSTUFEN)}"
    )
    if stufe == "Prüfsumme":
        assert "http" in felder.get("Adresse", ""), (
            f"{pfad.name}: als per Pruefsumme belegt gefuehrt, aber ohne abrufbare Adresse"
        )


def test_jeder_eintrag_sagt_wofuer_er_gebraucht_wird():
    """Ein Beleg ohne Zweck ist Ballast - dann gehoert er geloescht, nicht gepflegt."""
    ohne = sorted(name for name, felder in eintraege().items() if not felder.get("Wofür"))
    assert not ohne, f"ohne Angabe 'Wofür': {ohne}"
