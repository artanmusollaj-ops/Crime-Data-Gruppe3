"""Das Brett »Soziales Umfeld« - Fallrate und Armut je Census Tract.

Die Fallrate je Tract ist dieselbe wie auf der »Geografie«: dieselbe Funktion
(``geografie.geografie``), Fallebene, nur Taten in der Stadt, der Nenner aus
dem Vintage der Tat. Daneben steht die Armutsquote und das Medianeinkommen
aus demselben ACS-Vintage (``gold/dim_tract_acs``).

**Feste Baender, nicht Fuenftel je Stadt.** Die Verteilungen beider Staedte
ueberlappen kaum: 2024 beginnt Detroits aermstes Fuenftel der Tracts bei 45 %
Armutsquote, Chicagos bei 29 %. Fuenftel je Stadt stellten Ungleiches
nebeneinander. Mit gemeinsamen Baendern wird sichtbar, ob Detroit bei
**gleicher** Armut hoeher liegt.

**Die Karte uebereinander ist bivariat:** je Tract eine von neun Farben, aus
drei Stufen der Fallrate und drei der Armutsquote. Die Stufen sind Terzile ueber
beide Staedte zusammen - dieselbe Farbe heisst in Chicago und Detroit dasselbe.

**Der Zusammenhang je Stadt ist Spearmans Rangkorrelation** ueber die Tracts mit
tragfaehiger Basis: robust gegen die wenigen Tracts mit sehr hohen Raten
(Innenstadt, Verkehrsknoten), die eine Pearson-Korrelation allein bestimmen
koennten.

**Was es nicht kann.** Ein Zusammenhang je Tract sagt nichts ueber einzelne
Menschen (oekologischer Fehlschluss). Tatort ist nicht Wohnort - Gebiete mit
vielen Pendlern bekommen eine hohe Rate auf wenige Einwohner. Die ACS-Werte
sind Fuenfjahres-Schaetzungen, und ihre Fehlermargen sind nicht geladen. Und die
Luecken sind ungleich: Ein Einkommen fehlt in Wayne County haeufiger als in Cook
County (Konzept, Abschnitt 11).
"""

from __future__ import annotations

from typing import Any

#: Baender der Armutsquote in Prozent - (Name, unten, oben). Fuer beide Staedte gleich.
ARMUT = (("unter 10 %", 0, 10), ("10 bis 20 %", 10, 20), ("20 bis 30 %", 20, 30),
         ("30 bis 40 %", 30, 40), ("40 % und mehr", 40, None))
#: Wie die Karte gezeichnet wird.
KARTEN = ("nebeneinander", "bivariat")


def lade_sozial(con, acs: str) -> None:
    """Armutsquote und Medianeinkommen je Tract und Vintage.

    Fehlt eine der beiden Spalten - ein Release, das sie nicht fuehrt -, bleibt
    sie leer: Das Brett zeigt dann keine Armut, das Dashboard laedt trotzdem.
    """
    vorhanden = {r[0] for r in con.execute(
        f"DESCRIBE SELECT * FROM read_parquet('{acs}', hive_partitioning = false)").fetchall()}

    def spalte(name: str, typ: str) -> str:
        return name if name in vorhanden else f"CAST(NULL AS {typ})"

    con.execute(f"""
        CREATE TABLE tract_sozial AS
        SELECT geoid, vintage, {spalte("poverty_rate", "DOUBLE")} AS armut,
               {spalte("median_household_income_usd", "INTEGER")} AS einkommen
        FROM read_parquet('{acs}', hive_partitioning = false)
        WHERE geoid IN (SELECT geoid FROM tract_geo)""")


def _band(armut: float | None) -> str | None:
    if armut is None:
        return None
    prozent = armut * 100
    for name, unten, oben in ARMUT:
        if prozent >= unten and (oben is None or prozent < oben):
            return name
    return None


