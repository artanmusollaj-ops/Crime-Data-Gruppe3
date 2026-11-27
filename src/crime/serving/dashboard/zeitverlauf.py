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

**Tag und Nacht.** Keine Uhrzeit sagt, ob es hell war - das haengt an
Jahreszeit und Ort. Seit Vertrag 9 traegt ``gold/dim_city_day`` je Stadt und
Tag ``sunrise_utc`` und ``sunset_utc`` (NOAA, am Schwerpunkt der Ortsgrenze).
Hell ist ein Fall, wenn ``sunrise_utc <= occurred_at_utc < sunset_utc`` fuer
seine meldende Stadt und seinen Ortstag gilt; sonst dunkel. Eine dritte
Gruppe heisst »Uhrzeit unsicher«: dieselben Platzhalter wie in der Heatmap
(Ortszeit genau 00:00:00 oder 12:00:00, ``PLATZHALTER_SQL``). Sie sind weder
hell noch dunkel, denn ihre wahre Uhrzeit ist unbekannt. Dorthin faellt auch
ein Fall ohne UTC-Zeitpunkt oder ohne Sonnenstand an seinem Tag; mit
Vertrag 9 kommt das nicht vor, weil ``dim_city_day`` jeden Tag der Fallspanne
fuehrt. Eine Daemmerungsklasse gibt es nicht.

Hell und dunkel sind verschieden lang - im Dezember gut neun Stunden Licht,
im Juni gut fuenfzehn. Die Faelle je Stunde teilen deshalb durch die
Stunden, die es im Zeitraum hell oder dunkel war, ueber alle Tage im
Datenfenster der Stadt. Die Dunkelstunden je Tag sind ``24 -
daylight_hours``; dass der Tag der Zeitumstellung 23 oder 25 Stunden hat,
wird vernachlaessigt (zwei Tage im Jahr, je eine Stunde). Die Platzhalter
fehlen im Zaehler beider Raten.

