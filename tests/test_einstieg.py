"""Die Einstiegsseite - gegen das Release geprueft, nicht gegen sich selbst.

Eine erzeugte Seite kann auf zwei Arten falsch sein: Sie kann Zahlen zeigen,
die nicht stimmen, und sie kann aelter sein als das, woraus sie entstand.
Beides steht hier.

Der Determinismus wird in einem **eigenen Prozess** geprueft. Zweimal im
selben Interpreter zu bauen, beweist wenig: Woerterbuecher behalten ihre
Reihenfolge, Zwischenstaende liegen noch herum, und ein Unterschied, der aus
der Umgebung kommt, faellt gerade nicht auf.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from gold_pipeline import RATENJAHR, raten_je_stadt

PROJEKT = Path(__file__).resolve().parents[1]
#: Der Erzeuger ist seit dem 12.10.2026 ein Modul des Pakets und kein Skript
#: unter ``tools/``: Die Seite ist ein Serving-Artefakt, und ``tools/`` liegt
#: nicht im Abbild (``.dockerignore``). Aufgerufen wird er deshalb wie
#: ``build_kibana`` - ueber ``-m``, aus dem Projektverzeichnis.
WERKZEUG = ("serving.build_einstieg",)
SEITE = PROJEKT / "docs" / "einstieg.html"
AKTUELL = PROJEKT / "data" / "releases" / "AKTUELL.json"
SRV01 = PROJEKT / "docker-compose.srv01.yml"


@pytest.fixture(scope="module")
def werkzeug():
    from serving import build_einstieg

    return build_einstieg


@pytest.fixture(scope="module")
def text() -> str:
    if not SEITE.is_file():
        pytest.skip("docs/einstieg.html nicht gebaut")
    return SEITE.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Die reinen Helfer
# --------------------------------------------------------------------------


def test_zahlen_tragen_den_schweizer_trenner(werkzeug):
    assert werkzeug.zahl(345073) == "345'073"
    assert werkzeug.zahl(85) == "85"


def test_kommazahlen_tragen_ein_komma(werkzeug):
    assert werkzeug.komma(94.5) == "94,5"
    assert werkzeug.komma(96.88, 2) == "96,88"


def test_unterhalb_der_aufloesung_steht_eine_schranke(werkzeug):
    """``0,0 MB`` sagt nichts - und sieht nach einem Fehler aus."""
    assert werkzeug.groesse(1000) == "&lt; 0,1"
    assert werkzeug.groesse(15_000_000) == "14,3"


# --------------------------------------------------------------------------
# Was auf der Seite steht
# --------------------------------------------------------------------------


def test_die_seite_nennt_das_release(text):
    kennung = json.loads(AKTUELL.read_text(encoding="utf-8"))["release_id"] \
        if AKTUELL.is_file() else None
    if kennung is None:
        pytest.skip("kein Release")
    assert kennung in text, "die Seite nennt ein anderes Release als AKTUELL.json"


def test_jeder_beschickte_dienst_ist_verlinkt(text):
    """Nur Dienste, in denen etwas liegt.

    ClickHouse (18123) stand bis zum 5.10.2026 mit darauf. Es wird nicht mehr
    geladen, und ein Knopf zu einer leeren Datenbank sieht aus wie eine
    Auskunft - deshalb ist sein Fehlen hier die Zusage und nicht die Luecke.
    """
    for port in ("19200", "15601"):
        assert f"localhost:{port}" in text, f"kein Verweis auf Port {port}"
    assert "18123" not in text, (
        "die Seite verweist wieder auf ClickHouse - dort liegt nichts")


def test_die_seite_traegt_keinen_erzeugungszeitstempel(text):
    """Die Entscheidung, die die Seite reproduzierbar macht.

    Ein ``zuletzt erzeugt am ...`` waere verlockend und machte zwei Laeufe
    unvergleichbar. Schlimmer noch waere ein festgehaltener Dienstzustand -
    eine Seite, die behauptet, Kibana laufe, weil es vor drei Tagen lief.
    Geprueft wird deshalb, dass **kein** Datum darauf steht ausser denen, die
    aus dem Release kommen.

    **Ohne Release wird uebersprungen, nicht geurteilt.** Die Erlaubnisliste
    entsteht erst aus dem Release: seiner Kennung und dem Datumsbereich der
    Faktentabelle. Fehlt es, ist die Liste leer - und dann ist jedes Datum auf
    der Seite ein Fremdkoerper, auch das richtige. Genau so stand dieser Test
    vom 1. bis zum 3.10.2026 auf jedem Pull Request rot und meldete
    ``2024-01-01`` und ``2024-12-31`` als Zeitstempel, obwohl beide die
    Jahresgrenzen der Faktentabelle sind. ``data/`` ist nicht versioniert, ein
    frischer Klon hat also nie ein Release. Geprueft wird dort, wo die Daten
    liegen: auf dem eigenen Rechner und im woechentlichen Datenlauf.
    """
    if not AKTUELL.is_file():
        pytest.skip("kein Release - die Erlaubnisliste waere leer")
    daten = set(re.findall(r"\b20\d\d-\d\d-\d\d\b", text))
    kennung = json.loads(AKTUELL.read_text(encoding="utf-8"))["release_id"]
    erlaubt = {kennung[:10]}
    verzeichnis = AKTUELL.parent / f"release={kennung}"
    fakt = verzeichnis / "gold/dataset=fact_offense/part-0001.parquet"
    if fakt.is_file():
        duckdb = pytest.importorskip("duckdb")
        con = duckdb.connect()
        try:
            von, bis = con.execute(
                f"SELECT min(date), max(date) FROM read_parquet('{fakt}')"
            ).fetchone()
        finally:
            con.close()
        erlaubt |= {von.isoformat(), bis.isoformat()}
    fremd = daten - erlaubt
    assert not fremd, (
        f"{sorted(fremd)} steht auf der Seite, kommt aber nicht aus dem "
        f"Release - ein Zeitstempel macht sie unreproduzierbar")


def test_die_seite_verspricht_keinen_dienstzustand(text):
    """Sie darf nicht behaupten, etwas laufe - sie kann es nicht wissen."""
    for satz in ("läuft", "erreichbar", "zuletzt geprüft"):
        # Erlaubt ist der Konjunktiv ("sie tragen nur, wenn er läuft"),
        # verboten eine Zustandsaussage. Geprueft wird das Einfache: keine
        # gruene Marke neben einem Dienstnamen.
        pass
    assert "marke gut" not in text.split("Wo man fragt")[-1], (
        "die Seite zeigt eine Zustandsmarke bei den Diensten")


# --------------------------------------------------------------------------
# Gegen das Release
# --------------------------------------------------------------------------


@pytest.mark.referenzstand
def test_jede_zahl_der_seite_steht_so_im_release(text):
    """Zeilen-, Spaltenzahlen und Raten - gegen die Dateien gerechnet."""
    duckdb = pytest.importorskip("duckdb")
    import pyarrow.parquet as pq

    if not AKTUELL.is_file():
        pytest.skip("kein Release")
    kennung = json.loads(AKTUELL.read_text(encoding="utf-8"))["release_id"]
    gold = AKTUELL.parent / f"release={kennung}" / "gold"

    for pfad in sorted(gold.glob("dataset=*/part-0001.parquet")):
        name = pfad.parent.name.removeprefix("dataset=")
        datei = pq.ParquetFile(pfad)
        zeilen = f"{datei.metadata.num_rows:,}".replace(",", "'")
        spalten = len(datei.schema_arrow)
        muster = (rf'name">{re.escape(name)}</span></td>'
                  rf'<td class="n">{re.escape(zeilen)}</td>'
                  rf'<td class="n">{spalten}</td>')
        assert re.search(muster, text), (
            f"{name}: {zeilen} Zeilen / {spalten} Spalten stehen nicht so auf "
            f"der Seite. DuckDBs DESCRIBE zaehlt zwei Hive-Spalten mit, die in "
            f"keiner Datei stehen - genau daran ist die erste Fassung "
            f"gescheitert.")

    tract = gold / "dataset=dim_tract/part-0001.parquet"
    acs = gold / "dataset=dim_tract_acs/part-0001.parquet"
    fakt = gold / "dataset=fact_offense/part-0001.parquet"
    con = duckdb.connect()
    try:
        # Aus gold_pipeline, mit dem Jahresfilter darin. Eine Kopie ohne ihn
        # haette ab dem 4.10.2026 sechs Jahrgaenge gezaehlt und einen Nenner
        # von einem - und die Seite waere gegen eine Zahl geprueft worden, die
        # keine Rate ist.
        raten = con.execute(raten_je_stadt(
            f"read_parquet('{fakt}')", f"read_parquet('{tract}')",
            f"read_parquet('{acs}')")).fetchall()
    finally:
        con.close()
    assert f"Jahrgang {RATENJAHR}" in text, (
        f"die Seite nennt den Jahrgang {RATENJAHR} nicht, fuer den ihre Raten "
        "gelten - ein Release traegt sechs")
    for zeile in raten:
        stadt, rate = zeile[0], zeile[4]
        gesucht = f"{rate:.1f}".replace(".", ",")
        assert f"<strong>{gesucht}</strong>" in text, (
            f"{stadt}: Rate {gesucht} steht nicht auf der Seite")


@pytest.mark.referenzstand
def test_die_abgelegte_seite_ist_nicht_aelter_als_das_release(tmp_path):
    """Zwei Laeufe, zwei Prozesse - und dieselbe Datei.

    Deckt beides ab: dass das Erzeugen reproduzierbar ist, und dass das, was
    im Repository liegt, dem frischen Bau entspricht.
    """
    if not AKTUELL.is_file():
        pytest.skip("kein Release")
    pytest.importorskip("duckdb")

    gebaut = []
    for n in range(2):
        ziel = tmp_path / f"lauf{n}.html"
        fertig = subprocess.run(
            [sys.executable, "-m", *WERKZEUG, "--ziel", str(ziel)],
            capture_output=True, text=True, cwd=PROJEKT)
        assert fertig.returncode == 0, fertig.stderr[-1500:]
        gebaut.append(ziel.read_text(encoding="utf-8"))

    assert gebaut[0] == gebaut[1], (
        "zwei Laeufe liefern verschiedene Seiten - irgendwo steckt etwas "
        "Veraenderliches darin")
    if SEITE.is_file():
        assert SEITE.read_text(encoding="utf-8") == gebaut[0], (
            "docs/einstieg.html ist aelter als das Release. "
            "python -m serving.build_einstieg")


def test_die_generatorenzahl_im_bild_zaehlt_tools():
    """Die Generatorenzahl im Bild zaehlt ``tools/`` - und dieser Erzeuger
    steht seit dem 12.10.2026 nicht mehr darin.

    Der Test hiess ``test_das_werkzeug_steht_im_architekturbild``, solange
    ``build_einstieg`` eines der Werkzeuge unter ``tools/`` war. Mit dem Umzug
    nach ``serving`` ist er genau der Waechter, der den Umzug sichtbar macht:
    Die Zahl im Bild fiel von zehn auf neun, und ohne einen frischen Bau des
    Bildes faellt er. Er bleibt hier und nicht in
    ``tests/test_architekturbilder.py``, weil der Umzug dieses Erzeugers der
    Grund fuer die neue Zahl ist.
    """
    bild = PROJEKT / "docs" / "bilder" / "architektur-kontext.svg"
    if not bild.is_file():
        pytest.skip("Bild nicht gebaut")
    # Dieselbe Zaehlweise wie im Bild: alles unter tools/, nicht nur was
    # ``build_`` heisst - ``extend_micr_arrest_charges`` gehoert dazu.
    anzahl = len(list((PROJEKT / "tools").glob("*.py")))
    text = bild.read_text(encoding="utf-8")
    assert f"{anzahl} Generatoren" in text, (
        f"das Bild nennt nicht {anzahl} Generatoren. "
        f"python tools/build_architekturbilder.py")
    assert not (PROJEKT / "tools" / "build_einstieg.py").exists(), (
        "build_einstieg liegt wieder unter tools/ - dort ist es nicht im "
        "Abbild (.dockerignore) und kann die ausgelieferte Seite nicht bauen")


def test_die_seite_nennt_so_viele_bretter_wie_es_gibt(werkzeug, text):
    """Die Zahl im Generator gegen ``BRETTER``, nicht gegen sich selbst.

    Bis zum 11.10.2026 stand im Generator "Drei Bretter", waehrend
    ``build_kibana.BRETTER`` vier fuehrte. Aufgefallen ist es nicht, weil
    ``test_die_abgelegte_seite_ist_nicht_aelter_als_das_release`` die Seite
    gegen ihren **Generator** haelt - und beide sagten dasselbe Falsche.
    """
    from serving.build_kibana import BRETTER

    wort = werkzeug.ZAHLWORT[len(BRETTER)].capitalize()
    kibana = next(d for d in werkzeug.dienste() if d[0] == "Kibana")
    assert kibana[3].startswith(f"{wort} Bretter"), (
        f"der Generator nennt nicht {wort.lower()} Bretter: {kibana[3][:60]}")
    assert f"{wort} Bretter" in text, (
        "docs/einstieg.html ist aelter als der Generator. "
        "python -m serving.build_einstieg")


# --------------------------------------------------------------------------
# Die Zugaenge (FR-31): vier, und einer, der noch keiner ist
# --------------------------------------------------------------------------


def blatt(werkzeug, fassung: str) -> str:
    """Die Seite in einer Fassung, aus einem erfundenen Release.

    Die Verweise haengen nicht an den Daten, nur an der Fassung. Mit einem
    erfundenen Release prueft der Waechter sie deshalb auch auf einem Rechner
    ohne gebautes ``data/`` - und das ist der Normalfall in CI. Was aus dem
    Release kommt, prueft der Referenzstand-Waechter oben.
    """
    mass = {
        "datensaetze": [("fact_offense", 1, 2, 3)],
        "staedte": [("chicago", 1, 2, 3.0)],
        "guete": [("chicago", 99.0, 99.0, 0.0)],
        "zeitraum": ("2021-01-01", "2026-06-30"),
        "ratenjahr": 2024,
    }
    return werkzeug.seite("2026-01-01T00-00-00Z", {}, mass, fassung)


def test_die_seite_nennt_vier_zugaenge(werkzeug, text):
    """FR-31 verlangt die Zugaenge auf der Seite - gezaehlt, nicht geglaubt.

    Vier gibt es: Elasticsearch, Kibana, DuckDB und seit dem 12.10.2026
    Jupyter. Die Admin-Konsole ist ein fuenfter Eintrag und **kein** Zugang;
    sie zaehlt hier bewusst nicht mit, und der Waechter darunter haelt fest,
    dass die Seite das auch sagt.

    Geprueft wird beides: die Liste im Erzeuger und die abgelegte Seite. Nur
    das Erste waere ein Test des Generators gegen sich selbst - genau der
    Fehler, der "Drei Bretter" vier Tage ueberlebt hat.
    """
    zugaenge = [d for d in werkzeug.dienste() if not werkzeug.ist_kuenftig(d)]
    namen = [d[0] for d in zugaenge]
    assert namen == ["Elasticsearch", "Kibana", "DuckDB", "Jupyter"], namen
    wort = werkzeug.ZAHLWORT[len(namen)].capitalize()
    assert f"{wort} Zugänge" in text, (
        f"die Seite nennt nicht {wort.lower()} Zugänge. "
        "python -m serving.build_einstieg")
    fehlend = [n for n in namen if f"<h3>{n}</h3>" not in text]
    assert not fehlend, f"keine Karte fuer: {fehlend}"


def test_die_admin_konsole_ist_als_kuenftig_gekennzeichnet(werkzeug, text):
    """Ein Knopf auf einen Hostnamen ohne Route sieht aus wie eine Auskunft.

    Die Admin-Konsole ist ein benannter Platzhalter: Sie nennt den Namen, der
    ins Muster ``urbancrime-*`` fällt - und damit unter die eine
    Access-Anwendung -, aber sie verweist auf nichts. Solange es den Dienst
    nicht gibt, ist das die einzige ehrliche Form.
    """
    eintrag = next(d for d in werkzeug.dienste() if d[0] == "Admin-Konsole")
    assert werkzeug.ist_kuenftig(eintrag), (
        "die Admin-Konsole ist nicht als kuenftig gekennzeichnet")
    assert eintrag[1] is None, (
        f"sie traegt eine Adresse ({eintrag[1]}) - den Dienst gibt es nicht")
    host = eintrag[5][1]
    assert host == "urbancrime-admin.datenwerft.ch", host

    for fassung in werkzeug.FASSUNGEN:
        seite = blatt(werkzeug, fassung)
        assert f'<code>{host}</code>' in seite, (
            f"{fassung}: der vorgesehene Name steht nicht auf der Seite")
        assert f'href="https://{host}' not in seite, (
            f"{fassung}: die Seite verlinkt {host} - die Route gibt es nicht")
    assert "künftig" in text and host in text, (
        "docs/einstieg.html ist aelter als der Generator. "
        "python -m serving.build_einstieg")


def test_kein_verweis_zeigt_ins_leere(werkzeug):
    """Jeder Verweis trifft etwas - je Fassung geprueft, nicht im Mittel.

    Die beiden Fassungen haben verschiedene Arten, ins Leere zu zeigen. Lokal
    waere es ein relativer Verweis auf ein Dokument, das es nicht gibt; auf
    dem Server waere es **jeder** relative Verweis, weil dort genau eine
    Datei ausgeliefert wird - und ein Hostname ``urbancrime-*``, zu dem keine
    Route gehoert.
    """
    router = re.findall(r"routers\.urbancrime-(\w+)\.rule: Host\(`([^`]+)`\)",
                        SRV01.read_text(encoding="utf-8"))
    geroutet = {host for _, host in router}
    assert geroutet, "keine Traefik-Router in docker-compose.srv01.yml gefunden"

    for fassung in werkzeug.FASSUNGEN:
        seite = blatt(werkzeug, fassung)
        ziele = re.findall(r'href="([^"]+)"', seite)
        relativ = [z for z in ziele if "//" not in z]
        if fassung == "server":
            assert not relativ, (
                f"die Serverfassung verweist relativ auf {relativ} - "
                "ausgeliefert wird nur diese eine Datei")
        else:
            tot = [z for z in relativ
                   if not (PROJEKT / "docs" / z.split("#")[0]).exists()]
            assert not tot, f"relativer Verweis ins Leere: {tot}"
        fremd = [z for z in ziele
                 if (m := re.match(r"https?://(urbancrime[^/]+)", z))
                 and m.group(1) not in geroutet]
        assert not fremd, (
            f"{fassung}: verweist auf {fremd}, wofuer "
            f"docker-compose.srv01.yml keine Route traegt")


def test_die_adressen_sind_umschaltbar_und_folgen_dem_muster(werkzeug):
    """Eine Variable, zwei Fassungen - und das Muster, an dem Access haengt.

    Beim Entwickeln zeigen die Verweise auf den lokalen Verbund, auf dem
    Server auf ``urbancrime-<dienst>.datenwerft.ch``. Dass es dasselbe Muster
    ist, an dem die **eine** Access-Anwendung haengt, ist der Grund dafuer,
    dass niemand eine Regel vergessen kann: ``urbancrime.datenwerft.ch`` ist
    der einzige Hostname, den es nicht deckt, und er bleibt unbesetzt.
    """
    lokal = {d[0]: d[1] for d in werkzeug.dienste("lokal")}
    server = {d[0]: d[1] for d in werkzeug.dienste("server")}
    assert set(lokal) == set(server), "die Fassungen nennen andere Dienste"

    assert lokal["Kibana"].startswith("http://localhost:15601")
    assert lokal["Elasticsearch"].startswith("http://localhost:19200")
    # Die Portzahl, nicht nur das Praefix: 8888 ist die Vorgabe von
    # ``jupyter lab`` und steht in keiner Compose-Datei - ein verschobener
    # Port faellt sonst nirgends auf.
    assert lokal["Jupyter"] == "http://localhost:8888/lab", lokal["Jupyter"]
    for name in ("Kibana", "Jupyter"):
        assert server[name].startswith(
            f"https://urbancrime-{name.lower()}.datenwerft.ch"), server[name]
    # Elasticsearch ist auf srv01 nicht geroutet (FR-11). Ein Knopf dafuer
    # waere entweder ein toter Link oder - schlimmer - ein offener
    # Datenspeicher, wenn jemand die Route nachtraeglich anlegt.
    assert server["Elasticsearch"] is None, (
        "die Serverfassung verlinkt Elasticsearch - es ist dort bewusst "
        "nicht geroutet")
    assert not any(h for h in server.values()
                   if h and h.startswith("https://urbancrime.datenwerft.ch")), (
        "die Seite besetzt urbancrime.datenwerft.ch - der eine Hostname, den "
        "das Access-Muster urbancrime-* nicht deckt")


def test_die_fassung_wird_benannt_und_nicht_geraten(werkzeug):
    """Ein Tippfehler in ``--adressen`` darf keine halbe Seite ergeben."""
    with pytest.raises(ValueError):
        werkzeug.dienste("srv01")
    zerleger = werkzeug.kommandozeile()
    assert zerleger.parse_args([]).adressen == "lokal", (
        "die Vorgabe ist nicht lokal - dann stuenden in der abgelegten Seite "
        "Serveradressen")


def test_die_jupyter_karte_sagt_dass_er_erst_zu_starten_ist(werkzeug):
    """Jupyter laeuft in **keiner** Fassung von selbst.

    Lokal kennt ``docker-compose.yml`` den Dienst gar nicht (clickhouse,
    elasticsearch, kibana), und ``jupyterlab`` steht nicht in
    ``requirements.lock`` - 8888 ist die Vorgabe eines von Hand gestarteten
    ``jupyter lab``. Auf ``srv01`` haelt ein ``profiles: [analyse]`` den
    Dienst aus ``up -d`` heraus. Ein Knopf ohne diesen Satz ergaebe auf der
    dauernd ausgelieferten Seite 404 oder 502.
    """
    for fassung, wort in (("lokal", "jupyter lab"),
                          ("server", "profile analyse")):
        karte = next(d for d in werkzeug.dienste(fassung) if d[0] == "Jupyter")
        assert "Zeitweilig" in karte[3] or "Von Hand" in karte[3], (
            f"{fassung}: die Jupyter-Karte sagt nicht, dass er zu starten ist")
        assert wort in karte[3], (
            f"{fassung}: sie nennt nicht, womit - erwartet {wort!r}")


def test_das_readme_nennt_so_viele_dashboards_wie_es_gibt(werkzeug):
    """Dieselbe Frage fuer das README - und seine Tabelle zaehlt mit.

    Die Einstiegsseite ist seit dem 11.10.2026 bewacht, das README war es
    nicht: Dort stand *„Vier gibt es"* mit einer vierzeiligen Tabelle, und
    beides haette veralten koennen, ohne dass etwas rot wird. Genau der Fall
    aus den Known pitfalls - dieselbe Aussage in zwei Dokumenten, ein
    Waechter nur ueber einem.

    Geprueft wird beides: das Zahlwort **und** dass die Tabelle so viele
    Zeilen hat. Ein Zahlwort allein liesse sich hochzaehlen, ohne die Zeile
    zu schreiben.
    """

    from serving.build_kibana import BRETTER

    text = (PROJEKT / "README.md").read_text(encoding="utf-8")
    wort = werkzeug.ZAHLWORT[len(BRETTER)].capitalize()
    assert f"{wort} gibt es:" in text, (
        f"das README nennt nicht '{wort} gibt es:' - "
        f"build_kibana.BRETTER fuehrt {len(BRETTER)} Bretter")

    tabelle = text[text.index(f"{wort} gibt es:"):]
    tabelle = tabelle[tabelle.index("| Dashboard | zeigt |"):]
    # Bis zur ersten Zeile, die keine Tabellenzeile mehr ist. Ein blosses
    # Filtern haette alle spaeteren Tabellen des README mitgezaehlt - beim
    # ersten Anlauf waren es 35 statt 7.
    zeilen = []
    for z in tabelle.splitlines()[2:]:
        if not z.startswith("|"):
            break
        zeilen.append(z)
    assert len(zeilen) == len(BRETTER), (
        f"die Tabelle im README hat {len(zeilen)} Zeilen, "
        f"BRETTER fuehrt {len(BRETTER)} Bretter")

    # Und jedes Brett kommt darin vor - nicht nur die richtige Anzahl.
    gelistet = " ".join(zeilen)
    fehlend = [b.titel.split(" — ")[0] for b in BRETTER
               if b.titel.split(" — ")[0] not in gelistet]
    assert not fehlend, f"im README fehlen: {fehlend}"


# --------------------------------------------------------------------------
# Die Grenzen der Aussage (FR-33)
# --------------------------------------------------------------------------

#: Die drei Grenzen, die FR-33 verlangt, als Wortgruppen. Je Grenze muessen
#: **alle** Marken in **einem** Abschnitt stehen. So gefasst, weil die
#: Formulierung frei bleiben soll, der Gegenstand aber nicht: "Erfassung ist
#: nicht Kriminalitaet, Tatort nicht Wohnort, oekologischer Fehlschluss."
GRENZEN = {
    "Erfassung ist nicht Kriminalitaet": ("Erfassung", "Kriminalität"),
    "Tatort ist nicht Wohnort": ("Tatort", "Wohnort"),
    "oekologischer Fehlschluss": ("kologisch", "Fehlschluss"),
}


def abschnitte(text: str) -> list[str]:
    """Die ``<section>``-Bloecke der Seite, je einer als Zeichenkette."""
    return re.findall(r"<section>(.*?)</section>", text, re.DOTALL)


def test_die_seite_nennt_die_drei_grenzen_der_aussage(text):
    """FR-33, und der Grund steht im Gegenstand der Arbeit.

    Die Seite zeigt eine Rate je 1'000 Einwohner und stellt zwei Staedte
    nebeneinander - die einladendste Zahl im ganzen Projekt, falsch gelesen
    zu werden. Drei Grenzen gehoeren deshalb **auf die Seite** und nicht in
    ein Dokument daneben: Erfassung ist nicht Kriminalitaet, Tatort nicht
    Wohnort, und eine Flaechenrate sagt nichts ueber die Menschen darin.

    Bis zum 18.10.2026 stand keine davon darauf. Die Zahlen waren bewacht,
    ihre Lesart nicht - und eine bewachte Zahl, die falsch gelesen wird, ist
    nicht besser als eine falsche.
    """
    fehlen = [name for name, marken in GRENZEN.items()
              if not any(all(marke in abschnitt for marke in marken)
                         for abschnitt in abschnitte(text))]
    assert not fehlen, (
        "Die Startseite nennt diese Grenzen der Aussage nicht (FR-33): "
        + ", ".join(fehlen))


def test_die_grenzen_stehen_zusammen_in_einem_abschnitt(text):
    """Verstreut zaehlt nicht.

    Drei Saetze in drei Abschnitten erfuellen den Buchstaben und nicht den
    Zweck: Wer die Raten liest, soll ihre Grenzen an einer Stelle finden und
    nicht ueber die Seite suchen muessen. Dieser Test ist der Grund, warum
    der Waechter darueber **nicht** genuegt - er allein waere auch gruen,
    wenn je ein Wort in einem anderen Abschnitt stuende.
    """
    treffer = [abschnitt for abschnitt in abschnitte(text)
               if all(any(all(marke in abschnitt for marke in marken)
                          for marken in [GRENZEN[name]])
                      for name in GRENZEN)]
    assert treffer, (
        "kein Abschnitt nennt alle drei Grenzen - sie gehoeren zusammen, "
        "sonst findet sie niemand, der gerade eine Rate liest")


def test_die_grenzen_folgen_unmittelbar_auf_die_raten(text):
    """Ort und Reihenfolge sind Teil der Aussage.

    Eine Grenze hinter dem Betriebsteil liest niemand mehr. Sie gehoert in
    den Abschnitt **direkt** nach dem, der die beiden Staedte
    nebeneinanderstellt - dort steht die Zahl, die falsch gelesen werden
    kann, und dort ist der Leser gerade.

    Geprueft wird ueber die Reihenfolge der Abschnitte und nicht ueber eine
    Ueberschrift: Wie der Abschnitt heisst, soll frei bleiben.
    """
    bloecke = abschnitte(text)
    staedte = [i for i, a in enumerate(bloecke)
               if "Chicago" in a and "Detroit" in a]
    grenzen = [i for i, a in enumerate(bloecke) if "Fehlschluss" in a]
    assert staedte and grenzen, (
        f"Staedtevergleich in {staedte}, Grenzen in {grenzen} - "
        "einer der beiden Abschnitte fehlt")
    assert grenzen[0] == staedte[0] + 1, (
        f"die Grenzen stehen als Abschnitt {grenzen[0]}, der "
        f"Staedtevergleich als {staedte[0]} - erwartet ist unmittelbar "
        "danach")


def test_die_grenzen_der_seite_sind_die_des_konzepts(text):
    """Dieselbe Aussage an zwei Stellen braucht einen Waechter ueber beide.

    `ln2_konzept.md` 11 fuehrt die Grenzen der Aussage unter *Zur
    Datengrundlage* - mit denselben drei Titeln, die jetzt auf der
    Startseite stehen. Ohne diesen Test veraltet die unbewachte von beiden:
    Am 11.10.2026 sind auf einmal acht Aussagen ueberholt gewesen, weil ein
    Waechter nur ein Dokument erfasste.

    Geprueft wird eine Richtung - **jeder Titel der Seite steht im
    Konzept**. Das Konzept darf mehr nennen (es nennt fuenf), die Seite
    nichts, was dort nicht steht. Faellt dieser Test nach einer Umformulierung
    im Konzept, gehoert `serving/build_einstieg.py` mitgezogen und die Seite
    neu gebaut; umgekehrt ist die Seite nicht der Ort, an dem eine neue
    Limitation zuerst erscheint.
    """
    konzept = PROJEKT / "docs" / "ln2_konzept.md"
    if not konzept.is_file():
        pytest.skip("docs/ln2_konzept.md fehlt")
    fett = set(re.findall(r"\*\*(.+?)\*\*", konzept.read_text(encoding="utf-8")))
    # Nur die Grenzenliste: ``dl.fakten`` oben traegt die Kennzahlen des
    # Releases und hat mit dem Konzept nichts zu tun.
    liste = re.search(r'<dl class="grenzen">(.*?)</dl>', text, re.DOTALL)
    assert liste, 'die Seite hat keine Liste <dl class="grenzen">'
    titel = re.findall(r"<dt>(.*?)</dt>", liste.group(1), re.DOTALL)
    assert titel, "die Seite nennt keine Grenzen als <dt>"
    fremd = [t for t in titel if t not in fett and f"{t}." not in fett]
    assert not fremd, (
        "diese Titel stehen auf der Startseite, aber nicht im Konzept: "
        f"{fremd} - eine Limitation entsteht im Konzept, nicht auf der Seite")
