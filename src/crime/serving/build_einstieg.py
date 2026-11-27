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
import os
import re
import sys
from collections.abc import Mapping
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

#: Was die Fassung ``server`` einsetzt, und woher (FR-46, seit 14.11.2026).
#:
#: Bis dahin standen die Hostnamen ``urbancrime-<dienst>.datenwerft.ch`` und
#: die Befehle mit ``docker-compose.srv01.yml`` und ``docker/srv01-datenlauf.sh``
#: hier im Code - im Abbild also eine Annahme, dass es auf srv01 laeuft.
#: Jetzt setzt sie ``docker-compose.srv01.yml`` den Diensten ``pipeline`` und
#: ``worker``. Die **Flagge** waehlt weiter die Fassung (siehe oben); die
#: Umgebung liefert nur die Werte, und nur fuer ``server``. Die Fassung
#: ``lokal`` liest keine davon, eine liegen gebliebene ``.env`` aendert die
#: abgelegte Seite also nicht.
#:
#: ``EINSTIEG_ADRESSMUSTER`` traegt ``{dienst}`` an der Stelle des
#: Dienstnamens, ``STAPEL_COMPOSE`` die Compose-Datei, ``STAPEL_DATENLAUF``
#: das Skript, das den Datenlauf anstoesst.
SERVERWERTE = ("EINSTIEG_ADRESSMUSTER", "STAPEL_COMPOSE", "STAPEL_DATENLAUF")


class FehlendeServerangabe(ValueError):
    """Die Fassung ``server`` braucht einen Wert, den die Umgebung nicht hat."""


def serverwerte(umgebung: Mapping[str, str] | None = None) -> dict[str, str]:
    """Die drei Werte der Serverfassung - oder ein Abbruch mit dem Namen.

    Kein Rueckfall auf die Werte von srv01: Genau der war die Annahme, die
    FR-46 aus dem Abbild nimmt. Eine Seite mit fremden Hostnamen saehe in
    jeder anderen Umgebung richtig aus und fuehrte ins Leere.
    """
    umgebung = os.environ if umgebung is None else umgebung
    werte = {name: (umgebung.get(name) or "").strip() for name in SERVERWERTE}
    fehlend = [name for name, wert in werte.items() if not wert]
    if fehlend:
        raise FehlendeServerangabe(
            f"--adressen server braucht {', '.join(fehlend)} in der Umgebung "
            "(gesetzt in der Compose-Beschreibung des Stapels)")
    # Genau einmal: Ohne Platzhalter truegen alle Karten dieselbe Adresse,
    # mit zweien zerlegten geroutet_muster und kurzname am ersten, und die
    # Seite zaehlte "kein Verweise".
    if werte["EINSTIEG_ADRESSMUSTER"].count("{dienst}") != 1:
        raise FehlendeServerangabe(
            "EINSTIEG_ADRESSMUSTER muss {dienst} genau einmal enthalten, etwa "
            "https://{dienst}.example.org")
    return werte


def adresse(muster: str, dienst: str) -> str:
    """``{dienst}`` im Muster ersetzt - ohne ``str.format``, das an jeder
    anderen geschweiften Klammer im Muster scheiterte."""
    return muster.replace("{dienst}", dienst)


def geroutet_muster(muster: str) -> re.Pattern[str]:
    """Woran eine Adresse nach dem Muster zu erkennen ist."""
    vorn, _, hinten = muster.partition("{dienst}")
    return re.compile(re.escape(vorn) + r"[\w-]+" + re.escape(hinten))


def kurzname(muster: str) -> str:
    """Der Name, unter dem die Seite die gerouteten Adressen zusammenfasst.

    Der Teil des Hostnamens, der ``{dienst}`` traegt, mit ``*`` an dessen
    Stelle - aus ``https://urbancrime-{dienst}.example.org`` wird
    ``urbancrime-*``, das Muster, an dem eine Access-Anwendung haengt.
    """
    rest = muster.split("//", 1)[-1].split("/", 1)[0]
    teil = next((t for t in rest.split(".") if "{dienst}" in t), rest)
    return teil.replace("{dienst}", "*")


