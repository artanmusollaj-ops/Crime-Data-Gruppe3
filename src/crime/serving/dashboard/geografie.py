"""Das Brett »Geografie« - nach Artans Entwurf ``dashboard_räumliche_verteilung.png``.

Eine Karte je Stadt, jede Flaeche nach einer Kennzahl gefaerbt, dazu die
Flaechen mit den hoechsten Werten.

**Faelle je 1'000 Einwohner, nicht Delikte je 100'000.** Die Rate folgt
``gold_pipeline.raten_je_tract`` und damit Kibana und den Dokumenten:
Fallebene vorn (Entscheid E5), gezaehlt nach meldender Stadt, nur Taten mit
``geo_status = 'inside_city'``, der Nenner aus dem Vintage der Tat.

**Zwei Schalter** (seit 25.11.2026): ``raum`` und ``kennzahl``. Ein Link
mit dem frueheren ``ansicht`` gilt weiter (``ANSICHT_ALT``).

``raum``:

- ``tract``: Census Tracts aus ``dim_tract_geo``.
- ``bezirk``: Polizeibezirke aus ``dim_police_area`` (Gold-Vertrag 11),
  Einwohner aus ``serving.dashboard.bezirke``. Chicagos District 31 zaehlt
  nicht, er umfasst Norridge und Harwood Heights.
- ``stadtteil``: Chicagos Community Areas und Detroits Master Plan
  Neighborhoods aus ``dim_community_area`` (Gold-Vertrag 12), Einwohner wie
  bei den Bezirken. In Detroit ist der Schluessel ein Name.
- ``sechseck``: ein Raster aus Sechsecken mit ``taten.SECHSECK_M`` Metern
  Kantenlaenge, unabhaengig davon, wie Grenzen gezogen sind. **Ohne
  Einwohner**: Die Rate ist hier die Dichte, Faelle je km² und Jahr, und
  eine geglaettete Rate gibt es nicht. Gezeigt werden Zellen mit Faellen.

  *Warum ein Raster.* Tracts, Bezirke und Stadtteile sind nach Einwohnern
  oder nach der Verwaltung geschnitten, und wie hoch eine Rate je Flaeche
  ausfaellt, haengt auch davon ab, wo die Grenzen liegen: das »Modifiable
  Areal Unit Problem« nach Openshaw (1984), »The Modifiable Areal Unit
  Problem«, CATMOG 38, Geo Books, Norwich. Gleich grosse Zellen sind das
  Gegenbild, das von keiner dieser Grenzen abhaengt - zeigt eine Haeufung
  sich in beiden, liegt sie nicht am Zuschnitt.

  *Warum Sechsecke.* Jede Zelle hat sechs Nachbarn im selben Abstand, und
  keine Richtung ist bevorzugt; im Quadratraster liegen die Eck-Nachbarn
  weiter weg als die Kanten-Nachbarn. Birch, Oom und Beecham (2007),
  »Rectangular and hexagonal grids used for observation, experiment and
  simulation in ecology«, Ecological Modelling 206(3-4), 347-359.

  *Warum 500 m.* Gesetzt, nicht hergeleitet. Die Zellen sind so in Chicago
  etwa so fein wie die Tracts (2024 968 Zellen mit Faellen, 793 Tracts), in
  Detroit feiner (618 Zellen, 273 Tracts).

  *Was die Karte nicht sagt.* Ohne Einwohner zeigt die Dichte, wo viele
  Faelle sind, nicht, wo das Risiko hoch ist: Innenstadt und
  Geschaeftsstrassen werden dunkel, weil sich dort viele Menschen aufhalten.

``kennzahl``:

- ``rate``: Faelle je 1'000 Einwohner und Jahr (Sechseck: je km² und Jahr).
- ``geglaettet``: die Rate nach Empirical Bayes, global je Stadt nach
  Marshall (1991), »Mapping disease and mortality rates using empirical Bayes
  estimators«, Applied Statistics 40(2), 283-294: Kleine Flaechen ruecken zum
  Mittel der Stadt, grosse behalten ihre Rate. Statt einer Schraffur zeigt
  die Karte so auch die kleinen Tracts, ohne dass ein einzelner Fall sie
  dunkel faerbt.
- ``veraenderung``: Faelle gegenueber denselben Tagen ein Jahr frueher, in
  Prozent, ueber die Tage, die in beiden Jahren Daten haben
  (``zeitraum.vergleich``). Bis ein Jahr Spanne; Basis unter ``MINDESTFAELLE``
  Faellen im Vorjahr ist schraffiert.
- ``profil``: der Lokationsquotient - Anteil der gewaehlten Kategorien an den
  Faellen der Flaeche, geteilt durch denselben Anteil in der Stadt. Ueber 1
  ist die Kategorie dort haeufiger als im Mittel der Stadt. Er braucht keine
  Einwohner und umgeht damit »Tatort ist nicht Wohnort«; ohne gewaehlte
  Kategorie hat er keinen Sinn und meldet das.
- ``nacht``: Anteil der Faelle bei Dunkelheit, unter den Faellen mit
  sicherer Tatzeit (``taten.dunkel``).
- ``festnahme``: Anteil der Faelle mit Festnahme unter denen mit bekanntem
  Stand. Chicago fuehrt ``arrest``, Detroit den Stand des Falls (``CLEARED BY
  ARREST``). **Junge Faelle** sind noch nicht geklaert: Liegt das Ende des
  Zeitraums weniger als ``NACHFUEHRUNG_TAGE`` vor dem letzten Tag mit Daten,
  sagt das Brett es je Stadt dazu. In Detroit fiel die Quote 2025 auf 5,7 %
  und 2026 auf 4,6 %, nach 9 bis 12 % in den Jahren davor.

**Geringe Basis.** Fuer Raten unter 500 Einwohnern (bei 35 macht eine Tat
28,6 je 1'000), fuer Anteile unter ``MINDESTFAELLE`` Faellen im Nenner. Sie
werden schraffiert und stehen nicht in der Rangliste.

**Die Klassen sind Quantile, fuer beide Staedte gemeinsam**; fuer
Veraenderung und Profil feste Grenzen um den neutralen Wert, damit
Zunahme und Abnahme dieselbe Farbe in beiden Staedten tragen.

**Die Umrisse aus Gold, der Hintergrund von OpenStreetMap**, projiziert wie
die Kacheln nach Web-Mercator (``pfade``). Die Sechsecke entstehen je
Anfrage im Rahmen der Tract-Karte ihrer Stadt.

**Nicht verortet** sind Taten ohne Koordinate, ohne Tract oder ausserhalb
der Stadtgrenze. Sie fehlen auf der Karte und werden je Stadt gezaehlt.
"""

