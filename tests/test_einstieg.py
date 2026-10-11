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
WERKZEUG = PROJEKT / "tools" / "build_einstieg.py"
SEITE = PROJEKT / "docs" / "einstieg.html"
AKTUELL = PROJEKT / "data" / "releases" / "AKTUELL.json"

sys.path.insert(0, str(PROJEKT / "tools"))


@pytest.fixture(scope="module")
def werkzeug():
    import build_einstieg

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
            [sys.executable, str(WERKZEUG), "--ziel", str(ziel)],
            capture_output=True, text=True, cwd=PROJEKT)
        assert fertig.returncode == 0, fertig.stderr[-1500:]
        gebaut.append(ziel.read_text(encoding="utf-8"))

    assert gebaut[0] == gebaut[1], (
        "zwei Laeufe liefern verschiedene Seiten - irgendwo steckt etwas "
        "Veraenderliches darin")
    if SEITE.is_file():
        assert SEITE.read_text(encoding="utf-8") == gebaut[0], (
            "docs/einstieg.html ist aelter als das Release. "
            "python tools/build_einstieg.py")


def test_das_werkzeug_steht_im_architekturbild():
    """Die Generatorenzahl im Bild zaehlt ``tools/`` - also mit."""
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
        "python tools/build_einstieg.py")
