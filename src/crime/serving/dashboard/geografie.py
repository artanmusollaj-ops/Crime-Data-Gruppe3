"""Das Brett »Geografie« - nach Artans Entwurf ``dashboard_räumliche_verteilung.png``.

Eine Karte je Stadt, jeder Tract nach seiner Rate gefaerbt, dazu die Tracts
mit den hoechsten Raten.

**Faelle je 1'000 Einwohner, nicht Delikte je 100'000.** Die Karte folgt
``gold_pipeline.raten_je_tract`` und damit Kibana und den Dokumenten:
Fallebene vorn (Entscheid E5), gezaehlt nach meldender Stadt, nur Taten mit
``geo_status = 'inside_city'``, der Nenner aus dem Vintage der Tat.

**Geringe Basis heisst unter 500 Einwohner.** Die Einwohnerzahl je Tract
reicht von 35 bis 13'521; bei 35 macht eine einzige Tat 28,6 je 1'000
(``build_kibana._KLEINE_NENNER``). 2024 liegen 14 der 1'055 Tracts unter 500,
10 davon bei null. Sie werden schraffiert und stehen nicht in der Rangliste;
ohne Einwohner gibt es keine Rate.

**Die Klassen sind Quantile, fuer beide Staedte gemeinsam.** Feste Grenzen
wie im Entwurf passten zu einem Zeitraum und nicht zum naechsten; je Stadt
eigene Klassen machten dieselbe Farbe in Chicago und Detroit zu zwei Zahlen.

**Die Umrisse aus Gold, der Hintergrund von OpenStreetMap.** Die Tracts
kommen aus ``dim_tract_geo`` (TIGER); Strassen, Wasser und Ortsnamen sind die
Rasterkacheln von OpenStreetMap, im Browser geladen (``static/karte.js``).
Die Content-Security-Policy erlaubt dafuer nur diesen einen Host, und nur
fuer Bilder. Damit die Tracts auf den Kacheln liegen, projiziert ``pfade``
wie die Kacheln nach Web-Mercator.

**Nicht verortet** sind Taten ohne Koordinate, ohne Tract oder ausserhalb
der Stadtgrenze. Sie fehlen auf der Karte und werden je Stadt gezaehlt.

**Drei Ansichten** (seit 25.11.2026, Gold-Vertrag 11), ``ansicht``:

- ``tract``: die Rate je Census Tract, wie bisher.
- ``bezirk``: die Rate je Polizeibezirk. Gezaehlt werden dieselben Faelle wie
  je Tract (``inside_city``), gruppiert nach dem Bezirk ihrer Koordinate; der
  Nenner sind die Einwohner des Bezirks aus ``serving.dashboard.bezirke``.
  Ueber alle Bezirke einer Stadt ergibt das die Rate der Stadt.
- ``festnahme``: der Anteil der Faelle mit Festnahme je Bezirk. Chicago fuehrt
  ``arrest``, Detroit den Stand des Falls (``CLEARED BY ARREST``). Unter
  ``MINDESTFAELLE`` Faellen mit bekanntem Stand gilt ein Bezirk als geringe
  Basis. **Junge Faelle** sind noch nicht geklaert: Liegt das Ende des
  Zeitraums weniger als ``NACHFUEHRUNG_TAGE`` vor dem letzten Tag mit Daten,
  sagt das Brett es dazu. In Detroit fiel die Quote 2025 auf 5,7 % und 2026
  auf 4,6 %, nach 9 bis 12 % in den Jahren davor.
"""

from __future__ import annotations

import math
import re
from typing import Any

GERINGE_BASIS = 500
#: Unter so vielen Faellen mit bekanntem Stand ist eine Festnahmequote zu unruhig.
MINDESTFAELLE = 30
#: So lange nach der Tat wird der Stand eines Falls noch spuerbar nachgefuehrt.
NACHFUEHRUNG_TAGE = 365
ANSICHTEN = ("tract", "bezirk", "festnahme")
KLASSEN = 5
RANGLISTE = 5
#: Breite der Karte im SVG-Koordinatensystem; die Hoehe folgt der Stadt.
KARTENBREITE = 600.0
#: Aequatorumfang (WGS 84) in Kilometern.
_ERDUMFANG_KM = 40075.016686