from __future__ import annotations

import math
import re
from datetime import timedelta
from typing import Any

GERINGE_BASIS = 500
#: Unter so vielen Faellen im Nenner ist ein Anteil oder eine Veraenderung zu unruhig.
MINDESTFAELLE = 30
#: So lange nach der Tat wird der Stand eines Falls noch spuerbar nachgefuehrt.
NACHFUEHRUNG_TAGE = 365
RAEUME = ("tract", "bezirk", "stadtteil", "sechseck")
KENNZAHLEN = ("rate", "geglaettet", "veraenderung", "profil", "nacht", "festnahme")
#: Die fruehere einzige Auswahl, fuer Links von vor dem Umbau.
ANSICHT_ALT = {"tract": ("tract", "rate"), "bezirk": ("bezirk", "rate"),
               "festnahme": ("bezirk", "festnahme")}
#: Feste Grenzen um den neutralen Wert: Veraenderung in Prozent, Profil als Quotient.
#: Veraenderung: Bezirke bewegen sich von Jahr zu Jahr um wenige Prozent - ein
#: neutrales Band von +-10 % liess 2024 jeden Bezirk grau (gesehen am 25.11.2026).
FESTE_KLASSEN = {"veraenderung": [-20.0, -5.0, 5.0, 20.0],
                 "profil": [0.67, 0.9, 1.1, 1.5]}
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


def wahl(raum: str | None, kennzahl: str | None, ansicht: str | None) -> tuple[str, str]:
    """Raum und Kennzahl aus der Adresse; ``ansicht`` nur, wenn beide fehlen."""
    from serving.dashboard import EingabeFehler

    if not raum and not kennzahl and ansicht:
        if ansicht not in ANSICHT_ALT:
            raise EingabeFehler(f"Unbekannte Ansicht: {ansicht}")
        raum, kennzahl = ANSICHT_ALT[ansicht]
    raum, kennzahl = raum or "tract", kennzahl or "rate"
    if raum not in RAEUME:
        raise EingabeFehler(f"Unbekannter Raum: {raum}")
    if kennzahl not in KENNZAHLEN:
        raise EingabeFehler(f"Unbekannte Kennzahl: {kennzahl}")
    if raum == "sechseck" and kennzahl == "geglaettet":
        raise EingabeFehler("Sechsecke haben keine Einwohner – "
                            "geglättet wird nur eine Rate je Tract oder Bezirk")
    return raum, kennzahl


