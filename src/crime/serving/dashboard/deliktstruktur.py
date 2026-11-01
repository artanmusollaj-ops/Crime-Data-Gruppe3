"""Das Brett »Deliktstruktur« - nach Artans Entwurf ``dashboard_welche_delikte_ändern_sich.png``.

Welche Kategorien tragen die Kriminalitaet einer Stadt, und welche
veraendern sich gegen das Vorjahr?

**Faelle vorn, Delikte auf Wunsch** (Entscheid E5). Chicago erfasst je Fall
nur das schwerste Delikt, Detroit jedes. Auf der Tatebene stellt ein
Vergleich der *Struktur* Detroits vollstaendige Anklagen gegen eine
Chicagoer Zahl, die nie alle Delikte enthielt - er misst den
Erfassungsunterschied mit (``build_kibana._FALLEBENE_VORN``). Der Entwurf
beginnt mit Delikten; das Brett beginnt mit Faellen und bietet Delikte an.

**Zum Vorjahr je Stadt und Kategorie** ueber die Monate, die in beiden
Jahren fuer diese Stadt vollstaendig vorliegen - dieselbe Regel wie im
»Überblick«. Unter ``MINDESTZAHL`` Faellen im Vorjahr bleibt die
Veraenderung leer: Aus 3 gegen 6 wird +100 %, und das sagt nichts.
"""

from __future__ import annotations

from datetime import date
from typing import Any

#: Wie viele Kategorien die Balken und die Anteile einzeln zeigen.
IM_DIAGRAMM = 5
#: Wie viele Zeilen die Tabelle zeigt; der Rest wird gezaehlt.
IN_DER_TABELLE = 10
#: Darunter ist eine Veraenderung in Prozent kein Befund.
MINDESTZAHL = 20


def deliktstruktur(bestand, a) -> dict[str, Any]:
    from serving.dashboard import STADTNAMEN, UEBRIGE, kategorie_de

    cur = bestand._cursor()
    staedte = list(a.staedte)
    spalte = a.ebene
    monate = [date(a.jahr, m, 1) for m in range(a.von, a.bis + 1)]
    vormonate = [date(a.jahr - 1, m, 1) for m in range(a.von, a.bis + 1)]
    kat = "" if a.kategorie == "alle" else "AND kategorie = $kat"
    extra = {"kat": a.kategorie} if kat else {}

    def je(ms_je_stadt: dict[str, list[date]]) -> dict[tuple[str, str], int]:
        werte: dict[tuple[str, str], int] = {}
        for s, ms in ms_je_stadt.items():
            if not ms:
                continue
            for k, n in cur.execute(
                    f"SELECT kategorie, sum({spalte}) FROM monate WHERE stadt = $s "
                    f"AND monat IN $monate {kat} GROUP BY 1",
                    {"s": s, "monate": ms, **extra}).fetchall():
                werte[(s, k)] = int(n)
        return werte

    jetzt = je({s: monate for s in staedte})
    abd = bestand._abdeckung(cur, staedte, monate)
    vorabd = bestand._abdeckung(cur, staedte, vormonate)
    vergleichbar = {s: [i for i in range(len(monate))
                        if abd[s]["monate"][i] == "voll" and vorabd[s]["monate"][i] == "voll"]
                    for s in staedte}
    jetzt_v = je({s: [monate[i] for i in vergleichbar[s]] for s in staedte})
    vorher_v = je({s: [vormonate[i] for i in vergleichbar[s]] for s in staedte})

    gesamt: dict[str, int] = {}
    for (_, k), n in jetzt.items():
        gesamt[k] = gesamt.get(k, 0) + n
    reihenfolge = [k for k, _ in sorted(gesamt.items(), key=lambda kv: (-kv[1], kv[0]))]
    summe = {s: sum(n for (st, _), n in jetzt.items() if st == s) for s in staedte}

    def veraenderung(s: str, k: str) -> float | None:
        vorher = vorher_v.get((s, k), 0)
        if vorher < MINDESTZAHL:
            return None
        return round((jetzt_v.get((s, k), 0) - vorher) * 100.0 / vorher, 1)

    einzeln = reihenfolge[:IM_DIAGRAMM]
    anteile = []
    for s in staedte:
        teile = [{"kategorie": k, "name": kategorie_de(k),
                  "anteil": round(jetzt.get((s, k), 0) * 100.0 / summe[s], 1) if summe[s] else 0.0}
                 for k in einzeln]
        rest = summe[s] - sum(jetzt.get((s, k), 0) for k in einzeln)
        if len(reihenfolge) > IM_DIAGRAMM:
            teile.append({"kategorie": UEBRIGE, "name": UEBRIGE,
                          "anteil": round(rest * 100.0 / summe[s], 1) if summe[s] else 0.0})
        anteile.append({"stadt": s, "name": STADTNAMEN[s], "teile": teile})

    return {
        "auswahl": a.__dict__,
        "ebene": spalte,
        "balken": [{"kategorie": k, "name": kategorie_de(k),
                    "werte": {s: jetzt.get((s, k), 0) for s in staedte}} for k in einzeln],
        "anteile": anteile,
        "tabelle": [{
            "kategorie": k, "name": kategorie_de(k),
            "beispiele": bestand.beispiele.get(k, []),
            "werte": {s: jetzt.get((s, k), 0) for s in staedte},
            "vorjahr": {s: veraenderung(s, k) for s in staedte},
        } for k in reihenfolge[:IN_DER_TABELLE]],
        "weitere": max(0, len(reihenfolge) - IN_DER_TABELLE),
        "staedte": [{"stadt": s, "name": STADTNAMEN[s], "summe": summe[s],
                     "vergleichbare_monate": len(vergleichbar[s])} for s in staedte],
        "monate": len(monate),
        "mindestzahl": MINDESTZAHL,
        "stand": bestand.stand,
    }