#: Ein Ring: die innerste Klammer mit Koordinaten. So liest dieselbe Regel
#: ein POLYGON mit Loechern und ein MULTIPOLYGON - bis zum 25.11.2026 las
#: sie nur den ersten Ring, und Chicagos District 31 aus drei Teilen haette
#: nur einen gezeigt.
_RING = re.compile(r"\(([^()]*)\)")


def _welt(laenge: float, breite: float) -> tuple[float, float]:
    """Web-Mercator in Weltkoordinaten 0..1, Ursprung oben links.

    Dieselbe Rechnung wie die Kachelnummern der Kachelserver, nach
    OpenStreetMap Wiki, »Slippy map tilenames«
    (https://wiki.openstreetmap.org/wiki/Slippy_map_tilenames).
    """
    phi = math.radians(breite)
    return ((laenge + 180.0) / 360.0,
            (1.0 - math.log(math.tan(phi) + 1.0 / math.cos(phi)) / math.pi) / 2.0)


def pfade(zeilen) -> dict[str, dict[str, Any]]:
    """WKT-Polygone je Stadt als SVG-Pfade, in Web-Mercator.

    Eine SVG-Einheit ist ``1 / massstab`` Weltbreiten; mit ``x0`` und ``y0``
    rechnet der Browser daraus die Kacheln unter der Karte. ``zeilen``:
    (geoid, city, tract_name, boundary_wkt).
    """
    je_stadt: dict[str, list] = {}
    for geoid, stadt, name, wkt in zeilen:
        ringe = [[_welt(*map(float, p.split()[:2])) for p in ring.split(",")]
                 for ring in _RING.findall(wkt or "")]
        if not ringe or not stadt:
            continue
        je_stadt.setdefault(stadt, []).append((geoid, name, ringe))
    karten = {}
    for stadt, tracts in je_stadt.items():
        alle = [p for _, _, rs in tracts for ring in rs for p in ring]
        x0, x1 = min(p[0] for p in alle), max(p[0] for p in alle)
        y0, y1 = min(p[1] for p in alle), max(p[1] for p in alle)
        massstab = KARTENBREITE / (x1 - x0)
        # Ein Kilometer in Karteneinheiten, fuer die Massstabsleiste: Mercator
        # dehnt um 1/cos(Breite), gemessen in der Mitte der Stadt.
        mitte = math.degrees(math.atan(math.sinh(math.pi * (1 - (y0 + y1)))))
        km = massstab / (_ERDUMFANG_KM * math.cos(math.radians(mitte)))

        def xy(p):
            return f"{(p[0] - x0) * massstab:.1f} {(p[1] - y0) * massstab:.1f}"

        karten[stadt] = {
            "breite": KARTENBREITE, "hoehe": round((y1 - y0) * massstab, 1),
            "km": round(km, 2), "x0": x0, "y0": y0, "massstab": massstab,
            # Ein Teilpfad je Ring; Loecher stanzt fill-rule evenodd aus.
            "tracts": [{"geoid": g, "name": n,
                        "d": "".join("M" + "L".join(xy(p) for p in ring) + "Z" for ring in rs)}
                       for g, n, rs in tracts],
        }
    return karten


def geografie(bestand, a, ansicht: str = "tract") -> dict[str, Any]:
    from serving.dashboard import EingabeFehler
    if ansicht not in ANSICHTEN:
        raise EingabeFehler(f"Unbekannte Ansicht: {ansicht}")
    if ansicht != "tract":
        if not getattr(bestand, "karten_bezirke", None):
            raise EingabeFehler("Dieses Release fuehrt keine Polizeibezirke "
                                "(erst ab Gold-Vertrag 11)")
        return je_bezirk(bestand, a, festnahme=ansicht == "festnahme")
    return je_tract(bestand, a)


