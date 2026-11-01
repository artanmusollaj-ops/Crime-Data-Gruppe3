"""Schreibt ``docs/einstieg.html`` - die Seite, mit der ein Analyst anfaengt.

    python -m serving.build_einstieg
    python -m serving.build_einstieg --adressen server \
        --ziel /app/startseite/index.html

**Warum eine Datei und kein Dienst.** Die Frage *"was liegt hier, und wo frage
ich es?"* braucht keinen laufenden Prozess. Sie braucht eine Antwort, die
stimmt. Dieselbe Bauart wie ``build_referenz.py`` und
``build_architekturbilder.py``: lesen, rendern, schreiben. Die Seite oeffnet
man mit einem Doppelklick.

Seit dem 12.10.2026 liefert sie auf ``srv01`` zusaetzlich ein nginx aus
(``urbancrime-start``, FR-31). Das aendert nichts an dem Satz darueber: Der
Dienst **liefert** eine fertige Datei, er erzeugt sie nicht und fragt nichts
ab. Was er ausliefert, entsteht am Ende des Datenlaufs aus dem Release, das
dort wirklich liegt - nicht aus dem des letzten Checkouts.

**Warum dieses Modul in ``serving`` liegt und nicht unter ``tools/``.** Bis
zum 12.10.2026 war es ein Entwicklerwerkzeug neben ``build_referenz``. Mit dem
ausgelieferten Dienst ist es ein Serving-Artefakt wie ``build_kibana``,
``load_elasticsearch`` und ``pruefe_stand`` - und es *muss* hier liegen:
``.dockerignore`` haelt ``tools/`` aus dem Baukontext heraus, im Abbild gab es
dieses Modul also nicht. Importiert hat es ohnehin nur aus dem Paket und aus
der Standardbibliothek; der Umzug kostete keinen Import.

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
from pathlib import Path
from typing import Any

from manifeste import projektwurzel

#: Wohin die Seite ohne ``--ziel`` geht, **relativ** zur Projektwurzel.
#: Aufgeloest wird sie erst beim Aufruf (``vorgaben()``) und nicht beim
#: Import: Ein absoluter Pfad als Modulkonstante stand in der erzeugten
#: Code-Referenz als Vorgabewert - also der Pfad dieses Rechners in einer
#: Datei, die im Repository liegt, und ein Test faengt genau das.
ZIEL_IM_PROJEKT = Path("docs") / "einstieg.html"


def ziel_vorgabe() -> Path | None:
    """Wohin die Seite ohne ``--ziel`` geht - beim Aufruf bestimmt.

    Die Wurzel kommt aus ``manifeste.projektwurzel`` und nicht aus einer
    gezaehlten Elternebene: Dieses Modul lag bis zum 12.10.2026 unter
    ``tools/`` (eine Ebene unter der Wurzel) und liegt jetzt drei tiefer, im
    Abbild editierbar nach ``/app/src/crime`` installiert. Eine Zahl waere an
    jedem der drei Orte eine andere, und ``PROJECT_ROOT`` sticht sie ohnehin.

    ``None``, wenn sich keine Wurzel erkennen laesst - dann verlangt der
    Aufruf ``--ziel``, statt irgendwohin zu schreiben. Die **Datenwurzel**
    steht hier bewusst nicht daneben: Sie kommt aus ``storage.for_root``, wie
    bei jedem anderen Stufenmodul.
    """
    wurzel = projektwurzel()
    return wurzel / ZIEL_IM_PROJEKT if wurzel else None

#: Die Zugaenge, die beschickt werden. ClickHouse steht weiter im
#: ``docker-compose.yml`` und fehlt hier absichtlich: Seit dem 5.10.2026 wird
#: es nicht mehr geladen, und ein Knopf zu einer leeren Datenbank ist
#: schlimmer als keiner - er sieht aus wie eine Auskunft. Das ganze
#: Sternschema liegt in Elasticsearch (``serving.load_elasticsearch``).
#: Kleine Zahlen schreibt diese Seite aus - wie die uebrigen Dokumente.
ZAHLWORT = ("kein", "ein", "zwei", "drei", "vier", "fünf", "sechs", "sieben",
            "acht", "neun", "zehn", "elf", "zwölf", "dreizehn", "vierzehn",
            "fünfzehn", "sechzehn", "siebzehn", "achtzehn", "neunzehn",
            "zwanzig")


#: Die beiden Fassungen der Adressen. ``lokal`` ist die Vorgabe und die, die
#: im Repository liegt; ``server`` baut die Seite, die ``urbancrime-start``
#: auf ``srv01`` ausliefert.
#:
#: **Warum eine Flagge und keine Umgebungsvariable.** Beides waere "eine
#: Variable"; die Flagge steht aber an der Stelle, die sie setzt - in
#: ``docker/srv01-datenlauf.sh`` -, und ``tests/test_srv01_datenlauf.py``
#: liest sie dort aus dem Skript und haelt sie gegen ``--help``. Eine
#: Umgebungsvariable waere unsichtbar und koennte, wenn sie in einer ``.env``
#: liegen bleibt, die im Repository abgelegte Seite stillschweigend auf
#: Serveradressen umstellen - und der Zweitlauf-Waechter faende einen
#: Unterschied, dessen Ursache nicht im Aufruf steht.
FASSUNGEN = ("lokal", "server")


def dienste(fassung: str = "lokal") -> tuple[tuple, ...]:
    """Die Zugaenge - je Eintrag Name, Adresse, Rolle, Text, Beispiel, Vermerk.

    Eine Funktion und keine Konstante, weil **zwei** Angaben darin gemessen
    werden statt getippt: wie viele Dashboards es gibt, und welche Adressen
    gelten. Bis zum 11.10.2026 stand hier "Drei Bretter", waehrend ``BRETTER``
    vier fuehrte, und ``tests/test_einstieg.py`` hielt die Seite nur gegen
    ihren Generator - beide sagten dasselbe Falsche.

    **Seit dem 1.11.2026 nennen die beiden Fassungen verschiedene Dienste
    (C-9).** Auf srv01 ersetzt das eigene Dashboard Elasticsearch und Kibana;
    die Serverfassung fuehrt die beiden nicht mehr, weil ein Knopf auf einen
    Dienst, den es dort nicht gibt, schlimmer ist als keiner. Lokal stehen
    sie neben dem Dashboard.

    **Die Admin-Konsole ist seit dem 1.11.2026 ein Zugang.** Bis dahin stand
    sie hier als benannter Platzhalter mit der Marke *künftig* und ohne
    Verweis - richtig, solange es den Dienst nicht gab, und seit dem
    31.10.2026 falsch: Seither laeuft sie auf srv01. Auf dem Server traegt
    sie jetzt einen Knopf; lokal nennt sie den Befehl, weil die lokale
    Konsole ihre Adresse erst beim Start samt Einmal-Token ausgibt. Die
    Marke *künftig* und ``ist_kuenftig`` bleiben fuer den naechsten Dienst,
    der zuerst nur einen Namen hat.

    Der letzte Wert je Eintrag ist entweder ``None`` - dann traegt die Karte
    einen Knopf auf ihre Adresse - oder ein Paar ``(Marke, Adresse)``, das
    anstelle des Knopfes steht. Genau eines von beiden ist gesetzt; so kann
    keine Karte auf etwas verweisen, das in dieser Fassung nicht erreichbar
    ist.
    """
    from serving.build_kibana import BRETTER

    if fassung not in FASSUNGEN:
        raise ValueError(f"--adressen kennt nur {FASSUNGEN}, nicht {fassung!r}")
    server = fassung == "server"
    bretter = ZAHLWORT[len(BRETTER)].capitalize()

    # Elasticsearch gibt es nur noch lokal. Bis zum 1.11.2026 trug die
    # Serverfassung hier statt eines Knopfes die stapelinterne Adresse
    # (FR-11: dort nicht geroutet); seit C-9 laeuft es auf srv01 nicht mehr.
    es_adresse = "http://localhost:19200/fact_offense/_search?pretty"
    es_vermerk = None
    es_weg = ""

    # Jupyter laeuft in **keiner** der beiden Fassungen von selbst: Die
    # Entwicklungsfassung kennt den Dienst gar nicht (docker-compose.yml
    # traegt clickhouse, elasticsearch, kibana), und auf srv01 haelt ihn ein
    # ``profiles: [analyse]`` aus ``up -d`` heraus. Ein Knopf ohne diesen Satz
    # ergaebe 404 oder "Verbindung abgelehnt", und die Karte wuesste es.
    jupyter_start = (
        "<strong>Zeitweilig:</strong> Der Dienst trägt ein Compose-Profil und "
        "läuft erst, wenn ihn jemand startet — <code>docker compose -f "
        "docker-compose.srv01.yml --profile analyse up -d jupyter</code>."
        if server else
        "<strong>Von Hand zu starten:</strong> Der Entwicklungsverbund kennt "
        "keinen Notebook-Server; der Verweis trägt, sobald in diesem "
        "Verzeichnis <code>jupyter lab</code> läuft.")

    def web(dienst: str, pfad: str, port: int) -> str:
        """Dieselbe Adresse in beiden Fassungen - aus einem Muster, nicht getippt.

        Das Muster auf dem Server ist das, an dem die **eine**
        Access-Anwendung haengt (FR-22): ``urbancrime-<dienst>.datenwerft.ch``.
        Ein Hostname, der daneben entsteht, waere ein ungeschuetzter Dienst.
        """
        return (f"https://urbancrime-{dienst}.datenwerft.ch{pfad}" if server
                else f"http://localhost:{port}{pfad}")

    dashboard_weg = (
        " Auf diesem Server ersetzt es seit dem 1.11.2026 Elasticsearch und "
        "Kibana." if server else
        " <strong>Von Hand zu starten:</strong> <code>python -m "
        "serving.dashboard</code> — es liest dieselbe Ablage wie die Strecke.")
    dashboard = (
        "Dashboard", web("dashboard", "/", 8050), "Die Bretter, ohne Kibana",
        "Überblick, Zeitverlauf, Geografie, Deliktstruktur und Datenqualität "
        "nach Artans Entwürfen — Raten je 1'000 Einwohner nach derselben "
        "Regel wie Gold, Fälle vorn. Es liest das aktive Release und lädt ein "
        "neues von selbst nach." + dashboard_weg,
        None, None)

    elastic = () if server else (
    ("Elasticsearch", es_adresse,
     "Das Sternschema, sechs Indizes",
     "Volltext über die Beschreibung, Umkreissuche über den Ort — und seit "
     "dem 5.10.2026 auch Kalender, Wetter und die Einwohnerzahlen je Tract "
     "und Vintage. Ein Alias je Gold-Tabelle, jeder mit der Release-Kennung "
     "dahinter." + es_weg,
     'GET /fact_offense/_search\n{"query": {\n'
     '  "geo_distance": {\n'
     '    "distance": "500m",\n'
     '    "standort": {\n'
     '      "lat": 41.8827,\n'
     '      "lon": -87.6233}}}}',
     es_vermerk),
    ("Kibana", web("kibana", "/app/dashboards", 15601), "Die Dashboards",
     f"{bretter} Bretter, als Code gebaut — eines davon rechnet die Rate "
     "je 1'000 Einwohner in der Kachel. Die "
     "Suchleiste oben durchsucht die Beschreibung der Quelle.",
     None, None),
    )

    return elastic + (dashboard,) + (
    ("DuckDB", "https://duckdb.org/docs/stable/clients/cli/overview",
     "SQL über den Stern, mit Joins",
     "Für alles, was nicht auf einem Brett steht."
     + ("" if server else
        " Tat und Nenner verbindet seit 8.19 auch Elasticsearch (ES|QL "
        "<code>LOOKUP JOIN</code>) — hier liegt dafür der ganze Stern als SQL.")
     + " Die Sichten liegen in "
     "<code>data/serving/analyse.duckdb</code> und zeigen auf die "
     "Parquet-Dateien — keine Kopie, kein Dienst.",
     "SELECT reporting_city,\n       nibrs_family,\n       count(*) AS n\n"
     "FROM fact_offense\nGROUP BY 1, 2\nORDER BY n DESC\nLIMIT 10",
     None),
    ("Jupyter", web("jupyter", "/lab", 8888), "Notebooks, lesend",
     "Die drei belegenden Notebooks auf dem Release: Sternschema, Kontrollen, "
     "Quellbewegung. <code>data/</code> hängt schreibgeschützt, gelesen wird "
     "die selbständige <code>analyse.duckdb</code> aus dem Release — nicht "
     "die mit den Sichten, die zeigen auf Pfade dieses Rechners. Der "
     "Arbeitsbereich daneben ist beschreibbar, die mitgelieferten Notebooks "
     "sind Vorlagen. " + jupyter_start,
     None, None),
    ("Admin-Konsole",
     "https://urbancrime-admin.datenwerft.ch/" if server else None,
     "Betrieb und Kontrolle",
     "Die Engineering-Konsole: Mapping- und Einstellungsvorschläge mit "
     "Vier-Augen-Review, Kandidaten-Releases und ihre Freigabe, die Läufe "
     "und der Stand der Dienste. Änderungen gehen als Pull Request ins "
     "Repository, nicht direkt in die Daten."
     + (" Auf diesem Server läuft sie seit dem 31.10.2026 hinter derselben "
        "Access-Anwendung." if server else
        " <strong>Von Hand zu starten:</strong> Der Befehl gibt die Adresse "
        "samt Einmal-Token aus."),
     None, None if server else ("lokal", "python -m platform_admin serve")),
    )

def ist_kuenftig(eintrag: tuple) -> bool:
    """Ein Eintrag, hinter dem noch kein Dienst steht.

    Erkannt an seiner Marke und nicht an einer zweiten Angabe daneben: Ein
    Eintrag ohne Adresse, aber mit der Marke *kuenftig* ist genau der Fall,
    den die Seite kennzeichnen muss. Zwei Angaben koennten sich
    widersprechen, eine kann es nicht.
    """
    vermerk = eintrag[5]
    return bool(vermerk) and vermerk[0] == "künftig"


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
        # Lokal mit Absicht: Diese Seite liest ein **eingesetztes**
        # Release - `release holen --einsetzen` hat es an die festen
        # Pfade gelegt, bevor dieser Schritt laeuft
        # (`docker/srv01-datenlauf.sh`). Sie liest daneben `stat()` fuer
        # die Dateigroesse; das geht nur auf einer wirklichen Datei.
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
  /* Steht anstelle des Knopfes, wenn es in dieser Fassung keine Adresse gibt,
     die der Browser des Lesenden erreicht: ein Dienst nur im Stapelnetz, ein
     Dienst, den es noch nicht gibt. Ein Knopf waere dort ein toter Link. */
  .karte p.vermerk { font-family:var(--f-mono); font-size:12px; margin:0;
                     color:var(--muted); }
  .karte p.vermerk code { font-size:12px; }

  pre { font-family:var(--f-mono); font-size:12.5px; line-height:1.55;
        background:var(--paper); border:1px solid var(--rule);
        padding:11px 13px; overflow-x:auto; margin:0 0 12px; }
  code { font-family:var(--f-mono); font-size:.93em; }

  .marke { font-family:var(--f-mono); font-size:11px; padding:2px 7px;
           border-radius:3px; font-weight:500; white-space:nowrap; }
  .marke.gut { background:var(--gut-soft); color:var(--gut); }
  .marke.warn { background:var(--signal-soft); color:var(--signal); }
  .marke.kuenftig { background:var(--signal-soft); color:var(--signal); }
  .marke.intern { background:var(--sunk); color:var(--muted); }

  .hinweis { border-left:3px solid var(--signal); background:var(--signal-soft);
             padding:11px 15px; font-size:13.5px; margin:14px 0 0; }
  .hinweis strong { font-weight:600; }

  dl.fakten { display:grid; grid-template-columns:auto 1fr; gap:5px 18px;
              margin:0; font-size:14px; }
  dl.fakten dt { color:var(--muted); }
  dl.fakten dd { margin:0; font-family:var(--f-mono); }

  /* Die Grenzen der Aussage (FR-33). Fliesstext, nicht Kennzahlen: Jede
     steht in einer eigenen Zeile, damit keine im Absatz untergeht. */
  dl.grenzen { margin:0; }
  dl.grenzen dt { font-weight:600; margin-top:14px; }
  dl.grenzen dt:first-child { margin-top:0; }
  dl.grenzen dd { margin:4px 0 0; font-size:13.5px; color:var(--ink);
                  border-left:2px solid var(--rule); padding-left:13px; }

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


def seite(kennung: str, manifest: dict, mass: dict,
          fassung: str = "lokal") -> str:
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

    zugaenge = dienste(fassung)
    karten = []
    for eintrag in zugaenge:
        name, url, rolle, text, beispiel, vermerk = eintrag
        block = f"<pre>{html.escape(beispiel)}</pre>" if beispiel else ""
        if url:
            fuss = (f'<a class="knopf" href="{html.escape(url)}">'
                    f"{html.escape(name)} öffnen</a>")
        else:
            marke, adresse = vermerk
            klasse = "kuenftig" if ist_kuenftig(eintrag) else "intern"
            fuss = (f'<p class="vermerk">'
                    f'<span class="marke {klasse}">{html.escape(marke)}</span> '
                    f"<code>{html.escape(adresse)}</code></p>")
        karten.append(
            f'<article class="karte"><p class="rolle">{html.escape(rolle)}</p>'
            f"<h3>{html.escape(name)}</h3><p>{text}</p>{block}"
            f"{fuss}</article>")

    # Gezaehlt, nicht getippt - dieselbe Lehre wie bei den Brettern: Bis zum
    # 11.10.2026 stand im Generator eine Zahl, die der Liste darunter nicht
    # mehr entsprach, und kein Waechter sah es.
    jetzt = [d for d in zugaenge if not ist_kuenftig(d)]
    lokale = sum(1 for d in zugaenge if d[1] and "localhost" in d[1])
    geroutet = sum(1 for d in zugaenge if d[1] and "urbancrime-" in d[1])
    nachsatz = (
        f" Die {ZAHLWORT[lokale]} Verweise auf <code>localhost</code> tragen "
        "nur, solange das Gemeinte auf diesem Rechner läuft — je Karte steht "
        "dabei, was dafür zu starten ist." if lokale else
        f" Die {ZAHLWORT[geroutet]} Verweise auf <code>urbancrime-*</code> "
        "liegen hinter der Access-Anwendung, und DuckDB zeigt auf seine "
        "Dokumentation im Netz.")
    vorbehalt = ("".join(
        f" Die <strong>{html.escape(d[0])}</strong> gibt es noch nicht — ihr "
        f"Eintrag nennt den vorgesehenen Namen und verweist auf nichts."
        for d in zugaenge if ist_kuenftig(d)))

    fuss_weiter = (
        '<a href="referenz/index.html">Code-Referenz</a> · '
        '<a href="architektur-ist-und-ziel.md">Architektur</a>'
        if fassung == "lokal" else
        "Code-Referenz und Architektur liegen im Repository — ausgeliefert "
        "wird hier nur diese Seite.")

    # Auch die Befehle haengen an der Fassung. Ein "docker compose up -d" auf
    # der ausgelieferten Seite waere kein Fehler mit Folgen, aber ein Satz,
    # der dort nicht stimmt: Auf srv01 gibt es eine eigene Beschreibung, und
    # die Lader laufen als Stapellauf darin.
    if fassung == "lokal":
        aufbauen = ("docker compose up -d\n"
                    "python -m serving.load_elasticsearch\n"
                    "python -m serving.build_kibana\n"
                    "python -m serving.dashboard")
        pruefen = "python -m serving.pruefe_stand"
    else:
        aufbauen = ("docker compose -f docker-compose.srv01.yml up -d\n"
                    "docker/srv01-datenlauf.sh delta")
        pruefen = ("docker compose -f docker-compose.srv01.yml run --rm "
                   "pipeline \\\n    python -m serving.pruefe_stand")

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
  <h2>Was diese Zahlen nicht sagen</h2>
  <p class="unter">Drei Grenzen, und keine davon ist ein Mangel der Daten —
  sie gelten für jede Polizeistatistik und begrenzen, was aus dieser hier
  folgt.</p>
  <dl class="grenzen">
    <dt>Erfassung ist nicht Kriminalität</dt>
    <dd>Beide Quellen sind Verwaltungsdaten einer Polizeibehörde: Was
    <em>angezeigt</em> und <em>erfasst</em> wurde. Wie viel daneben
    unangezeigt bleibt, steht nicht darin und lässt sich daraus nicht
    schätzen. Unterschiedliches Anzeigeverhalten, unterschiedliche
    Polizeipräsenz und unterschiedliche Erfassungsregeln sehen in dieser
    Tabelle genauso aus wie unterschiedliche Kriminalität — und zwei Städte
    mit zwei Behörden und zwei Codesystemen sind genau der Fall, in dem das
    zählt.</dd>
    <dt>Tatort ist nicht Wohnort</dt>
    <dd>Jedes Delikt zählt dort, wo es geschah. Der Nenner der Rate sind
    die <em>Einwohner</em> dieses Tracts, der Zähler alle Anwesenden: Ein
    Geschäftsviertel mit wenigen Bewohnern und vielen Besuchern bekommt
    deshalb eine hohe Rate, ohne dass dort mehr passiert als zu erwarten
    wäre. Weder Täter noch Betroffene müssen dort wohnen.</dd>
    <dt>Ökologischer Fehlschluss</dt>
    <dd>Diese Zahlen gelten für Flächen, nicht für Menschen. Aus einer hohen
    Rate in einem Tract folgt nichts über irgendeine Person darin, und ein
    Zusammenhang zwischen Tract-Merkmalen und der Rate ist keiner zwischen
    Merkmalen von Menschen und ihrem Verhalten. Wer ihn so liest, zieht
    einen Schluss, den die Aggregation nicht erlaubt.</dd>
  </dl>
</section>

<section>
  <h2>Güte der Daten</h2>
  <p class="unter">Keine Zahl ohne ihre Unsicherheit.</p>
  {abschnitt_guete(mass["guete"])}
</section>

<section>
  <h2>Wo man fragt</h2>
  <p class="unter">{ZAHLWORT[len(jetzt)].capitalize()} Zugänge, je nach
  Frage.{nachsatz}{vorbehalt}</p>
  <div class="karten">{''.join(karten)}</div>
</section>

<section>
  <h2>Starten</h2>
  <p class="unter">Alles in diesen Diensten ist abgeleitet und wegwerfbar.
  Keine Zahl der Abgabe hängt an ihnen — sie hängt am Release.</p>
  <pre>{html.escape(aufbauen)}</pre>
  <p class="unter">Ob danach alle geladenen Orte denselben Stand zeigen, beantwortet
  ein Befehl. Diese Seite beantwortet es <em>nicht</em>: Sie ist eine Datei und
  weiss nichts davon, was gerade läuft — ein festgehaltenes „alles in Ordnung"
  wäre eine Behauptung über die Vergangenheit.</p>
  <pre>{html.escape(pruefen)}</pre>
</section>

<footer>
  Erzeugt von <code>python -m serving.build_einstieg</code> aus Release
  {html.escape(kennung)}. Nicht von Hand ändern — der nächste Lauf
  überschreibt es. Weiter: {fuss_weiter}
</footer>
</main>
</html>
"""