def _raenge(werte: list[float]) -> list[float]:
    """Raenge mit Mittelrang bei Gleichstand."""
    ordnung = sorted(range(len(werte)), key=lambda i: werte[i])
    raenge = [0.0] * len(werte)
    i = 0
    while i < len(ordnung):
        j = i
        while j + 1 < len(ordnung) and werte[ordnung[j + 1]] == werte[ordnung[i]]:
            j += 1
        for k in range(i, j + 1):
            raenge[ordnung[k]] = (i + j) / 2 + 1
        i = j + 1
    return raenge


def spearman(paare: list[tuple[float, float]]) -> float | None:
    """Spearmans Rangkorrelation - ``None`` bei weniger als zehn Paaren."""
    if len(paare) < 10:
        return None
    rx, ry = _raenge([p[0] for p in paare]), _raenge([p[1] for p in paare])
    n = len(paare)
    mx, my = sum(rx) / n, sum(ry) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    return round(sxy / (sxx * syy) ** 0.5, 2) if sxx and syy else None


def _terzile(werte: list[float]) -> list[float]:
    if len(werte) < 3:
        return []
    werte = sorted(werte)
    return [werte[len(werte) // 3], werte[(2 * len(werte)) // 3]]


def sozial(bestand, a, karte: str = "nebeneinander") -> dict[str, Any]:
    from serving.dashboard import EingabeFehler
    from serving.dashboard.geografie import geografie

    if karte not in KARTEN:
        raise EingabeFehler(f"Unbekannte Kartenart: {karte}")
    geo = geografie(bestand, a)
    vintage = geo["vintage"]
    cur = bestand._cursor()
    sozialwerte = {g: (arm, ein) for g, arm, ein in cur.execute(
        "SELECT geoid, armut, einkommen FROM tract_sozial WHERE vintage = $v",
        {"v": vintage}).fetchall()} if vintage else {}

    staedte = []
    alle_tragfaehig = []
    for s in geo["staedte"]:
        tracts = []
        for t in s["tracts"]:
            armut, einkommen = sozialwerte.get(t["geoid"], (None, None))
            tracts.append(t | {"armut": None if armut is None else round(armut * 100, 1),
                               "einkommen": einkommen, "band": _band(armut)})
        tragfaehig = [t for t in tracts if not t["geringe_basis"] and t["rate"] is not None
                      and t["armut"] is not None]
        alle_tragfaehig += tragfaehig
        baender = []
        for name, *_ in ARMUT:
            im = [t for t in tracts if t["band"] == name and t["einwohner"]]
            einwohner = sum(t["einwohner"] for t in im)
            faelle = sum(t["faelle"] for t in im)
            baender.append({"band": name, "tracts": len(im), "einwohner": einwohner,
                            "faelle": faelle,
                            "rate": round(faelle * 1000.0 / einwohner, 1) if einwohner else None})
        mit_rate = [b for b in baender if b["rate"] is not None and b["tracts"] >= 5]
        staedte.append({
            "stadt": s["stadt"], "name": s["name"], "tracts": tracts,
            "baender": baender,
            "spearman": spearman([(t["armut"], t["rate"]) for t in tragfaehig]),
            "spearman_einkommen": spearman([(t["einkommen"], t["rate"]) for t in tragfaehig
                                            if t["einkommen"] is not None]),
            "spanne": ({"arm": mit_rate[-1], "reich": mit_rate[0]} if len(mit_rate) >= 2 else None),
            "ohne_armut": sum(t["armut"] is None and bool(t["einwohner"]) for t in tracts),
            "ohne_einkommen": sum(t["einkommen"] is None and bool(t["einwohner"]) for t in tracts),
            "mit_einwohnern": sum(bool(t["einwohner"]) for t in tracts),
            "geringe": s["geringe"], "verortung": s["verortung"],
        })
    return {
        "auswahl": a.__dict__ | {"karte": karte},
        "vintage": vintage,
        "klassen": geo["klassen"],
        "armut": [{"band": n, "unten": u, "oben": o} for n, u, o in ARMUT],
        "bivariat": {"rate": _terzile([t["rate"] for t in alle_tragfaehig]),
                     "armut": _terzile([t["armut"] for t in alle_tragfaehig])},
        "geringe_basis": geo["geringe_basis"],
        "staedte": staedte,
        "stand": bestand.stand,
    }
