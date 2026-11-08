"""Das Brett »Quellbewegung« - was die Quellen nachtraeglich aendern und loeschen.

Beide Quellen bewegen sich nach der Veroeffentlichung: Detroit aendert
Eintraege noch Monate nach der Tat, Chicago entfernt welche. Das Brett zeigt
vier Dinge, alle aus ``serving/source_movement`` im aktiven Release:

1. **Welche Felder sich aendern und wie oft** - je Stadt, denn die Felder
   heissen in beiden Quellen anders. Zeitstempel sind vorgabemaessig
   ausgeblendet: Sie bewegen sich bei fast jeder Aenderung mit und
   verdeckten sonst, *was* sich aenderte.
2. **Wie oft derselbe Eintrag geaendert wird** - einmal, zweimal, oefter.
3. **Welche Eintraege verschwinden, und ob es immer dieselben Deliktsarten
   sind** - auf NIBRS gebracht, damit beide Staedte vergleichbar sind, und
   neben den Anteil gestellt, den die Kategorie am Bestand hat.
4. **Ob eine Stadt auffallend viel loescht oder aendert.**

**Warum je 10'000 Eintraege und Monat.** Die Vergleichspaare liegen
verschieden weit auseinander - von drei Stunden bis 28 Tage. Dreizehn
Loeschungen in einem Monat sind etwas anderes als dreizehn an einem Tag, und
aus 260'000 Zeilen etwas anderes als aus 88'000. Der Nenner ist deshalb je
Paar *Bestand x Tage / 30*, summiert ueber die Paare: die Eintragsmonate, in
denen eine Bewegung haette geschehen koennen.

**Der Test.** Sind die Raten beider Staedte gleich, verteilen sich die
beobachteten Ereignisse zufaellig im Verhaeltnis ihrer Eintragsmonate - die
Zahl in Chicago ist dann binomialverteilt mit diesem Anteil. Der p-Wert ist
die Wahrscheinlichkeit, unter dieser Annahme ein Ergebnis zu sehen, das
hoechstens so wahrscheinlich ist wie das beobachtete (exakter bedingter Test
fuer zwei Poisson-Raten, Przyborowski und Wilenski 1940; siehe Fay, M. P.
(2010): *Two-sided Exact Tests and Matching Confidence Intervals for
Discrete Data*, The R Journal 2(1), 53-58). Kein Normalnaeherungsverfahren:
Bei einer Handvoll Loeschungen traegt sie nicht.

**Zu wenig ist eine Aussage, keine Luecke.** Ein Paar ohne bestimmbaren
Bestand - sein Schnappschuss war aufgeraeumt, bevor Vertrag 4 von
``silver/source_change`` ihn festhielt - zaehlt mit, geht aber in keine Rate.
"""

from __future__ import annotations

import json
from math import exp, lgamma, log, log1p
from typing import Any

#: Wie viele Felder je Stadt einzeln erscheinen.
FELDER_IM_BALKEN = 12
#: Wie viele Wertwechsel je Stadt die Tabelle nennt.
UEBERGAENGE = 5
#: Wie viele entfernte Eintraege die Liste hoechstens zeigt.
LISTE = 200
#: Ab wann ein Unterschied als auffaellig gilt.
SIGNIFIKANZ = 0.05
#: Die Arten und ihre Namen auf dem Brett.
ARTEN = {"changed": "geaendert", "touched": "beruehrt", "removed": "entfernt",
         "added": "neu"}
FELDAUSWAHL = ("inhalt", "alle")
NICHT_BESTIMMBAR = "nicht_bestimmbar"


