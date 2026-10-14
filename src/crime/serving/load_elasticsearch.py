"""Laedt ein Release nach Elasticsearch - fuer die Fragen, die SQL schlecht stellt.

    python -m serving.load_elasticsearch              # das aktuelle Release
    python -m serving.load_elasticsearch --trocken    # nur zeigen, was liefe

**Was dieser Index kann, was eine SQL-Konsole nicht kann.**

1. **Volltext.** ``source_offense_description`` traegt 421 verschiedene
   Beschreibungen wie *ARSON: POSSESSION - EXPLOSIVE / INCENDIARY DEVICE*. Wer
   "explosive" sucht, muesste in SQL ``LIKE '%EXPLOSIVE%'`` schreiben und
   damit jede Zeile lesen. Elasticsearch hat den Wortindex dafuer.
2. **Umkreis.** 342'727 der 345'073 Zeilen tragen Koordinaten. *Alle Delikte
   im Umkreis von 500 m um diesen Punkt* ist in ``geo_distance`` eine Zeile -
   und genau die Frageform, die eine Wirkungsanalyse zu einer ortsgebundenen
   Massnahme braucht.
3. **Facetten.** Der Einstieg eines Analysten ist ein Suchfeld mit Zaehlern
   daneben, nicht eine leere SQL-Konsole.

**Warum hier das ganze Sternschema liegt und nicht ein Teil davon.** Bis zum
5.10.2026 lagen nur drei der sechs Gold-Tabellen hier - "nur was Text oder Ort
traegt" -, und ``dim_date`` und ``dim_city_day`` lagen in ClickHouse. Diese
Arbeitsteilung traegt nicht mehr: ClickHouse wird nicht mehr geladen
(Entscheid 5.10.2026), und damit lagen die Kalender- und die Wetterzahlen
nirgends mehr abfragbar. ``dim_tract_acs`` lag sogar in **keinem** der beiden
Speicher - sie kam mit Vertrag 6 und wurde in keinen Lader eingetragen.

Das war kein Fehler, der aufgefallen waere, sondern eine falsche Antwort:
``fact_offense`` traegt mit ``population_vintage`` nur den **Zeiger** auf den
richtigen Nenner. Ohne ``dim_tract_acs`` fehlt der Nenner selbst, und eine
Rate je 1'000 Einwohner ist aus Elasticsearch allein nicht zu rechnen - genau
die verlangen FR-27 und FR-31. Seither gilt die Zusage, dass ``INDIZES`` die
Tabellen aus ``gold_pipeline.TABELLEN`` **erschoepft**; ein Test haelt sie
fest, statt sie zu behaupten.

**Ein Stern in sechs Indizes ist seit dem 11.10.2026 wieder ein Stern.** Bis
dahin stand hier, Elasticsearch kenne keinen Join und wer Tat und Nenner
zusammenbringen wolle, stelle zwei Abfragen. Das stimmt seit 8.19 nicht mehr:
ES|QL hat ``LOOKUP JOIN``, und damit laesst sich die Rate je 1'000 Einwohner in
**einer** Abfrage rechnen - gemessen und zeichengleich mit den
Abgabedokumenten (siehe ``serving.build_kibana``).

Die Faehigkeit allein reicht aber nicht: Ein Nachschlagindex muss mit
``index.mode: lookup`` angelegt sein, sonst antwortet Elasticsearch mit
*„Lookup Join requires a single lookup mode index"*. Der Modus ist deshalb am
``Index`` entschieden (``nachschlag``) und wird nicht aus dem Namen geraten.
Die Quelle der Wahrheit bleibt trotzdem Parquet; wer rechnen will, was nicht
im Dashboard steht, nimmt die DuckDB-Sichten.

**Die Zusage, die auch hier gilt.** Geladen wird nie in ``fact_offense``,
sondern in einen Index, dessen Name das Release traegt. Erst nach bestandenem
Abgleich zeigt der **Alias** ``fact_offense`` darauf. Elasticsearch legt einen
Aliaswechsel atomar um, wenn Entfernen und Hinzufuegen in einem Aufruf stehen -
das ist dasselbe Versprechen wie das ``.part``-Umbenennen in ``storage``.

**Was hier Entscheidung ist und was abgelesen.** Abgelesen wird die
Spaltenliste aus dem Parquet. Entschieden ist, welche Felder durchsuchbar
(``text``) statt nur filterbar (``keyword``) sind und welches Spaltenpaar zum
Ort wird - Fragen, die niemand aus einem Schema ableiten kann. Ein Test haelt
beides gegeneinander: Jede Spalte des Releases braucht eine Entscheidung.

**Was an Elasticsearch anders ist als an einer Datenbank - und teuer war.**

*Geschriebenes ist nicht sofort sichtbar.* Ein Zaehlen direkt nach dem Laden
liefert zu wenig, weil der Index noch nicht aufgefrischt ist. Deshalb steht
``_refresh`` zwischen Schreiben und Pruefen, und nicht aus Hoeflichkeit.

*Die Massen-Schnittstelle meldet Erfolg, auch wenn sie scheitert.* ``_bulk``
antwortet mit HTTP 200 und traegt die Fehler einzeln im Rumpf. Wer nur den
Statuscode prueft, laedt die Haelfte und merkt es nie.

*Zaehlen ist nicht gleich zaehlen.* ``cardinality`` schaetzt (HyperLogLog) und
taugt fuer keinen Nachweis. Deshalb wird Eindeutigkeit hier nicht gemessen,
sondern erzwungen: Der Schluessel ist die Dokument-ID. Zwei gleiche Schluessel
ueberschreiben einander, und dann steht die Zeilenzahl nicht mehr - die
Zeilenpruefung *ist* die Schluesselpruefung.

*Auch ``terms`` schaetzt.* Fuer die Verteilung steht deshalb ``composite`` da:
Es zaehlt vollstaendig und blaettert. Mit ``missing_bucket`` faellt ausserdem
nichts weg, was NULL traegt - ``terms`` laesst solche Zeilen still unter den
Tisch fallen, und der Abgleich saehe trotzdem gruen aus.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite
from pathlib import Path
from typing import Any, Protocol

import pyarrow.parquet as pq

# Eine Frage, zwei Engines - nicht zwei Umsetzungen, die auseinanderlaufen
# koennen. ``abgleich_release`` liest nur ``.verteilung`` und ``.schluessel``,
# und genau die traegt ``Index`` unter denselben Namen.
from serving.load_clickhouse import LadeFehler, abgleich_release, vergleiche

DATENWURZEL = Path("data")

#: 9200 ist die Voreinstellung - und auf Entwicklungsrechnern regelmaessig von
#: etwas anderem belegt. Ein eigener Port kostet nichts und nimmt niemandem
#: seinen Dienst weg.
STANDARD_URL = "http://localhost:19200"

#: Die Variable, mit der die Umgebung diese Adresse ersetzt. Im Verbund heisst
#: der Dienst nicht ``localhost``, sondern so, wie das Compose-Netz ihn nennt
#: (``http://elasticsearch:9200``) - und ein Container kann keine
#: Kommandozeile tippen. Das Argument ``--url`` sticht sie weiterhin: Was
#: jemand hinschreibt, gilt vor dem, was in der Umgebung steht.
UMGEBUNGSVARIABLE = "ELASTICSEARCH_URL"


def vorgabe_url(umgebung: Mapping[str, str] | None = None) -> str:
    """Die Adresse, mit der ohne ``--url`` gearbeitet wird."""
    umgebung = os.environ if umgebung is None else umgebung
    return (umgebung.get(UMGEBUNGSVARIABLE) or "").strip() or STANDARD_URL


#: Wieviele Dokumente in einen ``_bulk``-Aufruf gehen. Gross genug, dass die
#: 345'073 Zeilen nicht in 345'073 Anfragen zerfallen; klein genug, dass der
#: Rumpf im einstelligen Megabyte-Bereich bleibt.
STAPEL = 5_000


# --------------------------------------------------------------------------
# Die Entscheidungen. Alles hier ist Abwaegung, keine Ableitung.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Index:
    """Was fuer einen Index entschieden werden muss, damit er etwas kann."""

    name: str
    #: Wird zur Dokument-ID. Damit ist Eindeutigkeit strukturell zugesichert
    #: und muss nicht geschaetzt werden - siehe Modulkopf.
    schluessel: tuple[str, ...]
    #: Spalten, ueber die der Abgleich gruppiert. Erlaubt sind Text und
    #: Ganzzahlen, nichts sonst: Ein Wahrheitswert kommt aus DuckDB als
    #: ``True`` und aus JSON als ``true``, ein Datum als ``date`` und von
    #: ``composite`` als Millisekunden seit 1970, und eine Gleitkommazahl
    #: vergleicht sich ohnehin nicht. In allen drei Faellen schluege der
    #: Abgleich an, ohne dass etwas fehlt.
    verteilung: tuple[str, ...]
    #: Spalten, die zerlegt und wortweise durchsuchbar werden. Alles andere
    #: bleibt ``keyword``: exakt, filterbar, gruppierbar. Die Voreinstellung
    #: ist bewusst die strengere - ``text`` ist die Ausnahme, die man
    #: begruenden muss.
    volltext: frozenset[str] = frozenset()
    #: ``(Breite, Laenge)``. Beide Spalten gehen im Feld ``standort`` auf und
    #: erscheinen nicht noch einmal einzeln: Ein Ort ist ein Wert, nicht zwei.
    geo: tuple[str, str] | None = None
    #: Die Spalte mit dem Umriss, als WKT. Wird ``geo_shape`` statt
    #: ``keyword``.
    #:
    #: Getrennt von ``geo``: Ein ``geo_point`` entsteht aus **zwei**
    #: Zahlenspalten und heisst danach ``standort``; eine Flaeche ist **eine**
    #: Textspalte und behaelt ihren Namen. Ohne diesen Eintrag laege der
    #: Umriss als ``keyword`` im Index - filterbar, gruppierbar und fuer eine
    #: Karte vollkommen nutzlos, und zwar ohne Fehlermeldung.
    flaeche: str | None = None
    #: Darf dieser Index in einem ES|QL-``LOOKUP JOIN`` rechts stehen?
    #:
    #: Entschieden am Index und nicht am Namen geraten: ``index.mode: lookup``
    #: ist eine Eigenschaft, die beim **Anlegen** gesetzt werden muss und
    #: danach feststeht. Ohne ihn bricht nicht der Ladelauf ab, sondern erst
    #: die Abfrage - mit *„Lookup Join requires a single lookup mode index;
    #: [dim_tract_acs] resolves to … in [standard] mode"*, und zwar in Kibana
    #: vor jemandem, der eine Zahl sehen wollte.
    #:
    #: Der Modus kostet eine Einschraenkung: Ein Lookup-Index hat genau einen
    #: Schnipsel. Elasticsearch weist ``number_of_shards: 2`` dafuer zurueck -
    #: hier unschaedlich, weil ohnehin einer gesetzt ist (ein Knoten).
    nachschlag: bool = False

    @property
    def quelle_im_release(self) -> str:
        return f"gold/dataset={self.name}/part-0001.parquet"


#: Alle Gold-Tabellen, Zeit und Zahlen eingeschlossen - und das ist eine
#: Zusage, nicht eine Aufzaehlung: ``INDIZES`` erschoepft
#: ``gold_pipeline.TABELLEN``, und ``test_load_elasticsearch`` haelt es fest.
#: Eine siebte Gold-Tabelle faellt damit nicht mehr still daneben, wie
#: ``dim_tract_acs`` es von Vertrag 6 bis zum 5.10.2026 tat. Warum nicht mehr
#: "nur was Text oder Ort traegt" gilt, steht im Modulkopf.
INDIZES: tuple[Index, ...] = (
    Index(
        name="fact_offense",
        # Gemessen am Release 2026-09-21T12-55-05Z: 345'073 Zeilen, ebenso
        # viele verschiedene offense_id. Der Schluessel traegt also.
        schluessel=("offense_id",),
        verteilung=("reporting_city", "mapping_status", "geo_status"),
        # Die einzige Spalte mit echter Sprache: 421 verschiedene Werte, 13
        # davon NULL. nibrs_code und die Statusspalten sind Kennungen - wer
        # die zerlegt, findet "11A" unter "11" und hat nichts gewonnen.
        volltext=frozenset({"source_offense_description"}),
        geo=("latitude", "longitude"),
    ),
    Index(
        name="dim_offense",
        schluessel=("nibrs_code",),
        verteilung=("nibrs_group", "crime_against"),
        # Das Nachschlagewerk, in dem ein Analyst blaettert: Wer "burglary"
        # tippt, soll den Code finden, ohne ihn zu kennen.
        volltext=frozenset({
            "nibrs_description", "nibrs_category", "retirement_note",
            "resolution"}),
    ),
    Index(
        name="dim_tract",
        schluessel=("geoid",),
        verteilung=("state_fips", "county_fips"),
        volltext=frozenset({"tract_name"}),
        # Der Schwerpunkt, nicht die Flaeche. Fuer *welcher Tract liegt in
        # der Naehe* reicht der Punkt; fuer *liegt dieser Punkt im Tract*
        # nicht - das bleibt die Aufgabe der Zuordnung in Silver. Die
        # Umrisse stehen seit Vertrag 8 in ``dim_tract_geo``, und zwar
        # bewusst nicht hier: Diese Dimension deckt beide Countys ab und
        # waere mit Geometrie 26 MB statt 194 KB.
        geo=("centroid_lat", "centroid_lon"),
    ),
    Index(
        name="dim_tract_geo",
        # Eine Zeile je Tract mit Stadt - 1'055 von den 6'282 in dim_tract.
        schluessel=("geoid",),
        # Nach Stadt laesst sich gruppieren, nach geoid waere es die
        # Schluesselpruefung ein zweites Mal in 1'055 Eimern.
        verteilung=("city",),
        volltext=frozenset({"tract_name"}),
        flaeche="boundary_wkt",
        # Fuer die Karte: Kibana faerbt die Flaechen und holt die Rate je
        # Tract ueber ``geoid`` dazu. Ohne index.mode lookup lehnt
        # Elasticsearch den Verbund ab - und zwar erst, wenn jemand die Karte
        # oeffnet.
        nachschlag=True,
    ),
    Index(
        name="dim_tract_acs",
        # Ein Tract kommt je Vintage einmal vor; erst das Paar ist eindeutig.
        # Gemessen am Release 2026-10-04T16-50-47Z: 25'128 Zeilen, ebenso
        # viele verschiedene (geoid, vintage) - vier Vintages mal 6'282
        # Tracts. ``geoid`` allein waere viermal belegt, und weil der
        # Schluessel die Dokument-ID ist, blieben 6'282 Dokumente uebrig: Der
        # Abgleich faellt, und zwar genau deshalb (siehe Modulkopf).
        schluessel=("geoid", "vintage"),
        # Die einzige Spalte, die sich gruppieren laesst, ohne der Schluessel
        # selbst zu sein. Eine Verteilung ueber ``geoid`` waere die
        # Schluesselpruefung ein zweites Mal, in 25'128 Eimern.
        verteilung=("vintage",),
        # Kein Volltext: ``geoid`` ist eine Kennung, und wer sie zerlegt,
        # findet 17031010100 unter 17031. Kein Ort: Die Flaeche steht in
        # ``dim_tract``, hier steht nur, wie viele Menschen darin leben.
        #
        # Der Nennerindex des Projekts - und damit der eine, der in einem
        # ``LOOKUP JOIN`` rechts stehen muss: Die Rate je 1'000 Einwohner
        # braucht Zaehler (``fact_offense``) und Nenner (hier) in einer
        # Abfrage. Die uebrigen fuenf bleiben ``standard``: Ein Modus, den
        # niemand braucht, ist eine Einschraenkung ohne Gegenwert.
        nachschlag=True,
    ),
    Index(
        name="dim_date",
        schluessel=("date",),
        # Der Kalender hat keine Statusspalten. ``day_name`` und
        # ``month_name`` sind das, was sich gruppieren laesst: 7 mal 12
        # Eimer, und jeder Tag des Jahrgangs faellt in genau einen. Fehlt ein
        # Wochentag oder ein Monat, faellt es hier auf. ``quarter`` und
        # ``month`` waeren dasselbe in Zahlen, aber eine Fehlermeldung mit
        # "Friday" darin liest sich besser als eine mit "5".
        verteilung=("day_name", "month_name"),
        # Kein Volltext: ``day_name`` und ``month_name`` sind Aufzaehlungen
        # mit sieben beziehungsweise zwoelf Werten, keine Sprache.
    ),
    Index(
        name="dim_city_day",
        # Eine Stadt hat je Tag eine Wetterzeile; erst das Paar ist
        # eindeutig. Gemessen: 4'196 Zeilen, ebenso viele verschiedene
        # (city, date).
        schluessel=("city", "date"),
        verteilung=("city", "station_id"),
        # ``station_name`` traegt zwei Werte ("DETROIT METRO AIRPORT, MI US"
        # und das Chicagoer Gegenstueck). Zwei Auspraegungen rechtfertigen
        # keinen Wortindex - ``text`` bleibt die Ausnahme, die man begruenden
        # muss, und hier liesse sie sich nicht begruenden.
        #
        # ``quality_flags`` ist eine Liste und bleibt ``keyword``:
        # Elasticsearch kennt keinen Listentyp, ein Feld nimmt einen Wert
        # oder viele. Filterbar ist es dadurch wie jede andere Kennung.
    ),
)

NACH_NAME = {i.name: i for i in INDIZES}


#: Arrow sagt, was in der Datei steht; Elasticsearch braucht seinen eigenen
#: Namen dafuer. Kein Eintrag heisst: Diese Spalte ist noch nicht entschieden,
#: und der Bau bricht ab, statt zu raten.
#:
#: ``string`` wird ``keyword`` und nicht ``text``. Das ist die wichtigere
#: Haelfte der Entscheidung: Auf ``text`` laesst sich nicht gruppieren, und
#: ein versehentlich zerlegtes Feld faellt erst auf, wenn eine Auswertung
#: leer zurueckkommt.
TYPEN = {
    "string": "keyword",
    "bool": "boolean",
    "double": "double",
    "int8": "byte",
    "int16": "short",
    "int32": "integer",
    "int64": "long",
    "date32[day]": "date",
    # Gemessen: kein einziger der 345'073 Zeitstempel traegt Bruchteile einer
    # Sekunde. Elasticsearchs ``date`` loest Millisekunden auf und verliert
    # hier also nichts. ``pruefe_zeitgenauigkeit`` haelt das fest, damit die
    # Aussage nicht stillschweigend veraltet.
    "timestamp[us]": "date",
    "timestamp[ms]": "date",
    "timestamp[s]": "date",
    # Elasticsearch kennt keinen Listentyp: Jedes Feld nimmt einen Wert oder
    # viele, der Typ bleibt derselbe.
    "list<element: string>": "keyword",
}


@dataclass(frozen=True)
class Feld:
    name: str
    arrow: str
    index: str = "fact_offense"

    @property
    def abbildung(self) -> dict[str, Any]:
        grund = TYPEN.get(self.arrow)
        if grund is None:
            raise LadeFehler(
                f"Fuer {self.name} ({self.arrow}) ist kein Elasticsearch-Typ "
                f"entschieden. Eintrag in TYPEN ergaenzen - geraten wird nicht."
            )
        if self.name not in NACH_NAME[self.index].volltext:
            return {"type": grund}
        if grund != "keyword":
            raise LadeFehler(
                f"{self.name} steht in volltext, ist aber {grund} - "
                f"durchsuchbar wird nur Text.")
        # Beides, und das ist kein Zaudern: ``text`` findet das Wort im Satz,
        # ``keyword`` zaehlt die Auspraegung. Ohne das Unterfeld scheitert
        # jede Gruppierung ueber die Beschreibung.
        return {"type": "text", "fields": {"keyword": {"type": "keyword"}}}


# --------------------------------------------------------------------------
# Abgelesen: was im Release wirklich steht
# --------------------------------------------------------------------------


def felder(parquet: Path, index: str = "fact_offense") -> list[Feld]:
    """Die Spalten aus der Datei - nicht aus einer zweiten Liste.

    Anders als bei ClickHouse wird hier **nicht** gezaehlt, wo NULL steht:
    Elasticsearch kennt keine Nullbarkeit. Ein Feld ist in einem Dokument da
    oder nicht, und beides ist erlaubt.
    """
    from storage import parquet_schema

    # Nicht ueber ``DESCRIBE``: DuckDB erfindet aus einem Hive-Pfad Spalten
    # dazu, die in keiner Datei stehen. Siehe ``storage.parquet``.
    return [Feld(f.name, str(f.type), index) for f in parquet_schema(parquet)]


def indexname(release_id: str, index: str = "fact_offense") -> str:
    """``2026-09-21T12-55-05Z`` -> ``fact_offense-20260921t125505z``.

    Elasticsearch verlangt Kleinbuchstaben in Indexnamen und verweigert
    Doppelpunkte. Der Bindestrich als Trenner ist dort ueblich, wo ClickHouse
    den Unterstrich nimmt - die Kennung bleibt in beiden Faellen lesbar.
    """
    return f"{index}-{re.sub(r'[^0-9A-Za-z]', '', release_id)}".lower()


# --------------------------------------------------------------------------
# Die erzeugten Anweisungen. Reine Funktionen - pruefbar ohne Elasticsearch.
# --------------------------------------------------------------------------


def mapping(liste: list[Feld], index: Index) -> dict[str, Any]:
    """Die Abbildung - und die Zusicherung, dass keine Spalte durchrutscht.

    ``dynamic: strict`` ist der Kern: Ohne ihn raet Elasticsearch den Typ
    eines unbekannten Feldes aus dem ersten Wert, den es sieht. Eine neue
    Gold-Spalte laege dann still im Index, mit einem geratenen Typ, und
    niemand haette entschieden. Mit ``strict`` scheitert stattdessen das
    Schreiben - genau da, wo es auffaellt.
    """
    nach_name = {f.name: f for f in liste}
    for name in index.schluessel:
        if name not in nach_name:
            raise LadeFehler(f"{name} steht im Schluessel, aber nicht im Release")

    verbraucht: set[str] = set()
    eigenschaften: dict[str, Any] = {}
    if index.geo:
        for name in index.geo:
            feld = nach_name.get(name)
            if feld is None:
                raise LadeFehler(
                    f"{name} ist als Ortsspalte gesetzt, steht aber nicht im "
                    f"Release")
            if TYPEN.get(feld.arrow) != "double":
                raise LadeFehler(
                    f"{name} ist als Ortsspalte gesetzt, ist aber "
                    f"{feld.arrow} - Koordinaten sind Gleitkommazahlen.")
        verbraucht.update(index.geo)
        eigenschaften["standort"] = {"type": "geo_point"}

    if index.flaeche:
        feld = nach_name.get(index.flaeche)
        if feld is None:
            raise LadeFehler(
                f"{index.flaeche} ist als Flaechenspalte gesetzt, steht aber "
                f"nicht im Release")
        if TYPEN.get(feld.arrow) != "keyword":
            raise LadeFehler(
                f"{index.flaeche} ist als Flaechenspalte gesetzt, ist aber "
                f"{feld.arrow} - ein Umriss kommt als WKT-Zeichenkette.")
        verbraucht.add(index.flaeche)
        # ``ignore_malformed`` bewusst **nicht**: Ein Umriss, den
        # Elasticsearch nicht versteht, soll den Ladelauf anhalten und nicht
        # als Loch in der Karte erscheinen, das niemand einer Ursache
        # zuordnen kann.
        eigenschaften[index.flaeche] = {"type": "geo_shape"}

    for feld in liste:
        if feld.name not in verbraucht:
            eigenschaften[feld.name] = feld.abbildung

    einstellungen: dict[str, Any] = {
        # Ein Knoten, keine Kopie: Der Dienst laeuft neben der Pipeline
        # und nicht in einem Rechenzentrum. Eine Replik auf demselben
        # Knoten bleibt ohnehin unzugewiesen und faerbt den Zustand gelb.
        "number_of_shards": 1,
        "number_of_replicas": 0,
    }
    if index.nachschlag:
        # Nur beim Anlegen setzbar, und nur so wird der Index fuer
        # ``LOOKUP JOIN`` ansprechbar - siehe ``Index.nachschlag``. Ein
        # nachtraegliches ``PUT /_settings`` lehnt Elasticsearch ab; wer den
        # Modus will, laedt den Index neu.
        einstellungen["mode"] = "lookup"

    return {
        "settings": einstellungen,
        "mappings": {"dynamic": "strict", "properties": eigenschaften},
    }


def _wert(v: Any) -> Any:
    """Was JSON nicht kann, und was Elasticsearch nicht annimmt."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.isoformat(timespec="seconds")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float):
        # ``json.dumps`` schreibt fuer NaN und Infinity die nackten Woerter
        # hin. Das ist kein gueltiges JSON, und Elasticsearch weist den
        # ganzen Stapel zurueck - wegen eines einzigen Wertes.
        return v if isfinite(v) else None
    return v