def geografie(bestand, a, ansicht: str | None = None, *, raum: str | None = None,
              kennzahl: str | None = None) -> dict[str, Any]:
    """Eine Kennzahl je Flaeche, fuer jede gewaehlte Stadt eine Karte."""
    from serving.dashboard import STADTNAMEN, EingabeFehler

    raum, kennzahl = wahl(raum, kennzahl, ansicht)
    if raum == "bezirk" and not getattr(bestand, "karten_bezirke", None):
        raise EingabeFehler("Dieses Release führt keine Polizeibezirke "
                            "(erst ab Gold-Vertrag 11)")
    if raum == "stadtteil" and not getattr(bestand, "karten_stadtteile", None):
        raise EingabeFehler("Dieses Release führt keine Stadtteile "
                            "(erst ab Gold-Vertrag 12)")
    if kennzahl == "profil" and a.kategorien is None:
        raise EingabeFehler("Das Deliktprofil braucht eine Auswahl von Kategorien – "
                            "es vergleicht ihren Anteil je Fläche mit dem der Stadt")
    cur = bestand._cursor()
    staedte = list(a.staedte)
    z = bestand.zeitraum(cur, a, staedte)
    p = {"staedte": staedte, **z.param, **a.kat_param}
    gewichte = {s: z.gewichte(s, bestand.vintage_je_jahr) for s in staedte}
    vintages = sorted({v for g in gewichte.values() if g for v in g})
    vintage = vintages[-1] if vintages else None

    vergleich = None
    if kennzahl == "veraenderung":
        if not z.vergleich_moeglich:
            raise EingabeFehler("Eine Veränderung zum Vorjahr gibt es bis ein Jahr Spanne")
        vergleich = z.vergleich(staedte)

    einheiten = _einheiten(cur, raum, staedte)
    zahlen = _zahlen(cur, raum, kennzahl, a, p, vergleich)
    einwohner = _einwohner(cur, raum, vintages)

    flaechen: dict[str, list] = {s: [] for s in staedte}
    for stadt, schluessel, name in einheiten:
        n = zahlen.get((stadt, schluessel), {})
        g = gewichte.get(stadt)
        jahre = (sum(w * einwohner[(stadt, schluessel, v)] for v, w in g.items())
                 if raum != "sechseck" and g
                 and all(einwohner.get((stadt, schluessel, v)) for v in g) else None)
        anzeige = einwohner.get((stadt, schluessel, vintage)) if vintage else None
        flaechen[stadt].append(_flaeche(raum, kennzahl, stadt, schluessel, name, n,
                                        jahre, anzeige, z))
    for stadt in staedte:
        if raum == "sechseck":
            # Nur Zellen mit Faellen, und Umrisse im Rahmen der Tract-Karte.
            flaechen[stadt] = [f for f in flaechen[stadt] if f["delikte"]]
            _sechseck_pfade(cur, bestand.karten.get(stadt), stadt, flaechen[stadt])
        if kennzahl == "geglaettet":
            _glaetten(flaechen[stadt])
        if kennzahl == "profil":
            _profil(flaechen[stadt])

    extra = {}
    for s in staedte:
        fl = flaechen[s]
        ende = z.fenster.get(s, (None, None))[1]
        fest, bekannt = sum(f["festnahmen"] for f in fl), sum(f["bekannt"] for f in fl)
        extra[s] = {
            "festnahmen": fest, "bekannt": bekannt,
            "anteil": round(fest * 100.0 / bekannt, 1) if bekannt else None,
            "jung": bool(ende and a.tag_bis > ende - timedelta(days=NACHFUEHRUNG_TAGE)),
        }
    tragfaehig = sorted(f["wert"] for fl in flaechen.values() for f in fl
                        if not f["geringe_basis"] and f["wert"] is not None)
    kat = a.kat_sql
    verortung = {s: {"inside_city": 0, "outside_city": 0, "no_tract": 0, "missing_coordinate": 0}
                 for s in staedte}
    for s, status, n in cur.execute(
            f"SELECT stadt, geo_status, count(*) FILTER (fall) FROM fakt WHERE stadt IN $staedte "
            f"AND tag BETWEEN $von AND $bis {kat} GROUP BY 1, 2", p).fetchall():
        verortung[s][status] = int(n)
    ansicht = next((k for k, v in ANSICHT_ALT.items() if v == (raum, kennzahl)), None)
    return {
        "auswahl": a.json | {"raum": raum, "kennzahl": kennzahl},
        "raum": raum, "kennzahl": kennzahl,
        # Fuer Leser von vor dem Umbau; None, wo es die Kombination nicht gab.
        "ansicht": ansicht,
        "vintage": vintage,
        "vintages": vintages,
        "achse": z.json(),
        "vergleich": [t.isoformat() for t in vergleich] if vergleich else None,
        "klassen": FESTE_KLASSEN.get(kennzahl) or klassengrenzen(tragfaehig),
        "geringe_basis": GERINGE_BASIS,
        "mindestfaelle": MINDESTFAELLE,
        "nachfuehrung_tage": NACHFUEHRUNG_TAGE,
        "staedte": [{
            "stadt": s, "name": STADTNAMEN[s],
            "tracts": flaechen[s],
            "hoechste": sorted((f for f in flaechen[s] if not f["geringe_basis"]
                                and f["wert"] is not None),
                               key=lambda f: (-f["wert"], f["geoid"]))[:RANGLISTE],
            "geringe": sum(f["geringe_basis"] for f in flaechen[s]),
            "verortung": verortung[s],
            **extra[s],
        } for s in staedte],
        "stand": bestand.stand,
    }


