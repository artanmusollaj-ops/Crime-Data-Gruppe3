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
"""

from __future__ import annotations

import math
import re
from datetime import date
from typing import Any

GERINGE_BASIS = 500
KLASSEN = 5
RANGLISTE = 5
#: Breite der Karte im SVG-Koordinatensystem; die Hoehe folgt der Stadt.
KARTENBREITE = 600.0
#: Aequatorumfang (WGS 84) in Kilometern.
_ERDUMFANG_KM = 40075.016686

_RING = re.compile(r"\(\(([^()]*)\)\)")


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
        treffer = _RING.search(wkt or "")
        if not treffer or not stadt:
            continue
        punkte = [_welt(*map(float, p.split()[:2])) for p in treffer.group(1).split(",")]
        je_stadt.setdefault(stadt, []).append((geoid, name, punkte))
    karten = {}
    for stadt, tracts in je_stadt.items():
        alle = [p for _, _, ps in tracts for p in ps]
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
            "tracts": [{"geoid": g, "name": n,
                        "d": "M" + "L".join(xy(p) for p in ps) + "Z"} for g, n, ps in tracts],
        }
    return karten


def geografie(bestand, a) -> dict[str, Any]:
    from serving.dashboard import STADTNAMEN

    cur = bestand._cursor()
    staedte = list(a.staedte)
    monate = [date(a.jahr, m, 1) for m in range(a.von, a.bis + 1)]
    kat = "" if a.kategorie == "alle" else "AND kategorie = $kat"
    p = {"staedte": staedte, "monate": monate, **({"kat": a.kategorie} if kat else {})}
    vintages = [r[0] for r in cur.execute(
        "SELECT DISTINCT vintage FROM tract_monat WHERE year(monat) = $j AND vintage IS NOT NULL",
        {"j": a.jahr}).fetchall()]
    vintage = vintages[0] if len(vintages) == 1 else None
    # Jeder Tract der Stadt, auch einer ohne Fall: Er ist eine Null, keine Luecke.
    zeilen = cur.execute(f"""
        SELECT g.city, g.geoid, g.tract_name, e.population,
               coalesce(t.faelle, 0), coalesce(t.delikte, 0)
        FROM tract_geo g
        LEFT JOIN tract_einwohner e ON e.geoid = g.geoid AND e.vintage = $vintage
        LEFT JOIN (SELECT geoid, sum(faelle) AS faelle, sum(delikte) AS delikte
                   FROM tract_monat WHERE stadt IN $staedte AND monat IN $monate {kat}
                   GROUP BY 1) t ON t.geoid = g.geoid
        WHERE g.city IN $staedte ORDER BY g.city, g.geoid""",
        {**p, "vintage": vintage}).fetchall()
    tracts = {s: [] for s in staedte}
    for stadt, geoid, name, einwohner, faelle, delikte in zeilen:
        rate = (round(faelle * 1000.0 / einwohner, 1)
                if einwohner else None)
        tracts[stadt].append({
            "geoid": geoid, "name": name, "einwohner": einwohner,
            "faelle": int(faelle), "delikte": int(delikte), "rate": rate,
            "geringe_basis": einwohner is None or einwohner < GERINGE_BASIS,
        })
    tragfaehig = sorted(t["rate"] for ts in tracts.values() for t in ts
                        if not t["geringe_basis"] and t["rate"] is not None)
    verortung = {s: {"inside_city": 0, "outside_city": 0, "no_tract": 0, "missing_coordinate": 0}
                 for s in staedte}
    for s, status, n in cur.execute(
            f"SELECT stadt, geo_status, sum(faelle) FROM verortung WHERE stadt IN $staedte "
            f"AND monat IN $monate {kat} GROUP BY 1, 2", p).fetchall():
        verortung[s][status] = int(n)
    return {
        "auswahl": a.__dict__,
        "vintage": vintage,
        "klassen": klassengrenzen(tragfaehig),
        "geringe_basis": GERINGE_BASIS,
        "staedte": [{
            "stadt": s, "name": STADTNAMEN[s],
            "tracts": tracts[s],
            "hoechste": sorted((t for t in tracts[s] if not t["geringe_basis"] and t["rate"]),
                               key=lambda t: (-t["rate"], t["geoid"]))[:RANGLISTE],
            "geringe": sum(t["geringe_basis"] for t in tracts[s]),
            "verortung": verortung[s],
        } for s in staedte],
        "stand": bestand.stand,
    }


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
