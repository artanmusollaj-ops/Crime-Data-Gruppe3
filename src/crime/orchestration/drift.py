"""Wie weit die dokumentierten Zahlen von einem frischen Lauf entfernt sind.

    python -m orchestration.drift                          # Tabelle auf stdout
    python -m orchestration.drift --summary "$GITHUB_STEP_SUMMARY" --json data/drift.json

Gelesen wird der Kopfabschnitt *Der Stand in Zahlen* aus ``docs/AENDERUNGEN.md``
- dieselben Zahlen, die die Waechter mit dem Marker ``referenzstand`` lokal
gegen den Referenzstand halten. Hier wird nichts gehalten, nur gemessen.

Warum das ein eigenes Werkzeug ist und nicht einfach ein roter Test: Der
woechentliche Datenlauf laedt die Quellen frisch, und die bewegen sich - Detroit
aendert Eintraege noch Jahre nach der Tat, Chicago liefert Deltas. Ein Test, der
die dokumentierte Zahl gegen den frischen Stand haelt, ist dort **jede Woche
rot**, und ein Alarm, der immer klingelt, ist keiner. Die Frage, die der
Datenlauf beantworten soll, ist nicht "stimmt die Zahl noch?", sondern **"wie
weit ist sie weg?"** - und die Antwort ist eine Zahl je Groesse, keine Farbe.

**Mit Schwelle.** Eine Tabelle, die niemand ansehen muss, ist der umgekehrte
Fehler. Deshalb wird der Lauf rot, wenn die Drift eine Toleranz ueberschreitet
- und die Toleranz ist das, was auf einer Folie stuende: eine **Rate je
1'000** bewegt sich um mindestens 0,1 (die Rundung, in der sie zitiert wird),
oder eine **Zeilen- oder Fallzahl** um mehr als 1 Prozent. Das Wochenrauschen
der Quellen liegt weit darunter (gemessen am 13.9.: Raten 0,0; Zahlen bis
0,13 Prozent); ein Quellenausfall, ein halber Full Load, eine Schemaaenderung
liegen weit darueber.

Fehlt eine Tabelle, steht "nicht gebaut" in der Zeile - das ist keine Drift,
die Strecke davor ist dann schon rot. Exit 1 nur bei ueberschrittener
Toleranz; ``--nur-melden`` schaltet das ab.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, NamedTuple

from storage import for_root
from storage import duckdb as storage_duckdb


AENDERUNGEN = Path("docs") / "AENDERUNGEN.md"
ANFANG = "## Der Stand in Zahlen"

# Die Toleranz. Raten absolut (je 1'000 Einwohner, eine Nachkommastelle),
# Zahlen relativ in Prozent.
MAX_RATE = 0.1
MAX_PROZENT = 1.0

# Jede Groesse: Schluessel, Beschriftung, Muster im Kopfabschnitt, Nachkommastellen.
# Die Muster sind dieselben wie in tests/test_aenderungen.py - dort halten sie,
# hier messen sie.
GROESSEN: tuple[tuple[str, str, str, int], ...] = (
    ("silver_rows", "`silver/crime_offense`, Zeilen",
     r"`silver/crime_offense` \| ([0-9']+) Zeilen", 0),
    ("gold_rows", "`gold/fact_offense`, Taten",
     r"`gold/fact_offense` \| \*\*([0-9']+)\*\* Zeilen", 0),
    ("chicago_delikte", "Chicago, Delikte in der Stadt",
     r"\| Chicago \| ([0-9']+) Delikte", 0),
    ("chicago_einwohner", "Chicago, Einwohner",
     r"\| Chicago \| [0-9']+ Delikte · ([0-9']+) Einwohner", 0),
    ("chicago_rate", "Chicago, je 1'000 (Tatkorn)",
     r"\| Chicago \|.*?\*\*([0-9]+,[0-9])\*\* je 1'000", 1),
    ("detroit_delikte", "Detroit, Delikte in der Stadt",
     r"\| Detroit \| ([0-9']+) Delikte", 0),
    ("detroit_einwohner", "Detroit, Einwohner",
     r"\| Detroit \| [0-9']+ Delikte · ([0-9']+) Einwohner", 0),
    ("detroit_rate", "Detroit, je 1'000 (Tatkorn)",
     r"\| Detroit \|.*?\*\*([0-9]+,[0-9])\*\* je 1'000", 1),
    ("chicago_faelle", "Chicago, Fälle (Fallkorn)",
     r"\| Fallkorn.*?Chicago ([0-9']+)", 0),
    ("detroit_faelle", "Detroit, Fälle (Fallkorn)",
     r"\| Fallkorn.*?Detroit ([0-9']+)", 0),
    ("detroit_rate_fallkorn", "Detroit, je 1'000 (Fallkorn)",
     r"\| Fallkorn.*?Detroit \*\*([0-9]+,[0-9])\*\* je 1'000", 1),
)


class Zeile(NamedTuple):
    schluessel: str
    name: str
    dokumentiert: float | None
    gemessen: float | None
    stellen: int

    @property
    def drift(self) -> float | None:
        if self.dokumentiert is None or self.gemessen is None:
            return None
        return round(self.gemessen - self.dokumentiert, self.stellen)

    @property
    def prozent(self) -> float | None:
        if self.drift is None or not self.dokumentiert:
            return None
        return round(100 * self.drift / self.dokumentiert, 2)

    @property
    def ist_rate(self) -> bool:
        return self.stellen > 0

    def ueber(self, max_rate: float = MAX_RATE, max_prozent: float = MAX_PROZENT) -> bool:
        """Ob die Drift die Toleranz ueberschreitet. Nicht gebaut heisst nein."""
        if self.drift is None:
            return False
        if self.ist_rate:
            return abs(self.drift) >= max_rate
        # Ungerundet: 1'001 auf 100'000 sind 1,001 Prozent, und die zwei
        # Nachkommastellen der Anzeige duerfen die Schwelle nicht verstecken.
        return abs(100 * self.drift / self.dokumentiert) > max_prozent


def zahl(text: str) -> float:
    return float(text.replace("'", "").replace(",", "."))


def dokumentiert(text: str) -> dict[str, float]:
    """Die Zahlen aus dem Kopfabschnitt; was nicht drinsteht, fehlt im Ergebnis."""
    anfang = text.index(ANFANG)
    ende = text.index("\n## ", anfang + len(ANFANG))
    kopf = text[anfang:ende]
    gefunden: dict[str, float] = {}
    for schluessel, _, muster, _ in GROESSEN:
        treffer = re.search(muster, kopf)
        if treffer:
            gefunden[schluessel] = zahl(treffer.group(1))
    return gefunden


def gemessen(data_root: Path) -> dict[str, float]:
    """Dieselben Groessen aus den gebauten Tabellen; was nicht gebaut ist, fehlt."""
    ablage = for_root(data_root)
    rel = {
        "silver": "silver/dataset=crime_offense/part-0001.parquet",
        "gold": "gold/dataset=fact_offense/part-0001.parquet",
        "tract": "gold/dataset=dim_tract/part-0001.parquet",
    }
    da = {name: ablage.exists(r) for name, r in rel.items()}
    silver, gold, tract = (ablage.resolve_read_path(rel[n]) for n in ("silver", "gold", "tract"))
    werte: dict[str, float] = {}
    con = storage_duckdb.connect(ablage.config)
    try:
        if da["silver"]:
            werte["silver_rows"] = con.execute(
                f"SELECT count(*) FROM read_parquet('{silver}')").fetchone()[0]
        if da["gold"]:
            werte["gold_rows"] = con.execute(
                f"SELECT count(*) FROM read_parquet('{gold}')").fetchone()[0]
            for stadt, faelle in con.execute(f"""
                SELECT reporting_city, count(*) FILTER (counts_case)
                FROM read_parquet('{gold}') GROUP BY 1
            """).fetchall():
                werte[f"{stadt}_faelle"] = faelle
        if da["gold"] and da["tract"]:
            for stadt, delikte, einwohner, rate, rate_fall in con.execute(f"""
                WITH e AS (
                    SELECT city, sum(population) AS n
                    FROM read_parquet('{tract}') WHERE city IS NOT NULL GROUP BY 1
                )
                SELECT t.city, count(*), any_value(e.n),
                       round(count(*) * 1000.0 / any_value(e.n), 1),
                       round(count(*) FILTER (f.counts_case) * 1000.0 / any_value(e.n), 1)
                FROM read_parquet('{gold}') f
                JOIN read_parquet('{tract}') t ON t.geoid = f.tract_geoid
                JOIN e ON e.city = t.city
                GROUP BY 1
            """).fetchall():
                werte[f"{stadt}_delikte"] = delikte
                werte[f"{stadt}_einwohner"] = einwohner
                werte[f"{stadt}_rate"] = rate
                if stadt == "detroit":
                    werte["detroit_rate_fallkorn"] = rate_fall
    finally:
        con.close()
    return werte


def zeilen(dok: dict[str, float], mess: dict[str, float]) -> list[Zeile]:
    return [Zeile(s, name, dok.get(s), mess.get(s), stellen)
            for s, name, _, stellen in GROESSEN]


def format_zahl(wert: float | None, stellen: int, vorzeichen: bool = False) -> str:
    if wert is None:
        return "—"
    if stellen == 0:
        text = f"{int(round(wert)):,}".replace(",", "'")
    else:
        text = f"{wert:.{stellen}f}".replace(".", ",")
    if vorzeichen and wert > 0:
        text = "+" + text
    return text


def ueberschritten(alle: list[Zeile], max_rate: float = MAX_RATE,
                   max_prozent: float = MAX_PROZENT) -> list[Zeile]:
    return [z for z in alle if z.ueber(max_rate, max_prozent)]


def tabelle(alle: list[Zeile], fingerabdruck: str | None = None, *,
            max_rate: float = MAX_RATE, max_prozent: float = MAX_PROZENT) -> str:
    """Markdown - fuer die Job-Zusammenfassung in GitHub Actions und stdout."""
    kopf = ["## Drift gegen den dokumentierten Stand", ""]
    if fingerabdruck:
        kopf.append(f"Frischer Lauf, Fingerabdruck der Eingaben `{fingerabdruck}`.")
    kopf += [
        "*Dokumentiert* ist der Kopf von `docs/AENDERUNGEN.md` (der Referenzstand), "
        "*gemessen* der Lauf von heute. Die Drift ist eine Zahl, keine Farbe - "
        f"rot wird es erst über der Toleranz: Raten ab {format_zahl(max_rate, 1)} je 1'000, "
        f"Zahlen über {format_zahl(max_prozent, 1)} %.",
        "",
        "| Grösse | dokumentiert | gemessen | Drift | % | Toleranz |",
        "| --- | ---: | ---: | ---: | ---: | :---: |",
    ]
    for z in alle:
        if z.dokumentiert is None:
            dok, mess, drift, prozent = "nicht dokumentiert", format_zahl(z.gemessen, z.stellen), "—", "—"
        elif z.gemessen is None:
            dok, mess, drift, prozent = format_zahl(z.dokumentiert, z.stellen), "nicht gebaut", "—", "—"
        else:
            dok = format_zahl(z.dokumentiert, z.stellen)
            mess = format_zahl(z.gemessen, z.stellen)
            drift = format_zahl(z.drift, z.stellen, vorzeichen=True)
            prozent = format_zahl(z.prozent, 2, vorzeichen=True)
        toleranz = "**überschritten**" if z.ueber(max_rate, max_prozent) else "ok"
        kopf.append(f"| {z.name} | {dok} | {mess} | {drift} | {prozent} | {toleranz} |")
    zu_weit = ueberschritten(alle, max_rate, max_prozent)
    kopf.append("")
    if zu_weit:
        kopf.append(f"**{len(zu_weit)} Grösse(n) über der Toleranz** - Zeit, den "
                    "Referenzstand nachzuziehen oder die Quelle anzusehen: "
                    + ", ".join(z.name for z in zu_weit) + ".")
    else:
        kopf.append("Alle Grössen innerhalb der Toleranz.")
    return "\n".join(kopf) + "\n"


def als_json(alle: list[Zeile], fingerabdruck: str | None, *,
             max_rate: float = MAX_RATE, max_prozent: float = MAX_PROZENT) -> dict[str, Any]:
    return {
        "fingerprint": fingerabdruck,
        "tolerance": {"rate_abs": max_rate, "count_percent": max_prozent},
        "within_tolerance": not ueberschritten(alle, max_rate, max_prozent),
        "measures": {
            z.schluessel: {"documented": z.dokumentiert, "measured": z.gemessen,
                           "drift": z.drift, "drift_percent": z.prozent,
                           "exceeded": z.ueber(max_rate, max_prozent)}
            for z in alle
        },
    }


def fingerabdruck_von(data_root: Path) -> str | None:
    protokoll = data_root / "pipeline_run.json"
    if not protokoll.exists():
        return None
    try:
        # run_all schreibt input_fingerprint; die ersten 16 Zeichen genuegen,
        # so zeigt es auch der Controller selbst an.
        wert = json.loads(protokoll.read_text(encoding="utf-8")).get("input_fingerprint")
    except (OSError, json.JSONDecodeError):
        return None
    return str(wert)[:16] if wert else None


def arguments() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Zeigt je Groesse, wie weit der dokumentierte Stand vom "
                    "gebauten entfernt ist. Scheitert nie."
    )
    p.add_argument("--data-root", type=Path, default=None,
                   help="Wurzel der Schichten (Vorgabe: LOCAL_DATA_ROOT oder data)")
    p.add_argument("--aenderungen", type=Path, default=AENDERUNGEN)
    p.add_argument("--summary", type=Path, default=None, metavar="DATEI",
                   help="Markdown anhaengen, etwa an $GITHUB_STEP_SUMMARY")
    p.add_argument("--json", type=Path, default=None, metavar="DATEI",
                   help="Ergebnis als JSON schreiben")
    p.add_argument("--max-rate", type=float, default=MAX_RATE, metavar="X",
                   help=f"Toleranz fuer Raten je 1'000, absolut (Vorgabe {MAX_RATE})")
    p.add_argument("--max-prozent", type=float, default=MAX_PROZENT, metavar="P",
                   help=f"Toleranz fuer Zeilen- und Fallzahlen in Prozent (Vorgabe {MAX_PROZENT})")
    p.add_argument("--nur-melden", action="store_true",
                   help="auch ueber der Toleranz mit Exit 0 enden")
    return p.parse_args()


def main() -> int:
    args = arguments()
    dok = dokumentiert(args.aenderungen.read_text(encoding="utf-8"))
    mess = gemessen(for_root(args.data_root).local_root)
    alle = zeilen(dok, mess)
    fingerabdruck = fingerabdruck_von(for_root(args.data_root).local_root)
    schwellen = {"max_rate": args.max_rate, "max_prozent": args.max_prozent}
    text = tabelle(alle, fingerabdruck, **schwellen)
    print(text)
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as f:
            f.write(text + "\n")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(als_json(alle, fingerabdruck, **schwellen),
                                        indent=2, ensure_ascii=False), encoding="utf-8")
    zu_weit = ueberschritten(alle, **schwellen)
    if zu_weit and not args.nur_melden:
        # Als Annotation, damit es auf der Laufseite steht, nicht nur im Log.
        print("::error::Drift ueber der Toleranz: "
              + ", ".join(f"{z.name} ({format_zahl(z.drift, z.stellen, True)})" for z in zu_weit))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
