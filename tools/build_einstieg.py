"""Schreibt ``docs/einstieg.html`` - die Seite, mit der ein Analyst anfaengt.

    python tools/build_einstieg.py

**Warum eine Datei und kein Dienst.** Die Frage *"was liegt hier, und wo frage
ich es?"* braucht keinen laufenden Prozess. Sie braucht eine Antwort, die
stimmt. Dieselbe Bauart wie ``build_referenz.py`` und
``build_architekturbilder.py``: lesen, rendern, schreiben. Die Seite oeffnet
man mit einem Doppelklick.

**Was darauf steht und was bewusst nicht.** Alles auf der Seite folgt aus dem
Release - Kennung, Vertragsversionen, Zeilenzahlen, Kennzahlen, Gueteziffern.
Nichts davon ist abgeschrieben; alles wird beim Erzeugen gemessen.

**Kein Zeitstempel und kein eingefrorener Dienstzustand.** Beides waere
verlockend ("zuletzt geprueft am ..."), und beides machte die Seite
unreproduzierbar: Zweimal erzeugt, zweimal andere Bytes, und ein Vergleich
sagte nichts mehr. Schlimmer noch waere ein festgehaltener Dienstzustand -
eine Seite, die behauptet, Kibana laufe, weil es vor drei Tagen lief. Fuer
alles Lebendige nennt die Seite deshalb den **Befehl**
(``serving.pruefe_stand``) und nicht sein Ergebnis von gestern.

**Die Rate je 1'000 ist nicht neu erfunden.** Sie kommt aus
``gold_pipeline.raten_je_stadt`` - derselben Abfrage, mit der
``tests/test_aenderungen.py`` die Zahl im Aenderungsprotokoll bewacht: nur
Delikte in Tracts, die einer der beiden Staedte zugeordnet sind, geteilt durch
deren Einwohnerzahl. Eine zweite Definition waere eine zweite Wahrheit.

**Und sie nennt ihr Jahr.** Ein Release traegt seit dem 4.10.2026 sechs
Jahrgaenge. Die Zeilenzahlen der Tabellen sind deshalb der ganze Bestand - das
ist die Frage "was liegt hier?" -, die Staedtetabelle dagegen zeigt
``gold_pipeline.RATENJAHR``. Beides auf einer Seite gemischt und beides
unbeschriftet waere das eine Versehen, das diese Seite nicht machen darf:
sechs Jahre Zaehler auf einem Jahr Nenner ergeben 500,7 je 1'000, und die Zahl
sieht aus wie eine Zahl.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any

PROJEKT = Path(__file__).resolve().parents[1]
ZIEL = PROJEKT / "docs" / "einstieg.html"

#: Die Zugaenge, die beschickt werden. ClickHouse steht weiter im
#: ``docker-compose.yml`` und fehlt hier absichtlich: Seit dem 5.10.2026 wird
#: es nicht mehr geladen, und ein Knopf zu einer leeren Datenbank ist
#: schlimmer als keiner - er sieht aus wie eine Auskunft. Das ganze
#: Sternschema liegt in Elasticsearch (``serving.load_elasticsearch``).
#: Kleine Zahlen schreibt diese Seite aus - wie die uebrigen Dokumente.
ZAHLWORT = ("kein", "ein", "zwei", "drei", "vier", "fünf", "sechs", "sieben",
            "acht", "neun", "zehn")


def dienste() -> tuple[tuple, ...]:
    """Die Zugaenge, die beschickt werden - samt der Zahl der Bretter.

    Eine Funktion und keine Konstante, weil **eine** Angabe darin gemessen
    wird statt getippt: wie viele Dashboards es gibt. Bis zum 11.10.2026
    stand hier "Drei Bretter", waehrend ``BRETTER`` vier fuehrte, und
    ``tests/test_einstieg.py`` hielt die Seite nur gegen ihren Generator -
    beide sagten dasselbe Falsche.
    """
    from serving.build_kibana import BRETTER

    bretter = ZAHLWORT[len(BRETTER)].capitalize()
    return (
    ("Elasticsearch", "http://localhost:19200/fact_offense/_search?pretty",
     "Das Sternschema, sechs Indizes",
     "Volltext über die Beschreibung, Umkreissuche über den Ort — und seit "
     "dem 5.10.2026 auch Kalender, Wetter und die Einwohnerzahlen je Tract "
     "und Vintage. Ein Alias je Gold-Tabelle, jeder mit der Release-Kennung "
     "dahinter.",
     'GET /fact_offense/_search\n{"query": {\n'
     '  "geo_distance": {\n'
     '    "distance": "500m",\n'
     '    "standort": {\n'
     '      "lat": 41.8827,\n'
     '      "lon": -87.6233}}}}'),
    ("Kibana", "http://localhost:15601/app/dashboards", "Die Dashboards",
     f"{bretter} Bretter, als Code gebaut — eines davon rechnet die Rate "
     "je 1'000 Einwohner in der Kachel. Die "
     "Suchleiste oben durchsucht die Beschreibung der Quelle.",
     None),
    ("DuckDB", "https://duckdb.org/docs/stable/clients/cli/overview",
     "SQL über den Stern, mit Joins",
     "Für alles, was nicht auf einem Brett steht. Tat und Nenner verbindet "
     "seit 8.19 auch Elasticsearch (ES|QL <code>LOOKUP JOIN</code>) — hier "
     "liegt dafür der ganze Stern als SQL. Die Sichten liegen in "
     "<code>data/serving/analyse.duckdb</code> und zeigen auf die "
     "Parquet-Dateien — keine Kopie, kein Dienst.",
     "SELECT reporting_city,\n       nibrs_family,\n       count(*) AS n\n"
     "FROM fact_offense\nGROUP BY 1, 2\nORDER BY n DESC\nLIMIT 10"),
    )

#: Die Schwellen des Publish-Gates. Stehen hier, damit die Seite die
#: Gueteziffern nicht nur nennt, sondern einordnet.
GATE = {"inside_city": ("mindestens", 90.0), "exact": ("mindestens", 85.0),
        "unmapped": ("höchstens", 1.0)}


def zahl(n: Any) -> str:
    """Schweizer Tausendertrennung - wie ueberall sonst im Projekt."""
    return f"{n:,}".replace(",", "'") if isinstance(n, int) else str(n)


def komma(x: float, stellen: int = 1) -> str:
    return f"{x:.{stellen}f}".replace(".", ",")


def groesse(bytes_: int) -> str:
    """``0,0 MB`` sagt nichts - unterhalb der Aufloesung lieber eine Schranke."""
    mb = bytes_ / 1_048_576
    return komma(mb) if mb >= 0.05 else "&lt; 0,1"


def messe(verzeichnis: Path) -> dict[str, Any]:
    """Alles, was die Seite zeigt - aus dem Release gelesen, nicht abgeschrieben."""
    from storage.duckdb import verbinde

    from gold_pipeline import RATENJAHR, raten_je_stadt
    from storage import parquet_spalten

    gold = verzeichnis / "gold"
    fakt = gold / "dataset=fact_offense/part-0001.parquet"
    tract = gold / "dataset=dim_tract/part-0001.parquet"
    acs = gold / "dataset=dim_tract_acs/part-0001.parquet"
    con = verbinde()
    try:
        datensaetze = []
        for pfad in sorted(gold.glob("dataset=*/part-0001.parquet")):
            name = pfad.parent.name.removeprefix("dataset=")
            anzahl = con.execute(
                f"SELECT count(*) FROM read_parquet('{pfad}')").fetchone()[0]
            # Nicht ueber DESCRIBE: DuckDB ergaenzt aus dem Pfad zwei
            # Hive-Spalten, ``dataset`` und ``release``, die in keiner Datei
            # stehen. Die erste Fassung dieser Seite zeigte deshalb ueberall
            # zwei Spalten zu viel. Begruendung in ``storage.parquet``.
            spalten = len(parquet_spalten(pfad))
            datensaetze.append((name, anzahl, spalten,
                                pfad.stat().st_size))

        # Die Staedtetabelle steht in gold_pipeline.raten_je_stadt. Hier stand
        # bis zum 3.10.2026 eine Kopie mit dem Kommentar "dieselbe Abfrage wie
        # in tests/test_aenderungen.py - eine Definition". Zwei Fassungen sind
        # keine Definition; seit Vertrag 6 waeren es neun gewesen. Der
        # Jahresfilter steckt mit darin, seit ein Release sechs Jahrgaenge
        # traegt.
        staedte = [
            (z[0], z[1], z[3], z[4]) for z in con.execute(raten_je_stadt(
                f"read_parquet('{fakt}')", f"read_parquet('{tract}')",
                f"read_parquet('{acs}')")).fetchall()
        ]

        guete = con.execute(f"""
            SELECT reporting_city,
              round(100.0 * count(*) FILTER (WHERE geo_status = 'inside_city')
                    / count(*), 2),
              round(100.0 * count(*) FILTER (WHERE mapping_status = 'exact')
                    / count(*), 2),
              round(100.0 * count(*) FILTER (WHERE mapping_status = 'unmapped')
                    / count(*), 2)
            FROM read_parquet('{fakt}') GROUP BY 1 ORDER BY 1
        """).fetchall()

        zeitraum = con.execute(
            f"SELECT min(date), max(date) FROM read_parquet('{fakt}')"
        ).fetchone()
    finally:
        con.close()
    return {"datensaetze": datensaetze, "staedte": staedte, "guete": guete,
            "zeitraum": zeitraum, "ratenjahr": RATENJAHR}


# --------------------------------------------------------------------------
# Das Blatt
# --------------------------------------------------------------------------


STIL = """
  :root {
    --paper:#f6f8fa; --surface:#ffffff; --sunk:#eef1f5; --ink:#141b25;
    --muted:#5b6a7d; --rule:#d7dee7; --rule-2:#bfc9d6;
    --accent:#17627f; --accent-soft:#dcecf3;
    --signal:#9c5010; --signal-soft:#f6e7d6;
    --gut:#1d6b4f; --gut-soft:#dcefe6;
    --f-head:"IBM Plex Serif",Georgia,"Times New Roman",serif;
    --f-body:"IBM Plex Sans",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
    --f-mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
    color-scheme: light;
  }
  * { box-sizing:border-box; }
  body {
    margin:0; background:var(--sunk); color:var(--ink);
    font-family:var(--f-body); -webkit-font-smoothing:antialiased;
    line-height:1.5;
  }
  main { max-width:1040px; margin:0 auto; padding:32px 16px 72px; }

  header.kopf { border-bottom:2px solid var(--ink); padding-bottom:18px; margin-bottom:28px; }
  .eyebrow {
    font-family:var(--f-mono); font-size:11px; letter-spacing:.12em;
    text-transform:uppercase; color:var(--muted); margin:0 0 8px;
  }
  h1 { font-family:var(--f-head); font-weight:600; font-size:34px; margin:0 0 10px;
       letter-spacing:-.015em; line-height:1.1; }
  .lead { color:var(--muted); margin:0; max-width:68ch; }
  .lead strong { color:var(--ink); font-weight:600; }

  section { margin:0 0 34px; }
  h2 { font-family:var(--f-head); font-weight:600; font-size:20px; margin:0 0 4px; }
  .unter { color:var(--muted); font-size:14px; margin:0 0 14px; max-width:68ch; }

  table { border-collapse:collapse; width:100%; background:var(--surface);
          border:1px solid var(--rule); font-size:14px; }
  caption { text-align:left; color:var(--muted); font-size:13px; padding:0 0 6px; }
  th, td { padding:7px 12px; text-align:left; border-bottom:1px solid var(--rule); }
  thead th { background:var(--paper); font-weight:600; font-size:12.5px;
             letter-spacing:.02em; color:var(--muted); }
  tbody tr:last-child td { border-bottom:0; }
  td.n, th.n { text-align:right; font-family:var(--f-mono);
               font-variant-numeric:tabular-nums; }
  td.name { font-family:var(--f-mono); }

  .karten { display:grid; gap:14px; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); }
  .karte { background:var(--surface); border:1px solid var(--rule);
           border-top:3px solid var(--accent); padding:16px 18px 18px; }
  .karte h3 { font-family:var(--f-head); font-size:17px; margin:0 0 2px; }
  .karte .rolle { font-family:var(--f-mono); font-size:11px; letter-spacing:.08em;
                  text-transform:uppercase; color:var(--accent); margin:0 0 10px; }
  .karte p { font-size:13.5px; color:var(--muted); margin:0 0 12px; }
  .karte a.knopf {
    display:inline-block; font-family:var(--f-mono); font-size:12.5px;
    color:var(--accent); text-decoration:none; border:1px solid var(--rule-2);
    padding:5px 11px; background:var(--paper);
  }
  .karte a.knopf:hover { background:var(--accent-soft); border-color:var(--accent); }

  pre { font-family:var(--f-mono); font-size:12.5px; line-height:1.55;
        background:var(--paper); border:1px solid var(--rule);
        padding:11px 13px; overflow-x:auto; margin:0 0 12px; }
  code { font-family:var(--f-mono); font-size:.93em; }

  .marke { font-family:var(--f-mono); font-size:11px; padding:2px 7px;
           border-radius:3px; font-weight:500; white-space:nowrap; }
  .marke.gut { background:var(--gut-soft); color:var(--gut); }
  .marke.warn { background:var(--signal-soft); color:var(--signal); }

  .hinweis { border-left:3px solid var(--signal); background:var(--signal-soft);
             padding:11px 15px; font-size:13.5px; margin:14px 0 0; }
  .hinweis strong { font-weight:600; }

  dl.fakten { display:grid; grid-template-columns:auto 1fr; gap:5px 18px;
              margin:0; font-size:14px; }
  dl.fakten dt { color:var(--muted); }
  dl.fakten dd { margin:0; font-family:var(--f-mono); }

  footer { border-top:1px solid var(--rule); margin-top:40px; padding-top:14px;
           color:var(--muted); font-size:12.5px; }
  @media (max-width:640px) { h1 { font-size:26px; } main { padding:22px 16px 48px; } }