def _einheiten(cur, raum: str, staedte: list[str]) -> list[tuple]:
    """Jede Flaeche der Staedte, auch eine ohne Fall: Sie ist eine Null, keine Luecke."""
    if raum == "tract":
        return cur.execute("SELECT city, geoid, tract_name FROM tract_geo "
                           "WHERE city IN $s ORDER BY city, geoid", {"s": staedte}).fetchall()
    if raum == "bezirk":
        return [(s, str(n), name) for s, n, name in cur.execute(
            "SELECT stadt, nr, name FROM bezirk WHERE zaehlt AND stadt IN $s ORDER BY stadt, nr",
            {"s": staedte}).fetchall()]
    if raum == "stadtteil":
        return cur.execute(
            "SELECT stadt, kennung, name FROM stadtteil WHERE zaehlt AND stadt IN $s "
            "ORDER BY stadt, name", {"s": staedte}).fetchall()
    return [(s, f"{q},{r}", f"Sechseck {q},{r}") for s, q, r in cur.execute(
        "SELECT DISTINCT stadt::VARCHAR, hq, hr FROM fakt WHERE stadt IN $s "
        "AND geo_status = 'inside_city' AND hq IS NOT NULL ORDER BY 1, 2, 3",
        {"s": staedte}).fetchall()]


def _schluessel_sql(raum: str) -> tuple[str, str]:
    """Der Schluessel einer Tat im gewaehlten Raum, und was dafuer zu verbinden ist."""
    if raum == "tract":
        return "n.geoid", "JOIN tract_nr n ON n.nr = f.tract"
    if raum == "bezirk":
        return "CAST(f.bezirk AS VARCHAR)", ""
    if raum == "stadtteil":
        return "CAST(f.stadtteil AS VARCHAR)", ""
    return "CAST(f.hq AS VARCHAR) || ',' || CAST(f.hr AS VARCHAR)", ""


