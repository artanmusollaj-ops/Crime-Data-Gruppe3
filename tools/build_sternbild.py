#!/usr/bin/env python3
"""Zeichnet das Sternschema aus ``gold_pipeline.TABELLEN`` und den Gold-Manifesten.

    python tools/build_sternbild.py            # schreibt beide Fassungen
    python tools/build_sternbild.py --pruefen  # vergleicht nur, Exit 1 bei Abweichung

**Warum erzeugt.** Bis zum 25.11.2026 war ``docs/bilder/stern.svg`` von Hand
gezeichnet. Es zeigte vier Dimensionen und 344'617 Taten - den Stand des
Jahrgangs 2024 vom September -, als Gold elf Tabellen und 1'895'123 Taten
hatte. Die Kopie in ``docs/sternschema-und-wuerfel.html`` zeigte einen dritten
Stand. Kein Waechter sah hin: Die Zahlen standen mit schmalen Leerzeichen da,
und ``tests/test_dokumentzahlen.py`` liest weder SVG noch diese Seite.

**Was erzeugt wird.** Zwei Fassungen desselben Bilds:

- ``docs/bilder/stern.svg``, eingebunden in ``sternschema-und-wuerfel.md``.
  Sie traegt ihre Farben selbst, mit einer Regel fuer den dunklen Modus.
- der Block zwischen ``<!-- stern -->`` und ``<!-- /stern -->`` in
  ``docs/sternschema-und-wuerfel.html``. Dort ohne eigenen ``<style>`` - er
  galte fuer jedes SVG der Seite -, die Farben kommen aus deren Variablen.

**Woher was kommt.** Welche Tabellen es gibt, aus ``gold_pipeline.TABELLEN``;
eine neue Tabelle ohne Platz in ``LAGE`` bricht den Lauf ab und nennt sie. Die
Zeilen aus den Manifesten unter ``data/gold/``. Von Hand gepflegt sind nur Lage,
Granularitaet, Beispielspalten und Schluessel - was sich nicht ableiten laesst.

``tests/test_sternbild.py`` haelt: jede Gold-Tabelle im Bild, beide Fassungen
gleich, und ein zweiter Lauf in einem eigenen Prozess liefert dieselben Bytes.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROJEKT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJEKT / "src" / "crime"))
from gold_pipeline import TABELLEN  # noqa: E402
from manifeste import tabellen  # noqa: E402

SVG_ZIEL = PROJEKT / "docs" / "bilder" / "stern.svg"
SEITE = PROJEKT / "docs" / "sternschema-und-wuerfel.html"
ANFANG, ENDE = "<!-- stern -->", "<!-- /stern -->"

BREITE, HOEHE = 880, 560
KASTEN_B, KASTEN_H = 214, 70
BRUECKE_H = 44
SPALTE = {"links": 16, "mitte": 333, "rechts": 650}
ZEILE = {"oben": 24, "mitte": 238, "unten": 452}

#: Wo jede Tabelle steht. Brücken liegen zwischen den beiden Dimensionen, die
#: sie verbinden, und haben keine Kante zur Faktentabelle.
LAGE: dict[str, tuple[str, str]] = {
    "fact_offense": ("mitte", "mitte"),
    "dim_date": ("mitte", "oben"),
    "dim_city_day": ("mitte", "unten"),
    "dim_tract": ("links", "mitte"),
    "dim_police_area": ("links", "oben"),
    "dim_community_area": ("links", "unten"),
    "dim_offense": ("rechts", "mitte"),
    "dim_tract_acs": ("rechts", "oben"),
    "dim_tract_geo": ("rechts", "unten"),
    "bridge_tract_police_area": ("links", "oben-mitte"),
    "bridge_tract_community_area": ("links", "mitte-unten"),
}

#: Was eine Zeile ist, und zwei Spalten, die zeigen, was die Tabelle traegt.
INHALT: dict[str, tuple[str, str]] = {
    "fact_offense": ("eine Tat", "Schlüssel + Messgrössen"),
    "dim_date": ("ein Kalendertag", "month · year_is_complete"),
    "dim_city_day": ("Stadt und Tag", "temp_max_c · sunset_utc"),
    "dim_tract": ("ein Tract", "city · city_area_share"),
    "dim_police_area": ("ein Polizeibezirk", "area_name · within_city"),
    "dim_community_area": ("ein Stadtteil", "area_name · within_city"),
    "dim_offense": ("ein NIBRS-Delikt", "nibrs_category · nibrs_group"),
    "dim_tract_acs": ("Tract und Vintage", "population · poverty_rate"),
    "dim_tract_geo": ("ein Tract der Städte", "boundary_wkt"),
    "bridge_tract_police_area": ("Tract × Bezirk", "tract_share"),
    "bridge_tract_community_area": ("Tract × Stadtteil", "tract_share"),
}

#: Die Kante zur Faktentabelle: deren Spalten, gegen den Schlüssel der Dimension.
SCHLUESSEL: dict[str, tuple[str, ...]] = {
    "dim_date": ("date",),
    "dim_city_day": ("(reporting_city, date)",),
    "dim_tract": ("tract_geoid",),
    "dim_offense": ("nibrs_code",),
    "dim_police_area": ("(reporting_city,", " police_area)"),
    "dim_community_area": ("(reporting_city,", " community_area)"),
    "dim_tract_acs": ("(tract_geoid,", " population_vintage)"),
    "dim_tract_geo": ("tract_geoid",),
}

MONO = "ui-monospace,SFMono-Regular,Menlo,monospace"
SANS = "ui-sans-serif,system-ui,-apple-system,sans-serif"


def zahl(n: int) -> str:
    """1895123 -> 1'895'123, wie in den Dokumenten."""
    return f"{n:,}".replace(",", "'")


def zeilen_aus_manifesten(data_root: Path = PROJEKT / "data") -> dict[str, int]:
    """Zeilen je Gold-Tabelle; ueber Vintages summiert, falls eine darunter liegt."""
    je: dict[str, int] = {}
    for tab in tabellen(data_root, ("gold",)):
        if tab.zeilen is None:
            raise SystemExit(f"gold/{tab.name}: Manifest ohne Zeilenzahl")
        je[tab.name] = je.get(tab.name, 0) + int(tab.zeilen)
    return je


def _rahmen(name: str) -> tuple[float, float, float, float]:
    spalte, zeile = LAGE[name]
    x = SPALTE[spalte]
    if name == "fact_offense":
        return x - 8, ZEILE["mitte"] - 10, KASTEN_B + 16, KASTEN_H + 20
    if "-" in zeile:
        oben, unten = zeile.split("-")
        mitte = (ZEILE[oben] + KASTEN_H + ZEILE[unten]) / 2
        return x, mitte - BRUECKE_H / 2, KASTEN_B, BRUECKE_H
    return x, ZEILE[zeile], KASTEN_B, KASTEN_H


def _kasten(name: str, n: int, *, seite: bool) -> list[str]:
    x, y, b, h = _rahmen(name)
    grain, spalten = INHALT[name]
    if name == "fact_offense":
        fuellung = ('fill="var(--signal)"' if seite else 'class="signal"')
        rand = 'stroke="currentColor" stroke-width="1.7"'
        return [
            f'  <g>\n    <rect x="{x:g}" y="{y:g}" width="{b:g}" height="{h:g}" rx="5" '
            f'{fuellung} fill-opacity="0.10" {rand}/>',
            _text(x + 13, y + 26, name, MONO, 13.5, gewicht=600),
            _text(x + 13, y + 46, f"{zahl(n)} Zeilen · {grain}", SANS, 11.5, deckung=0.78),
            _text(x + 13, y + 64, spalten, MONO, 10.5, deckung=0.55) + "\n  </g>",
        ]
    if name.startswith("bridge_"):
        return [
            f'  <g>\n    <rect x="{x:g}" y="{y:g}" width="{b:g}" height="{h:g}" rx="4" '
            'fill="none" stroke="currentColor" stroke-width="1" stroke-dasharray="4 3" '
            'stroke-opacity="0.7"/>',
            _text(x + 10, y + 18, name, MONO, 11, gewicht=600),
            _text(x + 10, y + 34, f"{zahl(n)} Zeilen · {grain}", SANS, 10.5,
                  deckung=0.7) + "\n  </g>",
        ]
    return [
        f'  <g>\n    <rect x="{x:g}" y="{y:g}" width="{b:g}" height="{h:g}" rx="5" '
        'fill="currentColor" fill-opacity="0.045" stroke="currentColor" stroke-width="1.1"/>',
        _text(x + 13, y + 24, name, MONO, 13.5, gewicht=600),
        _text(x + 13, y + 42, f"{zahl(n)} Zeilen · {grain}", SANS, 11.5, deckung=0.78),
        _text(x + 13, y + 59, spalten, MONO, 10.5, deckung=0.55) + "\n  </g>",
    ]


def _text(x: float, y: float, inhalt: str, schrift: str, groesse: float, *,
          gewicht: int | None = None, deckung: float | None = None,
          anker: str = "start") -> str:
    zusatz = f' font-weight="{gewicht}"' if gewicht else ""
    zusatz += f' fill-opacity="{deckung:g}"' if deckung is not None else ""
    anker_attr = f' text-anchor="{anker}"' if anker != "start" else ""
    return (f'    <text x="{x:g}" y="{y:g}"{anker_attr} font-family="{schrift}" '
            f'font-size="{groesse:g}"{zusatz} fill="currentColor">{inhalt}</text>')


def _kante(name: str) -> list[str]:
    """Pfeil von der Dimension zur Faktentabelle, mit dem Schluessel daran."""
    fx, fy, fb, fh = _rahmen("fact_offense")
    x, y, b, h = _rahmen(name)
    spalte, zeile = LAGE[name]
    if spalte == "mitte":
        x1, y1 = x + b / 2, (y + h if zeile == "oben" else y)
        x2, y2 = x1, (fy - 4 if zeile == "oben" else fy + fh + 4)
        lx, ly, anker = x1 + 8, (y1 + y2) / 2 + 4, "start"
    elif zeile == "mitte":
        x1 = x + b if spalte == "links" else x
        y1 = y + h / 2
        x2 = fx - 4 if spalte == "links" else fx + fb + 4
        y2 = y1
        lx, ly, anker = (x1 + x2) / 2, y1 - 8, "middle"
    else:
        x1 = x + b if spalte == "links" else x
        y1 = y + h / 2
        x2 = fx + 22 if spalte == "links" else fx + fb - 22
        y2 = fy - 4 if zeile == "oben" else fy + fh + 4
        # Rechts unten steht das Schild rechts der Linie: links davon laege es
        # auf dem Schild der Kante von dim_city_day.
        rechts_unten = spalte == "rechts" and zeile == "unten"
        lx = (x1 + x2) / 2 + (6 if spalte == "links" or rechts_unten else -6)
        ly = (y1 + y2) / 2 + (-14 if zeile == "oben" else 4)
        anker = "start" if spalte == "links" or rechts_unten else "end"
    linie = (f'  <line x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" stroke="currentColor" '
             'stroke-width="1.2" stroke-opacity="0.55" marker-end="url(#pfeil)"/>')
    schilder = [
        _text(lx, ly + 13 * i, teil, MONO, 10.5, deckung=0.75, anker=anker)
        .replace("    <text", "  <text", 1)
        for i, teil in enumerate(SCHLUESSEL[name])
    ]
    return [linie, *schilder]


def _bruecke_kanten(name: str) -> list[str]:
    """Gestrichelt zu beiden Dimensionen, die die Bruecke verbindet."""
    x, y, b, h = _rahmen(name)
    mitte = x + b / 2
    zeilen = LAGE[name][1].split("-")
    oben = ZEILE[zeilen[0]] + KASTEN_H
    unten = ZEILE[zeilen[1]]
    stil = ('stroke="currentColor" stroke-width="1" stroke-dasharray="4 3" '
            'stroke-opacity="0.6"')
    return [f'  <line x1="{mitte:g}" y1="{oben:g}" x2="{mitte:g}" y2="{y:g}" {stil}/>',
            f'  <line x1="{mitte:g}" y1="{y + h:g}" x2="{mitte:g}" y2="{unten:g}" {stil}/>']


def svg(zeilen: dict[str, int], *, seite: bool = False) -> str:
    """Das Bild; ``seite`` fuer die HTML-Seite, die die Farben selbst setzt."""
    fehlt = [t for t in TABELLEN if t not in LAGE or t not in INHALT]
    if fehlt:
        raise SystemExit(f"Gold-Tabelle ohne Platz im Sternbild: {', '.join(fehlt)} - "
                         "in tools/build_sternbild.py LAGE und INHALT ergaenzen")
    ohne = [t for t in TABELLEN if t not in zeilen]
    if ohne:
        raise SystemExit(f"Kein Manifest unter data/gold/ fuer: {', '.join(ohne)} - "
                         "erst Gold bauen")
    dims = [t for t in TABELLEN if t.startswith("dim_")]
    bruecken = [t for t in TABELLEN if t.startswith("bridge_")]
    beschreibung = (
        "Das Sternschema: die Faktentabelle fact_offense in der Mitte, darum "
        f"{len(dims)} Dimensionen ({', '.join(dims)}), je über einen Schlüssel "
        f"verbunden; dazu {len(bruecken)} Brücken ({', '.join(bruecken)}), die "
        "Tracts auf Polizeibezirke und Stadtteile verteilen.")
    teile = []
    kopf = 'xmlns="http://www.w3.org/2000/svg" ' if not seite else ""
    if not seite:
        teile.append('<?xml version="1.0" encoding="UTF-8"?>')
    teile.append(f'<svg {kopf}viewBox="0 0 {BREITE} {HOEHE}" role="img" width="100%" '
                 f'height="auto"\n     aria-label="{beschreibung}">')
    if not seite:
        teile.append("<style>\n  svg { color: #14304a; }\n  .signal { fill: #c2410c; }\n"
                     "  @media (prefers-color-scheme: dark) {\n    svg { color: #dde5ee; }\n"
                     "    .signal { fill: #dda05c; }\n  }\n</style>")
    teile.append('  <defs><marker id="pfeil" viewBox="0 0 10 10" refX="9" refY="5" '
                 'markerWidth="7" markerHeight="7" orient="auto-start-reverse">\n'
                 '    <path d="M 0 1 L 9 5 L 0 9 z" fill="currentColor"/></marker></defs>')
    for name in TABELLEN:
        teile.extend(_kasten(name, zeilen[name], seite=seite))
    for name in TABELLEN:
        if name in SCHLUESSEL:
            teile.extend(_kante(name))
        elif name.startswith("bridge_"):
            teile.extend(_bruecke_kanten(name))
    teile.append(_text(16, HOEHE - 8, "Jede Frage ist ein Filter, ein GROUP BY und ein JOIN. "
                       "Gestrichelt: Brücken, die die Einwohner der Tracts auf Bezirke und "
                       "Stadtteile verteilen.", SANS, 12, deckung=0.7)
                 .replace("    <text", "  <text", 1))
    teile.append("</svg>")
    return "\n".join(teile) + "\n"


def seite_mit(html: str, bild: str) -> str:
    """Die HTML-Seite mit dem Bild zwischen den Markern."""
    muster = re.compile(re.escape(ANFANG) + r".*?" + re.escape(ENDE), re.S)
    if len(muster.findall(html)) != 1:
        raise SystemExit(f"{SEITE.name}: braucht genau einen Block {ANFANG} … {ENDE}")
    return muster.sub(lambda _: f"{ANFANG}\n{bild}{ENDE}", html)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--pruefen", action="store_true",
                   help="nichts schreiben; Exit 1, wenn eine Fassung abweicht")
    args = p.parse_args(argv)
    zeilen = zeilen_aus_manifesten()
    if not zeilen:
        raise SystemExit("keine Gold-Manifeste unter data/gold/ - erst Gold bauen")
    neu = {SVG_ZIEL: svg(zeilen),
           SEITE: seite_mit(SEITE.read_text(encoding="utf-8"), svg(zeilen, seite=True))}
    abweichend = [p for p, inhalt in neu.items()
                  if not p.exists() or p.read_text(encoding="utf-8") != inhalt]
    if args.pruefen:
        for pfad in abweichend:
            print(f"veraltet: {pfad.relative_to(PROJEKT)}")
        return 1 if abweichend else 0
    for pfad, inhalt in neu.items():
        pfad.write_text(inhalt, encoding="utf-8", newline="\n")
        print(f"{pfad.relative_to(PROJEKT)} geschrieben")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
