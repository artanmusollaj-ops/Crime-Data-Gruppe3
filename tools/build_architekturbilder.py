#!/usr/bin/env python3
"""Erzeugt die beiden Architekturbilder aus dem Code, nicht aus der Erinnerung.

    python tools/build_architekturbilder.py

Schreibt ``docs/bilder/architektur-pakete.svg`` und
``docs/bilder/architektur-datenfluss.svg``.

**Warum erzeugt und nicht gezeichnet.** Konzept 5.3 fuehrt seit Wochen
*"kein Diagramm der Abhaengigkeitskanten"* als Luecke. Ein von Hand
gezeichnetes Bild waere sie los - und am Tag darauf falsch, sobald jemand
einen Import verschiebt. Dieses Werkzeug liest die Kanten aus dem AST und die
Stufen aus ``orchestration.run_all``; ein Test prueft, dass ein zweiter Lauf
dieselbe Datei liefert. Dieselbe Regel wie bei den Crosswalks und beim
Feldkatalog.

**Warum zwei Bilder.** Sie zeigen Verschiedenes, und das faellt sonst niemandem
auf:

*Pakete* zeigt, wer wessen **Code** benutzt. Dort fehlt eine Kante von
``silver_pipeline`` zu ``chicago_pipeline``, obwohl Silver Chicagos Daten
liest - denn es liest sie ueber die Ablage, nicht ueber einen Import. Genau
das ist der Entwurf: Die Schichten haengen an Dateien, nicht aneinander.

*Datenfluss* zeigt, was ``run_all`` tatsaechlich tut - dreizehn Stufen in vier
Gruppen, in der Reihenfolge, die gilt.
"""

from __future__ import annotations

import ast
import sys
from collections import defaultdict
from pathlib import Path

PROJEKT = Path(__file__).resolve().parents[1]
QUELLE = PROJEKT / "src" / "crime"
BILDER = PROJEKT / "docs" / "bilder"

sys.path.insert(0, str(QUELLE))

# Der Stil der bestehenden Bilder, damit sich diese hier einfuegen.
KOPF = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {breite} {hoehe}" role="img" width="100%" height="auto"
     aria-label="{beschreibung}">
