"""Das Brett »Datenqualität« - nach Artans Entwurf ``dashboard_sind_die_daten_bereit.png``.

Sind die Daten im gewaehlten Ausschnitt analysebereit?

**Dieselben Schwellen wie das Publish-Gate.** ``gold_pipeline.GATE_MINDESTENS``
und ``GATE_HOECHSTENS``: mindestens 85 % exakt zugeordnet, mindestens 90 %
im Stadtgebiet verortet, hoechstens 1 % ohne Zuordnung. Das Gate misst
global ueber alle Taten (``build_gold.abdeckung``); das Brett misst ueber
die Auswahl und haelt dieselben Schwellen daneben. Eine eigene Schwelle
waere eine zweite Wahrheit.

**Gezaehlt werden Taten**, wie im Gate - nicht Faelle.

**Die vier Zuordnungen, die Gold kennt** (``MAPPING_STATUS_WERTE``):
``exact``, ``fallback_90Z``, ``ambiguous``, ``unmapped``. Der Entwurf zeigt
»Admin Review«; das ist in diesem Projekt eine *Herkunft* einer Zuordnung
(``config/mapping_overrides.csv``), kein Status - eine korrigierte Zuordnung
ist danach ``exact``.

**Fachlich, nicht technisch.** Laufzeiten, Speicher und Fehler der Strecke
stehen im Betriebsblick (Grafana); hier steht, ob die Zahlen tragen.
"""

from __future__ import annotations

from typing import Any

from gold_pipeline import GATE_HOECHSTENS, GATE_MINDESTENS, MAPPING_STATUS_WERTE

#: Reihenfolge der Zuordnungen im Balken: von gut nach schlecht.
ZUORDNUNGEN = ("exact", "fallback_90Z", "ambiguous", "unmapped")
if set(ZUORDNUNGEN) != MAPPING_STATUS_WERTE:
    # Kommt in Gold ein Status dazu, fehlte er hier still im Balken.
    raise RuntimeError(f"ZUORDNUNGEN kennt {ZUORDNUNGEN}, Gold {sorted(MAPPING_STATUS_WERTE)}")


def _anteil(n: int, alle: int) -> float | None:
    return round(n * 100.0 / alle, 2) if alle else None