def _zahlen(cur, raum, kennzahl, a, p, vergleich) -> dict[tuple, dict[str, int]]:
    """Je Stadt und Flaeche die Zaehler, die die Kennzahlen brauchen."""
    schluessel, verbund = _schluessel_sql(raum)
    kat_f = a.kat_sql.replace("kategorie", "f.kategorie")
    # Das Profil teilt durch alle Faelle der Flaeche - der Kategoriefilter gilt
    # dort nur fuer den Zaehler.
    filter_alle = "" if kennzahl == "profil" else kat_f
    in_kat = ("f.kategorie IN $kat" if a.kategorien is not None else "TRUE")
    zeitraum = "f.tag BETWEEN $von AND $bis"
    werte = dict(p)
    vorjahr = "FALSE"
    if vergleich:
        from serving.dashboard.zeitraum import vor_einem_jahr
        werte |= {"v_von": vergleich[0], "v_bis": vergleich[1],
                  "w_von": vor_einem_jahr(vergleich[0]), "w_bis": vor_einem_jahr(vergleich[1])}
        zeitraum = ("(f.tag BETWEEN $v_von AND $v_bis OR f.tag BETWEEN $w_von AND $w_bis)")
        vorjahr = "f.tag BETWEEN $w_von AND $w_bis"
    sql = f"""
        SELECT f.stadt::VARCHAR, {schluessel} AS k,
               count(*) FILTER (f.fall AND NOT {vorjahr} AND {in_kat}) AS faelle,
               count(*) FILTER (NOT {vorjahr} AND {in_kat}) AS delikte,
               count(*) FILTER (f.fall AND NOT {vorjahr}) AS faelle_alle,
               count(*) FILTER (f.fall AND {vorjahr} AND {in_kat}) AS faelle_vorjahr,
               count(*) FILTER (f.fall AND NOT {vorjahr} AND {in_kat} AND f.festnahme) AS fest,
               count(*) FILTER (f.fall AND NOT {vorjahr} AND {in_kat}
                                AND f.festnahme IS NOT NULL) AS bekannt,
               count(*) FILTER (f.fall AND NOT {vorjahr} AND {in_kat} AND f.dunkel) AS dunkel,
               count(*) FILTER (f.fall AND NOT {vorjahr} AND {in_kat}
                                AND f.dunkel IS NOT NULL) AS licht_bekannt
        FROM fakt f {verbund}
        WHERE f.stadt IN $staedte AND f.geo_status = 'inside_city'
          AND {zeitraum} {filter_alle}
        GROUP BY 1, 2"""
    from serving.dashboard.zeitraum import benutzt
    namen = ("faelle", "delikte", "faelle_alle", "faelle_vorjahr", "fest", "bekannt",
             "dunkel", "licht_bekannt")
    return {(s, k): dict(zip(namen, map(int, rest)))
            for s, k, *rest in cur.execute(sql, benutzt(sql, werte)).fetchall()}


def _einwohner(cur, raum: str, vintages: list[int]) -> dict[tuple, float]:
    if raum == "tract":
        return {(s, g, v): n for s, g, v, n in cur.execute(
            "SELECT t.city, e.geoid, e.vintage, e.population FROM tract_einwohner e "
            "JOIN tract_geo t USING (geoid) WHERE e.vintage IN $v",
            {"v": vintages or [0]}).fetchall()}
    if raum == "bezirk":
        return {(s, str(n), v): e for s, n, v, e in cur.execute(
            "SELECT stadt, nr, vintage, population FROM bezirk_einwohner WHERE vintage IN $v",
            {"v": vintages or [0]}).fetchall()}
    if raum == "stadtteil":
        return {(s, k, v): e for s, k, v, e in cur.execute(
            "SELECT stadt, kennung, vintage, population FROM stadtteil_einwohner "
            "WHERE vintage IN $v", {"v": vintages or [0]}).fetchall()}
    return {}


def _anteil(zaehler: int, nenner: int) -> float | None:
    return round(zaehler * 100.0 / nenner, 1) if nenner else None


def _flaeche(raum, kennzahl, stadt, schluessel, name, n, jahre, anzeige, z) -> dict[str, Any]:
    faelle = n.get("faelle", 0)
    if raum == "sechseck":
        from serving.dashboard.taten import SECHSECK_M
        km2 = 3 * math.sqrt(3) / 2 * (SECHSECK_M / 1000) ** 2
        tage = z.tage_mit_daten(stadt)
        rate = round(faelle / km2 / (tage / 365.25), 1) if tage else None
    else:
        rate = round(faelle * 1000.0 / jahre, 1) if jahre else None
    vorjahr = n.get("faelle_vorjahr", 0)
    werte = {
        "rate": rate, "geglaettet": rate,
        "veraenderung": (round((faelle - vorjahr) * 100.0 / vorjahr, 1) if vorjahr else None),
        "profil": None,
        "nacht": _anteil(n.get("dunkel", 0), n.get("licht_bekannt", 0)),
        "festnahme": _anteil(n.get("fest", 0), n.get("bekannt", 0)),
    }
    if kennzahl in ("rate", "geglaettet"):
        gering = (faelle < 1 if raum == "sechseck"
                  else anzeige is None or anzeige < GERINGE_BASIS)
    else:
        nenner = {"veraenderung": vorjahr, "profil": n.get("faelle_alle", 0),
                  "nacht": n.get("licht_bekannt", 0), "festnahme": n.get("bekannt", 0)}[kennzahl]
        gering = nenner < MINDESTFAELLE
    return {
        "geoid": schluessel, "name": name,
        "einwohner": round(anzeige) if anzeige else None,
        "personenjahre": round(jahre, 1) if jahre else None,
        "faelle": faelle, "delikte": n.get("delikte", 0), "rate": rate,
        "faelle_alle": n.get("faelle_alle", 0), "faelle_vorjahr": vorjahr,
        "festnahmen": n.get("fest", 0), "bekannt": n.get("bekannt", 0),
        "anteil": werte["festnahme"],
        "dunkel": n.get("dunkel", 0), "licht_bekannt": n.get("licht_bekannt", 0),
        "nachtanteil": werte["nacht"], "veraenderung": werte["veraenderung"],
        "wert": werte[kennzahl],
        "geringe_basis": bool(gering),
    }