def lade_bewegung(con, ablage, release: str, delikte: str) -> dict[str, Any] | None:
    """Legt die Tabelle ``bewegung`` an - oder ``None``, wenn das Release sie nicht fuehrt."""
    rel = f"{release}/serving/dataset=source_movement"
    if not ablage.exists(rel, "manifest.json"):
        return None
    pfad = ablage.resolve_read_path(rel, "part-0001.parquet")
    manifest = json.loads(ablage.read_text(rel, "manifest.json"))
    # Ein Release von vor dem 8.11.2026 abends kennt den Jahrgang nicht; dann
    # bleibt er leer, und der Filter bietet keinen an.
    jahrgang = ("b.event_year" if "event_year" in (manifest.get("schema") or {})
                else "CAST(NULL AS INTEGER)")
    # Spalten ausgeschrieben, kein SELECT * (AGENTS.md, »Known pitfalls«).
    con.execute(f"""
        CREATE TABLE bewegung AS
        SELECT b.city AS stadt, b.offense_id, b.previous_run_id, b.run_id,
               b.previous_snapshot_at AS von, b.snapshot_at AS bis,
               b.change_type AS art, b.field AS feld, b.is_stamp AS stempel,
               b.value_old AS alt, b.value_new AS neu,
               b.source_offense_code AS code,
               b.source_offense_category AS quellkategorie,
               CASE WHEN b.offense_id IS NULL THEN NULL
                    WHEN b.source_offense_code IS NULL THEN '{NICHT_BESTIMMBAR}'
                    WHEN d.nibrs_category IS NULL THEN 'unmapped'
                    ELSE d.nibrs_category END AS kategorie,
               b.previous_rows AS bestand,
               {jahrgang} AS jahrgang
        FROM read_parquet('{pfad}', hive_partitioning = false) b
        LEFT JOIN read_parquet('{delikte}', hive_partitioning = false) d USING (nibrs_code)""")
    return {"gebaut": manifest.get("built_at_utc"), "zeilen": manifest.get("row_count")}


def gleiche_rate(k1: int, e1: float, k2: int, e2: float) -> dict[str, Any]:
    """Exakter bedingter Test, ob zwei Poisson-Raten gleich sein koennen.

    ``k`` sind Ereignisse, ``e`` die Exposition (hier Eintragsmonate). Unter
    der Annahme gleicher Raten ist ``k1`` bei gegebener Summe binomialverteilt
    mit ``p = e1 / (e1 + e2)``. Zweiseitig: summiert wird ueber alle
    Ergebnisse, die hoechstens so wahrscheinlich sind wie das beobachtete.
    Quelle im Moduldocstring.
    """
    n = k1 + k2
    if n == 0 or e1 <= 0 or e2 <= 0:
        return {"p_wert": None, "erwartet": None, "faktor": None}
    p = e1 / (e1 + e2)

    def logpmf(k: int) -> float:
        return (lgamma(n + 1) - lgamma(k + 1) - lgamma(n - k + 1)
                + k * log(p) + (n - k) * log1p(-p))

    beobachtet = logpmf(k1)
    # Die relative Toleranz wie in R binom.test: Gleich wahrscheinliche
    # Ergebnisse auf der Gegenseite zaehlen mit, Rundungsrauschen nicht weg.
    p_wert = sum(exp(lp) for lp in map(logpmf, range(n + 1))
                 if lp <= beobachtet + 1e-7)
    return {
        "p_wert": min(1.0, p_wert),
        "erwartet": [round(n * p, 1), round(n * (1 - p), 1)],
        # Wie viel hoeher die hoehere Rate ist - als Faktor >= 1, nicht als
        # 0,00 : 1, das bei einem grossen Unterschied nichts mehr zeigt.
        "faktor": (round(max(k1 / e1, k2 / e2) / min(k1 / e1, k2 / e2), 1)
                   if k1 and k2 else None),
    }


def _rate(n: int, exposition: float) -> float | None:
    return round(n * 10_000 / exposition, 2) if exposition > 0 else None


