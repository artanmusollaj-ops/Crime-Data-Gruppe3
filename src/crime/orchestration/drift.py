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

Der Exit-Code ist immer 0. Fehlt eine Tabelle, steht "nicht gebaut" in der
Zeile; das Werkzeug ist auch dann nuetzlich, wenn die Strecke vorher
abgebrochen ist.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, NamedTuple

import duckdb


AENDERUNGEN = Path("docs") / "AENDERUNGEN.md"
ANFANG = "## Der Stand in Zahlen"

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
    silver = data_root / "silver" / "dataset=crime_offense" / "part-0001.parquet"
    gold = data_root / "gold" / "dataset=fact_offense" / "part-0001.parquet"
    tract = data_root / "gold" / "dataset=dim_tract" / "part-0001.parquet"
    werte: dict[str, float] = {}
    con = duckdb.connect()
    try:
        if silver.exists():
            werte["silver_rows"] = con.execute(
                f"SELECT count(*) FROM read_parquet('{silver}')").fetchone()[0]
        if gold.exists():
            werte["gold_rows"] = con.execute(
                f"SELECT count(*) FROM read_parquet('{gold}')").fetchone()[0]
            for stadt, faelle in con.execute(f"""
                SELECT reporting_city, count(*) FILTER (counts_case)
                FROM read_parquet('{gold}') GROUP BY 1
            """).fetchall():
                werte[f"{stadt}_faelle"] = faelle
        if gold.exists() and tract.exists():
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


def tabelle(alle: list[Zeile], fingerabdruck: str | None = None) -> str:
    """Markdown - fuer die Job-Zusammenfassung in GitHub Actions und stdout."""
    kopf = ["## Drift gegen den dokumentierten Stand", ""]
    if fingerabdruck:
        kopf.append(f"Frischer Lauf, Fingerabdruck der Eingaben `{fingerabdruck}`.")
    kopf += [
        "*Dokumentiert* ist der Kopf von `docs/AENDERUNGEN.md` (der Referenzstand), "
        "*gemessen* der Lauf von heute. Die Drift ist keine Farbe, sondern eine Zahl: "
        "So weit haben sich die Quellen seit dem Referenzstand bewegt.",
        "",
        "| Grösse | dokumentiert | gemessen | Drift | % |",
        "| --- | ---: | ---: | ---: | ---: |",
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
        kopf.append(f"| {z.name} | {dok} | {mess} | {drift} | {prozent} |")
    return "\n".join(kopf) + "\n"


def als_json(alle: list[Zeile], fingerabdruck: str | None) -> dict[str, Any]:
    return {
        "fingerprint": fingerabdruck,
        "measures": {
            z.schluessel: {"documented": z.dokumentiert, "measured": z.gemessen,
                           "drift": z.drift, "drift_percent": z.prozent}
            for z in alle
        },
    }


def fingerabdruck_von(data_root: Path) -> str | None:
    protokoll = data_root / "pipeline_run.json"
    if not protokoll.exists():
        return None
    try:
        return json.loads(protokoll.read_text(encoding="utf-8")).get("fingerprint")
    except (OSError, json.JSONDecodeError):
        return None


def arguments() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Zeigt je Groesse, wie weit der dokumentierte Stand vom "
                    "gebauten entfernt ist. Scheitert nie."
    )
    p.add_argument("--data-root", type=Path, default=Path("data"))
    p.add_argument("--aenderungen", type=Path, default=AENDERUNGEN)
    p.add_argument("--summary", type=Path, default=None, metavar="DATEI",
                   help="Markdown anhaengen, etwa an $GITHUB_STEP_SUMMARY")
    p.add_argument("--json", type=Path, default=None, metavar="DATEI",
                   help="Ergebnis als JSON schreiben")
    return p.parse_args()


def main() -> int:
    args = arguments()
    dok = dokumentiert(args.aenderungen.read_text(encoding="utf-8"))
    mess = gemessen(args.data_root)
    alle = zeilen(dok, mess)
    fingerabdruck = fingerabdruck_von(args.data_root)
    text = tabelle(alle, fingerabdruck)
    print(text)
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as f:
            f.write(text + "\n")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(als_json(alle, fingerabdruck), indent=2,
                                        ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