def _glaetten(flaechen: list[dict]) -> None:
    """Empirical Bayes nach Marshall (1991), global je Stadt.

    m ist die Rate der Stadt, s2 die Streuung der Raten um m, gewichtet nach
    Personenjahren, abzueglich dessen, was der Zufall allein erklaert
    (m / mittlere Personenjahre). Eine Flaeche mit n Personenjahren behaelt
    das Gewicht s2 / (s2 + m / n) ihrer eigenen Rate. Ohne Einwohner bleibt
    sie ohne Wert. Die Rate je 1'000 wird dazu in Faelle je Person gewandelt.
    """
    mit = [(f["faelle"], f["personenjahre"] / 1000.0) for f in flaechen if f["personenjahre"]]
    if not mit:
        return
    summe_n = sum(n for _, n in mit)
    m = sum(x for x, _ in mit) / summe_n
    mittel_n = summe_n / len(mit)
    s2 = max(sum(n * (x / n - m) ** 2 for x, n in mit) / summe_n - m / mittel_n, 0.0)
    for f in flaechen:
        if not f["personenjahre"]:
            f["wert"] = None
            continue
        n = f["personenjahre"] / 1000.0
        gewicht = s2 / (s2 + m / n) if s2 + m / n else 0.0
        f["wert"] = round(gewicht * (f["faelle"] / n) + (1 - gewicht) * m, 1)
        f["gewicht"] = round(gewicht, 3)
        # Geglaettet traegt jede Flaeche mit Einwohnern - auch die kleine.
        f["geringe_basis"] = False


def _profil(flaechen: list[dict]) -> None:
    """Lokationsquotient: Anteil der Kategorie hier durch ihren Anteil in der Stadt."""
    kat = sum(f["faelle"] for f in flaechen)
    alle = sum(f["faelle_alle"] for f in flaechen)
    if not kat or not alle:
        return
    stadt = kat / alle
    for f in flaechen:
        f["wert"] = (round(f["faelle"] / f["faelle_alle"] / stadt, 2)
                     if f["faelle_alle"] else None)


def _sechseck_pfade(cur, k: dict | None, stadt: str, flaechen: list[dict]) -> None:
    """Die Umrisse der Sechsecke als Pfade im Rahmen der Tract-Karte ``k``."""
    if not k or not flaechen:
        return
    from serving.dashboard.taten import ERDRADIUS_M, SECHSECK_M
    lat0, lon0 = cur.execute("SELECT lat, lon FROM mitte WHERE stadt = $s",
                             {"s": stadt}).fetchone()
    kos = math.cos(math.radians(lat0))

    def lonlat(x: float, y: float) -> tuple[float, float]:
        return (lon0 + math.degrees(x / (ERDRADIUS_M * kos)),
                lat0 + math.degrees(y / ERDRADIUS_M))

    for f in flaechen:
        q, r = map(int, f["geoid"].split(","))
        cx = SECHSECK_M * (math.sqrt(3) * q + math.sqrt(3) / 2 * r)
        cy = SECHSECK_M * 1.5 * r
        ecken = []
        for i in range(6):
            w = math.radians(60 * i - 30)
            wx, wy = _welt(*lonlat(cx + SECHSECK_M * math.cos(w), cy + SECHSECK_M * math.sin(w)))
            ecken.append(f"{(wx - k['x0']) * k['massstab']:.1f} {(wy - k['y0']) * k['massstab']:.1f}")
        f["d"] = "M" + "L".join(ecken) + "Z"


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