def dokumente(parquet: Path, index: Index) -> Iterator[tuple[str, dict]]:
    """``(Dokument-ID, Dokument)`` je Zeile des Releases.

    Stapelweise gelesen und nicht am Stueck: Das Release traegt 345'073
    Zeilen, und die muessen nicht alle gleichzeitig als Python-Objekte im
    Speicher liegen.
    """
    datei = pq.ParquetFile(parquet)
    geo = set(index.geo or ())
    for stapel in datei.iter_batches(batch_size=STAPEL):
        for zeile in stapel.to_pylist():
            dokument = {k: _wert(v) for k, v in zeile.items()
                        if k not in geo and v is not None}
            if index.geo:
                breite, laenge = (zeile[index.geo[0]], zeile[index.geo[1]])
                # Fehlt der Ort, fehlt das Feld. Ein ``null`` an dieser
                # Stelle wiese Elasticsearch als ungueltigen geo_point
                # zurueck - 2'346 Zeilen ohne Koordinaten haetten gereicht,
                # um den Lauf scheitern zu lassen.
                if breite is not None and laenge is not None:
                    dokument["standort"] = {"lat": breite, "lon": laenge}
            kennung = "|".join(str(zeile[s]) for s in index.schluessel)
            yield kennung, dokument


def massenrumpf(ziel: str, teil: list[tuple[str, dict]]) -> str:
    """Der ``_bulk``-Rumpf: je Dokument zwei Zeilen, getrennt durch Umbrueche.

    ``index`` und nicht ``create``: Ein zweites Dokument mit derselben
    Kennung soll das erste ersetzen und nicht scheitern. Genau dadurch wird
    ein doppelter Schluessel an der Zeilenzahl sichtbar, statt einen
    Fehlerhaufen zu erzeugen - siehe Modulkopf.
    """
    zeilen = []
    for kennung, dokument in teil:
        zeilen.append(json.dumps({"index": {"_index": ziel, "_id": kennung}}))
        zeilen.append(json.dumps(dokument, ensure_ascii=False))
    return "\n".join(zeilen) + "\n"