def quellbewegung(bestand, werte: dict[str, str]) -> dict[str, Any]:
    from serving.dashboard import STAEDTE, STADTNAMEN, EingabeFehler, kategorie_de

    stadt = werte.get("stadt", "beide")
    if stadt not in ("beide", *STAEDTE):
        raise EingabeFehler(f"Unbekannte Stadt: {stadt}")
    felderwahl = werte.get("felder", "inhalt")
    if felderwahl not in FELDAUSWAHL:
        raise EingabeFehler(f"Unbekannte Feldauswahl: {felderwahl}")
    staedte = list(STAEDTE) if stadt == "beide" else [stadt]
    antwort: dict[str, Any] = {"auswahl": {"stadt": stadt, "felder": felderwahl},
                               "stand": bestand.stand, "quelle": bestand.bewegung}
    if bestand.bewegung is None:
        return antwort | {"vorhanden": False}
    cur = bestand._cursor()

    # -- Die beiden Filter: Jahrgang und Beobachtungszeitraum -----------------
    # Der Zeitraum waehlt **Paare**, nach dem Monat des juengeren Abzugs: Eine
    # Bewegung geschah irgendwann zwischen den beiden Abzuegen und laesst sich
    # keinem Tag zuordnen, nur ihrem Paar.
    jahrgaenge = [r[0] for r in cur.execute(
        "SELECT DISTINCT jahrgang FROM bewegung WHERE jahrgang IS NOT NULL ORDER BY 1").fetchall()]
    monate = [r[0] for r in cur.execute(
        "SELECT DISTINCT strftime(bis, '%Y-%m') FROM bewegung ORDER BY 1").fetchall()]
    jahrgang = werte.get("jahrgang") or "alle"
    if jahrgang != "alle":
        try:
            jahrgang = int(jahrgang)
        except ValueError:
            raise EingabeFehler(f"Unbekannter Jahrgang: {jahrgang}") from None
        if jahrgang not in jahrgaenge:
            raise EingabeFehler(f"Kein Paar im Jahrgang {jahrgang}")
    von = werte.get("beob_von") or (monate[0] if monate else "")
    bis = werte.get("beob_bis") or (monate[-1] if monate else "")
    if monate and (von not in monate or bis not in monate):
        raise EingabeFehler(f"Kein beobachteter Monat: {von if von not in monate else bis}")
    if von > bis:
        raise EingabeFehler("Der Beobachtungszeitraum braucht von <= bis")
    antwort["auswahl"] |= {"jahrgang": jahrgang, "beob_von": von, "beob_bis": bis}
    antwort["optionen"] = {"jahrgaenge": jahrgaenge, "monate": monate}
    p: dict[str, Any] = {"staedte": staedte, "von": von, "bis": bis}
    wo = "stadt IN $staedte AND strftime(bis, '%Y-%m') BETWEEN $von AND $bis"
    if jahrgang != "alle":
        wo += " AND jahrgang = $jahrgang"
        p["jahrgang"] = jahrgang

    # -- Die Paare: Zeitraum, Bestand und was sich darin bewegt hat -----------
    paare = []
    for (s, vorher, nachher, von, bis, menge, *zahlen) in cur.execute(f"""
            SELECT stadt, previous_run_id, run_id, min(von), min(bis), max(bestand),
                   {', '.join(f"count(DISTINCT offense_id) FILTER (art = '{a}')"
                              for a in ARTEN)}
            FROM bewegung WHERE {wo}
            GROUP BY 1, 2, 3 ORDER BY 1, 4, 5, 2""", p).fetchall():
        tage = (bis - von).total_seconds() / 86_400
        paare.append({
            "stadt": s, "von": von.isoformat(), "bis": bis.isoformat(),
            "tage": round(tage, 2), "bestand": menge,
            "exposition": menge * tage / 30 if menge is not None else None,
            **{ARTEN[a]: int(z) for a, z in zip(ARTEN, zahlen)},
        })

    kennzahlen = []
    for s in staedte:
        eigene = [x for x in paare if x["stadt"] == s]
        mit = [x for x in eigene if x["exposition"] is not None]
        exposition = sum(x["exposition"] for x in mit)
        kennzahlen.append({
            "stadt": s, "name": STADTNAMEN[s], "paare": len(eigene),
            "paare_ohne_bestand": len(eigene) - len(mit),
            "von": min((x["von"] for x in eigene), default=None),
            "bis": max((x["bis"] for x in eigene), default=None),
            "eintragsmonate": round(exposition, 1),
            **{name: sum(x[name] for x in eigene) for name in ARTEN.values()},
            "je_10000": {name: _rate(sum(x[name] for x in mit), exposition)
                         for name in ARTEN.values()},
        })

    # -- Der Staedtevergleich -------------------------------------------------
    vergleich = []
    if len(staedte) == 2 and all(k["eintragsmonate"] > 0 for k in kennzahlen):
        a, b = kennzahlen
        for name in ("entfernt", "geaendert", "neu"):
            ka = sum(x[name] for x in paare if x["stadt"] == a["stadt"] and x["exposition"])
            kb = sum(x[name] for x in paare if x["stadt"] == b["stadt"] and x["exposition"])
            test = gleiche_rate(ka, a["eintragsmonate"], kb, b["eintragsmonate"])
            hoeher = None
            if test["p_wert"] is not None and test["p_wert"] < SIGNIFIKANZ:
                hoeher = a["stadt"] if ka / a["eintragsmonate"] > kb / b["eintragsmonate"] \
                    else b["stadt"]
            vergleich.append({"art": name, "anzahl": {a["stadt"]: ka, b["stadt"]: kb},
                              "rate": {a["stadt"]: a["je_10000"][name],
                                       b["stadt"]: b["je_10000"][name]},
                              **test, "auffaellig": hoeher})

    # -- Welche Felder sich aendern -------------------------------------------
    # Der Nenner folgt der Auswahl: ohne Stempel die inhaltlich geaenderten
    # Eintraege, mit ihnen auch die nur beruehrten.
    nur_inhalt = "AND NOT stempel" if felderwahl == "inhalt" else ""
    arten = "('changed')" if felderwahl == "inhalt" else "('changed', 'touched')"
    geaenderte = dict(cur.execute(
        "SELECT stadt, count(DISTINCT (previous_run_id, run_id, offense_id)) FROM bewegung "
        f"WHERE art IN {arten} AND {wo} GROUP BY 1", p).fetchall())
    felder: dict[str, list[dict[str, Any]]] = {s: [] for s in staedte}
    for s, feld, stempel, aenderungen, eintraege in cur.execute(f"""
            SELECT stadt, feld, bool_or(stempel), count(*),
                   count(DISTINCT (previous_run_id, run_id, offense_id))
            FROM bewegung WHERE feld IS NOT NULL AND {wo} {nur_inhalt}
            GROUP BY 1, 2 ORDER BY 1, 4 DESC, 2""", p).fetchall():
        felder[s].append({"feld": feld, "stempel": bool(stempel), "aenderungen": int(aenderungen),
                          "anteil": (round(eintraege * 100.0 / geaenderte[s], 1)
                                     if geaenderte.get(s) else None)})
    felder = {s: z[:FELDER_IM_BALKEN] for s, z in felder.items()}

    haeufigkeit = {s: {"1": 0, "2": 0, "3+": 0} for s in staedte}
    for s, mal, n in cur.execute(f"""
            SELECT stadt, least(mal, 3), count(*) FROM (
                SELECT stadt, offense_id, count(DISTINCT (previous_run_id, run_id)) AS mal
                FROM bewegung WHERE art = 'changed' AND {wo} GROUP BY 1, 2)
            GROUP BY 1, 2""", p).fetchall():
        haeufigkeit[s]["3+" if mal >= 3 else str(mal)] = int(n)

    uebergaenge = [
        {"stadt": s, "feld": f, "alt": a_, "neu": n_, "anzahl": int(n)}
        for s, f, a_, n_, n in cur.execute(f"""
            SELECT stadt, feld, alt, neu, n FROM (
                SELECT stadt, feld, alt, neu, count(*) AS n,
                       row_number() OVER (PARTITION BY stadt
                                          ORDER BY count(*) DESC, feld, alt, neu) AS rang
                FROM bewegung WHERE art = 'changed' AND NOT stempel AND {wo}
                GROUP BY 1, 2, 3, 4)
            WHERE rang <= {UEBERGAENGE} ORDER BY stadt, rang""", p).fetchall()]

    # -- Was verschwindet -----------------------------------------------------
    weg: dict[str, dict[str, int]] = {}
    for s, k, n in cur.execute(f"""
            SELECT stadt, kategorie, count(DISTINCT (previous_run_id, run_id, offense_id))
            FROM bewegung WHERE art = 'removed' AND {wo} GROUP BY 1, 2""",
                               p).fetchall():
        weg.setdefault(k, {})[s] = int(n)
    # Der Vergleichsmassstab: der Anteil der Kategorie an den Taten der Stadt
    # im ganzen Release. Nicht derselbe Bestand wie die Abzuege, aber derselbe
    # Massstab - eine Kategorie, die ein Prozent der Taten stellt und die
    # Haelfte der Loeschungen, faellt auf.
    taten: dict[str, dict[str, int]] = {}
    # Mit Jahrgang: der Anteil an den Taten **dieses** Jahrgangs.
    nur_jahr = "" if jahrgang == "alle" else "AND year(monat) = $jahrgang"
    for s, k, n in cur.execute(
            f"SELECT stadt, kategorie, sum(delikte) FROM monate WHERE stadt IN $staedte "
            f"{nur_jahr} GROUP BY 1, 2",
            {"staedte": staedte} | ({} if jahrgang == "alle" else {"jahrgang": jahrgang})
    ).fetchall():
        taten.setdefault(s, {})[k] = int(n)
    summe_weg = {s: sum(z.get(s, 0) for z in weg.values()) for s in staedte}
    summe_taten = {s: sum(taten.get(s, {}).values()) for s in staedte}
    kategorien = sorted(
        ({"kategorie": k,
          "name": "Nicht bestimmbar" if k == NICHT_BESTIMMBAR else kategorie_de(k),
          "anzahl": {s: z.get(s, 0) for s in staedte},
          "anteil": {s: (round(z.get(s, 0) * 100.0 / summe_weg[s], 1) if summe_weg[s] else None)
                     for s in staedte},
          "anteil_taten": {s: (round(taten.get(s, {}).get(k, 0) * 100.0 / summe_taten[s], 2)
                               if summe_taten[s] and k != NICHT_BESTIMMBAR else None)
                           for s in staedte}}
         for k, z in weg.items()),
        key=lambda z: (-sum(z["anzahl"].values()), z["name"]))
    konzentration = {}
    for s in staedte:
        eigene = [(z["anzahl"][s], z["name"]) for z in kategorien if z["anzahl"][s]]
        if eigene:
            n, name = max(eigene)
            konzentration[s] = {"kategorien": len(eigene), "haeufigste": name,
                                "anteil": round(n * 100.0 / summe_weg[s], 1)}
    liste = [
        {"stadt": s, "name": STADTNAMEN[s], "offense_id": o, "code": c,
         "quellkategorie": q,
         "kategorie": None if k is None else (
             "Nicht bestimmbar" if k == NICHT_BESTIMMBAR else kategorie_de(k)),
         "von": v.isoformat(), "bis": b.isoformat()}
        for s, o, c, q, k, v, b in cur.execute(f"""
            SELECT stadt, offense_id, code, quellkategorie, kategorie, von, bis
            FROM bewegung WHERE art = 'removed' AND {wo}
            ORDER BY bis DESC, stadt, offense_id LIMIT {LISTE}""", p).fetchall()]

    return antwort | {
        "vorhanden": True,
        "staedte": kennzahlen,
        "vergleich": vergleich,
        "signifikanz": SIGNIFIKANZ,
        "paare": [{k: v for k, v in x.items() if k != "exposition"} for x in paare],
        "felder": felder,
        "haeufigkeit": haeufigkeit,
        "uebergaenge": uebergaenge,
        "entfernt": {"kategorien": kategorien, "konzentration": konzentration,
                     "liste": liste, "gesamt": summe_weg},
    }
