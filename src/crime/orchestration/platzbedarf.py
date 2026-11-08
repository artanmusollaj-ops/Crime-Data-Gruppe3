"""Was die Strecke an Platz braucht - gemessen, und je Quelle hochgerechnet.

    python -m orchestration.platzbedarf                       # messen und rechnen
    python -m orchestration.platzbedarf --jahre 2021-2026     # anderer Bereich
    python -m orchestration.platzbedarf --json                # fuer Werkzeuge

**Warum es dieses Modul gibt.** Der Speicherbedarf des Mehrjahreslaufs stand
bis zum 4.10.2026 als **ein Faktor** in den Planungsdokumenten: 1'874'417
Zeilen gegen 348'341 sind das 5,38-Fache, aufgerundet 5,5 - und dieser Faktor
wurde auf ganz ``data/`` angewandt. Daran war dreierlei falsch, und jedes
einzeln:

1. **Ein Zeilenverhaeltnis ist kein Byteverhaeltnis.** Parquet komprimiert
   spaltenweise; Detroits Zeile kostet in Bronze rund dreimal so viel wie
   Chicagos, weil sie mehr und laengere Textfelder traegt.
2. **Nicht alles waechst mit den Jahren.** NOAA liefert mit GHCN-Daily immer
   die ganze Reihe einer Station - weitere Jahrgaenge kosten dort nichts
   zusaetzlich. Census waechst nicht mit den Jahren, sondern mit den
   **Vintages**, und davon braucht ein Bereich weniger, als er Jahre hat:
   Jahre ohne eigenes Vintage borgen das juengste (``vintages_for``).
3. **Die Basis war der Bestand, nicht ein Jahrgang.** ``data/`` haeuft Laeufe
   und Releases an. Den Faktor darauf anzuwenden rechnet das Anhaeufen mit
   hoch - dieselbe Falle wie "den Bestand aus Bronze lesen", diesmal in der
   Basis. Basis je Jahrgang ist deshalb der **groesste** Lauf je Quelle und
   Vintage, nicht die Summe ihrer Laeufe.

**Was die Basis abdeckt, muss erst heraus.** Eine Basis je Jahrgang entsteht
nur, wenn aus den gemessenen Bytes herausgeteilt wird, was darin schon an
Mehrjahrigkeit steckt - und das gibt es in zwei Dimensionen. Bei Census sind
es die **Vintages** (``Basis.vintages``), bei den Taten die **Jahrgaenge**
(``Basis.jahre``). Fuer ``raw`` und ``bronze`` bleibt die Jahres-Dimension
leer, und das stimmt: Die Ingestion laeuft je Jahr, ein Lauf traegt einen
Jahrgang. Fuer Silver, Gold, Serving und ein Release stimmte es bis zum
4.10.2026 ebenfalls - dann baute der Mehrjahreslauf alle sechs Jahrgaenge in
dieselben Dateien, und die Rechnung nahm sie trotzdem noch einmal mit 5,38:
**9'345 MB statt 2'375 MB**. Derselbe Fehler, der bei den Vintages schon
behoben war, eine Dimension daneben.

Herausgekommen sind aus dem einen Faktor vier Regeln (``ERKLAERUNG``). Das
Ergebnis steht erzeugt in ``docs/intern/platzbedarf.md``; geschrieben wird es
von ``tools/build_platzbedarf.py``, das nichts anderes tut als dieses Modul
aufzurufen und zu setzen.

**Was es nicht tut.** Nichts laden und nichts bauen. Es liest, was da ist,
und rechnet. Ohne Netz, ohne ``CENSUS_API_KEY``, ohne DuckDB. Die Zeilen je
Jahrgang kann es nicht messen - die stehen gemessen, mit Datum und Adresse, in
``config/zeilen_je_jahrgang.csv``.

**Die Unschaerfe, die bleibt.** Die Hochrechnung beschreibt **einen** Lauf je
Quelle und Jahrgang, nicht ein ``data/``, das wochenlang mitlaeuft. Wer
woechentlich laedt, haeuft darueber hinaus an - was davon weg darf, sagt
``orchestration.aufraeumen``, und nur das macht die Zahl hier zu einer
Obergrenze.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, NamedTuple

from census_pipeline import vintages_for
from chicago_pipeline.download_chicago import DEFAULT_YEAR
from orchestration import LAUF_MANIFEST
from orchestration.aufraeumen import RELEASES_N
from silver_pipeline import STUDIENSTAEDTE
from storage import (
    LAUFSCHICHTEN,
    Config,
    SCHICHTEN,
    StorageError,
    TABELLENSCHICHTEN,
    Storage,
    for_root,
    release,
)


#: Die Staedte, kleingeschrieben - abgeleitet aus dem einen Register. Eine
#: dritte Stadt wird in ``silver_pipeline.STUDIENSTAEDTE`` eingetragen, sonst
#: nirgends; sie braucht dann Zeilen in ``config/zeilen_je_jahrgang.csv``, und
#: fehlen sie, sagt ``hochrechnung`` das mit Namen.
STAEDTE = tuple(sorted(name.lower() for name in STUDIENSTAEDTE.values()))

#: Das Jahr, das die gemessenen Laeufe tragen - die Basis der Hochrechnung.
#: Dieselbe Vorgabe, mit der die Ingestion laeuft; eine eigene Konstante hier
#: waere die zweite Fassung, die als erste veraltet.
BASISJAHR = DEFAULT_YEAR

#: Wo die gemessenen Zeilen je Stadt und Jahr liegen.
ZEILEN_DATEI = "zeilen_je_jahrgang.csv"

# -- Die vier Regeln --------------------------------------------------------

TATEN = "Taten"
CENSUS = "Census"
KONSTANT = "konstant"
RELEASES = "Releases"

ERKLAERUNG = {
    TATEN: "Zeilen je Jahr x Bytes je Zeile",
    CENSUS: "distinkte ACS-Vintages x Kosten je Vintage",
    KONSTANT: "waechst nicht mit den Jahren",
    # Nicht "RELEASES_N x heutige Groesse eines Standes": Der Inhalt eines
    # Standes waechst mit. Erst wird er nach seinen eigenen Regeln
    # hochgerechnet, dann mit der Zahl der Staende genommen - sonst stimmte
    # die Formelspalte nicht mit Basis und Ergebnis daneben zusammen.
    RELEASES: f"Inhalt eines Standes hochgerechnet, dann x {RELEASES_N} Staende",
}

#: Welche Regel eine Quelle traegt. Der Schluessel ist der erste Pfadteil unter
#: der Schicht - bei ``raw`` und ``bronze`` die Quelle (``city=chicago``), bei
#: den Tabellenschichten die Tabelle (``dataset=fact_offense``), dazu die
#: wenigen Dateien, die ohne ``dataset=`` daneben liegen.
#:
#: **Von Hand gefuehrt, und das mit Absicht** - wie die Beschreibungen in
#: ``tools/build_feldkatalog.py``. Eine neue Tabelle laesst den Lauf scheitern
#: und wird genannt: Wer eine Tabelle hinzufuegt, soll sagen, *womit* sie
#: waechst. Geraten waere schlimmer, denn geraten faellt niemandem auf.
REGEL_JE_QUELLE: dict[str, str] = {
    # Ingestion
    "city=chicago": TATEN,
    "city=detroit": TATEN,
    "dataset=acs5_tract": CENSUS,
    "dataset=tiger_tract": CENSUS,
    "dataset=tiger_place": CENSUS,
    # GHCN-Daily liefert die ganze Reihe einer Station, egal welches Jahr
    # gefragt war. Sechs Jahrgaenge kosten dort keine Byte mehr als einer.
    "dataset=noaa_ghcnd": KONSTANT,
    # Silver
    "dataset=crime_offense": TATEN,
    "dataset=source_change": TATEN,
    "dataset=tract": CENSUS,
    "dataset=place": CENSUS,
    "dataset=weather_day": KONSTANT,
    # Gold
    "dataset=fact_offense": TATEN,
    "dataset=dim_offense": TATEN,
    # dim_date traegt eine Zeile je Kalendertag - das waechst mit den Jahren,
    # aber nicht mit den Taten. Es sind Kilobytes; die Taten-Regel
    # ueberschaetzt sie und darf es.
    "dataset=dim_date": TATEN,
    "dataset=dim_tract": CENSUS,
    # Eine Zeile je Tract mit Stadt, und der Umriss darin waechst mit
    # der Flaeche, nicht mit den Taten. Ein Jahrgang mehr kostet hier
    # keine Byte.
    "dataset=dim_tract_geo": CENSUS,
    "dataset=dim_tract_acs": CENSUS,
    "dataset=dim_city_day": KONSTANT,
    # Serving
    "dataset=comparison_day": TATEN,
    "dataset=comparison_week": TATEN,
    "dataset=comparison_month": TATEN,
    "dataset=partition_quality": TATEN,
    # Eine Zeile je Tract mit Einwohnern, fuer **ein** Bezugsjahr
    # (gold_pipeline.RATENJAHR). Ein Jahrgang mehr in den Falldaten
    # aendert die Zeilenzahl nicht - sie haengt an den Tracts.
    "dataset=rate_tract": CENSUS,
    # Waechst mit den Bewegungen der Quelle, und die mit dem Bestand: Ein
    # Jahrgang mehr ist ein Vollabzug mehr, der sich bewegen kann.
    "dataset=source_movement": TATEN,
    # Im Release materialisiert, unter data/serving nur Sichten - dort um
    # zwei Groessenordnungen kleiner. Beide Male haengt die Groesse an den
    # Fakten, und deshalb gilt beide Male dieselbe Regel.
    "analyse.duckdb": TATEN,
    "tracts.geojson": CENSUS,
    # Marken und Zeiger: ein paar Hundert Bytes, und sie bleiben es.
    "tracts.manifest.json": KONSTANT,
    "manifest.json": KONSTANT,
    release.RELEASE_MANIFEST: KONSTANT,
    release.AKTUELL: KONSTANT,
    ".gitkeep": KONSTANT,
}


class Schicht(NamedTuple):
    """Die Belegung einer Schicht, so wie sie jetzt daliegt."""

    name: str
    bytes: int
    dateien: int


class Basis(NamedTuple):
    """Was **ein** Jahrgang einer Quelle in einer Schicht kostet.

    ``laeufe`` sagt, aus wie vielen Laeufen der Bestand dieser Quelle besteht -
    ``bytes`` ist der groesste davon, nicht ihre Summe. ``staende`` ist 1,
    ausser bei Releases: Dort bleiben ``RELEASES_N`` Kopien liegen.

    ``vintages`` und ``jahre`` sagen beide, wie viel Mehrjahrigkeit in
    ``bytes`` schon steckt - ``vintages`` in der Census-Dimension, ``jahre`` in
    der Jahres-Dimension -, und ``_regel`` teilt beide wieder heraus. Ein
    leeres ``jahre`` heisst "ein Jahrgang, naemlich ``basisjahr``" und ist das
    Verhalten, mit dem das Modul begann, als es nur Einjahresbauten gab.
    """

    schicht: str
    quelle: str
    regel: str
    bytes: int
    laeufe: int = 1
    vintages: int = 1
    staende: int = 1
    jahre: tuple[int, ...] = ()


class Hochgerechnet(NamedTuple):
    """Eine Basis, auf die Jahre gerechnet - mit der angewandten Regel."""

    basis: Basis
    faktor: float
    bytes: int
    wie: str


class Zeilen(NamedTuple):
    """Die gemessenen Zeilen je Stadt und Jahr, mit Herkunft."""

    je_stadt_und_jahr: dict[tuple[str, int], int]
    gemessen_am: str
    quellen: dict[str, str]


class Laufstand(NamedTuple):
    """Was ``data/pipeline_run.json`` ueber den letzten Gesamtlauf sagt.

    ``jahre`` sind die Jahrgaenge, die er gebaut hat, ``release`` die Kennung
    des Standes, den er dabei gebildet hat (leer, wenn er keinen bildete).
    Beides leer heisst: Es gibt kein Protokoll, und dann rechnet jede
    Tabellenschicht wieder mit einem Jahrgang als Basis.
    """

    jahre: tuple[int, ...] = ()
    release: str = ""


# ---------------------------------------------------------------------------
# Messen
# ---------------------------------------------------------------------------


def nur_lokal(data_root: Path | None = None) -> Storage:
    """Eine Ablage, die ausschliesslich diese Platte sieht.

    ``docs/intern/platzbedarf.md`` ist ein erzeugtes Artefakt und muss
    reproduzierbar sein. Mit ``STORAGE_BACKEND=hybrid`` zaehlte ``belegung``
    auch den gemeinsamen Bestand auf SeaweedFS mit - und dann stuende im
    Dokument, wer es gebaut hat, nicht was unter ``data/`` liegt. Gebaut wird
    die Ablage deshalb ohne ``load()``: keine ``.env``, kein Netz, kein
    Schluessel.
    """
    return Storage(Config(local_root=Path(data_root or "data")))


def belegung(ablage: Storage) -> tuple[Schicht, ...]:
    """Bytes und Dateizahl je Schicht, in der Reihenfolge der Strecke.

    Eine Schicht, die es nicht gibt, steht mit 0 Bytes und 0 Dateien da und
    bricht nichts ab: Ein frischer Klon hat ``data/serving`` noch nicht, und
    das ist kein Fehler, sondern der Anfang. ``.part``-Verzeichnisse zaehlen
    nie - ``Storage.groessen_unter`` laesst sie weg, wie jede andere Suche in
    der Ablage.
    """
    gemessen = []
    for name in SCHICHTEN:
        groessen = ablage.groessen_unter(name)
        gemessen.append(Schicht(name, sum(groessen.values()), len(groessen)))
    return tuple(gemessen)


def summe(schichten: tuple[Schicht, ...]) -> Schicht:
    """Alle Schichten zusammen - unter dem Namen ``data/``."""
    return Schicht("data/", sum(s.bytes for s in schichten),
                   sum(s.dateien for s in schichten))


def regel_fuer(quelle: str) -> str:
    """Die Regel einer Quelle - oder ein Abbruch, der sie nennt.

    Der Umweg ist Absicht und derselbe wie beim Feldkatalog: Eine neue Tabelle
    laesst den Lauf scheitern, statt still in eine geratene Regel zu fallen.
    """
    try:
        return REGEL_JE_QUELLE[quelle]
    except KeyError:
        raise SystemExit(
            f"Keine Regel fuer '{quelle}'. In REGEL_JE_QUELLE in "
            f"src/crime/orchestration/platzbedarf.py eintragen - erlaubt sind "
            f"{', '.join(sorted(ERKLAERUNG))}. Geraten wird hier nichts: Eine "
            f"falsche Regel faellt niemandem auf, ein Abbruch schon."
        ) from None


def _jahre_aus_liste(wert: Any) -> tuple[int, ...]:
    """``[2021, 2022]`` zu ``(2021, 2022)`` - und alles andere zu ``()``.

    Fremder Inhalt, auch wenn er aus dem eigenen Protokoll kommt: Ein Feld,
    das nicht so aussieht wie erwartet, heisst hier "weiss ich nicht" und
    nicht "Traceback".
    """
    if not isinstance(wert, list):
        return ()
    try:
        return tuple(sorted({int(jahr) for jahr in wert}))
    except (TypeError, ValueError):
        return ()


def _gelesen(ablage: Storage, *teile: str) -> dict[str, Any] | None:
    """Ein kleines JSON aus der Ablage - oder ``None``, wenn es nichts hergibt.

    Erst ``exists``, dann ``read_text``: Ohne die Frage vorher wirft der
    ``s3``-Modus eine Transportausnahme fuer eine Datei, die einfach nicht da
    ist. Jede Stoerung beim Lesen und jedes unlesbare JSON gelten hier als
    "nicht da" - dieses Modul misst und rechnet, es prueft nichts.
    """
    if not ablage.exists(*teile):
        return None
    try:
        gelesen = json.loads(ablage.read_text(*teile))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, StorageError):
        return None
    return gelesen if isinstance(gelesen, dict) else None


def laufstand(ablage: Storage) -> Laufstand:
    """Die Jahrgaenge des letzten Gesamtlaufs - gelesen, nicht geraten.

    ``run_all`` schreibt am Ende ``data/pipeline_run.json`` und nennt darin
    ``years`` (die gebauten Jahrgaenge) und ``release`` (den Stand, den er
    gebildet hat). Genau das braucht die Rechnung: Eine Silver-Tabelle sagt von
    sich aus nicht, wie viele Jahrgaenge in ihr stehen - sie ist eine Datei an
    einem Pfad ohne ``year=``.

    Gelesen wird **ueber die Ablage**, nicht ueber einen offenen Pfad: Im
    ``s3``-Modus liegt das Protokoll oben wie alles andere, und ein
    ``Path.open`` haette hier nur den ``local``-Modus bedient.

    **Nichts davon ist Pflicht.** Fehlt die Datei, ist sie kaputt oder nennt
    sie keine ``years``, kommt ein leerer ``Laufstand`` zurueck. Ein Abbruch
    waere falsch: Die Hochrechnung soll auch in einem Klon laufen, in dem noch
    kein Gesamtlauf lief, und ohne Protokoll gilt das alte Verhalten - ein
    Jahrgang je Stand.
    """
    protokoll = _gelesen(ablage, LAUF_MANIFEST)
    if protokoll is None:
        return Laufstand()
    freigabe = protokoll.get("release")
    kennung = freigabe.get("release_id") if isinstance(freigabe, dict) else None
    return Laufstand(_jahre_aus_liste(protokoll.get("years")),
                     str(kennung) if kennung else "")


def _je_eintrag(ablage: Storage, schicht: str) -> tuple[dict[str, int],
                                                        dict[str, set[str]]]:
    """Bytes je oberstem Eintrag unter ``schicht``, dazu dessen Vintages."""
    bytes_je: dict[str, int] = {}
    vintages: dict[str, set[str]] = {}
    for rel, groesse in ablage.groessen_unter(schicht).items():
        teile = rel.split("/")
        eintrag = teile[1] if len(teile) > 1 else teile[0]
        bytes_je[eintrag] = bytes_je.get(eintrag, 0) + groesse
        vintages.setdefault(eintrag, set()).update(
            teil.removeprefix("vintage=") for teil in teile
            if teil.startswith("vintage="))
    return bytes_je, vintages


def _laufschicht(ablage: Storage, schicht: str) -> list[Basis]:
    """Je Quelle der groesste fertige Lauf **je Vintage**, nicht die Summe aller.

    Eine Quelle haeuft Laeufe an - ``raw/city=chicago`` traegt mehrere, darunter
    mehr als eine Volladung. Sie zu addieren hiesse, das Anhaeufen mit
    hochzurechnen; was ein Jahrgang kostet, sagt der groesste.

    **Je Vintage, und das ist der Unterschied.** ``bytes`` muss in beiden Pfaden
    dasselbe bedeuten: in ``_tabellenschicht`` spannt es alle
    ``vintage=``-Partitionen einer Tabelle, und ``_regel`` teilt es fuer Census
    durch ``vintages``. Die erste Fassung hier nahm den groessten Lauf *ueber
    alle* Vintages und zaehlte die Vintages trotzdem alle - bei zwei geladenen
    Vintages kam fuer Census das Doppelte **eines** Vintages heraus statt des
    Vierfachen, und die gedruckte Regel nannte die halben Kosten je Vintage.
    Gruppiert wird deshalb erst je Vintage, dort der groesste Lauf, und das
    wird summiert.

    Ein Lauf gilt als **Einheit**, auch wenn er in mehreren Verzeichnissen
    liegt: Ein ACS-Lauf steht unter ``state=17`` und ``state=26``, ein
    NOAA-Lauf unter zwei Stationen. Gruppiert wird deshalb ueber den
    Verzeichnisnamen des Laufs, und die Teile werden addiert - dieselbe
    Einteilung, die ``orchestration.aufraeumen`` trifft.

    **Die Jahre bleiben leer, und hier ist das richtig.** ``jahre=()`` heisst
    "ein Jahrgang" - und ein Lauf traegt genau einen: ``run_all`` entfaltet die
    Ingestion je Jahr (``entfalte``, ``je="jahr"``) und ruft sie als
    ``chicago_2021`` ... ``chicago_2026`` einzeln auf, Detroit ebenso; Detroits
    Pfad schreibt den Jahrgang sogar als ``year=`` hin. ``max`` ueber die
    Laeufe liefert deshalb einen Jahrgang und nicht sechs. Das ist der Teil,
    der leicht wieder falsch wird: Sobald eine Quelle mehrere Jahrgaenge in
    **einem** Lauf laedt, gehoeren deren Jahre hierhin, sonst rechnet
    ``_regel`` sie ein zweites Mal hoch - genau der Fehler, den
    ``_tabellenschicht`` am 4.10.2026 hatte.
    """
    je_quelle: dict[str, dict[tuple[str, str], int]] = {}
    for lauf in ablage.laeufe(schicht):
        teile = lauf.relativ.split("/")
        quelle, verzeichnis = teile[1], teile[-1]
        vintage = next((teil.removeprefix("vintage=") for teil in teile
                        if teil.startswith("vintage=")), "")
        laeufe = je_quelle.setdefault(quelle, {})
        schluessel = (vintage, verzeichnis)
        laeufe[schluessel] = (laeufe.get(schluessel, 0)
                              + ablage.bytes_unter(lauf.relativ))

    gefunden: list[Basis] = []
    for quelle, laeufe in sorted(je_quelle.items()):
        je_vintage: dict[str, int] = {}
        for (vintage, _), groesse in laeufe.items():
            je_vintage[vintage] = max(je_vintage.get(vintage, 0), groesse)
        gefunden.append(Basis(
            schicht, quelle, regel_fuer(quelle), sum(je_vintage.values()),
            laeufe=len({verzeichnis for _, verzeichnis in laeufe}),
            vintages=len(je_vintage), jahre=()))
    return gefunden


def _tabellenschicht(ablage: Storage, schicht: str,
                     jahre: tuple[int, ...] = ()) -> list[Basis]:
    """Je Tabelle ihr jetziger Stand - und welche Jahrgaenge darin stehen.

    Silver, Gold und Serving werden **ersetzt**, nicht angehaeuft: Was
    dasteht, ist genau ein Stand. Bis zum 4.10.2026 stand hier weiter, ein
    Stand sei "damit schon die Basis je Jahrgang" - und das galt nur, solange
    ein Lauf einen Jahrgang baute. Seit dem Mehrjahreslauf tragen dieselben
    Dateien alle sechs, und die Rechnung nahm sie trotzdem noch einmal mit
    5,38: 9'345 MB statt 2'375 MB. ``jahre`` teilt das wieder heraus, genau
    wie ``vintages`` es fuer die Census-Dimension schon tat.

    Woher die Jahre kommen, sagt ``laufstand``: aus ``pipeline_run.json``, denn
    eine Silver-Tabelle liegt an einem Pfad ohne ``year=`` und sagt von sich
    aus nichts darueber. Fehlen sie, bleibt es beim alten Verhalten.
    """
    bytes_je, vintages = _je_eintrag(ablage, schicht)
    return [
        Basis(schicht, eintrag, regel_fuer(eintrag), groesse,
              vintages=max(len(vintages[eintrag]), 1), jahre=jahre)
        for eintrag, groesse in sorted(bytes_je.items())
    ]


def _release_jahre(ablage: Storage, verzeichnis: str,
                   stand: Laufstand) -> tuple[int, ...]:
    """Welche Jahrgaenge ein Release-Stand abdeckt - belegt, sonst ``()``.

    Zwei Wege, und der zweite nur mit Beweis:

    1. ``release.json`` nennt seit dem 4.10.2026 selbst ``years``
       (``storage.release.release_manifest``). Steht es da, gilt es - das ist
       die direkte Auskunft des Standes ueber sich selbst.
    2. Ein Stand von davor sagt es nicht: Sein Manifest kennt ``status``,
       ``release_id``, ``created_at_utc``, ``code_version``,
       ``contract_versions``, ``input_fingerprint``, ``derived_from``,
       ``gate``, ``tables``, ``files`` und ``bytes`` - keine Jahre. Dann gelten
       die Jahre aus ``pipeline_run.json``, **aber nur**, wenn dieses Protokoll
       genau diesen Stand als sein Release benennt.

    Sonst ``()``, und der Stand wird wie ein Jahrgang gerechnet. Geraten wird
    nichts: Der groesste liegende Stand kann aus einem Einjahresbau stammen,
    waehrend der letzte Lauf sechs Jahrgaenge baute - dann waere es die
    Hochrechnung, die zu klein ausfaellt, und zu klein ist hier die
    gefaehrliche Richtung.
    """
    manifest = _gelesen(ablage, release.RELEASES, verzeichnis,
                        release.RELEASE_MANIFEST) or {}
    if (eigene := _jahre_aus_liste(manifest.get("years"))):
        return eigene
    kennung = verzeichnis.removeprefix("release=")
    return stand.jahre if stand.release and stand.release == kennung else ()


def _releases(ablage: Storage, stand: Laufstand = Laufstand()) -> list[Basis]:
    """Der groesste Release-Stand, aufgeschluesselt nach seinem Inhalt.

    Ein Release ist kein Fass mit einer Groesse, sondern eine eingefrorene
    Kopie von Gold und Serving; ``fact_offense`` und die materialisierte
    DuckDB machen fast alles davon aus. Beide wachsen mit den Taten -
    ``RELEASES_N`` mal die **heutige** Groesse eines Standes waere deshalb zu
    wenig. Darum wird der Stand nach seinem Inhalt hochgerechnet und erst dann
    mit ``RELEASES_N`` genommen (``staende``). Gemessen wird der **groesste**
    Stand; die Staende unterscheiden sich untereinander um Zehntel-MB.

    Welche Jahrgaenge dieser Stand abdeckt, sagt ``_release_jahre`` - und nur,
    wenn es dafuer einen Beleg gibt. Ohne ihn wird er wie ein Jahrgang
    gerechnet, so wie vor dem Mehrjahreslauf.
    """
    staende: dict[str, dict[str, int]] = {}
    daneben: dict[str, int] = {}
    for rel, groesse in ablage.groessen_unter(release.RELEASES).items():
        teile = rel.split("/")
        if len(teile) > 2 and teile[1].startswith("release="):
            # releases/release=<Kennung>/<schicht>/<eintrag>/... bzw. release.json
            inhalt = "/".join(teile[2:4]) if len(teile) > 3 else teile[2]
            staende.setdefault(teile[1], {})
            staende[teile[1]][inhalt] = staende[teile[1]].get(inhalt, 0) + groesse
        else:
            name = teile[-1]
            daneben[name] = daneben.get(name, 0) + groesse

    gefunden: list[Basis] = []
    if staende:
        name_groesster, groesster = max(
            staende.items(), key=lambda eintrag: sum(eintrag[1].values()))
        jahre = _release_jahre(ablage, name_groesster, stand)
        for inhalt, groesse in sorted(groesster.items()):
            eintrag = inhalt.rsplit("/", 1)[-1]
            gefunden.append(Basis(release.RELEASES, inhalt, regel_fuer(eintrag),
                                  groesse, laeufe=len(staende),
                                  staende=RELEASES_N, jahre=jahre))
    for name, groesse in sorted(daneben.items()):
        gefunden.append(Basis(release.RELEASES, name, regel_fuer(name), groesse))
    return gefunden


def basis_je_jahrgang(ablage: Storage) -> tuple[Basis, ...]:
    """Was ein Jahrgang je Quelle und Schicht kostet - die Eingabe der Rechnung.

    Der ``Laufstand`` wird **einmal** gelesen und beiden Seiten gereicht: Die
    Tabellenschichten tragen die Jahrgaenge des letzten Laufs, ein Release nur
    dann, wenn es sich als dessen Stand ausweist. Die Laufschichten brauchen
    ihn nicht - dort traegt ein Lauf einen Jahrgang.
    """
    stand = laufstand(ablage)
    gefunden: list[Basis] = []
    for schicht in LAUFSCHICHTEN:
        gefunden.extend(_laufschicht(ablage, schicht))
    for schicht in TABELLENSCHICHTEN:
        gefunden.extend(_tabellenschicht(ablage, schicht, stand.jahre))
    gefunden.extend(_releases(ablage, stand))
    return tuple(gefunden)


# ---------------------------------------------------------------------------
# Die gemessenen Zeilen je Jahrgang
# ---------------------------------------------------------------------------


def zeilen_je_jahrgang(config_root: Path) -> Zeilen:
    """Liest ``config/zeilen_je_jahrgang.csv``.

    Die Zeilen je Stadt und Jahr sind **gemessene Fremddaten** und keine
    Konstante im Code: Sie wurden am 3.10.2026 an beiden APIs abgefragt, und
    sie aendern sich, wenn die Quellen nachmelden. Darum liegen sie mit
    Messdatum und Adresse unter ``config/`` - wie die Crosswalks, und aus
    demselben Grund: Eine Zahl ohne ihre Herkunft ist eine Behauptung.

    Die Datei liegt mit LF. Die ``.gitattributes`` bekommt dafuer **keine**
    ``eol``-Regel ueber ``config/``: Die Crosswalks daneben liegen absichtlich
    mit CRLF, und drei Tests vergleichen genau diese Bytes.
    """
    pfad = Path(config_root) / ZEILEN_DATEI
    if not pfad.is_file():
        raise SystemExit(
            f"{pfad} fehlt - ohne die gemessenen Zeilen je Jahrgang laesst "
            f"sich nichts hochrechnen."
        )
    je: dict[tuple[str, int], int] = {}
    gemessen: set[str] = set()
    quellen: dict[str, str] = {}
    with pfad.open(encoding="utf-8", newline="") as datei:
        for zeile in csv.DictReader(datei):
            if not zeile.get("stadt"):
                continue
            stadt = zeile["stadt"].strip().lower()
            je[(stadt, int(zeile["jahr"]))] = int(zeile["zeilen"])
            gemessen.add(zeile.get("gemessen_am", "").strip())
            quellen[stadt] = zeile.get("quelle", "").strip()
    return Zeilen(je, ", ".join(sorted(g for g in gemessen if g)), quellen)


def _fehlende_zeilen(jahre: tuple[int, ...], zeilen: Zeilen) -> list[str]:
    return [f"{stadt} {jahr}" for jahr in jahre for stadt in STAEDTE
            if (stadt, jahr) not in zeilen.je_stadt_und_jahr]


# ---------------------------------------------------------------------------
# Rechnen
# ---------------------------------------------------------------------------


def hochrechnung(basis: tuple[Basis, ...], jahre: tuple[int, ...],
                 zeilen: Zeilen, *, basisjahr: int = BASISJAHR
                 ) -> tuple[Hochgerechnet, ...]:
    """Jede Basis auf ``jahre`` gerechnet, je Quelle mit ihrer eigenen Regel.

    Vier Regeln statt eines Faktors - die Begruendung steht oben im Modul.
    Fehlt fuer ein Jahr eine gemessene Zeilenzahl, bricht das ab und nennt
    Stadt und Jahr: Ein stillschweigend uebersprungenes Jahr waere eine zu
    kleine Zahl, und eine zu kleine Zahl ist hier die gefaehrliche Richtung.
    Dasselbe gilt fuer die Jahrgaenge, die eine Basis schon abdeckt
    (``Basis.jahre``) - ohne ihre Zeilen laesst sich kein Jahrgang
    herausteilen.
    """
    jahre = tuple(sorted(set(jahre)))
    if not jahre:
        raise SystemExit("Keine Jahre angegeben - nichts hochzurechnen.")
    fehlend = _fehlende_zeilen(jahre, zeilen)
    if fehlend:
        raise SystemExit(
            f"Keine gemessene Zeilenzahl fuer {', '.join(fehlend)}. Sie gehoert "
            f"mit Messdatum und Adresse in config/{ZEILEN_DATEI} - geschaetzt "
            f"wird hier nichts."
        )
    if (basisjahr_fehlt := _fehlende_zeilen((basisjahr,), zeilen)):
        raise SystemExit(
            f"Keine gemessene Zeilenzahl fuer das Basisjahr "
            f"({', '.join(basisjahr_fehlt)}) - ohne sie gibt es keine Bytes "
            f"je Zeile."
        )
    # Dasselbe fuer die Jahrgaenge, die in den gemessenen Artefakten schon
    # drinstecken: Ohne ihre Zeilen laesst sich die Basis je Jahrgang nicht
    # herausteilen. Sie einfach weglassen hiesse, die Bytes auf zu wenige
    # Zeilen zu verteilen - also zu viele Bytes je Zeile und eine zu grosse
    # Hochrechnung.
    abgedeckt = tuple(sorted({jahr for b in basis for jahr in b.jahre}))
    if (deckung_fehlt := _fehlende_zeilen(abgedeckt, zeilen)):
        raise SystemExit(
            f"Keine gemessene Zeilenzahl fuer {', '.join(deckung_fehlt)} - "
            f"diese Jahrgaenge liegen gebaut da (data/{LAUF_MANIFEST}), also "
            f"gehoeren sie mit Messdatum und Adresse in "
            f"config/{ZEILEN_DATEI}."
        )

    noetige_vintages = vintages_for(jahre)
    gerechnet: list[Hochgerechnet] = []
    for b in basis:
        faktor, wie = _regel(b, jahre, zeilen, basisjahr, noetige_vintages)
        if b.staende > 1:
            faktor *= b.staende
            wie = f"{wie}, dann x {b.staende} Staende"
        gerechnet.append(Hochgerechnet(b, faktor, round(b.bytes * faktor), wie))
    return tuple(gerechnet)


def _staedte(quelle: str) -> tuple[str, ...]:
    """Welche Staedte in dieser Quelle stecken.

    ``raw/city=chicago`` traegt eine; ``silver/dataset=crime_offense`` und
    alles Abgeleitete tragen beide, und nur mit beiden stimmt dort das
    Verhaeltnis Bytes je Zeile.
    """
    if quelle.startswith("city="):
        return (quelle.removeprefix("city="),)
    return STAEDTE


def _regel(b: Basis, jahre: tuple[int, ...], zeilen: Zeilen, basisjahr: int,
           noetige_vintages: tuple[int, ...]) -> tuple[float, str]:
    if b.regel == KONSTANT:
        return 1.0, ERKLAERUNG[KONSTANT]

    if b.regel == CENSUS:
        # Nicht die Jahre kosten, sondern die Vintages: Ein Jahr jenseits des
        # juengsten veroeffentlichten ACS-Vintages borgt dieses statt ein
        # eigenes zu bekommen (census_pipeline.vintage_for). Ein Bereich
        # braucht deshalb in der Regel weniger Vintages, als er Jahre hat.
        faktor = len(noetige_vintages) / b.vintages
        je_vintage = b.bytes / b.vintages
        return faktor, (f"{len(noetige_vintages)} Vintages "
                        f"({', '.join(str(v) for v in noetige_vintages)}) x "
                        f"{je_vintage / 1e6:.1f} MB je Vintage")

    staedte = _staedte(b.quelle)
    # Die Jahres-Dimension, das Gegenstueck zu ``vintages`` darueber: Geteilt
    # wird durch die Zeilen der Jahrgaenge, die in ``bytes`` schon stecken -
    # nicht durch die des Basisjahrs. Ein fest angenommenes Basisjahr nahm die
    # sechs Jahrgaenge eines Silver-Standes noch einmal mit 5,38. Leer heisst
    # ein Jahrgang, naemlich das Basisjahr, und damit das alte Verhalten.
    abgedeckt = b.jahre or (basisjahr,)
    hier = sum(zeilen.je_stadt_und_jahr[(s, j)] for s in staedte for j in abgedeckt)
    dort = sum(zeilen.je_stadt_und_jahr[(s, j)] for s in staedte for j in jahre)
    return dort / hier, (f"{dort:,} Zeilen x {b.bytes / hier:.1f} Bytes je "
                         f"Zeile".replace(",", "'"))


def je_regel(gerechnet: tuple[Hochgerechnet, ...]) -> dict[str, tuple[int, int]]:
    """Basis und Hochrechnung je Regel - (Bytes jetzt, Bytes gerechnet)."""
    zusammen: dict[str, tuple[int, int]] = {}
    for h in gerechnet:
        name = RELEASES if h.basis.staende > 1 else h.basis.regel
        jetzt, dann = zusammen.get(name, (0, 0))
        zusammen[name] = (jetzt + h.basis.bytes, dann + h.bytes)
    return {name: zusammen[name] for name in ERKLAERUNG if name in zusammen}


def je_schicht(gerechnet: tuple[Hochgerechnet, ...]) -> dict[str, tuple[int, int]]:
    """Basis und Hochrechnung je Schicht, in der Reihenfolge der Strecke."""
    zusammen: dict[str, tuple[int, int]] = {}
    for h in gerechnet:
        jetzt, dann = zusammen.get(h.basis.schicht, (0, 0))
        zusammen[h.basis.schicht] = (jetzt + h.basis.bytes, dann + h.bytes)
    return {name: zusammen[name] for name in SCHICHTEN if name in zusammen}


# ---------------------------------------------------------------------------
# Darstellen
# ---------------------------------------------------------------------------


def megabyte(bytes_: int) -> str:
    """MB mit Komma und Schweizer Tausendertrenner - wie ueberall im Projekt."""
    return f"{bytes_ / 1e6:,.1f}".replace(",", "@").replace(".", ",").replace("@", "'")


def jahre_aus(text: str) -> tuple[int, ...]:
    """``2021-2026`` oder ``2024`` - der Bereich, auf den gerechnet wird.

    Jede Ablehnung ist ein ``SystemExit`` **mit Grund**. Ein nackter
    ``ValueError`` aus ``int()`` waere ein Traceback fuer einen Tippfehler an
    der Befehlszeile, und zwei Sorten Fehler fuer dieselbe Sache.
    """
    teile = text.replace(" ", "").split("-")
    if len(teile) > 2:
        raise SystemExit(f"--jahre versteht '2021-2026' oder '2024', nicht '{text}'")
    try:
        zahlen = [int(teil) for teil in teile]
    except ValueError:
        raise SystemExit(
            f"--jahre versteht Jahreszahlen, nicht '{text}' - "
            f"etwa '2021-2026' oder '2024'") from None
    if len(zahlen) == 1:
        return (zahlen[0],)
    von, bis = zahlen
    if bis < von:
        raise SystemExit(f"--jahre {text}: {bis} liegt vor {von}")
    return tuple(range(von, bis + 1))


def als_json(schichten: tuple[Schicht, ...], gerechnet: tuple[Hochgerechnet, ...],
             jahre: tuple[int, ...], zeilen: Zeilen,
             backend: str = "local") -> dict[str, Any]:
    return {
        "jahre": list(jahre),
        "basisjahr": BASISJAHR,
        "backend": backend,
        "gemessen_am": zeilen.gemessen_am,
        "belegung": [s._asdict() for s in schichten],
        "summe": summe(schichten)._asdict(),
        "hochrechnung": [
            {**h.basis._asdict(), "faktor": round(h.faktor, 4),
             "hochgerechnet_bytes": h.bytes, "wie": h.wie}
            for h in gerechnet
        ],
        "je_regel": {name: {"jetzt_bytes": j, "hochgerechnet_bytes": d}
                     for name, (j, d) in je_regel(gerechnet).items()},
        "regeln": ERKLAERUNG,
    }


def zeige(schichten: tuple[Schicht, ...], gerechnet: tuple[Hochgerechnet, ...],
          jahre: tuple[int, ...], zeilen: Zeilen, backend: str = "local") -> None:
    # Der Modus gehoert dazu, nicht als Fussnote: Im ``hybrid``-Modus zaehlt
    # ``belegung`` den gemeinsamen Bestand auf SeaweedFS mit, und dann ist die
    # Summe nicht die Belegung dieser Platte. ``tools/build_platzbedarf.py``
    # misst darum immer lokal - ein erzeugtes Dokument darf nicht davon
    # abhaengen, wer es gebaut hat.
    print(f"Belegung je Schicht (STORAGE_BACKEND={backend})")
    for s in schichten:
        vermerk = "" if s.dateien else "   (nicht gebaut)"
        print(f"  {s.name:<10} {megabyte(s.bytes):>9} MB  {s.dateien:>5} Dateien{vermerk}")
    ganz = summe(schichten)
    print(f"  {'-' * 10} {'-' * 9}     {'-' * 5}")
    print(f"  {ganz.name:<10} {megabyte(ganz.bytes):>9} MB  {ganz.dateien:>5} Dateien")

    if not gerechnet:
        print(f"\nKeine Hochrechnung: unter {ganz.name} liegt nichts. Erst "
              f"'python -m orchestration.run_all' laufen lassen.")
        return

    bereich = f"{jahre[0]}-{jahre[-1]}" if len(jahre) > 1 else str(jahre[0])
    # Welche Jahrgaenge gebaut daliegen, gehoert in die Kopfzeile: "Basis 2024"
    # allein hiesse, die Tabellenschichten traegen einen Jahrgang - und genau
    # diese Annahme war der Fehler, den ``Basis.jahre`` behebt.
    abgedeckt = tuple(sorted({jahr for h in gerechnet for jahr in h.basis.jahre}))
    gebaut = (f", gebaut liegen {abgedeckt[0]}-{abgedeckt[-1]}"
              if len(abgedeckt) > 1 else "")
    print(f"\nHochrechnung auf {bereich}, Basis {BASISJAHR}{gebaut} "
          f"(Zeilen gemessen am {zeilen.gemessen_am})")
    for name, (jetzt, dann) in je_regel(gerechnet).items():
        print(f"  {name:<10} {ERKLAERUNG[name]}")
        print(f"             {megabyte(jetzt):>9} MB -> {megabyte(dann):>9} MB")

    print("\nJe Quelle")
    schicht = None
    for h in gerechnet:
        if h.basis.schicht != schicht:
            schicht = h.basis.schicht
            print(f"\n  {schicht}")
        wort = "Staende" if h.basis.staende > 1 else "Laeufe"
        laeufe = f"{h.basis.laeufe} {wort}" if h.basis.laeufe > 1 else ""
        print(f"    {h.basis.quelle:<32} {megabyte(h.basis.bytes):>8} MB -> "
              f"{megabyte(h.bytes):>9} MB  {h.basis.regel}: {h.wie}"
              + (f"  [{laeufe}]" if laeufe else ""))

    hoch = sum(h.bytes for h in gerechnet)
    print(f"\n{bereich}: {megabyte(ganz.bytes)} MB jetzt -> {megabyte(hoch)} MB "
          f"({hoch / 1e9:.2f} GB) hochgerechnet.")
    print("Gerechnet ist ein Lauf je Quelle und Jahrgang, nicht ein data/, das "
          "wochenlang mitlaeuft.")


def arguments(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m orchestration.platzbedarf",
        description="Misst die Belegung je Schicht und rechnet sie je Quelle "
                    "auf einen Jahresbereich hoch - mit einer Regel je Quelle "
                    "statt einem Faktor fuer alles.")
    p.add_argument("--data-root", type=Path, default=None,
                   help="lokale Wurzel (Vorgabe: LOCAL_DATA_ROOT oder data)")
    p.add_argument("--config-root", type=Path, default=Path("config"),
                   help=f"wo {ZEILEN_DATEI} liegt (Vorgabe: config)")
    p.add_argument("--jahre", default="2021-2026",
                   help="der Bereich, auf den gerechnet wird (Vorgabe 2021-2026)")
    p.add_argument("--json", action="store_true",
                   help="als JSON statt als Tabelle - fuer Werkzeuge")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = arguments(argv)
    ablage = for_root(args.data_root)
    jahre = jahre_aus(args.jahre)
    schichten = belegung(ablage)
    zeilen = zeilen_je_jahrgang(args.config_root)

    basis = basis_je_jahrgang(ablage)
    # Ein frischer Klon hat kein data/. Dann gibt es keine Basis, und ohne
    # Basis wird nicht geteilt - ein Hinweis, kein Abbruch und erst recht
    # keine Division durch Null.
    gerechnet = hochrechnung(basis, jahre, zeilen) if basis else ()

    if args.json:
        print(json.dumps(als_json(schichten, gerechnet, jahre, zeilen, ablage.backend),
                         indent=2, ensure_ascii=False))
    else:
        zeige(schichten, gerechnet, jahre, zeilen, ablage.backend)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
