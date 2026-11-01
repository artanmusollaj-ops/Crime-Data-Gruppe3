"""Das Brett »Zeitverlauf« - nach Artans Entwurf ``dashboard_zeitliche_muster_erkenn.png``.

Drei Fragen: Wie verlaufen die Fallzahlen gegen dieselben Monate des
Vorjahrs? Wann in der Woche und am Tag geschieht es? Und entwickeln sich
beide Staedte gleich, unabhaengig von ihrer Groesse?

**Faelle, nicht Taten.** Der Entwurf spricht von Fallzahlen, und die
Fallebene (``counts_case``) ist die Zahl, die die Dokumente vorn nennen.
Das Brett »Überblick« zeigt beide.

**Die Stunde ist Ortszeit**, ``fact_offense.hour_of_day``: America/Chicago
und America/Detroit. Auf UTC laege Detroits Abendspitze eine Stunde neben
Chicagos (``build_kibana._ORTSZEIT``).

**Genau 00:00 und 12:00 fehlen in der Heatmap.** Dort haeufen sich
Platzhalter fuer eine unbekannte Tatzeit - in Chicago 9'445 Faelle um 00:00
gegen 1'967 um 00:01 (2024). Kibana zeichnet sie mit und vermerkt es; der
Entwurf verlangt, fehlende Tatzeiten getrennt auszuweisen. Das Brett nimmt
sie heraus und nennt ihre Zahl. Darunter sind auch echte Taten um genau
00:00 - sie fehlen dann mit, und die Zahl steht daneben.

**Der Index beginnt beim ersten vollstaendigen Monat.** Der Entwurf setzt
»Januar = 100«; liegt der Januar nur zum Teil vor, waere jeder spaetere
Monat ein scheinbarer Anstieg.
"""

from __future__ import annotations

from datetime import date
from typing import Any

WOCHENTAGE = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
ZEITZONEN = {"chicago": "America/Chicago", "detroit": "America/Detroit"}


def zeitverlauf(bestand, a) -> dict[str, Any]:
    from serving.dashboard import STADTNAMEN

    cur = bestand._cursor()
    staedte = list(a.staedte)
    monate = [date(a.jahr, m, 1) for m in range(a.von, a.bis + 1)]
    vormonate = [date(a.jahr - 1, m, 1) for m in range(a.von, a.bis + 1)]
    kat = "" if a.kategorie == "alle" else "AND kategorie = $kat"
    extra = {"kat": a.kategorie} if kat else {}

    def faelle(ms: list[date]) -> dict[tuple[str, date], int]:
        return {(s, m): int(n) for s, m, n in cur.execute(
            f"SELECT stadt, monat, sum(faelle) FROM monate WHERE stadt IN $staedte "
            f"AND monat IN $monate {kat} GROUP BY 1, 2",
            {"staedte": staedte, "monate": ms, **extra}).fetchall()}

    jetzt, vorher = faelle(monate), faelle(vormonate)
    abd, vorabd = bestand._abdeckung(cur, staedte, monate), bestand._abdeckung(cur, staedte, vormonate)

    def reihe(s, ms, werte, abdeckung):
        return [None if abdeckung[s]["monate"][i] == "fehlt" else werte.get((s, m), 0)
                for i, m in enumerate(ms)]

    ergebnis = []
    for s in staedte:
        werte = reihe(s, monate, jetzt, abd)
        status = abd[s]["monate"]
        basis = next((i for i, z in enumerate(status) if z == "voll" and werte[i]), None)
        index = [None if basis is None or v is None else round(v * 100.0 / werte[basis], 1)
                 for v in werte]
        ergebnis.append({
            "stadt": s, "name": STADTNAMEN[s], "zeitzone": ZEITZONEN[s],
            "monate": [m.isoformat() for m in monate],
            "jetzt": werte, "status": status,
            "vorjahr": reihe(s, vormonate, vorher, vorabd), "status_vorjahr": vorabd[s]["monate"],
            "index": {"basis": monate[basis].isoformat() if basis is not None else None,
                      "werte": index},
            "heatmap": _heatmap(cur, s, monate, kat, extra),
        })
    return {
        "auswahl": a.__dict__,
        "vergleich": {"jahr": a.jahr, "vorjahr": a.jahr - 1,
                      "vorjahr_vorhanden": a.jahr - 1 in bestand.jahre},
        "staedte": ergebnis,
        "wochentage": list(WOCHENTAGE),
        "stand": bestand.stand,
    }


def _heatmap(cur, stadt: str, monate: list[date], kat: str, extra: dict) -> dict[str, Any]:
    """Durchschnittliche Faelle je Wochentag und Stunde, ohne Platzhalterzeiten."""
    p = {"stadt": stadt, "monate": monate, **extra}
    tage = dict(cur.execute(
        "SELECT wochentag, sum(n) FROM tage WHERE stadt = $stadt AND monat IN $monate "
        "GROUP BY 1", {"stadt": stadt, "monate": monate}).fetchall())
    matrix = [[0.0] * 24 for _ in WOCHENTAGE]
    for wt, h, n in cur.execute(
            f"SELECT wochentag, stunde, sum(faelle) FROM stunden WHERE stadt = $stadt "
            f"AND monat IN $monate AND NOT platzhalter {kat} GROUP BY 1, 2", p).fetchall():
        if tage.get(wt):
            matrix[wt - 1][h] = round(n / tage[wt], 2)
    platzhalter, alle = cur.execute(
        f"SELECT coalesce(sum(faelle) FILTER (platzhalter), 0), coalesce(sum(faelle), 0) "
        f"FROM stunden WHERE stadt = $stadt AND monat IN $monate {kat}", p).fetchone()
    return {
        "werte": matrix,
        "max": max(max(z) for z in matrix),
        "tage": int(sum(tage.values())),
        "platzhalter": int(platzhalter),
        "platzhalter_anteil": round(platzhalter * 100.0 / alle, 1) if alle else None,
    }