def abgleich_anfrage(index: Index, weiter: dict | None = None) -> dict[str, Any]:
    """Die Verteilungsfrage - vollstaendig, nicht geschaetzt.

    ``composite`` zaehlt jede Auspraegung und blaettert ueber ``after``.
    ``missing_bucket`` haelt die Zeilen fest, bei denen die Spalte fehlt:
    DuckDBs ``GROUP BY`` fuehrt NULL als eigene Gruppe, und ohne diesen
    Schalter taete Elasticsearch es nicht.
    """
    quellen = [{f: {"terms": {"field": _gruppenfeld(f, index),
                              "missing_bucket": True}}}
               for f in index.verteilung]
    zusammen: dict[str, Any] = {"sources": quellen, "size": 1000}
    if weiter:
        zusammen["after"] = weiter
    return {"size": 0, "aggs": {"verteilung": {"composite": zusammen}}}


def _gruppenfeld(name: str, index: Index) -> str:
    """Gruppiert wird nie auf ``text`` - dafuer gibt es das Unterfeld."""
    return f"{name}.keyword" if name in index.volltext else name


def bestehende_aliase(antwort: dict[str, Any], alias: str) -> list[str]:
    """Welche Indizes der Alias heute traegt - aus der Gesamtliste gefiltert.

    Gefragt wird ``GET /_alias`` und nicht ``GET /_alias/<name>``: Letzteres
    antwortet mit **404**, solange der Alias noch gar nicht existiert, und das
    ist beim allerersten Laden immer der Fall. ``ignore_unavailable`` hilft
    dort nicht - es gilt fuer fehlende Indizes, nicht fuer fehlende Aliase.
    Das Doppel im Test hatte das nicht nachgebildet; der Lauf gegen einen
    echten Dienst schon.
    """
    return sorted(i for i, eintrag in antwort.items()
                  if alias in eintrag.get("aliases", {}))