"""


def tabelle(kopf: list[str], zeilen: list[list[str]],
            rechts: set[int] = frozenset(), beschriftung: str = "") -> str:
    kopfzeile = "".join(
        f'<th class="n">{html.escape(t)}</th>' if i in rechts
        else f"<th>{html.escape(t)}</th>" for i, t in enumerate(kopf))
    koerper = []
    for zeile in zeilen:
        zellen = "".join(
            f'<td class="n">{z}</td>' if i in rechts else f"<td>{z}</td>"
            for i, z in enumerate(zeile))
        koerper.append(f"<tr>{zellen}</tr>")
    bes = f"<caption>{html.escape(beschriftung)}</caption>" if beschriftung else ""
    return (f"<table>{bes}<thead><tr>{kopfzeile}</tr></thead>"
            f"<tbody>{''.join(koerper)}</tbody></table>")


def abschnitt_guete(guete: list[tuple]) -> str:
    zeilen = []
    for stadt, inside, exakt, unmapped in guete:
        zellen = [f"<strong>{html.escape(stadt.capitalize())}</strong>"]
        for wert, schluessel in ((inside, "inside_city"), (exakt, "exact"),
                                 (unmapped, "unmapped")):
            richtung, schwelle = GATE[schluessel]
            haelt = (wert >= schwelle if richtung == "mindestens"
                     else wert <= schwelle)
            marke = "gut" if haelt else "warn"
            zellen.append(f'{komma(wert, 2)} %&nbsp;'
                          f'<span class="marke {marke}">'
                          f'{richtung} {komma(schwelle, 0)}</span>')
        zeilen.append(zellen)
    return tabelle(
        ["Stadt", "im Stadtgebiet verortet", "exakt auf NIBRS", "nicht zugeordnet"],
        zeilen, rechts={1, 2, 3},
        beschriftung="Dieselben Grössen, gegen die das Publish-Gate prüft. "
                     "Gold entsteht nur, wenn jede Stadt jede Schwelle hält.")


def seite(kennung: str, manifest: dict, mass: dict) -> str:
    code = manifest.get("code_version", {})
    vertraege = manifest.get("contract_versions", {})
    von, bis = mass["zeitraum"]

    fakten = {
        "Release": kennung,
        "erstellt": manifest.get("created_at_utc", "—"),
        "Zeitraum der Daten": f"{von} bis {bis}",
        "Vertrag gold": str(vertraege.get("gold", "—")),
        "Code": (code.get("git_commit", "—")[:12]
                 + (" (dirty)" if code.get("git_dirty") else "")),
        "Eingangs-Fingerabdruck": manifest.get("input_fingerprint", "—")[:16] + "…",
    }
    fakten_html = "".join(
        f"<dt>{html.escape(k)}</dt><dd>{html.escape(v)}</dd>"
        for k, v in fakten.items())

    datensaetze = tabelle(
        ["Datensatz", "Zeilen", "Spalten", "MB"],
        [[f'<span class="name">{html.escape(n)}</span>', zahl(z), zahl(s),
          groesse(b)]
         for n, z, s, b in mass["datensaetze"]],
        rechts={1, 2, 3})

    staedte = tabelle(
        ["Stadt", "Delikte", "Einwohner", "je 1'000"],
        [[f"<strong>{html.escape(s.capitalize())}</strong>", zahl(d), zahl(e),
          f"<strong>{komma(r)}</strong>"]
         for s, d, e, r in mass["staedte"]],
        rechts={1, 2, 3})

    karten = []
    for name, url, rolle, text, beispiel in dienste():
        block = f"<pre>{html.escape(beispiel)}</pre>" if beispiel else ""
        karten.append(
            f'<article class="karte"><p class="rolle">{html.escape(rolle)}</p>'
            f"<h3>{html.escape(name)}</h3><p>{text}</p>{block}"
            f'<a class="knopf" href="{html.escape(url)}">{html.escape(name)} öffnen</a>'
            f"</article>")

    return f"""<!DOCTYPE html>