def je_tract(bestand, a) -> dict[str, Any]:
    cur = bestand._cursor()
    staedte = list(a.staedte)
    z = bestand.zeitraum(cur, a, staedte)
    kat = a.kat_sql
    p = {"staedte": staedte, **z.param, **a.kat_param}
    # Je Stadt die Jahre je Vintage im Zeitraum (serving.dashboard.zeitraum):
    # Die Rate eines Tracts ist Faelle je 1'000 Einwohner und Jahr, wie die der
    # Stadt im »Überblick«. Gezeigt werden die Einwohner des juengsten Vintage.
    gewichte = {s: z.gewichte(s, bestand.vintage_je_jahr) for s in staedte}
    vintages = sorted({v for g in gewichte.values() if g for v in g})
    vintage = vintages[-1] if vintages else None
    einwohner: dict[tuple[str, int], int] = {(g, v): n for g, v, n in cur.execute(
        "SELECT geoid, vintage, population FROM tract_einwohner WHERE vintage IN $v",
        {"v": vintages or [0]}).fetchall()}
    # Jeder Tract der Stadt, auch einer ohne Fall: Er ist eine Null, keine Luecke.
    zeilen = cur.execute(f"""
        SELECT g.city, g.geoid, g.tract_name,
               coalesce(t.faelle, 0), coalesce(t.delikte, 0)
        FROM tract_geo g
        LEFT JOIN (SELECT n.geoid, count(*) FILTER (f.fall) AS faelle, count(*) AS delikte
                   FROM fakt f JOIN tract_nr n ON n.nr = f.tract
                   WHERE f.stadt IN $staedte AND f.geo_status = 'inside_city'
                     AND f.tag BETWEEN $von AND $bis {kat.replace('kategorie', 'f.kategorie')}
                   GROUP BY 1) t ON t.geoid = g.geoid
        WHERE g.city IN $staedte ORDER BY g.city, g.geoid""", p).fetchall()
    tracts = {s: [] for s in staedte}
    for stadt, geoid, name, faelle, delikte in zeilen:
        g = gewichte.get(stadt)
        jahre = (sum(w * einwohner[(geoid, v)] for v, w in g.items())
                 if g and all(einwohner.get((geoid, v)) for v in g) else None)
        anzeige = einwohner.get((geoid, vintage)) if vintage else None
        rate = round(faelle * 1000.0 / jahre, 1) if jahre else None
        tracts[stadt].append({
            "geoid": geoid, "name": name, "einwohner": anzeige,
            "personenjahre": round(jahre, 1) if jahre else None,
            "faelle": int(faelle), "delikte": int(delikte), "rate": rate, "wert": rate,
            "geringe_basis": anzeige is None or anzeige < GERINGE_BASIS,
        })
    return _antwort(bestand, a, cur, p, "tract", vintage, vintages, z, tracts)


def _antwort(bestand, a, cur, p, ansicht, vintage, vintages, z, flaechen,
             extra=None) -> dict[str, Any]:
    """Was alle Ansichten teilen: Klassen, Rangliste, Verortung."""
    from serving.dashboard import STADTNAMEN

    staedte = list(a.staedte)
    kat = a.kat_sql
    tragfaehig = sorted(t["wert"] for ts in flaechen.values() for t in ts
                        if not t["geringe_basis"] and t["wert"] is not None)
    verortung = {s: {"inside_city": 0, "outside_city": 0, "no_tract": 0, "missing_coordinate": 0}
                 for s in staedte}
    for s, status, n in cur.execute(
            f"SELECT stadt, geo_status, count(*) FILTER (fall) FROM fakt WHERE stadt IN $staedte "
            f"AND tag BETWEEN $von AND $bis {kat} GROUP BY 1, 2", p).fetchall():
        verortung[s][status] = int(n)
    return {
        "auswahl": a.json | {"ansicht": ansicht},
        "ansicht": ansicht,
        "vintage": vintage,
        "vintages": vintages,
        "achse": z.json(),
        "klassen": klassengrenzen(tragfaehig),
        "geringe_basis": GERINGE_BASIS,
        "staedte": [{
            "stadt": s, "name": STADTNAMEN[s],
            "tracts": flaechen[s],
            "hoechste": sorted((t for t in flaechen[s] if not t["geringe_basis"] and t["wert"]),
                               key=lambda t: (-t["wert"], t["geoid"]))[:RANGLISTE],
            "geringe": sum(t["geringe_basis"] for t in flaechen[s]),
            "verortung": verortung[s],
            **((extra or {}).get(s) or {}),
        } for s in staedte],
        "stand": bestand.stand,
    }


