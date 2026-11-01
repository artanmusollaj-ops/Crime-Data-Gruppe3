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

from datetime import date
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
    monate = [date(a.jahr, m, 1) for m in range(a.von, a.bis + 1)]
    kat = "" if a.kategorie == "alle" else "AND kategorie = $kat"
    p = {"staedte": staedte, "monate": monate, **({"kat": a.kategorie} if kat else {})}

    def zaehle(spalte: str) -> dict[str, dict[str, int]]:
        werte: dict[str, dict[str, int]] = {s: {} for s in staedte}
        for s, w, n in cur.execute(
                f"SELECT stadt, {spalte}, sum(delikte) FROM qualitaet WHERE stadt IN $staedte "
                f"AND monat IN $monate {kat} GROUP BY 1, 2", p).fetchall():
            werte[s][str(w)] = int(n)
        return werte

    zuordnung, verortung, ortszeit = zaehle("mapping_status"), zaehle("geo_status"), zaehle(
        "ortszeit_mehrdeutig")
    doppelt = dict(cur.execute(
        "SELECT stadt, coalesce(sum(doppelt), 0) FROM doppelte WHERE stadt IN $staedte "
        "AND monat IN $monate GROUP BY 1", p).fetchall())
    abd = bestand._abdeckung(cur, staedte, monate)
    # Ein Monat nach der juengsten Tat des ganzen Bestands kann noch nicht
    # vorliegen: »noch nicht erschienen«, nicht »fehlt«. Fehlt er nur einer
    # Stadt, waehrend die andere ihn hat, ist er eine Luecke.
    juengste = cur.execute("SELECT max(bis) FROM fenster").fetchone()[0]

    stadtwerte = []
    for s in staedte:
        alle = sum(zuordnung[s].values())
        stadtwerte.append({
            "stadt": s, "name": STADTNAMEN[s], "delikte": alle,
            "monate": ["spaeter" if z == "fehlt" and juengste and m > juengste else z
                       for z, m in zip(abd[s]["monate"], monate)],
            "vollstaendig": abd[s]["vollstaendig"],
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
    vollstaendig = sum(all(abd[s]["monate"][i] == "voll" for s in staedte) for i in range(len(monate)))

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
        "auswahl": a.__dict__,
        "kennzahlen": {
            "vollstaendige_monate": vollstaendig, "monate": len(monate),
            "ohne_zuordnung": _anteil(ohne_zuordnung, alle),
            "ohne_koordinate": _anteil(ohne_koordinate, alle),
            "doppelte_ids": doppelte_ids, "delikte": alle,
            "ortszeit_mehrdeutig": mehrdeutig,
        },
        "monate": [m.isoformat() for m in monate],
        "staedte": stadtwerte,
        "pruefungen": pruefungen,
        "referenz": bestand.referenz(a.jahr),
        "stand": bestand.stand,
    }