<html lang="de">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Einstieg · Release {html.escape(kennung)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:wght@500;600&display=swap">
<style>{STIL}</style>
<main>
<header class="kopf">
  <p class="eyebrow">Chicago · Detroit · Vergleich der Kriminalitätslage</p>
  <h1>Einstieg</h1>
  <p class="lead">Was hier liegt, und wo man es fragt. Alles auf dieser Seite
  ist aus dem Release <strong>{html.escape(kennung)}</strong> gemessen — keine
  Zahl ist abgeschrieben. Die Seite wird erzeugt, nicht gepflegt.</p>
</header>

<section>
  <h2>Der Stand</h2>
  <p class="unter">Jede Zahl im Projekt lässt sich auf genau dieses Release
  zurückführen. Der Code-Verweis sagt, mit welchem Stand es gebaut wurde.</p>
  <dl class="fakten">{fakten_html}</dl>
</section>

<section>
  <h2>Was drin liegt</h2>
  <p class="unter">Ein Sternschema: eine Faktentabelle, vier Dimensionen.</p>
  {datensaetze}
</section>

<section>
  <h2>Die beiden Städte im Jahrgang {mass["ratenjahr"]}</h2>
  <p class="unter">Gezählt werden nur Delikte in Tracts, die einer der beiden
  Städte zugeordnet sind — sonst verglichen man Stadtgebiete verschiedenen
  Zuschnitts. Und nur die des Jahrgangs {mass["ratenjahr"]}: Eine Rate braucht
  einen Zeitraum, das Release trägt sechs.</p>
  {staedte}
  <p class="hinweis"><strong>Absolute Zahlen führen hier in die Irre.</strong>
  Chicago hat in fast jeder Kategorie mehr Fälle und ist zugleich viermal so
  gross. Erst die Rate macht die beiden vergleichbar.</p>
</section>

<section>
  <h2>Güte der Daten</h2>
  <p class="unter">Keine Zahl ohne ihre Unsicherheit.</p>
  {abschnitt_guete(mass["guete"])}
</section>

<section>
  <h2>Wo man fragt</h2>
  <p class="unter">Drei Zugänge, je nach Frage. Die beiden ersten Verweise
  zeigen auf den lokalen Verbund — sie tragen nur, wenn er läuft.</p>
  <div class="karten">{''.join(karten)}</div>
</section>

<section>
  <h2>Starten</h2>
  <p class="unter">Alles in diesen Diensten ist abgeleitet und wegwerfbar.
  Keine Zahl der Abgabe hängt an ihnen — sie hängt am Release.</p>
  <pre>docker compose up -d
python -m serving.load_elasticsearch
python -m serving.build_kibana</pre>
  <p class="unter">Ob danach alle geladenen Orte denselben Stand zeigen, beantwortet
  ein Befehl. Diese Seite beantwortet es <em>nicht</em>: Sie ist eine Datei und
  weiss nichts davon, was gerade läuft — ein festgehaltenes „alles in Ordnung"
  wäre eine Behauptung über die Vergangenheit.</p>
  <pre>python -m serving.pruefe_stand</pre>
</section>

<footer>
  Erzeugt von <code>tools/build_einstieg.py</code> aus Release
  {html.escape(kennung)}. Nicht von Hand ändern — der nächste Lauf
  überschreibt es. Weiter: <a href="referenz/index.html">Code-Referenz</a> ·
  <a href="architektur-ist-und-ziel.md">Architektur</a>
</footer>
</main>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    sys.path.insert(0, str(PROJEKT / "src" / "crime"))
    from serving.load_elasticsearch import aktuelles_release

    zerleger = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    zerleger.add_argument("--data-root", type=Path, default=PROJEKT / "data")
    zerleger.add_argument("--ziel", type=Path, default=ZIEL)
    args = zerleger.parse_args(argv)

    kennung, verzeichnis = aktuelles_release(args.data_root)
    manifest = json.loads(
        (verzeichnis / "release.json").read_text(encoding="utf-8"))

    args.ziel.parent.mkdir(parents=True, exist_ok=True)
    args.ziel.write_text(seite(kennung, manifest, messe(verzeichnis)),
                         encoding="utf-8")
    # Kurz, wo es geht - aber ein ``--ziel`` darf auch ausserhalb des
    # Projekts liegen, und dann wirft ``relative_to``. Der Test baut genau
    # dorthin.
    try:
        name = args.ziel.relative_to(PROJEKT)
    except ValueError:
        name = args.ziel
    print(f"{name} geschrieben "
          f"({args.ziel.stat().st_size // 1024} KB, Release {kennung})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