def kommandozeile() -> argparse.ArgumentParser:
    zerleger = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # Ohne Wert: ``for_root(None)`` nimmt die eingestellte lokale Wurzel -
    # derselbe Weg wie in ``load_elasticsearch`` und ``pruefe_stand``. Eine
    # eigene Vorgabe hier waere der einzige Ort im Paket, der sie raet.
    zerleger.add_argument("--data-root", type=Path, default=None)
    zerleger.add_argument("--ziel", type=Path, default=ziel_vorgabe())
    # Die eine Umschaltung, und sie steht im Aufruf: ``lokal`` ist die
    # Vorgabe, weil die im Repository abgelegte Seite die des
    # Entwicklungsrechners ist. ``server`` setzt der Datenlauf auf srv01.
    zerleger.add_argument("--adressen", choices=FASSUNGEN, default="lokal",
                          help="welche Dienstadressen auf der Seite stehen")
    return zerleger


def main(argv: list[str] | None = None) -> int:
    from storage import for_root

    from serving.load_elasticsearch import aktuelles_release

    args = kommandozeile().parse_args(argv)
    from storage.verwaltet import sperre
    sperre(for_root(args.data_root).local_root, worker_erlaubt=True)
    from storage.analysesitzung import schreibzugriff
    # Serving schreibt nicht nach bronze/silver/gold: Die Sperre haelt
    # Analysen fern, der Herkunftsnachweis (.analyse/stand.json) bleibt gueltig.
    with schreibzugriff(for_root(args.data_root).local_root, invalidieren=False):
        if args.ziel is None:
            print("Keine Projektwurzel erkannt - --ziel angeben (oder "
                  "PROJECT_ROOT setzen).")
            return 2

        kennung, verzeichnis = aktuelles_release(for_root(args.data_root).local_root)
        manifest = json.loads(
            (verzeichnis / "release.json").read_text(encoding="utf-8"))

        args.ziel.parent.mkdir(parents=True, exist_ok=True)
        args.ziel.write_text(
            seite(kennung, manifest, messe(verzeichnis), args.adressen),
            encoding="utf-8")
        # Kurz, wo es geht - aber ein ``--ziel`` darf auch ausserhalb des
        # Projekts liegen, und dann wirft ``relative_to``. Der Test baut genau
        # dorthin.
        wurzel = projektwurzel()
        try:
            name = args.ziel.relative_to(wurzel) if wurzel else args.ziel
        except ValueError:
            name = args.ziel
        print(f"{name} geschrieben "
              f"({args.ziel.stat().st_size // 1024} KB, Release {kennung})")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