def alias_umlegen(alias: str, neu: str, alt: list[str]) -> dict[str, Any]:
    """Der Zeigerwechsel - in einem Aufruf, und deshalb ohne Luecke.

    Zwei getrennte Aufrufe haetten einen Moment, in dem der Alias auf nichts
    oder auf beides zeigt. Elasticsearch fuehrt die Liste hier als eine
    Aenderung aus.
    """
    schritte: list[dict] = [{"remove": {"index": i, "alias": alias}} for i in alt]
    schritte.append({"add": {"index": neu, "alias": alias}})
    return {"actions": schritte}


def _ordne(zeilen: list[tuple]) -> list[tuple]:
    """Beide Seiten in dieselbe Reihenfolge - NULL inbegriffen.

    DuckDB sortiert NULL ans Ende, ``composite`` stellt den leeren Eimer nach
    vorn. Verglichen wird deshalb erst nach einer eigenen Ordnung, sonst
    schluege der Abgleich an, obwohl beide Seiten dasselbe sagen.
    """
    return sorted(zeilen, key=lambda t: tuple((v is None, str(v)) for v in t))


# --------------------------------------------------------------------------
# Der Ablauf
# --------------------------------------------------------------------------


class Klient(Protocol):
    """So wenig, wie dieses Modul von Elasticsearch braucht.

    Damit laeuft der Test gegen ein Dictionary statt gegen einen Dienst -
    genau wie ``FakeS3Client`` in ``storage`` und ``FalscheDatenbank`` bei
    ClickHouse.
    """

    def anfrage(self, methode: str, pfad: str,
                koerper: dict | None = None) -> dict: ...

    def massen(self, ndjson: str) -> dict: ...