def datenqualitaet(bestand, a) -> dict[str, Any]:
    from serving.dashboard import STADTNAMEN

    cur = bestand._cursor()
    staedte = list(a.staedte)
    z = bestand.zeitraum(cur, a, staedte)
    kat = a.kat_sql
    p = {"staedte": staedte, **z.param, **a.kat_param}

    def zaehle(spalte: str) -> dict[str, dict[str, int]]:
        werte: dict[str, dict[str, int]] = {s: {} for s in staedte}
        for s, w, n in cur.execute(
                f"SELECT stadt, {spalte}, count(*) FROM fakt WHERE stadt IN $staedte "
                f"AND tag BETWEEN $von AND $bis {kat} GROUP BY 1, 2", p).fetchall():
            werte[s][str(w)] = int(n)
        return werte

    zuordnung, verortung, ortszeit = zaehle("mapping_status"), zaehle("geo_status"), zaehle(
        "ortszeit_mehrdeutig")
    doppelt = dict(cur.execute(
        "SELECT stadt, count(*) - count(DISTINCT id) FROM doppelte WHERE stadt IN $staedte "
        "AND tag BETWEEN $von AND $bis GROUP BY 1", {"staedte": staedte, **z.param}).fetchall())
    status = {s: z.status(s, rand=False) for s in staedte}
    # Eine Periode nach der juengsten Tat des ganzen Bestands kann noch nicht
    # vorliegen: »noch nicht erschienen«, nicht »fehlt«. Fehlt sie nur einer
    # Stadt, waehrend die andere sie hat, ist sie eine Luecke.
    juengste = cur.execute("SELECT max(bis) FROM fenster").fetchone()[0]

    stadtwerte = []
    for s in staedte:
        alle = sum(zuordnung[s].values())
        stadtwerte.append({
            "stadt": s, "name": STADTNAMEN[s], "delikte": alle,
            "monate": ["spaeter" if st == "fehlt" and juengste and m > juengste else st
                       for st, m in zip(status[s], z.starts)],
            "vollstaendig": status[s].count("voll"),
            "zuordnung": {z: _anteil(zuordnung[s].get(z, 0), alle) for z in ZUORDNUNGEN},
            "verortung": {g: _anteil(verortung[s].get(g, 0), alle)
                          for g in ("inside_city", "outside_city", "no_tract", "missing_coordinate")},
        })

    def gesamt(werte: dict[str, dict[str, int]], schluessel: str) -> tuple[int, int]:
        return (sum(werte[s].get(schluessel, 0) for s in staedte),
                sum(sum(werte[s].values()) for s in staedte))

    exakt, alle = gesamt(zuordnung, "exact")
    ohne_zuordnung, _ = gesamt(zuordnung, "unmapped")
    im_gebiet, _ = gesamt(verortung, "inside_city")
    ohne_koordinate, _ = gesamt(verortung, "missing_coordinate")
    mehrdeutig, _ = gesamt(ortszeit, "True")
    doppelte_ids = int(sum(doppelt.get(s, 0) for s in staedte))
    vollstaendig = sum(all(status[s][i] == "voll" for s in staedte) for i in range(len(z.starts)))

    def gate(wert: float | None, schwelle: float, mindestens: bool) -> str:
        if wert is None:
            return "keine_daten"
        return "ok" if (wert >= schwelle if mindestens else wert <= schwelle) else "warnung"

    pruefungen = [
        {"aspekt": "NIBRS-Zuordnung exakt", "wert": _anteil(exakt, alle),
         "schwelle": f"mindestens {GATE_MINDESTENS['exact']:g} %",
         "status": gate(_anteil(exakt, alle), GATE_MINDESTENS["exact"], True)},
        {"aspekt": "Ohne NIBRS-Zuordnung", "wert": _anteil(ohne_zuordnung, alle),
         "schwelle": f"höchstens {GATE_HOECHSTENS['unmapped']:g} %",
         "status": gate(_anteil(ohne_zuordnung, alle), GATE_HOECHSTENS["unmapped"], False)},
        {"aspekt": "Verortung im Stadtgebiet", "wert": _anteil(im_gebiet, alle),
         "schwelle": f"mindestens {GATE_MINDESTENS['inside_city']:g} %",
         "status": gate(_anteil(im_gebiet, alle), GATE_MINDESTENS["inside_city"], True)},
        {"aspekt": "Eindeutige Delikt-ID", "wert": doppelte_ids, "schwelle": "keine doppelte",
         "status": "ok" if doppelte_ids == 0 else "warnung"},
    ]
    return {
        "auswahl": a.json,
        "zuordnung_detail": _zuordnung_detail(cur, staedte, p, kat),
        "kennzahlen": {
            "vollstaendige_monate": vollstaendig, "monate": len(z.starts),
            "ohne_zuordnung": _anteil(ohne_zuordnung, alle),
            "ohne_koordinate": _anteil(ohne_koordinate, alle),
            "doppelte_ids": doppelte_ids, "delikte": alle,
            "ortszeit_mehrdeutig": mehrdeutig,
        },
        "monate": [m.isoformat() for m in z.starts],
        "achse": z.json(),
        "staedte": stadtwerte,
        "pruefungen": pruefungen,
        "referenz": bestand.referenz(a),
        "stand": bestand.stand,
    }


def _zuordnung_detail(cur, staedte: list[str], p: dict[str, Any], kat: str) -> list[dict[str, Any]]:
    """Je Stadt und Quellcode: wohin er in NIBRS faellt, mit Status und Taten.

    Fuer die Tafel »NIBRS-Zuordnung im Detail«. Filtern nach Status und Suche
    tut die Seite selbst: Es sind wenige hundert Zeilen, und so bleibt die
    Auswahl beim Umschalten ohne Rundweg zum Server.
    """
    from serving.dashboard import STADTNAMEN, kategorie_de

    zeilen = cur.execute(f"""
        SELECT stadt, quellcode, min(quelltext), nibrs_code, min(nibrs_text), kategorie,
               status, sum(delikte)
        FROM (SELECT q.stadt, q.quellcode, q.quelltext, q.nibrs_code,
                     d.nibrs_description AS nibrs_text, f.kategorie, q.status, 1 AS delikte
              FROM fakt f JOIN quelle q ON q.nr = f.quelle
              LEFT JOIN delikt d ON d.nibrs_code = q.nibrs_code
              WHERE f.stadt IN $staedte AND f.tag BETWEEN $von AND $bis {kat})
        GROUP BY stadt, quellcode, nibrs_code, kategorie, status
        ORDER BY 8 DESC, 1, 2""", p).fetchall()
    je_stadt: dict[str, int] = {}
    for z in zeilen:
        je_stadt[z[0]] = je_stadt.get(z[0], 0) + int(z[7])
    return [{
        "stadt": s, "name": STADTNAMEN[s], "quellcode": q, "quelltext": qt,
        "nibrs_code": n, "nibrs_text": nt,
        "kategorie": "Ohne Zuordnung" if k == "unmapped" else kategorie_de(k),
        "status": st, "delikte": int(m), "anteil": _anteil(int(m), je_stadt[s]),
    } for s, q, qt, n, nt, k, st, m in zeilen]
