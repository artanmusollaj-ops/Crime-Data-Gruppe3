"""Das Brett »Wetter« - haengen die Fallzahlen am Wetter, und wie stark?

Das Konzept fuehrt das Wetter als dritte Zeitachse neben Tat und Raum
(``gold/dim_city_day``, eine Station je Stadt, tagesgenau). Dieses Brett
stellt es neben die Faelle.

**Die Jahreszeit ist die Falle.** Im Sommer ist es warm, und im Sommer gibt
es mehr Faelle - aus vielen Gruenden, von denen die Temperatur einer ist.
Ueber alle Tage 2021-2025 (lokales Release, gemessen am 8.11.2026) haengen Hoechsttemperatur und Faelle je Tag mit
r = 0,56 (Chicago) und 0,59 (Detroit) zusammen. Misst man dagegen jeden Tag am
Mittel **seines Monats** - wie viel waermer war er, wie viel mehr Faelle hatte
er -, bleibt r = 0,39 und 0,33. Das Brett zeigt deshalb beides: die rohe
Verteilung, an der man die Jahreszeit sieht, und die bereinigte, an der man
das Wetter sieht.

**Der Effekt je Grad** ist die Steigung der bereinigten Werte: um wie viel
Prozent ein Tag ueber seinem Monatsmittel liegt, je Grad, das er waermer ist.
Das Intervall daneben nimmt die Tage als unabhaengig und ist deshalb eher zu
schmal - aufeinanderfolgende Tage aehneln sich (Wetterlagen, Wochentag).

**Faelle, nicht Taten** (Entscheid E5), wie auf den uebrigen Brettern.

**Was es nicht kann.** Gemessen wird am Flughafen (O'Hare, Detroit Metro),
nicht im Quartier. NOAA veroeffentlicht mit rund vier Tagen Nachlauf. Wochentag
und Feiertage sind nicht herausgerechnet. Und ein Zusammenhang ist keine
Ursache: An heissen Tagen sind mehr Menschen draussen - das ist eine
Erklaerung, keine Messung.
"""

from __future__ import annotations

from datetime import date
from math import sqrt
from typing import Any

#: Baender der Tageshoechsttemperatur in Grad Celsius - (Name, unten, oben).
TEMPERATUR = (("unter 0 °C", None, 0), ("0 bis 10 °C", 0, 10), ("10 bis 20 °C", 10, 20),
              ("20 bis 30 °C", 20, 30), ("30 °C und mehr", 30, None))
#: Baender der Abweichung vom Monatsmittel in Kelvin.
ABWEICHUNG = (("5 K und mehr kälter", None, -5), ("bis 5 K kälter", -5, 0),
              ("bis 5 K wärmer", 0, 5), ("5 K und mehr wärmer", 5, None))
#: Ab wie viel Millimetern ein Tag nass heisst. Fuenf Millimeter sind ein
#: Regentag, an dem man den Schirm braucht, nicht ein Nieseln.
NASS_MM = 5.0
#: Ab wie vielen Tagen ein Band eine Aussage traegt.
MINDESTTAGE = 10


def lade_wetter(con, ablage, release: str, fakten: str, delikte: str) -> bool:
    """Legt ``wetter`` und ``tagesfaelle`` an - ``False``, wenn das Release kein Wetter fuehrt."""
    rel = f"{release}/gold/dataset=dim_city_day"
    if not ablage.exists(rel, "manifest.json"):
        return False
    pfad = ablage.resolve_read_path(rel, "part-0001.parquet")
    con.execute(f"""
        CREATE TABLE wetter AS
        SELECT city AS stadt, date AS tag, temp_max_c AS tmax, temp_min_c AS tmin,
               precipitation_mm AS regen, snowfall_mm AS schnee,
               coalesce(precipitation_trace, false) AS regen_spur,
               station_name AS station
        FROM read_parquet('{pfad}', hive_partitioning = false)""")
    # Faelle je Stadt, Tag und Kategorie - die Fallebene (counts_case).
    con.execute(f"""
        CREATE TABLE tagesfaelle AS
        SELECT f.reporting_city AS stadt, f.date AS tag,
               CASE WHEN f.nibrs_code IS NULL THEN 'unmapped'
                    ELSE d.nibrs_category END AS kategorie,
               count(*) FILTER (f.counts_case) AS faelle
        FROM read_parquet('{fakten}', hive_partitioning = false) f
        LEFT JOIN read_parquet('{delikte}', hive_partitioning = false) d USING (nibrs_code)
        GROUP BY ALL""")
    return True


def _band(wert: float | None, baender) -> str | None:
    if wert is None:
        return None
    for name, unten, oben in baender:
        if (unten is None or wert >= unten) and (oben is None or wert < oben):
            return name
    return None


def _effekt(zeilen: list[tuple]) -> dict[str, Any] | None:
    """Steigung der relativen Abweichung je Kelvin, mit 95-%-Intervall (Prozent)."""
    punkte = [(dt, df) for dt, df in zeilen if dt is not None and df is not None]
    n = len(punkte)
    if n < MINDESTTAGE:
        return None
    mx = sum(p[0] for p in punkte) / n
    my = sum(p[1] for p in punkte) / n
    sxx = sum((x - mx) ** 2 for x, _ in punkte)
    sxy = sum((x - mx) * (y - my) for x, y in punkte)
    syy = sum((y - my) ** 2 for _, y in punkte)
    if sxx == 0 or syy == 0:
        return None
    b = sxy / sxx
    se = sqrt(max(syy - b * sxy, 0) / (n - 2) / sxx)
    return {"je_grad": round(b * 100, 2), "von": round((b - 1.96 * se) * 100, 2),
            "bis": round((b + 1.96 * se) * 100, 2), "r": round(sxy / sqrt(sxx * syy), 2),
            "tage": n}