class HttpKlient:
    """Der schmale Weg ueber die HTTP-Schnittstelle - ohne neue Abhaengigkeit.

    ``elasticsearch-py`` waere bequemer, brauchte aber einen Eintrag in den
    Abhaengigkeiten und muesste zur Serverfassung passen. Was dieses Modul
    tut, sind fuenf Aufrufe; die kann die Standardbibliothek.
    """

    def __init__(self, url: str = STANDARD_URL) -> None:
        self.url = url.rstrip("/")

    def _sende(self, methode: str, pfad: str, rumpf: bytes | None,
               typ: str) -> dict:
        anfrage = urllib.request.Request(
            f"{self.url}{pfad}", data=rumpf, method=methode,
            headers={"Content-Type": typ} if rumpf else {})
        try:
            with urllib.request.urlopen(anfrage, timeout=300) as antwort:
                return json.loads(antwort.read() or b"{}")
        except urllib.error.HTTPError as fehler:
            text = fehler.read().decode("utf-8", "replace")[:600]
            raise LadeFehler(
                f"{methode} {pfad} -> HTTP {fehler.code}: {text}") from fehler

    def anfrage(self, methode: str, pfad: str,
                koerper: dict | None = None) -> dict:
        rumpf = (json.dumps(koerper).encode("utf-8")
                 if koerper is not None else None)
        return self._sende(methode, pfad, rumpf, "application/json")

    def massen(self, ndjson: str) -> dict:
        # Der eigene Medientyp ist Pflicht: Mit ``application/json`` weist
        # Elasticsearch den ganzen Stapel zurueck.
        return self._sende("POST", "/_bulk", ndjson.encode("utf-8"),
                           "application/x-ndjson")