<style>
  svg {{ color: #14304a; }}
  .signal {{ fill: #c2410c; }}
  .signal-strich {{ stroke: #c2410c; }}
  @media (prefers-color-scheme: dark) {{
    svg {{ color: #dde5ee; }}
    .signal {{ fill: #dda05c; }}
    .signal-strich {{ stroke: #dda05c; }}
  }}
</style>
  <defs><marker id="pfeil" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
    <path d="M 0 1 L 9 5 L 0 9 z" fill="currentColor"/></marker></defs>
"""
MONO = "ui-monospace,SFMono-Regular,Menlo,monospace"
SANS = "ui-sans-serif,system-ui,-apple-system,sans-serif"


def kasten(x: float, y: float, b: float, h: float, name: str, zusatz: str = "",
           betont: bool = False) -> str:
    """Ein Knoten im Stil der uebrigen Bilder des Projekts."""
    klasse = ' class="signal"' if betont else ""
    teile = [
        f'  <g>\n    <rect x="{x:.0f}" y="{y:.0f}" width="{b:.0f}" height="{h:.0f}" rx="5" '
        f'fill="currentColor" fill-opacity="0.045" stroke="currentColor" stroke-width="1.1"/>',
        f'    <text x="{x + b / 2:.0f}" y="{y + (25 if zusatz else h / 2 + 5):.0f}" '
        f'text-anchor="middle" font-family="{MONO}" font-size="13" font-weight="600"'
        f'{klasse} fill="currentColor">{name}</text>',
    ]
    if zusatz:
        teile.append(
            f'    <text x="{x + b / 2:.0f}" y="{y + 42:.0f}" text-anchor="middle" '
            f'font-family="{SANS}" font-size="11" fill="currentColor" '
            f'fill-opacity="0.72">{zusatz}</text>'
        )
    teile.append("  </g>")
    return "\n".join(teile)


def pfeil(x1: float, y1: float, x2: float, y2: float, gestrichelt: bool = False) -> str:
    strich = ' stroke-dasharray="4 3"' if gestrichelt else ""
    return (f'  <line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" '
            f'stroke="currentColor" stroke-opacity="0.45" stroke-width="1.1"'
            f'{strich} marker-end="url(#pfeil)"/>')


def beschriftung(x: float, y: float, text: str, gross: bool = False) -> str:
    return (f'  <text x="{x:.0f}" y="{y:.0f}" font-family="{SANS}" '
            f'font-size="{12 if gross else 11}" font-weight="{600 if gross else 400}" '
            f'fill="currentColor" fill-opacity="{0.8 if gross else 0.6}">{text}</text>')


# ---------------------------------------------------------------------------
# Bild 1: welches Paket benutzt wessen Code
# ---------------------------------------------------------------------------


def importgraph() -> dict[str, set[str]]:
    """Die Kanten zwischen den Paketen, aus dem AST gelesen."""
    pakete = {
        p.name for p in QUELLE.iterdir()
        if p.is_dir() and not p.name.startswith((".", "_")) and "egg-info" not in p.name
    }
    kanten: dict[str, set[str]] = {p: set() for p in pakete}
    for pfad in sorted(QUELLE.rglob("*.py")):
        paket = pfad.relative_to(QUELLE).parts[0]
        if paket not in pakete:
            continue
        for knoten in ast.walk(ast.parse(pfad.read_text(encoding="utf-8"))):
            ziele = []
            if isinstance(knoten, ast.ImportFrom) and knoten.module:
                ziele = [knoten.module.split(".")[0]]
            elif isinstance(knoten, ast.Import):
                ziele = [a.name.split(".")[0] for a in knoten.names]
            for ziel in ziele:
                if ziel in pakete and ziel != paket:
                    kanten[paket].add(ziel)
    return kanten


def tiefen(kanten: dict[str, set[str]]) -> dict[str, int]:
    """Laengster Weg zu einem Blatt - das ergibt die Zeile im Bild."""
    merker: dict[str, int] = {}

    def tiefe(paket: str, unterwegs: frozenset[str] = frozenset()) -> int:
        if paket in merker:
            return merker[paket]
        if paket in unterwegs:                       # Zyklus: der Test faengt ihn
            return 0
        ziele = kanten.get(paket, set())
        wert = 0 if not ziele else 1 + max(
            tiefe(z, unterwegs | {paket}) for z in sorted(ziele)
        )
        merker[paket] = wert
        return wert

    return {p: tiefe(p) for p in sorted(kanten)}


FUNDAMENT = ("manifeste", "storage")


def bild_pakete(kanten: dict[str, set[str]]) -> str:
    """Die Abhaengigkeiten - ohne die, die alles verdecken.

    Von 19 Kanten zeigen 16 auf ``manifeste`` und ``storage``. Alle zu
    zeichnen ergibt ein Knaeuel, in dem die drei uebrigen untergehen - und
    genau die tragen die Aussage: Gold ruht auf Silver, und Silver benutzt
    die Konstanten der Census- und Wetter-Ingestion.

    Die beiden Fundamente stehen deshalb als Band darunter, und die Bildunter-
    schrift sagt genau, wer sie benutzt. Das ist keine Vereinfachung, sondern
    dieselbe Aussage in lesbar.
    """
    fundament = [p for p in FUNDAMENT if p in kanten]
    oben = {p: {z for z in ziele if z not in FUNDAMENT}
            for p, ziele in kanten.items() if p not in FUNDAMENT}
    tiefe = tiefen(oben)

    zeilen: dict[int, list[str]] = defaultdict(list)
    for paket, t in sorted(tiefe.items()):
        zeilen[t].append(paket)
    # Wer von oben einen Pfeil bekommt, steht in der Mitte - sonst queren
    # Silvers zwei Kanten das ganze Bild.
    for t, pakete in zeilen.items():
        ziel_von_oben = {z for q in oben for z in oben[q] if z in pakete}
        innen = sorted(p for p in pakete if p in ziel_von_oben)
        aussen = sorted(p for p in pakete if p not in ziel_von_oben)
        zeilen[t] = aussen[::2] + innen + aussen[1::2][::-1]

    KASTEN_H, ZEILE_H, LUECKE, RAND = 34, 84, 22, 24
    breiten = {p: max(132, 8 * len(p) + 26) for p in list(tiefe) + fundament}
    zeilenbreite = {t: sum(breiten[p] for p in ps) + LUECKE * (len(ps) - 1)
                    for t, ps in zeilen.items()}
    band_breite = sum(breiten[p] for p in fundament) + LUECKE * (len(fundament) - 1)
    breite = max(max(zeilenbreite.values()), band_breite + 200) + 2 * RAND
    tiefste = max(zeilen)
    band_y = RAND + (tiefste + 1) * ZEILE_H + 14
    hoehe = band_y + KASTEN_H + 92

    lage: dict[str, tuple[float, float, float]] = {}
    for t, pakete in sorted(zeilen.items()):
        x = (breite - zeilenbreite[t]) / 2
        y = RAND + (tiefste - t) * ZEILE_H
        for paket in pakete:
            lage[paket] = (x, y, breiten[paket])
            x += breiten[paket] + LUECKE

    striche = []
    for quelle in sorted(oben):
        for ziel in sorted(oben[quelle]):
            qx, qy, qb = lage[quelle]
            zx, zy, zb = lage[ziel]
            striche.append(pfeil(qx + qb / 2, qy + KASTEN_H, zx + zb / 2, zy - 4))

    kaesten = [kasten(x, y, b, KASTEN_H, paket)
               for paket, (x, y, b) in sorted(lage.items())]

    # Das Band: ein Rahmen um die beiden Fundamente.
    rx = (breite - band_breite) / 2
    band = [f'  <rect x="{rx - 22:.0f}" y="{band_y - 20:.0f}" '
            f'width="{band_breite + 44:.0f}" height="{KASTEN_H + 40:.0f}" rx="7" '
            f'fill="currentColor" fill-opacity="0.028" stroke="currentColor" '
            f'stroke-opacity="0.35" stroke-width="1" stroke-dasharray="5 4"/>',
            beschriftung(rx - 22, band_y - 6, "Fundament")]
    x = rx
    for paket in fundament:
        band.append(kasten(x, band_y, breiten[paket], KASTEN_H, paket, betont=True))
        x += breiten[paket] + LUECKE

    benutzt_storage = sorted(p for p, z in kanten.items() if "storage" in z)
    ohne_manifeste = sorted(p for p in kanten
                            if p not in FUNDAMENT and "manifeste" not in kanten[p])
    # Die Gesamtzahl wird gerechnet und nicht geschrieben: Sie stand bis zum
    # 20.9.2026 als "19" im Text, waehrend der Graph laengst 23 Kanten hatte.
    # Ein erzeugtes Bild, das eine feste Zahl mitfuehrt, ist kein erzeugtes Bild.
    gesamt = sum(len(z) for z in kanten.values())
    fuss = [
        beschriftung(RAND, hoehe - 32,
                     f"Pfeil bedeutet: benutzt den Code von. Nur {sum(len(z) for z in oben.values())} "
                     f"der {gesamt} Kanten sind gezeichnet."),
        beschriftung(RAND, hoehe - 14,
                     f"Die {len(fundament)} Fundamente benutzen alle übrigen Pakete "
                     f"({len(benutzt_storage)} × storage; manifeste "
                     # Solange jedes Paket manifeste benutzt, bleibt die Liste
                     # leer - dann darf da kein "ausser" stehen.
                     + (f"alle ausser {', '.join(ohne_manifeste)}"
                        if ohne_manifeste else "ausnahmslos alle")
                     + ") - ihre Pfeile sind weggelassen."),
    ]
    stufen = tiefen(kanten)
    oberste = max(stufen.values(), default=0)
    zuoberst = ", ".join(p for p, s in sorted(stufen.items()) if s == oberste)
    beschreibung = (
        f"Abhängigkeiten zwischen den {len(kanten)} Paketen unter src/crime, "
        f"{gesamt} Kanten. Zuoberst {zuoberst}, darunter silver_pipeline, das "
        "census_pipeline und weather_pipeline benutzt; daneben die übrigen "
        "Ingestion-Pakete. Unten als Band die beiden Fundamente manifeste und "
        "storage, die praktisch alle Pakete benutzen."
    )
    return (KOPF.format(breite=breite, hoehe=hoehe, beschreibung=beschreibung)
            + "\n".join(striche + kaesten + band + fuss) + "\n</svg>\n")


# ---------------------------------------------------------------------------
# Bild 2: was run_all tatsaechlich tut
# ---------------------------------------------------------------------------


def bild_datenfluss() -> str:
    from orchestration import run_all

    gruppen = {g: [] for g in run_all.GRUPPEN}
    for stufe in run_all.STUFEN:
        gruppen[stufe.gruppe].append(stufe.name)

    SCHICHT = {
        "ingestion": ("raw + bronze", "je Lauf ein Verzeichnis, unveränderlich"),
        "silver": ("silver", "gedeutet: Typen, Einheiten, Schlüssel"),
        "gold": ("gold", "Sternschema, eine Zeile je Tat"),
        "serving": ("serving", "lokal gebaut; als Release publiziert"),
    }
    KASTEN_H, ZEILE_H, RAND, BREITE = 52, 104, 24, 860
    hoehe = RAND + len(run_all.GRUPPEN) * ZEILE_H + 34

    teile = []
    for i, gruppe in enumerate(run_all.GRUPPEN):
        y = RAND + i * ZEILE_H
        schicht, erklaerung = SCHICHT[gruppe]
        stufen = ", ".join(gruppen[gruppe])
        anzahl = len(gruppen[gruppe])
        wort = "Stufe" if anzahl == 1 else "Stufen"
        teile.append(kasten(RAND + 250, y, BREITE - 2 * RAND - 250, KASTEN_H,
                            schicht, f"{anzahl} {wort}: {stufen}"))
        teile.append(beschriftung(RAND, y + 22, gruppe, gross=True))
        teile.append(beschriftung(RAND, y + 40, erklaerung))
        if i:
            mitte = RAND + 250 + (BREITE - 2 * RAND - 250) / 2
            teile.append(pfeil(mitte, y - ZEILE_H + KASTEN_H, mitte, y - 4))

    teile.append(beschriftung(
        RAND, hoehe - 12,
        "Aus orchestration.run_all.STUFEN erzeugt. Abbruch beim ersten Fehler; "
        "die Reihenfolge ist real, nicht dekorativ."
    ))
    beschreibung = (
        f"Der Datenfluss in vier Gruppen mit {len(run_all.STUFEN)} Stufen: "
        "Ingestion schreibt raw und bronze, silver deutet, gold baut das "
        "Sternschema, serving stellt bereit - und ein gruener Lauf wird zum Release."
    )
    return (KOPF.format(breite=BREITE, hoehe=hoehe, beschreibung=beschreibung)
            + "\n".join(teile) + "\n</svg>\n")


# ---------------------------------------------------------------------------
# Bild 3: der Systemkontext neben der inneren Architektur
# ---------------------------------------------------------------------------
# Die beiden anderen Bilder zeigen je eine Innenansicht. Dieses hier setzt sie
# in ihre Umgebung: Wer stoesst die Strecke an, woher kommen die Daten, wo
# liegen sie, und womit ist das gebaut. Vier Baender, weil das vier
# verschiedene Fragen sind, die man sonst in einem Knaeuel beantwortet.


def _quellname(modul: str) -> str:
    """``census_pipeline.download_tiger`` -> ``TIGER``."""
    letzt = modul.rsplit(".", 1)[-1]
    roh = letzt.replace("download_", "").replace("extract_", "")
    return {"acs": "ACS", "tiger": "TIGER", "noaa": "NOAA"}.get(roh, roh.capitalize())


def _gepinnt(paket: str) -> str:
    """Die Version aus requirements.lock - nicht die zufaellig installierte.

    Eine ``importlib.metadata``-Abfrage haette das Bild vom Rechner abhaengig
    gemacht, auf dem es entsteht. Die Sperrdatei liegt im Repository.
    """
    sperre = PROJEKT / "requirements.lock"
    if sperre.is_file():
        for zeile in sperre.read_text(encoding="utf-8").splitlines():
            if zeile.lower().startswith(paket + "=="):
                return zeile.split("==", 1)[1].strip()
    return ""


def bild_kontext() -> str:
    from orchestration import run_all
    from storage import config as speicherconfig

    quellen = sorted({_quellname(s.modul) for s in run_all.STUFEN if s.quelle})
    schichten = [("raw + bronze", "unveränderliche Läufe"),
                 ("silver", "gedeutet, zwei Städte eine Tabelle"),
                 ("gold", "Sternschema + drei Würfel in serving"),
                 ("serving", "Sichten, Vergleichstabellen, Release")]
    steuerung = sorted(p.stem for p in (QUELLE / "orchestration").glob("*.py")
                       if p.stem != "__init__")
    werkzeuge = sorted(p.stem for p in (PROJEKT / "tools").glob("*.py"))
    notebooks = len(list((PROJEKT / "notebooks").glob("*.ipynb")))
    duckdb_version = _gepinnt("duckdb")

    B, RAND = 980, 26
    SP_B, SP_H = 168, 44          # Spalten- und Kastenmasse der Mitte
    MITTE_X = 330
    band_y = RAND + 20
    quell_y = band_y + 74
    schicht_y = quell_y + 104
    ZEILE = 66
    speicher_y = schicht_y + len(schichten) * ZEILE + 34
    hoehe = speicher_y + 126

    teile: list[str] = []

    def rahmen(x, y, b, h, titel):
        teile.append(
            f'  <rect x="{x:.0f}" y="{y:.0f}" width="{b:.0f}" height="{h:.0f}" rx="7" '
            f'fill="currentColor" fill-opacity="0.028" stroke="currentColor" '
            f'stroke-opacity="0.35" stroke-width="1" stroke-dasharray="5 4"/>')
        teile.append(beschriftung(x, y - 6, titel, gross=True))

    # --- 1 Entwicklungswerkzeuge, als Band ueber allem ---------------------
    rahmen(RAND, band_y, B - 2 * RAND, 48, "Entwicklungswerkzeuge")
    teile.append(beschriftung(
        RAND + 14, band_y + 21,
        f"Python · DuckDB {duckdb_version} mit spatial · pytest · ruff · "
        f"{notebooks} Notebooks · {len(werkzeuge)} Generatoren unter tools/"))
    teile.append(beschriftung(
        RAND + 14, band_y + 38,
        "erzeugt mit: " + ", ".join(werkzeuge[:3]) + " …"))

    # --- 2 Systemkontext: die Quellen --------------------------------------
    beschriftung_y = quell_y - 6
    teile.append(beschriftung(RAND, beschriftung_y,
                              f"Systemkontext · {len(quellen)} öffentliche Quellen",
                              gross=True))
    q_b = (B - 2 * RAND - (len(quellen) - 1) * 12) / len(quellen)
    for i, name in enumerate(quellen):
        x = RAND + i * (q_b + 12)
        teile.append(kasten(x, quell_y, q_b, 38, name))
        teile.append(pfeil(x + q_b / 2, quell_y + 38,
                           MITTE_X + SP_B / 2, schicht_y - 4))

    # --- 3 Datenfluss: die Schichten, als Kette ----------------------------
    # An den linken Rand wie die uebrigen vier Bandtitel - in der Mitte lag er
    # im Pfeilbuendel der Quellen.
    teile.append(beschriftung(RAND, schicht_y - 28, "Datenfluss", gross=True))
    for i, (name, was) in enumerate(schichten):
        y = schicht_y + i * ZEILE
        teile.append(kasten(MITTE_X, y, SP_B, SP_H, name))
        teile.append(beschriftung(MITTE_X + SP_B + 14, y + 27, was))
        if i:
            teile.append(pfeil(MITTE_X + SP_B / 2, y - ZEILE + SP_H,
                               MITTE_X + SP_B / 2, y - 4))

    # --- 3b DuckDB, als Rahmen um die Schichten, die es traegt -------------
    # raw und bronze entstehen mit Python und pyarrow; erst ab silver rechnet
    # DuckDB, und in serving ist es zusaetzlich der Zugang fuer eigene Abfragen.
    duck_y = schicht_y + ZEILE - 10
    duck_h = (len(schichten) - 2) * ZEILE + SP_H + 20
    teile.append(
        f'  <rect x="{MITTE_X - 12:.0f}" y="{duck_y:.0f}" '
        f'width="{B - RAND - MITTE_X + 12:.0f}" height="{duck_h:.0f}" rx="7" '
        f'fill="none" stroke="currentColor" stroke-opacity="0.28" '
        f'stroke-width="1" stroke-dasharray="2 4"/>')
    teile.append(beschriftung(
        MITTE_X - 12, duck_y + duck_h + 16,
        f"DuckDB {duckdb_version} — Verarbeitungsengine (silver, gold) "
        "und SQL-Zugang (serving)"))

    # --- 4 Steuerung, links, mit gestrichelten Pfeilen ---------------------
    st_h = len(steuerung) * 17 + 26
    st_y = schicht_y + 18
    rahmen(RAND, st_y, MITTE_X - RAND - 54, st_h, "Steuerung")
    for i, modul in enumerate(steuerung):
        teile.append(beschriftung(RAND + 12, st_y + 20 + i * 17,
                                  f"orchestration.{modul}"))
    for i in range(len(schichten)):
        y = schicht_y + i * ZEILE + SP_H / 2
        teile.append(pfeil(MITTE_X - 50, min(max(y, st_y + 10), st_y + st_h - 10),
                           MITTE_X - 4, y, gestrichelt=True))

    # --- 5 Speicherorte, unten ---------------------------------------------
    rahmen(RAND, speicher_y, B - 2 * RAND, 72, "Speicherorte")
    orte = [("data/ lokal", "alle Schichten, je Lauf ein Verzeichnis"),
            ("SeaweedFS", "optional, S3-kompatibel"),
            ("releases/", "gold + serving, mit Prüfsummen")]
    o_b = (B - 2 * RAND - 28 - (len(orte) - 1) * 14) / len(orte)
    for i, (name, was) in enumerate(orte):
        x = RAND + 14 + i * (o_b + 14)
        teile.append(kasten(x, speicher_y + 12, o_b, 50, name, was,
                            betont=(name == "SeaweedFS")))
    teile.append(pfeil(MITTE_X + SP_B / 2,
                       schicht_y + (len(schichten) - 1) * ZEILE + SP_H,
                       MITTE_X + SP_B / 2, speicher_y - 4))

    teile.append(beschriftung(
        RAND, hoehe - 34,
        f"Modi der Ablage: {' | '.join(speicherconfig.BACKENDS)} — "
        "local ohne SeaweedFS, s3 ohne lokalen Bestand, hybrid beides."))
    teile.append(beschriftung(
        RAND, hoehe - 16,
        "Durchgezogen: Datenfluss. Gestrichelt: Steuerung — nicht alle "
        "Steuerungspfeile sind eingezeichnet. DuckDB ist Verarbeitungsengine "
        "und SQL-Zugang zugleich."))

    beschreibung = (
        f"Komponenten und Beziehungen der Plattform: {len(quellen)} öffentliche "
        f"Quellen speisen {len(schichten)} Schichten, gesteuert von "
        f"{len(steuerung)} Modulen unter orchestration; abgelegt lokal unter "
        f"data/, optional auf SeaweedFS, veröffentlicht als Release. "
        f"Entwickelt mit Python, DuckDB {duckdb_version}, pytest und ruff."
    )
    return (KOPF.format(breite=B, hoehe=hoehe, beschreibung=beschreibung)
            + "\n".join(teile) + "\n</svg>\n")


def main() -> int:
    BILDER.mkdir(parents=True, exist_ok=True)
    for name, inhalt in (
        ("architektur-pakete.svg", bild_pakete(importgraph())),
        ("architektur-datenfluss.svg", bild_datenfluss()),
        ("architektur-kontext.svg", bild_kontext()),
    ):
        (BILDER / name).write_text(inhalt, encoding="utf-8")
        print(f"docs/bilder/{name} geschrieben")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