def dienste(fassung: str = "lokal",
            umgebung: Mapping[str, str] | None = None) -> tuple[tuple, ...]:
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

    Die Fassung ``server`` liest ihre Werte aus ``umgebung`` (ohne Angabe
    ``os.environ``, siehe ``SERVERWERTE``) und wirft
    ``FehlendeServerangabe``, wenn einer fehlt.
    """
    from serving.build_kibana import BRETTER

    if fassung not in FASSUNGEN:
        raise ValueError(f"--adressen kennt nur {FASSUNGEN}, nicht {fassung!r}")
    server = fassung == "server"
    werte = serverwerte(umgebung) if server else {}
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
        + html.escape(werte.get("STAPEL_COMPOSE", ""))
        + " --profile analyse up -d jupyter</code>."
        if server else
        "<strong>Von Hand zu starten:</strong> Der Entwicklungsverbund kennt "
        "keinen Notebook-Server; der Verweis trägt, sobald in diesem "
        "Verzeichnis <code>jupyter lab</code> läuft.")

    # Seit dem 27.11.2026 nimmt Jupyter auf dem Server die Anmeldung bei
    # Access (serving.jupyter_zugang). Ohne diesen Satz suchte, wer die Seite
    # liest, nach einem Token, das er nicht braucht und nicht sehen kann.
    jupyter_anmeldung = (
        "<strong>Anmeldung:</strong> Wer bei Cloudflare Access angemeldet ist, "
        "ist es auch in Jupyter — ohne Token. Das Token gilt nur noch für den "
        "Weg ohne Access, etwa über einen <code>ssh</code>-Tunnel. "
        if server else "")

    def web(dienst: str, pfad: str, port: int) -> str:
        """Dieselbe Adresse in beiden Fassungen - aus einem Muster, nicht getippt.

        Das Muster auf dem Server ist das, an dem die **eine**
        Access-Anwendung haengt (FR-22) - auf srv01
        ``urbancrime-<dienst>.datenwerft.ch``, gesetzt als
        ``EINSTIEG_ADRESSMUSTER``. Ein Hostname, der daneben entsteht, waere
        ein ungeschuetzter Dienst.
        """
        return (adresse(werte["EINSTIEG_ADRESSMUSTER"], dienst) + pfad if server
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
     "sind Vorlagen. " + jupyter_anmeldung + jupyter_start,
     None, None),
    ("Admin-Konsole",
     web("admin", "/", 0) if server else None,
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
        # Seit dem 12.11.2026 (E-2) vorn die Fallebene: Faelle und ihre Rate,
        # die Tatebene als zweite Rate daneben. Die Reihenfolge der Spalten
        # aus raten_je_stadt: Stadt, Taten, Faelle, Einwohner, Rate, Fallrate.
        staedte = [
            (z[0], z[2], z[3], z[5], z[4]) for z in con.execute(raten_je_stadt(
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


#: Woher Farben, Schrift und Logo kommen: aus dem Dashboard, als Paketdatei.
#: Seit dem 16.11.2026 sieht die Startseite aus wie das Dashboard, und die
#: Werte stehen nur dort. ``pyproject.toml`` liefert ``serving.dashboard``
#: mit ``static/*`` aus - die Dateien liegen also auch im Abbild.
DASHBOARD_STATISCH = ("dashboard", "static")


def dashboard_datei(name: str) -> str:
    """Eine Datei aus ``serving/dashboard/static`` als Text.

    Ueber ``importlib.resources`` und nicht ueber einen Pfad neben diesem
    Modul: So findet es die Datei auch in einem installierten Paket. Gelesen
    wird ueber ``serving`` und nicht ueber ``serving.dashboard`` - das
    Unterpaket zu importieren hiesse, die ganze Dashboard-Abfrage zu laden,
    um eine Stildatei zu lesen.
    """
    from importlib.resources import files

    return files("serving").joinpath(*DASHBOARD_STATISCH, name).read_text(
        encoding="utf-8")


def dashboard_wurzel() -> str:
    """Der ``:root``-Block aus ``dashboard.css``, wie er dort steht.

    Er traegt alle Farbvariablen und die Schrift. Eingesetzt und nicht
    abgeschrieben: Wechselt das Dashboard eine Farbe, traegt die naechste
    Startseite sie mit, ohne dass hier jemand etwas anfasst.
    """
    treffer = re.search(r":root\s*\{.*?\}", dashboard_datei("dashboard.css"),
                        re.DOTALL)
    if treffer is None:
        raise ValueError("dashboard.css hat keinen :root-Block - woher "
                         "nimmt die Startseite ihre Farben?")
    return treffer.group(0)


def dashboard_logo() -> str:
    """Das Logo aus dem Kopf des Dashboards (``index.html``), woertlich."""
    treffer = re.search(r'<svg class="logo".*?</svg>',
                        dashboard_datei("index.html"), re.DOTALL)
    if treffer is None:
        raise ValueError("index.html des Dashboards hat kein Logo mehr")
    return treffer.group(0)


#: Alles ausser Farben und Schrift - die kommen aus dem ``:root`` von
#: ``dashboard.css`` (``dashboard_wurzel``). Der Kopf uebernimmt die Regeln
#: von ``.kopf``, ``.marke``, ``.logo`` und ``.stand``. Die Karten (Abschnitte
#: und Zugaenge) folgen dem Vorbild von ``.brett`` und ``.tafel``: weiss,
#: abgerundet, Rand in ``--linie``. Der Knopf folgt ``.umschalter .an``
#: (``--blau``, weisse Schrift), der Hinweis dem Grund von ``.hinweis``, aber
#: ohne dessen Symbol. Uebernommen werden Regeln, nicht die Datei: Die
#: Startseite ist eine einzige Datei, die nginx aus einem anderen Host
#: ausliefert - ein Verweis auf ``/static/`` traefe dort nichts. Grautoene,
#: die das Dashboard als Zahl schreibt und nicht als Variable, stehen hier
#: ebenso als Zahl.
STIL = """
  * { box-sizing:border-box; }
  body { margin:0; background:var(--grund); color:var(--text); font-size:14px;
         line-height:1.5; }
  code, pre, td.n, td.name, dl.fakten dd {
    font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }

  .kopf { display:flex; justify-content:space-between; align-items:center;
          flex-wrap:wrap; gap:8px 16px;
          background:var(--navy); color:#fff; padding:12px 24px; }
  .marke { display:flex; align-items:center; gap:8px; font-size:20px; }
  .logo { width:26px; height:26px; fill:#4c9bff; }
  .produkt { font-weight:700; }
  .punkt, .bereich { color:#c9d3e0; }
  .stand { background:#2c3a4f; border-radius:6px; padding:6px 12px;
           font-size:13px; color:#dfe7f2; overflow-wrap:anywhere; }
  .stand b { color:#fff; }

  main { max-width:1080px; margin:0 auto; padding:16px 16px 8px; }
  .einleitung, section { background:var(--karte); border:1px solid var(--linie);
                         border-radius:10px; padding:16px 18px; margin:0 0 16px;
                         min-width:0; }
  .eyebrow { font-size:13px; color:var(--leise); margin:0 0 4px; }
  h1 { margin:0 0 8px; font-size:30px; }
  .lead { color:var(--leise); margin:0; max-width:76ch; }
  .lead strong { color:var(--text); }
  h2 { margin:0 0 4px; font-size:17px; }
  .unter { color:var(--leise); font-size:13px; margin:0 0 12px; max-width:76ch; }

  .rahmen { overflow-x:auto; border:1px solid var(--linie); border-radius:8px; }
  table { border-collapse:collapse; width:100%; font-size:14px; }
  caption { text-align:left; color:var(--leise); font-size:13px;
            padding:10px 12px 8px; }
  th, td { padding:8px 12px; text-align:left; border-top:1px solid var(--linie); }
  thead th { background:#f2f6fb; font-weight:600; vertical-align:bottom;
             border-top:0; }
  caption + thead th { border-top:1px solid var(--linie); }
  td.n, th.n { text-align:right; font-variant-numeric:tabular-nums;
               white-space:nowrap; }

  .karten { display:grid; gap:16px;
            grid-template-columns:repeat(auto-fit,minmax(min(300px,100%),1fr)); }
  .karte { border:1px solid var(--linie); border-left:4px solid var(--blau);
           border-radius:8px; padding:14px 14px 16px; min-width:0; }
  .karte h3 { font-size:17px; margin:0 0 4px; }
  .karte .rolle { font-size:12px; font-weight:600; color:var(--blau); margin:0 0 6px; }
  .karte p { font-size:13px; color:var(--leise); margin:0 0 12px; }
  .karte a.knopf { display:inline-block; background:var(--blau); color:#fff;
                   padding:8px 14px; border-radius:6px; text-decoration:none; }
  .karte a.knopf:hover { filter:brightness(0.92); }
  /* Steht anstelle des Knopfes, wenn es in dieser Fassung keine Adresse gibt,
     die der Browser des Lesenden erreicht: ein Dienst nur im Stapelnetz, ein
     Dienst, den es noch nicht gibt. Ein Knopf waere dort ein toter Link. */
  .karte p.vermerk { font-size:12px; margin:0; color:var(--leise);
                     overflow-wrap:anywhere; }

  pre { font-size:12.5px; line-height:1.55; background:#f7f9fc;
        border:1px solid var(--linie); border-radius:6px;
        padding:10px 12px; overflow-x:auto; margin:0 0 12px; }
  code { font-size:.93em; }

  /* Plaketten. Nicht ``marke``: Das ist im Kopf Logo und Name. */
  .plakette { font-size:12px; padding:2px 8px; border-radius:10px;
              font-weight:600; white-space:nowrap; }
  .plakette.gut { background:#e3f4ea; color:var(--gut); }
  .plakette.warn, .plakette.kuenftig { background:#fdf3dc; color:#a66f00; }
  .plakette.intern { background:#eef1f5; color:var(--leise); }

  .hinweis { background:#eef4fd; border-radius:6px; padding:10px 12px;
             font-size:13px; margin:12px 0 0; }

  dl.fakten { display:grid; grid-template-columns:auto 1fr; gap:6px 18px;
              margin:0; }
  dl.fakten dt { color:var(--leise); }
  dl.fakten dd { margin:0; overflow-wrap:anywhere; min-width:0; }

  /* Die Grenzen der Aussage (FR-33). Fliesstext, nicht Kennzahlen: Jede
     steht in einer eigenen Zeile, damit keine im Absatz untergeht. */
  dl.grenzen { margin:0; }
  dl.grenzen dt { font-weight:600; margin-top:14px; }
  dl.grenzen dt:first-child { margin-top:0; }
  dl.grenzen dd { margin:4px 0 0; font-size:13px; color:var(--text);
                  border-left:3px solid var(--blau); padding-left:12px; }

  footer { max-width:1080px; margin:0 auto; padding:6px 16px 18px;
           color:var(--leise); font-size:12px; }
  footer a { color:var(--blau); }
  @media (max-width:640px) {
    .kopf { padding:12px 16px; }
    h1 { font-size:24px; }
    main { padding:12px 12px 4px; }
    .einleitung, section { padding:14px; }
    footer { padding:6px 12px 18px; }
  }
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
    # Der Rahmen scrollt, nicht die Seite: Auf 360 px ist die Guetetabelle
    # breiter als der Bildschirm.
    return (f'<div class="rahmen"><table>{bes}<thead><tr>{kopfzeile}</tr></thead>'
            f"<tbody>{''.join(koerper)}</tbody></table></div>")


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
                          f'<span class="plakette {marke}">'
                          f'{richtung} {komma(schwelle, 0)}</span>')
        zeilen.append(zellen)
    return tabelle(
        ["Stadt", "im Stadtgebiet verortet", "exakt auf NIBRS", "nicht zugeordnet"],
        zeilen, rechts={1, 2, 3},
        beschriftung="Dieselben Grössen, gegen die das Publish-Gate prüft. "
                     "Gold entsteht nur, wenn jede Stadt jede Schwelle hält.")


def seite(kennung: str, manifest: dict, mass: dict,
          fassung: str = "lokal",
          umgebung: Mapping[str, str] | None = None) -> str:
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
        ["Stadt", "Fälle", "Einwohner", "je 1'000", "Tatebene je 1'000"],
        [[f"<strong>{html.escape(s.capitalize())}</strong>", zahl(f), zahl(e),
          f"<strong>{komma(r)}</strong>", komma(rt)]
         for s, f, e, r, rt in mass["staedte"]],
        rechts={1, 2, 3, 4})

    zugaenge = dienste(fassung, umgebung)
    werte = serverwerte(umgebung) if fassung == "server" else {}
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
                    f'<span class="plakette {klasse}">{html.escape(marke)}</span> '
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
    muster = werte.get("EINSTIEG_ADRESSMUSTER", "")
    treffer = geroutet_muster(muster) if muster else None
    geroutet = sum(1 for d in zugaenge if d[1] and treffer and treffer.match(d[1]))
    nachsatz = (
        f" Die {ZAHLWORT[lokale]} Verweise auf <code>localhost</code> tragen "
        "nur, solange das Gemeinte auf diesem Rechner läuft — je Karte steht "
        "dabei, was dafür zu starten ist." if lokale else
        f" Die {ZAHLWORT[geroutet]} Verweise auf "
        f"<code>{html.escape(kurzname(muster))}</code> "
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
        compose = werte["STAPEL_COMPOSE"]
        aufbauen = (f"docker compose -f {compose} up -d\n"
                    f"{werte['STAPEL_DATENLAUF']} delta")
        pruefen = (f"docker compose -f {compose} run --rm "
                   "pipeline \\\n    python -m serving.pruefe_stand")

    return f"""<!DOCTYPE html>
<html lang="de">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Einstieg · Release {html.escape(kennung)}</title>
<style>
{dashboard_wurzel()}
{STIL}</style>
<header class="kopf">
  <div class="marke">
    {dashboard_logo()}
    <span class="produkt">Urban Crime</span><span class="punkt">·</span><span class="bereich">Start</span>
  </div>
  <div class="stand">Release <b>{html.escape(kennung)}</b></div>
</header>
<main>
<div class="einleitung">
  <p class="eyebrow">Chicago · Detroit · Vergleich der Kriminalitätslage</p>
  <h1>Einstieg</h1>
  <p class="lead">Was hier liegt, und wo man es fragt. Alles auf dieser Seite
  ist aus dem Release <strong>{html.escape(kennung)}</strong> gemessen — keine
  Zahl ist abgeschrieben. Die Seite wird erzeugt, nicht gepflegt.</p>
</div>

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
  <p class="unter">Gezählt werden Fälle — je Vorfall das schwerste Delikt, nach
  derselben Regel für beide Städte; die Tatebene zählt jedes Delikt. Und nur
  Fälle in Tracts, die einer der beiden Städte zugeordnet sind — sonst verglichen man Stadtgebiete verschiedenen
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

</main>
<footer>
  Erzeugt von <code>python -m serving.build_einstieg</code> aus Release
  {html.escape(kennung)}. Nicht von Hand ändern — der nächste Lauf
  überschreibt es. Weiter: {fuss_weiter}
</footer>
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
    # Vor der Sperre und vor jedem Lesen: Fehlt ein Serverwert, soll der Lauf
    # nichts angefasst haben, wenn er abbricht.
    if args.adressen == "server":
        try:
            serverwerte()
        except FehlendeServerangabe as fehler:
            print(f"build_einstieg: {fehler}", file=sys.stderr)
            return 1
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