def pruefe_zeitgenauigkeit(parquet: Path, liste: list[Feld]) -> None:
    """Haelt fest, was im Modulkopf behauptet wird.

    ``date`` loest Millisekunden auf. Solange kein Zeitstempel feiner ist,
    kostet das nichts - aber das ist eine Messung und keine Eigenschaft der
    Welt. Traegt Gold eines Tages Mikrosekunden, soll es hier auffallen und
    nicht in einer Auswertung.
    """
    from storage.duckdb import verbinde

    spalten = [f.name for f in liste if f.arrow.startswith("timestamp")]
    if not spalten:
        return
    teile = ", ".join(
        f'count(*) FILTER (WHERE epoch_us("{s}") % 1000 <> 0)' for s in spalten)
    con = verbinde()
    try:
        feiner = con.execute(
            f"SELECT {teile} FROM read_parquet('{parquet}')").fetchone()
    finally:
        con.close()
    for name, anzahl in zip(spalten, feiner):
        if anzahl:
            raise LadeFehler(
                f"{name} traegt {anzahl:,} Zeitstempel feiner als eine "
                f"Millisekunde. Elasticsearchs 'date' wuerde sie kuerzen - "
                f"entweder auf date_nanos wechseln oder klaeren, woher die "
                f"Genauigkeit kommt.")