def je_bezirk(bestand, a, *, festnahme: bool) -> dict[str, Any]:
    """Rate oder Festnahmequote je Polizeibezirk, Faelle wie je Tract."""
    from datetime import timedelta

    cur = bestand._cursor()
    staedte = list(a.staedte)
    z = bestand.zeitraum(cur, a, staedte)
    kat = a.kat_sql
    p = {"staedte": staedte, **z.param, **a.kat_param}
    gewichte = {s: z.gewichte(s, bestand.vintage_je_jahr) for s in staedte}
    vintages = sorted({v for g in gewichte.values() if g for v in g})
    vintage = vintages[-1] if vintages else None
    einwohner = {(s, n, v): e for s, n, v, e in cur.execute(
        "SELECT stadt, nr, vintage, population FROM bezirk_einwohner WHERE vintage IN $v",
        {"v": vintages or [0]}).fetchall()}
    # Jeder zaehlende Bezirk der Stadt, auch einer ohne Fall.
    zeilen = cur.execute(f"""
        SELECT b.stadt, b.nr, b.name,
               coalesce(t.faelle, 0), coalesce(t.delikte, 0),
               coalesce(t.fest, 0), coalesce(t.bekannt, 0)
        FROM bezirk b
        LEFT JOIN (SELECT f.stadt::VARCHAR AS stadt, f.bezirk,
                          count(*) FILTER (f.fall) AS faelle, count(*) AS delikte,
                          count(*) FILTER (f.fall AND f.festnahme) AS fest,
                          count(*) FILTER (f.fall AND f.festnahme IS NOT NULL) AS bekannt
                   FROM fakt f
                   WHERE f.stadt IN $staedte AND f.geo_status = 'inside_city'
                     AND f.tag BETWEEN $von AND $bis {kat.replace('kategorie', 'f.kategorie')}
                   GROUP BY 1, 2) t ON t.stadt = b.stadt AND t.bezirk = b.nr
        WHERE b.zaehlt AND b.stadt IN $staedte
        ORDER BY b.stadt, b.nr""", p).fetchall()
    flaechen: dict[str, list] = {s: [] for s in staedte}
    for stadt, nr, name, faelle, delikte, fest, bekannt in zeilen:
        g = gewichte.get(stadt)
        jahre = (sum(w * einwohner[(stadt, nr, v)] for v, w in g.items())
                 if g and all(einwohner.get((stadt, nr, v)) for v in g) else None)
        anzeige = einwohner.get((stadt, nr, vintage)) if vintage else None
        rate = round(faelle * 1000.0 / jahre, 1) if jahre else None
        anteil = round(fest * 100.0 / bekannt, 1) if bekannt else None
        flaechen[stadt].append({
            "geoid": str(nr), "name": name,
            "einwohner": round(anzeige) if anzeige else None,
            "personenjahre": round(jahre, 1) if jahre else None,
            "faelle": int(faelle), "delikte": int(delikte), "rate": rate,
            "festnahmen": int(fest), "bekannt": int(bekannt), "anteil": anteil,
            "wert": anteil if festnahme else rate,
            "geringe_basis": (bekannt < MINDESTFAELLE if festnahme
                              else anzeige is None or anzeige < GERINGE_BASIS),
        })
    extra = {}
    for s in staedte:
        fest = sum(t["festnahmen"] for t in flaechen[s])
        bekannt = sum(t["bekannt"] for t in flaechen[s])
        ende = z.fenster.get(s, (None, None))[1]
        extra[s] = {
            "festnahmen": fest, "bekannt": bekannt,
            "anteil": round(fest * 100.0 / bekannt, 1) if bekannt else None,
            # Ob der Zeitraum in die Zeit reicht, in der Faelle noch geklaert werden.
            "jung": bool(ende and a.tag_bis > ende - timedelta(days=NACHFUEHRUNG_TAGE)),
        }
    antwort = _antwort(bestand, a, cur, p, "festnahme" if festnahme else "bezirk",
                       vintage, vintages, z, flaechen, extra)
    antwort["mindestfaelle"] = MINDESTFAELLE
    antwort["nachfuehrung_tage"] = NACHFUEHRUNG_TAGE
    return antwort


def _rund(v: float) -> float:
    """Zwei gueltige Stellen: 13,47 wird 13, 0,347 wird 0,35."""
    if v <= 0:
        return 0.0
    stellen = 1 - int(math.floor(math.log10(v)))
    return round(v, max(stellen, 0))


def klassengrenzen(werte: list[float]) -> list[float]:
    """Die oberen Grenzen der ersten KLASSEN-1 Klassen, aus den Quantilen.

    Gerundet auf zwei gueltige Stellen und ohne Doppel - bei wenigen Werten
    gibt es dann weniger Klassen, nicht leere.
    """
    if not werte:
        return []
    grenzen = []
    for i in range(1, KLASSEN):
        g = _rund(werte[min(len(werte) - 1, int(len(werte) * i / KLASSEN))])
        if g > 0 and (not grenzen or g > grenzen[-1]):
            grenzen.append(g)
    return grenzen