Der Dunkel-Anteil je Kategorie ist ``dunkel / (hell + dunkel)``, ohne die
unsicheren Faelle, fuer hoechstens die acht haeufigsten Kategorien. Er sagt,
zu welcher Tatzeit ein Fall gemeldet ist, nicht warum: Licht ist keine
Ursache, und die gemeldete Tatzeit ist nicht immer die wahre.
"""

from __future__ import annotations

from typing import Any

WOCHENTAGE = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
ZEITZONEN = {"chicago": "America/Chicago", "detroit": "America/Detroit"}
#: Die drei Gruppen der Tafel »Tag und Nacht«, in der Reihenfolge der Anzeige.
LICHTGRUPPEN = (("hell", "Tageslicht"), ("dunkel", "Dunkelheit"),
                ("unsicher", "Uhrzeit unsicher"))
#: Wie viele Kategorien der Dunkel-Anteil hoechstens zeigt.
LICHT_KATEGORIEN = 8
#: Was ``dim_city_day`` und ``fact_offense`` fuer die Tafel fuehren muessen.
SONNENSPALTEN = ("sunrise_utc", "sunset_utc", "daylight_hours")


def _spalten(con, pfad: str) -> set[str]:
    """Die Spalten der Datei - aus dem Parquet-Schema, ohne ``SELECT *``.

    ``con`` bleibt in der Signatur, damit die Aufrufer gleich bleiben; gelesen
    wird ueber ``storage.parquet_schema``, lokal wie auf S3, und ohne die
    Hive-Spalte aus dem Pfad (AGENTS.md, »Known pitfalls«).
    """
    from storage import parquet_spalten
    return set(parquet_spalten(pfad))


def lade_licht(con, ablage, release: str, fakten: str, delikte: str) -> str | None:
    """Legt ``licht`` und ``lichtstunden`` an - oder sagt, warum es nicht geht.

    ``licht``: Faelle (``counts_case``) je Stadt, Tag, Kategorie und Gruppe
    hell, dunkel oder unsicher. ``lichtstunden``: je Stadt und Tag die
    Stunden mit und ohne Tageslicht ueber die Tage im Datenfenster der Stadt
    (Tabelle ``fenster``, die vorher angelegt sein muss).

    Gibt ``None`` zurueck, wenn beide Tabellen stehen, sonst den Grund. Ein
    aelteres Release (Vertrag <= 8) bleibt lesbar - die Tafel bleibt dann leer
    und sagt warum, wie das Brett »Wetter« ohne ``dim_city_day``.
    """
    from serving.dashboard import PLATZHALTER_SQL

    rel = f"{release}/gold/dataset=dim_city_day"
    if not ablage.exists(rel, "manifest.json"):
        return "Dieses Release führt keine Tabelle dim_city_day."
    pfad = ablage.resolve_read_path(rel, "part-0001.parquet")
    fehlt = [s for s in SONNENSPALTEN if s not in _spalten(con, pfad)]
    if fehlt:
        return ("Dieses Release ist vor dem Sonnenstand gebaut (Gold-Vertrag 8 oder "
                f"älter): dim_city_day führt {', '.join(fehlt)} nicht.")
    if "occurred_at_utc" not in _spalten(con, fakten):
        return "fact_offense führt in diesem Release keinen UTC-Zeitpunkt."
    con.execute(f"""
        CREATE TABLE licht AS
        SELECT f.reporting_city AS stadt, f.date AS tag,
               CASE WHEN f.nibrs_code IS NULL THEN 'unmapped'
                    ELSE d.nibrs_category END AS kategorie,
               CASE WHEN {PLATZHALTER_SQL} OR f.occurred_at_utc IS NULL
                         OR c.sunrise_utc IS NULL OR c.sunset_utc IS NULL THEN 'unsicher'
                    WHEN f.occurred_at_utc >= c.sunrise_utc
                         AND f.occurred_at_utc < c.sunset_utc THEN 'hell'
                    ELSE 'dunkel' END AS gruppe,
               count(*) FILTER (f.counts_case) AS faelle
        FROM read_parquet('{fakten}', hive_partitioning = false) f
        LEFT JOIN read_parquet('{delikte}', hive_partitioning = false) d USING (nibrs_code)
        LEFT JOIN read_parquet('{pfad}', hive_partitioning = false) c
               ON c.city = f.reporting_city AND c.date = f.date
        GROUP BY ALL""")
    con.execute(f"""
        CREATE TABLE lichtstunden AS
        SELECT c.city AS stadt, c.date AS tag,
               sum(c.daylight_hours) AS hell, sum(24 - c.daylight_hours) AS dunkel
        FROM read_parquet('{pfad}', hive_partitioning = false) c
        JOIN fenster x ON x.stadt = c.city AND c.date BETWEEN x.von AND x.bis
        GROUP BY ALL""")
    return None


def zeitverlauf(bestand, a) -> dict[str, Any]:
    from serving.dashboard import STADTNAMEN
    from serving.dashboard.zeitraum import benutzt, vor_einem_jahr

    cur = bestand._cursor()
    staedte = list(a.staedte)
    z = bestand.zeitraum(cur, a, staedte)
    kat = a.kat_sql
    extra = a.kat_param

    def faelle(von, bis, tag: str) -> dict[tuple[str, Any], int]:
        """Faelle je Stadt und Periode; ``tag`` legt einen Vorjahrestag auf diese Achse."""
        sql = (f"SELECT stadt, {z.periode_sql(tag)}, count(*) FILTER (fall) FROM fakt "
               f"WHERE stadt IN $staedte AND tag BETWEEN $a AND $b {kat} GROUP BY 1, 2")
        return {(s, m): int(n) for s, m, n in cur.execute(sql, benutzt(
            sql, {"staedte": staedte, "a": von, "b": bis, **z.param, **extra})).fetchall()}

    jetzt = faelle(z.von, z.bis, "tag")
    # Das Vorjahr auf derselben Achse: jeder Tag ein Jahr spaeter gelegt. Nur
    # bis ein Jahr Spanne (serving.dashboard.zeitraum).
    vorjahr_vorhanden = z.vergleich_moeglich and any(
        z.fenster.get(s) and z.mit_daten(s, vor_einem_jahr(z.von), vor_einem_jahr(z.bis))
        for s in staedte)
    vorher = (faelle(vor_einem_jahr(z.von), vor_einem_jahr(z.bis),
                     "(tag + INTERVAL 1 YEAR)::DATE") if vorjahr_vorhanden else {})

    licht_kat = _licht_kategorien(bestand, cur, staedte, z, kat, extra)
    ergebnis = []
    for s in staedte:
        status = z.status(s)
        werte = [None if st == "fehlt" else jetzt.get((s, m), 0)
                 for st, m in zip(status, z.starts)]
        vorstatus = z.status_vorjahr(s)
        basis = next((i for i, st in enumerate(status) if st == "voll" and werte[i]), None)
        index = [None if basis is None or v is None else round(v * 100.0 / werte[basis], 1)
                 for v in werte]
        ergebnis.append({
            "stadt": s, "name": STADTNAMEN[s], "zeitzone": ZEITZONEN[s],
            "monate": [m.isoformat() for m in z.starts],
            "jetzt": werte, "status": status,
            "vorjahr": ([None if st == "fehlt" else vorher.get((s, m), 0)
                         for st, m in zip(vorstatus, z.starts)]
                        if vorjahr_vorhanden else [None] * len(z.starts)),
            "status_vorjahr": vorstatus,
            "index": {"basis": z.starts[basis].isoformat() if basis is not None else None,
                      "werte": index},
            "heatmap": _heatmap(cur, s, z, kat, extra),
            "licht": _licht(bestand, cur, s, z, kat, extra, licht_kat),
        })
    return {
        "auswahl": a.json,
        "achse": z.json(),
        "vergleich": {"jahr": a.tag_von.year, "vorjahr": a.tag_von.year - 1,
                      "vorjahr_vorhanden": vorjahr_vorhanden,
                      "von": vor_einem_jahr(z.von).isoformat(),
                      "bis": vor_einem_jahr(z.bis).isoformat(),
                      "grund": (None if z.vergleich_moeglich else
                                "Kein Vorjahresvergleich über mehr als ein Jahr: "
                                "Das Jahr davor überlappte den Zeitraum selbst.")},
        "staedte": ergebnis,
        "wochentage": list(WOCHENTAGE),
        "stand": bestand.stand,
    }


def _heatmap(cur, stadt: str, z, kat: str, extra: dict) -> dict[str, Any]:
    """Durchschnittliche Faelle je Wochentag und Stunde, ohne Platzhalterzeiten."""
    p = {"stadt": stadt, **z.param, **extra}
    tage = dict(cur.execute(
        "SELECT isodow(tag), count(DISTINCT tag) FROM fakt WHERE stadt = $stadt "
        "AND tag BETWEEN $von AND $bis GROUP BY 1", {"stadt": stadt, **z.param}).fetchall())
    matrix = [[0.0] * 24 for _ in WOCHENTAGE]
    for wt, h, n in cur.execute(
            f"SELECT isodow(tag), stunde, count(*) FILTER (fall) FROM fakt WHERE stadt = $stadt "
            f"AND tag BETWEEN $von AND $bis AND NOT platzhalter {kat} GROUP BY 1, 2", p).fetchall():
        if tage.get(wt):
            matrix[wt - 1][h] = round(n / tage[wt], 2)
    platzhalter, alle = cur.execute(
        f"SELECT count(*) FILTER (fall AND platzhalter), count(*) FILTER (fall) "
        f"FROM fakt WHERE stadt = $stadt AND tag BETWEEN $von AND $bis {kat}", p).fetchone()
    return {
        "werte": matrix,
        "max": max(max(z) for z in matrix),
        "tage": int(sum(tage.values())),
        "platzhalter": int(platzhalter),
        "platzhalter_anteil": round(platzhalter * 100.0 / alle, 1) if alle else None,
    }


def _licht_kategorien(bestand, cur, staedte: list[str], z, kat: str,
                      extra: dict) -> list[str]:
    """Die haeufigsten Kategorien ueber alle gewaehlten Staedte zusammen.

    Einmal fuer alle Staedte, nicht je Stadt: Sonst stuende in »Beide« eine
    Kategorie aus Chicagos acht haeufigsten bei Detroit leer, obwohl Detroit
    dort Faelle hat.
    """
    if getattr(bestand, "ohne_licht", "nicht geladen"):
        return []
    return [k for (k,) in cur.execute(
        f"SELECT kategorie FROM licht WHERE stadt IN $staedte AND tag BETWEEN $von AND $bis "
        f"{kat} AND gruppe IN ('hell', 'dunkel') GROUP BY 1 HAVING sum(faelle) > 0 "
        f"ORDER BY sum(faelle) DESC, 1 LIMIT {LICHT_KATEGORIEN}",
        {"staedte": staedte, **z.param, **extra}).fetchall()]


def _licht(bestand, cur, stadt: str, z, kat: str, extra: dict,
           auswahl: list[str]) -> dict[str, Any]:
    """Faelle nach Tageslicht, Dunkelheit und unsicherer Uhrzeit (siehe Moduldoku)."""
    from serving.dashboard import kategorie_de

    grund = getattr(bestand, "ohne_licht", "Der Sonnenstand ist nicht geladen.")
    if grund:
        return {"vorhanden": False, "grund": grund}
    p = {"stadt": stadt, **z.param, **extra}
    je_gruppe = dict(cur.execute(
        f"SELECT gruppe, sum(faelle) FROM licht WHERE stadt = $stadt AND tag BETWEEN $von AND $bis "
        f"{kat} GROUP BY 1", p).fetchall())
    gruppen = {g: int(je_gruppe.get(g, 0)) for g, _ in LICHTGRUPPEN}
    alle = sum(gruppen.values())
    hell_h, dunkel_h = cur.execute(
        "SELECT coalesce(sum(hell), 0), coalesce(sum(dunkel), 0) FROM lichtstunden "
        "WHERE stadt = $stadt AND tag BETWEEN $von AND $bis", {"stadt": stadt, **z.param}).fetchone()

    def anteil(n: int, von: int) -> float | None:
        return round(n * 100.0 / von, 1) if von else None

    je_kategorie = {k: (int(h or 0), int(d or 0)) for k, h, d in cur.execute(
        f"SELECT kategorie, sum(faelle) FILTER (gruppe = 'hell'), "
        f"sum(faelle) FILTER (gruppe = 'dunkel') FROM licht "
        f"WHERE stadt = $stadt AND tag BETWEEN $von AND $bis AND kategorie IN $auswahl {kat} "
        f"GROUP BY 1", p | {"auswahl": auswahl or [""]}).fetchall()}
    kategorien = []
    for k in auswahl:
        hell, dunkel = je_kategorie.get(k, (0, 0))
        kategorien.append({"kategorie": k, "name": kategorie_de(k), "faelle": hell + dunkel,
                           "dunkel_anteil": anteil(dunkel, hell + dunkel)})
    bekannt = gruppen["hell"] + gruppen["dunkel"]
    return {
        "vorhanden": True,
        "faelle": alle,
        "gruppen": [{"gruppe": g, "name": n, "faelle": gruppen[g], "anteil": anteil(gruppen[g], alle)}
                    for g, n in LICHTGRUPPEN],
        "dunkel_anteil": anteil(gruppen["dunkel"], bekannt),
        "stunden": {"hell": round(float(hell_h), 1), "dunkel": round(float(dunkel_h), 1)},
        "je_stunde": {"hell": round(gruppen["hell"] / hell_h, 2) if hell_h else None,
                      "dunkel": round(gruppen["dunkel"] / dunkel_h, 2) if dunkel_h else None},
        "kategorien": kategorien,
    }