def aktuelles_release(datenwurzel: Path) -> tuple[str, Path]:
    """Die Kennung, auf die der Zeiger zeigt, und das Verzeichnis dazu."""
    zeiger = datenwurzel / "releases" / "AKTUELL.json"
    if not zeiger.is_file():
        raise LadeFehler(f"{zeiger} fehlt - erst 'run_all --release' laufen lassen")
    kennung = json.loads(zeiger.read_text(encoding="utf-8"))["release_id"]
    verzeichnis = datenwurzel / "releases" / f"release={kennung}"
    if not verzeichnis.is_dir():
        raise LadeFehler(f"Release {kennung} liegt nicht lokal: {verzeichnis}")
    return kennung, verzeichnis


def quelle(verzeichnis: Path, index: Index) -> Path:
    parquet = verzeichnis / index.quelle_im_release
    if not parquet.is_file():
        raise LadeFehler(f"{parquet} fehlt im Release")
    return parquet


def schreibe(klient: Klient, ziel: str, parquet: Path, index: Index) -> int:
    """Fuellt den Index stapelweise - und glaubt der Antwort nicht ungeprueft."""
    geschrieben = 0
    teil: list[tuple[str, dict]] = []

    def leeren() -> None:
        nonlocal geschrieben
        if not teil:
            return
        antwort = klient.massen(massenrumpf(ziel, teil))
        # HTTP 200 heisst hier nur, dass der Stapel angekommen ist.
        if antwort.get("errors"):
            erste = next(
                (e for e in antwort.get("items", [])
                 if "error" in e.get("index", {})), {})
            raise LadeFehler(
                f"_bulk meldet Fehler, z.B. "
                f"{erste.get('index', {}).get('error')}")
        geschrieben += len(teil)
        teil.clear()

    for eintrag in dokumente(parquet, index):
        teil.append(eintrag)
        if len(teil) >= STAPEL:
            leeren()
    leeren()
    return geschrieben