def wetter(bestand, a) -> dict[str, Any]:
    from serving.dashboard import STADTNAMEN

    antwort: dict[str, Any] = {"auswahl": a.__dict__, "stand": bestand.stand}
    if not bestand.wetter:
        return antwort | {"vorhanden": False}
    cur = bestand._cursor()
    staedte = list(a.staedte)
    von = date(a.jahr, a.von, 1)
    bis = date(a.jahr + (a.bis == 12), a.bis % 12 + 1, 1)
    kat = "" if a.kategorie == "alle" else "AND kategorie = $kat"
    p = {"staedte": staedte, "von": von, "bis": bis} | (
        {"kat": a.kategorie} if kat else {})

    # Ein Tag je Stadt mit Wetter, im Fenster der Falldaten dieser Stadt: Ein
    # Tag nach dem Datenende ist kein Tag ohne Faelle. Ohne Fall im Fenster
    # dagegen schon - dann ist er eine Null, keine Luecke.
    tage = cur.execute(f"""
        WITH f AS (
            SELECT stadt, tag, sum(faelle) AS faelle FROM tagesfaelle
            WHERE stadt IN $staedte AND tag >= $von AND tag < $bis {kat} GROUP BY 1, 2),
        t AS (
            SELECT w.stadt, w.tag, w.tmax, w.regen, w.schnee, coalesce(f.faelle, 0) AS faelle
            FROM wetter w JOIN fenster x ON x.stadt = w.stadt AND w.tag BETWEEN x.von AND x.bis
            LEFT JOIN f ON f.stadt = w.stadt AND f.tag = w.tag
            WHERE w.stadt IN $staedte AND w.tag >= $von AND w.tag < $bis AND w.tmax IS NOT NULL)
        SELECT stadt, tag, tmax, regen, schnee, faelle,
               tmax - avg(tmax) OVER m AS dt,
               CASE WHEN avg(faelle) OVER m > 0
                    THEN faelle / avg(faelle) OVER m - 1 END AS df
        FROM t WINDOW m AS (PARTITION BY stadt, year(tag), month(tag))
        ORDER BY stadt, tag""", p).fetchall()

    ergebnis = []
    for s in staedte:
        eigene = [z for z in tage if z[0] == s]
        if not eigene:
            ergebnis.append({"stadt": s, "name": STADTNAMEN[s], "tage": 0})
            continue
        roh: dict[str, list[float]] = {}
        bereinigt: dict[str, list[float]] = {}
        nass: dict[str, list[float]] = {}
        for _, _, tmax, regen, schnee, faelle, dt, df in eigene:
            roh.setdefault(_band(tmax, TEMPERATUR), []).append(faelle)
            if df is not None:
                bereinigt.setdefault(_band(dt, ABWEICHUNG), []).append(df)
                art = ("Schnee" if schnee and schnee > 0 else
                       "nass" if regen is not None and regen >= NASS_MM else
                       "leicht" if regen and regen > 0 else
                       "trocken" if regen is not None else None)
                if art:
                    nass.setdefault(art, []).append(df)

        def mittel(werte: list[float], prozent: bool = False):
            if not werte:
                return None
            m = sum(werte) / len(werte)
            return round(m * 100, 1) if prozent else round(m, 1)

        rohe_korrelation = _effekt([(z[2], z[5]) for z in eigene])
        ergebnis.append({
            "stadt": s, "name": STADTNAMEN[s], "tage": len(eigene),
            "station": cur.execute("SELECT any_value(station) FROM wetter WHERE stadt = $s",
                                   {"s": s}).fetchone()[0],
            "faelle_je_tag": mittel([z[5] for z in eigene]),
            "effekt": _effekt([(z[6], z[7]) for z in eigene]),
            "r_roh": rohe_korrelation["r"] if rohe_korrelation else None,
            "temperatur": [{"band": n, "tage": len(roh.get(n, [])),
                            "faelle_je_tag": mittel(roh.get(n, []))} for n, *_ in TEMPERATUR],
            "abweichung": [{"band": n, "tage": len(bereinigt.get(n, [])),
                            "prozent": mittel(bereinigt.get(n, []), True)}
                           for n, *_ in ABWEICHUNG],
            "niederschlag": [{"band": n, "tage": len(nass.get(n, [])),
                              "prozent": mittel(nass.get(n, []), True)}
                             for n in ("trocken", "leicht", "nass", "Schnee")],
            "monate": _monate(eigene),
        })
    return antwort | {"vorhanden": True, "staedte": ergebnis, "mindesttage": MINDESTTAGE,
                      "nass_mm": NASS_MM}


def _monate(tage: list[tuple]) -> list[dict[str, Any]]:
    """Je Monat mittlere Hoechsttemperatur und Faelle je Tag - die Jahreszeit."""
    je: dict[str, list[tuple]] = {}
    for z in tage:
        je.setdefault(z[1].strftime("%Y-%m-01"), []).append(z)
    return [{"monat": m, "tmax": round(sum(z[2] for z in zs) / len(zs), 1),
             "faelle_je_tag": round(sum(z[5] for z in zs) / len(zs), 1), "tage": len(zs)}
            for m, zs in sorted(je.items())]
