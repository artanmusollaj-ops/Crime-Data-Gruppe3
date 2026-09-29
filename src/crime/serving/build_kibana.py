"""Baut die Dashboards - als Code, nicht als Klickarbeit.

    python -m serving.build_kibana              # anlegen und pruefen
    python -m serving.build_kibana --trocken    # nur zeigen, was entstuende

**Warum das nicht im Browser passiert.** Ein zusammengeklicktes Dashboard lebt
in Kibanas eigenem Index. Es laesst sich nicht lesen, nicht vergleichen, nicht
begruenden, und es ist weg, sobald jemand den Container neu aufsetzt. Alles
andere in diesem Projekt ist reproduzierbar; ein Dashboard, das es nicht ist,
waere die eine Stelle, an der man sich auf einen Zustand verlaesst, den
niemand nachbauen kann. Deshalb stehen die Dashboards hier als Beschreibung
und werden ueber die Saved-Objects-Schnittstelle angelegt.

**Eine Beschreibung, zwei Darstellungen.** Jede ``Tafel`` sagt einmal, was sie
zeigt. Daraus entsteht **beides**: das Lens-Dokument fuer Kibana und die
gleichwertige Elasticsearch-Abfrage. Der Test stellt die Abfrage wirklich und
prueft, dass sie etwas zurueckgibt - damit ist nicht nur belegt, dass das JSON
angenommen wurde, sondern dass die Tafel auch etwas anzeigen *kann*. Ein
Dashboard, das sauber importiert und leer bleibt, ist der Normalfall bei
erzeugten Dashboards; hier faellt er auf.

**Was daran teuer war.**

*Kibana zeigt die letzten 15 Minuten.* Unsere Daten enden am 31.12.2024. Ohne
``timeRestore`` mit festem Fenster oeffnet sich jedes Dashboard leer, und
nichts deutet darauf hin, dass nur der Zeitraum falsch steht. Das Fenster
kommt deshalb aus dem Release und nicht aus einer Voreinstellung.

*Auf ``text`` laesst sich nicht gruppieren.* ``source_offense_description``
liegt als ``text`` mit ``.keyword``-Unterfeld (siehe ``load_elasticsearch``).
Eine Tafel, die das Feld direkt gruppiert, importiert anstandslos und bleibt
dann leer. ``feldname`` haengt das Unterfeld an, und ein Test haelt es gegen
die echte Abbildung im Index.

*Angenommen ist nicht gerendert.* Die Schnittstelle nimmt jedes JSON. Ob eine
Tafel wirklich erscheint, haengt daran, dass jeder Verweis der Darstellung auf
eine Spalte zeigt, die es gibt - und genau das prueft ``pruefe_tafel``, weil
Kibana es nicht tut.
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from serving.load_clickhouse import LadeFehler
from serving.load_elasticsearch import aktuelles_release

#: Kibana liegt neben Elasticsearch; der Port ist aus demselben Grund
#: verschoben wie dort (5601 ist die Voreinstellung und oft belegt).
STANDARD_URL = "http://localhost:15601"

#: Die Fassung, die in jedes Tafelobjekt geschrieben wird. Kibana wandert
#: gespeicherte Objekte anhand dieser Angabe auf neuere Staende.
FASSUNG = "8.15.0"

#: Kibanas Raster ist 48 Spalten breit. Halb heisst 24, ein Drittel 16.
RASTER = 48

#: Die Datenansicht, auf der alle Tafeln liegen. Feste Kennung, damit ein
#: zweiter Lauf dieselbe trifft statt eine zweite anzulegen.
ANSICHT = "crime-fact-offense"

#: Lens nennt die Zeilenzahl so. Kein Feld im Index - ein Platzhalter.
ZEILEN = "___records___"

#: Bis hierher zaehlt ``cardinality`` exakt, darueber schaetzt es. Gemessen
#: liegen die beiden Kacheln, die es benutzen, bei 1'146 Tracts und 429
#: Quellcodes - weit darunter. 40'000 ist das Hoechste, was Elasticsearch
#: zulaesst; die Voreinstellung waere 3'000.
GENAUIGKEIT = 40_000


class Klient(Protocol):
    """So wenig, wie dieses Modul von Kibana braucht."""

    def anfrage(self, methode: str, pfad: str,
                koerper: Any | None = None) -> Any: ...


# --------------------------------------------------------------------------
# Die Beschreibung. Was eine Tafel zeigt - einmal gesagt.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Kennzahl:
    """Was gezaehlt wird."""

    kennung: str
    beschriftung: str
    operation: str = "count"
    feld: str | None = None

    @property
    def lens_spalte(self) -> dict[str, Any]:
        return {
            "label": self.beschriftung,
            "dataType": "number",
            "operationType": self.operation,
            "sourceField": self.feld or ZEILEN,
            "isBucketed": False,
            "scale": "ratio",
            "params": {"emptyAsNull": False},
        }

    @property
    def aggregation(self) -> dict[str, Any] | None:
        """``count`` ist in Elasticsearch keine Aggregation, sondern der Umfang.

        **``unique_count`` schaetzt.** Kibana setzt es auf ``cardinality`` um,
        und das ist HyperLogLog: bis zur Genauigkeitsschwelle exakt, darueber
        ungefaehr - ohne dass die Kachel es sagt. Die Schwelle wird deshalb
        hier gesetzt und nicht der Voreinstellung ueberlassen; ein Test haelt
        die tatsaechlichen Werte dagegen.
        """
        if self.operation == "count":
            return None
        if self.operation == "unique_count":
            return {"cardinality": {"field": self.feld,
                                    "precision_threshold": GENAUIGKEIT}}
        return {self.operation.replace("average", "avg"): {"field": self.feld}}


@dataclass(frozen=True)
class Eimer:
    """Wonach gruppiert wird."""

    kennung: str
    beschriftung: str
    operation: str          # "terms" oder "date_histogram"
    feld: str
    groesse: int = 10
    intervall: str = "1M"
    #: Fuer ``text``-Felder muss das Unterfeld angehaengt werden - sonst
    #: importiert die Tafel sauber und bleibt leer.
    unterfeld_keyword: bool = False
    #: ``"anzahl"`` sortiert die groessten Gruppen nach vorn - richtig fuer
    #: *welche Delikte sind haeufig*. ``"schluessel"`` sortiert nach dem Wert
    #: selbst und ist Pflicht, wo die Reihenfolge eine Bedeutung hat: Ein
    #: Tagesverlauf nach Haeufigkeit sortiert (0, 12, 17, 16, ...) zeigt
    #: keinen Verlauf mehr, sondern eine Rangliste.
    ordnung: str = "anzahl"

    @property
    def feldname(self) -> str:
        return f"{self.feld}.keyword" if self.unterfeld_keyword else self.feld

    def lens_spalte(self, nach: str) -> dict[str, Any]:
        """``nach`` ist die Kennzahl, nach der ``terms`` sortiert."""
        if self.operation == "date_histogram":
            return {
                "label": self.beschriftung, "dataType": "date",
                "operationType": "date_histogram", "sourceField": self.feldname,
                "isBucketed": True, "scale": "interval",
                "params": {"interval": self.intervall, "includeEmptyRows": True,
                           "dropPartials": False},
            }
        nach_schluessel = self.ordnung == "schluessel"
        return {
            "label": self.beschriftung, "dataType": "string",
            "operationType": "terms", "sourceField": self.feldname,
            "isBucketed": True, "scale": "ordinal",
            "params": {
                "size": self.groesse,
                "orderBy": ({"type": "alphabetical", "fallback": False}
                            if nach_schluessel
                            else {"type": "column", "columnId": nach}),
                "orderDirection": "asc" if nach_schluessel else "desc",
                "otherBucket": False, "missingBucket": False,
                "parentFormat": {"id": "terms"}},
        }

    @property
    def aggregation(self) -> dict[str, Any]:
        if self.operation == "date_histogram":
            return {"date_histogram": {"field": self.feldname,
                                       "calendar_interval": self.intervall}}
        ordnung = ({"_key": "asc"} if self.ordnung == "schluessel"
                   else {"_count": "desc"})
        return {"terms": {"field": self.feldname, "size": self.groesse,
                          "order": ordnung}}


#: Welche Lens-Darstellung zu welcher Art gehoert. Getrennt gehalten, weil
#: die Zuordnung eine Entscheidung ist und keine Ableitung.
ARTEN = {
    "zahl": "lnsMetric",
    "balken": "lnsXY",
    "linie": "lnsXY",
    "ring": "lnsPie",
    "tabelle": "lnsDatatable",
}


@dataclass(frozen=True)
class Tafel:
    """Eine Kachel im Dashboard."""

    kennung: str
    titel: str
    art: str
    kennzahl: Kennzahl
    eimer: tuple[Eimer, ...] = ()
    breite: int = 24
    hoehe: int = 15

    def __post_init__(self) -> None:
        if self.art not in ARTEN:
            raise LadeFehler(
                f"{self.kennung}: Art '{self.art}' ist nicht entschieden. "
                f"Bekannt sind {', '.join(sorted(ARTEN))}.")
        if self.art == "zahl" and self.eimer:
            raise LadeFehler(
                f"{self.kennung}: Eine Zahl zeigt einen Wert und gruppiert "
                f"nicht.")
        if self.art in ("balken", "linie", "ring") and not self.eimer:
            raise LadeFehler(
                f"{self.kennung}: '{self.art}' braucht mindestens eine "
                f"Gruppierung, sonst ist es ein einzelner Balken.")
        if self.breite > RASTER:
            raise LadeFehler(
                f"{self.kennung}: {self.breite} Spalten passen nicht in ein "
                f"Raster von {RASTER}.")

    @property
    def schicht(self) -> str:
        return f"schicht-{self.kennung}"

    @property
    def spalten(self) -> dict[str, Any]:
        """Alle Lens-Spalten - Gruppierungen zuerst, dann die Kennzahl."""
        spalten = {e.kennung: e.lens_spalte(self.kennzahl.kennung)
                   for e in self.eimer}
        spalten[self.kennzahl.kennung] = self.kennzahl.lens_spalte
        return spalten

    @property
    def reihenfolge(self) -> list[str]:
        return [e.kennung for e in self.eimer] + [self.kennzahl.kennung]

    @property
    def darstellung(self) -> dict[str, Any]:
        """Der Teil, der sagt, welche Spalte wo hingehoert."""
        if self.art == "zahl":
            return {"layerId": self.schicht, "layerType": "data",
                    "metricAccessor": self.kennzahl.kennung}
        if self.art == "tabelle":
            return {"layerId": self.schicht, "layerType": "data",
                    "columns": [{"columnId": k, "isTransposed": False}
                                for k in self.reihenfolge]}
        if self.art == "ring":
            return {"shape": "donut", "layers": [{
                "layerId": self.schicht, "layerType": "data",
                "primaryGroups": [e.kennung for e in self.eimer],
                "metrics": [self.kennzahl.kennung],
                "numberDisplay": "percent", "categoryDisplay": "default",
                "legendDisplay": "default", "nestedLegend": False}]}
        reihe = "bar_stacked" if self.art == "balken" else "line"
        schicht: dict[str, Any] = {
            "layerId": self.schicht, "accessors": [self.kennzahl.kennung],
            "position": "top", "seriesType": reihe, "showGridlines": False,
            "layerType": "data", "xAccessor": self.eimer[0].kennung,
        }
        # Die zweite Gruppierung teilt die Reihen auf - genau so entsteht
        # "je Monat, getrennt nach Stadt" aus zwei Eimern.
        if len(self.eimer) > 1:
            schicht["splitAccessor"] = self.eimer[1].kennung
        return {"legend": {"isVisible": True, "position": "right"},
                "valueLabels": "hide", "preferredSeriesType": reihe,
                "layers": [schicht]}

    @property
    def aggregation(self) -> dict[str, Any]:
        """Dieselbe Frage, an Elasticsearch gestellt.

        Verschachtelt in der Reihenfolge der Eimer - so, wie Lens es auch
        tut. Die Kennzahl haengt innen, ausser sie ist ``count``: Den liefert
        jede Ebene als ``doc_count`` mit.
        """
        innen: dict[str, Any] = {}
        if (kz := self.kennzahl.aggregation) is not None:
            innen = {self.kennzahl.kennung: kz}
        for eimer in reversed(self.eimer):
            innen = {eimer.kennung: {**eimer.aggregation,
                                     **({"aggs": innen} if innen else {})}}
        return {"size": 0, "aggs": innen} if innen else {"size": 0}


@dataclass(frozen=True)
class Brett:
    """Ein Dashboard."""

    kennung: str
    titel: str
    beschreibung: str
    tafeln: tuple[Tafel, ...]
    #: Wird beim Bauen aus dem Release gefuellt, siehe ``zeitfenster``.
    zeitraum: tuple[str, str] = ("", "")


# --------------------------------------------------------------------------
# Die Dashboards. Alles hier ist Entscheidung.
# --------------------------------------------------------------------------

_GESAMT = Kennzahl("anzahl", "Delikte", "count")


BRETTER: tuple[Brett, ...] = (
    Brett(
        kennung="crime-ueberblick",
        titel="Überblick — Chicago gegen Detroit",
        beschreibung=(
            "Der Einstieg. Absolute Zahlen sagen wenig, solange die Städte "
            "verschieden gross sind — die Rate je 1'000 Einwohner steht in "
            "der DuckDB-Auswertung, nicht hier."),
        tafeln=(
            Tafel("gesamt", "Delikte insgesamt", "zahl", _GESAMT,
                  breite=12, hoehe=8),
            Tafel("je_stadt", "Delikte je Stadt", "balken", _GESAMT,
                  eimer=(Eimer("stadt", "Stadt", "terms", "reporting_city", 5),),
                  breite=36, hoehe=8),
            Tafel("verlauf", "Verlauf je Monat, getrennt nach Stadt", "balken",
                  _GESAMT,
                  eimer=(Eimer("monat", "Monat", "date_histogram",
                               "occurred_at_utc", intervall="1M"),
                         Eimer("stadt", "Stadt", "terms", "reporting_city", 5)),
                  breite=48, hoehe=15),
            Tafel("familien", "Anteil nach Deliktfamilie", "ring", _GESAMT,
                  eimer=(Eimer("familie", "NIBRS-Familie", "terms",
                               "nibrs_family", 8),),
                  breite=24, hoehe=15),
            Tafel("delikte", "Häufigste Delikte", "tabelle", _GESAMT,
                  eimer=(Eimer("art", "Delikt", "terms", "nibrs_code", 15),
                         Eimer("stadt", "Stadt", "terms", "reporting_city", 5)),
                  breite=24, hoehe=15),
        ),
    ),
    Brett(
        kennung="crime-datenqualitaet",
        titel="Datenqualität — Zuordnung und Verortung",
        beschreibung=(
            "Was die Strecke über sich selbst sagt. Dieselben Grössen, gegen "
            "die das Publish-Gate prüft: Zuordnung auf NIBRS und Verortung "
            "im Stadtgebiet."),
        tafeln=(
            Tafel("gesamt", "Delikte insgesamt", "zahl", _GESAMT,
                  breite=16, hoehe=8),
            Tafel("verortet", "Verschiedene Tracts", "zahl",
                  Kennzahl("tracts", "Tracts", "unique_count", "tract_geoid"),
                  breite=16, hoehe=8),
            Tafel("codes", "Verschiedene Quellcodes", "zahl",
                  Kennzahl("codes", "Codes", "unique_count",
                           "source_offense_code"),
                  breite=16, hoehe=8),
            Tafel("zuordnung", "Zuordnung auf NIBRS, je Stadt", "balken",
                  _GESAMT,
                  eimer=(Eimer("status", "Status", "terms", "mapping_status", 6),
                         Eimer("stadt", "Stadt", "terms", "reporting_city", 5)),
                  breite=24, hoehe=15),
            Tafel("verortung", "Verortung, je Stadt", "balken", _GESAMT,
                  eimer=(Eimer("status", "Status", "terms", "geo_status", 6),
                         Eimer("stadt", "Stadt", "terms", "reporting_city", 5)),
                  breite=24, hoehe=15),
        ),
    ),
    Brett(
        kennung="crime-volltext",
        titel="Deliktarten — Einstieg für die Volltextsuche",
        beschreibung=(
            "Die Suchleiste oben durchsucht die Beschreibung der Quelle: "
            "»source_offense_description: explosive« findet die Fälle, ohne "
            "dass man den Code kennt. Die Tafeln zeigen, was die Suche "
            "gerade übrig lässt."),
        tafeln=(
            Tafel("gesamt", "Treffer", "zahl", _GESAMT, breite=12, hoehe=8),
            Tafel("stunde", "Nach Tagesstunde", "balken", _GESAMT,
                  # Nach der Stunde sortiert, nicht nach der Haeufigkeit -
                  # sonst steht da eine Rangliste statt eines Tagesverlaufs.
                  eimer=(Eimer("stunde", "Stunde", "terms", "hour_of_day", 24,
                               ordnung="schluessel"),),
                  breite=36, hoehe=8),
            Tafel("beschreibungen", "Beschreibungen der Quelle", "tabelle",
                  _GESAMT,
                  # Das Unterfeld ist Pflicht: Auf ``text`` laesst sich nicht
                  # gruppieren, und die Tafel bliebe still leer.
                  eimer=(Eimer("text", "Beschreibung", "terms",
                               "source_offense_description", 20,
                               unterfeld_keyword=True),
                         Eimer("stadt", "Stadt", "terms", "reporting_city", 5)),
                  breite=48, hoehe=20),
        ),
    ),
)


# --------------------------------------------------------------------------
# Die erzeugten Objekte. Reine Funktionen - pruefbar ohne Kibana.
# --------------------------------------------------------------------------


def datenansicht(index: str = "fact_offense",
                 zeitfeld: str = "occurred_at_utc") -> dict[str, Any]:
    """Die Datenansicht - auf den **Alias**, nicht auf einen Release-Index.

    Damit zeigen die Dashboards nach jedem Ladelauf auf den neuen Stand,
    ohne dass hier etwas angefasst werden muss. Genau dafuer gibt es den
    Alias in ``load_elasticsearch``.
    """
    return {"type": "index-pattern", "id": ANSICHT,
            "attributes": {"title": index, "timeFieldName": zeitfeld},
            "references": []}


def pruefe_tafel(tafel: Tafel) -> None:
    """Zeigt jeder Verweis der Darstellung auf eine Spalte, die es gibt?

    Kibana prueft das nicht. Ein Verweis ins Leere importiert sauber und
    faellt erst auf, wenn jemand das Dashboard oeffnet und eine leere Kachel
    sieht - moeglicherweise in der Praesentation.
    """
    vorhanden = set(tafel.spalten)
    if set(tafel.reihenfolge) != vorhanden:
        raise LadeFehler(
            f"{tafel.kennung}: Reihenfolge und Spalten stimmen nicht überein")

    text = json.dumps(tafel.darstellung)
    verwiesen = {k for k in vorhanden if f'"{k}"' in text}
    fehlend = vorhanden - verwiesen
    if fehlend:
        raise LadeFehler(
            f"{tafel.kennung}: {sorted(fehlend)} stehen in den Spalten, "
            f"werden von der Darstellung aber nicht verwendet - die Tafel "
            f"zeigt sie nicht an.")


def lens_objekt(tafel: Tafel, brett: str) -> dict[str, Any]:
    """Ein gespeichertes Lens-Objekt je Tafel.

    Mit Verweis statt eingebettet: So bleibt jede Tafel fuer sich lesbar und
    laesst sich im Browser einzeln oeffnen.

    **Die Kennung traegt das Brett.** Drei Bretter haben je eine Tafel
    ``gesamt``, und zwei davon heissen verschieden - *Delikte insgesamt* und
    *Treffer*. Ohne den Brettnamen bekaemen sie dieselbe Kennung, und das
    letzte Anlegen ueberschriebe die anderen. Die Tafel des dritten Bretts
    truege dann den Titel des ersten.
    """
    pruefe_tafel(tafel)
    return {
        "type": "lens", "id": f"lens-{brett}-{tafel.kennung}",
        "attributes": {
            "title": tafel.titel,
            "visualizationType": ARTEN[tafel.art],
            "state": {
                "datasourceStates": {"formBased": {"layers": {tafel.schicht: {
                    "columns": tafel.spalten,
                    "columnOrder": tafel.reihenfolge,
                    "incompleteColumns": {}}}}},
                "filters": [],
                "query": {"language": "kuery", "query": ""},
                "visualization": tafel.darstellung,
            },
        },
        "references": [{
            "type": "index-pattern", "id": ANSICHT,
            "name": f"indexpattern-datasource-layer-{tafel.schicht}"}],
    }


def raster(tafeln: tuple[Tafel, ...]) -> list[dict[str, int]]:
    """Legt die Kacheln zeilenweise um, ohne dass jemand Koordinaten pflegt.

    Passt eine Tafel nicht mehr in die Zeile, beginnt eine neue. Die Hoehe
    der Zeile ist die groesste Tafel darin - sonst ueberlappen sich Kacheln,
    und Kibana schiebt sie beim Oeffnen wortlos umeinander.
    """
    gitter, x, y, zeilenhoehe = [], 0, 0, 0
    for tafel in tafeln:
        if x + tafel.breite > RASTER:
            x, y, zeilenhoehe = 0, y + zeilenhoehe, 0
        gitter.append({"x": x, "y": y, "w": tafel.breite, "h": tafel.hoehe})
        x += tafel.breite
        zeilenhoehe = max(zeilenhoehe, tafel.hoehe)
    return gitter


def dashboard_objekt(brett: Brett) -> dict[str, Any]:
    """Das Dashboard mit seinen Kacheln und dem festen Zeitfenster."""
    von, bis = brett.zeitraum
    if not von or not bis:
        raise LadeFehler(
            f"{brett.kennung}: ohne Zeitfenster öffnet Kibana die letzten 15 "
            f"Minuten und das Dashboard bleibt leer.")

    tafeln, verweise = [], []
    for tafel, platz in zip(brett.tafeln, raster(brett.tafeln)):
        nummer = f"p-{tafel.kennung}"
        tafeln.append({
            "version": FASSUNG, "type": "lens",
            "gridData": {**platz, "i": nummer}, "panelIndex": nummer,
            "embeddableConfig": {"enhancements": {}},
            "panelRefName": f"panel_{nummer}", "title": tafel.titel,
        })
        verweise.append({"name": f"{nummer}:panel_{nummer}", "type": "lens",
                         "id": lens_objekt(tafel, brett.kennung)["id"]})

    return {
        "type": "dashboard", "id": brett.kennung,
        "attributes": {
            "title": brett.titel,
            "description": brett.beschreibung,
            "panelsJSON": json.dumps(tafeln, ensure_ascii=False),
            "optionsJSON": json.dumps(
                {"useMargins": True, "syncColors": False,
                 "syncCursor": True, "syncTooltips": False,
                 "hidePanelTitles": False}),
            # Ohne das steht beim Oeffnen "letzte 15 Minuten" - und unsere
            # Daten enden am 31.12.2024.
            "timeRestore": True, "timeFrom": von, "timeTo": bis,
            "kibanaSavedObjectMeta": {"searchSourceJSON": json.dumps(
                {"query": {"language": "kuery", "query": ""}, "filter": []})},
        },
        "references": verweise,
    }


def zeitfenster(datenwurzel: Path) -> tuple[str, str]:
    """Das Fenster kommt aus dem Release, nicht aus einer Voreinstellung."""
    import duckdb

    _, verzeichnis = aktuelles_release(datenwurzel)
    parquet = verzeichnis / "gold/dataset=fact_offense/part-0001.parquet"
    con = duckdb.connect()
    try:
        von, bis = con.execute(
            f"SELECT min(occurred_at_utc), max(occurred_at_utc) "
            f"FROM read_parquet('{parquet}')").fetchone()
    finally:
        con.close()
    # Einen Tag Luft nach hinten, damit der letzte Tag ganz drin liegt.
    return (von.strftime("%Y-%m-%dT00:00:00.000Z"),
            bis.strftime("%Y-%m-%dT23:59:59.999Z"))


def objekte(bretter: tuple[Brett, ...]) -> list[dict[str, Any]]:
    """Alles, was angelegt wird - Datenansicht, Tafeln, Bretter."""
    alle: list[dict[str, Any]] = [datenansicht()]
    for brett in bretter:
        alle.extend(lens_objekt(t, brett.kennung) for t in brett.tafeln)
        alle.append(dashboard_objekt(brett))
    return alle


# --------------------------------------------------------------------------
# Der Ablauf
# --------------------------------------------------------------------------


class HttpKlient:
    """Kibanas Schnittstelle ueber die Standardbibliothek.

    ``kbn-xsrf`` ist Pflicht: Ohne diesen Kopf weist Kibana jeden schreibenden
    Aufruf mit 400 zurueck, unabhaengig vom Inhalt.
    """

    def __init__(self, url: str = STANDARD_URL) -> None:
        self.url = url.rstrip("/")

    def anfrage(self, methode: str, pfad: str,
                koerper: Any | None = None) -> Any:
        anfrage = urllib.request.Request(
            f"{self.url}{pfad}", method=methode,
            data=(json.dumps(koerper).encode("utf-8")
                  if koerper is not None else None),
            headers={"kbn-xsrf": "true", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(anfrage, timeout=120) as antwort:
                return json.loads(antwort.read() or b"{}")
        except urllib.error.HTTPError as fehler:
            text = fehler.read().decode("utf-8", "replace")[:600]
            raise LadeFehler(
                f"{methode} {pfad} -> HTTP {fehler.code}: {text}") from fehler


def lege_an(klient: Klient, alle: list[dict[str, Any]]) -> dict[str, Any]:
    """Anlegen und danach nachsehen, ob die Verweise tragen.

    ``overwrite`` ist gewollt: Ein zweiter Lauf soll denselben Stand
    herstellen und keine zweite Fassung danebenlegen.
    """
    antwort = klient.anfrage(
        "POST", "/api/saved_objects/_bulk_create?overwrite=true", alle)
    fehler = [o for o in antwort.get("saved_objects", []) if "error" in o]
    if fehler:
        raise LadeFehler(f"Kibana lehnte ab: {fehler[0].get('error')}")

    fehlend = pruefe_verweise(klient, alle)
    if fehlend:
        raise LadeFehler(f"Verweise zeigen ins Leere: {fehlend}")
    return {"angelegt": len(alle),
            "dashboards": sum(1 for o in alle if o["type"] == "dashboard")}


def pruefe_verweise(klient: Klient,
                    alle: list[dict[str, Any]]) -> list[str]:
    """Jeder Verweis muss auf ein Objekt zeigen, das wirklich da ist.

    Kibana legt ein Dashboard auch dann an, wenn seine Tafeln fehlen - beim
    Oeffnen steht dann *Could not locate that panel*. Billiger, es hier zu
    merken.
    """
    vorhanden = {(o["type"], o["id"]) for o in alle}
    return [f"{o['id']} -> {v['type']}/{v['id']}"
            for o in alle for v in o.get("references", [])
            if (v["type"], v["id"]) not in vorhanden]


def main(argv: list[str] | None = None) -> int:
    zerleger = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    zerleger.add_argument("--data-root", type=Path, default=None)
    zerleger.add_argument("--url", default=STANDARD_URL,
                          help=f"Kibana (Standard: {STANDARD_URL})")
    zerleger.add_argument("--trocken", action="store_true",
                          help="nur zeigen, was entstuende")
    args = zerleger.parse_args(argv)

    from storage import for_root

    fenster = zeitfenster(for_root(args.data_root).local_root)
    bretter = tuple(
        Brett(b.kennung, b.titel, b.beschreibung, b.tafeln, fenster)
        for b in BRETTER)
    alle = objekte(bretter)

    if args.trocken:
        for objekt in alle:
            print(f"{objekt['type']:<14} {objekt['id']}")
        print(f"\nZeitfenster: {fenster[0]} bis {fenster[1]}")
        return 0

    ergebnis = lege_an(HttpKlient(args.url), alle)
    for brett in bretter:
        print(f"{brett.titel}\n  {len(brett.tafeln)} Tafeln  ·  "
              f"{args.url}/app/dashboards#/view/{brett.kennung}")
    print(f"\n{ergebnis['angelegt']} Objekte, "
          f"{ergebnis['dashboards']} Dashboards, Zeitfenster {fenster[0][:10]} "
          f"bis {fenster[1][:10]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