def abgleich_elasticsearch(klient: Klient, ziel: str,
                           index: Index) -> dict[str, Any]:
    """Dieselben Fragen wie an das Release - nur an den Index gestellt."""
    zeilen = klient.anfrage("GET", f"/{ziel}/_count")["count"]

    verteilung: list[tuple] = []
    weiter: dict | None = None
    while True:
        antwort = klient.anfrage(
            "POST", f"/{ziel}/_search", abgleich_anfrage(index, weiter))
        eimer = antwort["aggregations"]["verteilung"]
        for b in eimer["buckets"]:
            verteilung.append(
                tuple(b["key"][f] for f in index.verteilung) + (b["doc_count"],))
        weiter = eimer.get("after_key")
        if not weiter or not eimer["buckets"]:
            break

    return {"zeilen": zeilen, "schluessel": zeilen, "verteilung": verteilung}


def lade(klient: Klient, kennung: str, parquet: Path, *,
         index: Index = INDIZES[0]) -> dict[str, Any]:
    """Anlegen, fuellen, auffrischen, pruefen, umlegen - in dieser Reihenfolge.

    Faellt der Abgleich, bleibt der Alias auf dem alten Index stehen. Der neue
    bleibt liegen: Er ist der Beleg dafuer, was schiefging, und kostet nichts
    ausser Platz.
    """
    ziel = indexname(kennung, index.name)
    liste = felder(parquet, index.name)
    pruefe_zeitgenauigkeit(parquet, liste)

    klient.anfrage("PUT", f"/{ziel}", mapping(liste, index))
    schreibe(klient, ziel, parquet, index)
    # Ohne das zaehlt der naechste Aufruf einen Index, der die neuen
    # Dokumente noch nicht kennt.
    klient.anfrage("POST", f"/{ziel}/_refresh")

    gefunden = abgleich_elasticsearch(klient, ziel, index)
    erwartet = abgleich_release(parquet, index)
    for seite in (erwartet, gefunden):
        seite["verteilung"] = _ordne([tuple(z) for z in seite["verteilung"]])
    vergleiche(erwartet, gefunden, index)   # wirft, bevor etwas sichtbar wird

    vorher = bestehende_aliase(klient.anfrage("GET", "/_alias"), index.name)
    klient.anfrage("POST", "/_aliases",
                   alias_umlegen(index.name, ziel, vorher))
    return {"release_id": kennung, "index": ziel, "felder": len(liste),
            "alias_vorher": vorher,
            **{k: erwartet[k] for k in ("zeilen", "schluessel")}}


def kommandozeile() -> argparse.ArgumentParser:
    """Die Kommandozeile - eigen, damit ihre Vorgaben pruefbar sind.

    Die Vorgabe von ``--url`` kommt aus der Umgebung und wird deshalb
    **beim Aufruf** gelesen, nicht beim Import. Ein getipptes ``--url``
    sticht sie; ``tests/serving/test_dienst_urls.py`` haelt beides fest.
    """
    zerleger = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    zerleger.add_argument("--data-root", type=Path, default=None,
                          help="lokale Wurzel; ohne Angabe entscheidet die Ablage")
    # Die Vorgabe wird hier gelesen, nicht beim Import: So sieht sie die
    # Umgebung des Aufrufs, und ein getipptes --url sticht sie trotzdem.
    zerleger.add_argument("--url", default=vorgabe_url(),
                          help=f"Elasticsearch (Standard: {UMGEBUNGSVARIABLE} "
                               f"oder {STANDARD_URL})")
    zerleger.add_argument("--trocken", action="store_true",
                          help="nur die Abbildungen zeigen, nichts ausfuehren")
    return zerleger


def main(argv: list[str] | None = None) -> int:
    args = kommandozeile().parse_args(argv)

    # Der Pfad geht durch die Ablage und nicht an ihr vorbei: Im s3-Modus gibt
    # es keinen lokalen Bestand, und nur sie weiss, wo die Wurzel liegt.
    from storage import for_root

    kennung, verzeichnis = aktuelles_release(for_root(args.data_root).local_root)

    if args.trocken:
        for index in INDIZES:
            ziel = indexname(kennung, index.name)
            liste = felder(quelle(verzeichnis, index), index.name)
            print(f"PUT /{ziel}")
            print(json.dumps(mapping(liste, index), indent=2, ensure_ascii=False))
            print()
            print("POST /_aliases")
            print(json.dumps(alias_umlegen(index.name, ziel, []), indent=2))
            print("\n" + "-" * 72 + "\n")
        return 0

    klient = HttpKlient(args.url)
    for index in INDIZES:
        ergebnis = lade(klient, kennung, quelle(verzeichnis, index), index=index)
        print(f"{ergebnis['index']:<40} {ergebnis['zeilen']:>9,} Zeilen, "
              f"{ergebnis['felder']} Felder")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
