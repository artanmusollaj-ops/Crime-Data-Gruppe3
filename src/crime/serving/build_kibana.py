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

**Zwei Sorten Tafel, und die zweite rechnet.** Eine Lens-Tafel aus ``Kennzahl``
und ``Eimer`` kann zaehlen und gruppieren - nicht aber *teilen*. Eine Rate je
1'000 Einwohner braucht Zaehler und Nenner aus zwei Indizes und eine Division
danach; das ist in Lens' Eimersprache nicht sagbar. Dafuer gibt es die ``Art``
``esql_tabelle``: Sie traegt eine ``Abfrage`` in ES|QL, Kibana nimmt sie als
``datasourceStates.textBased`` an, und ``LOOKUP JOIN`` holt den Nenner dazu.

*Der stille Fehler dabei ist nicht die Abfrage, sondern der Nenner.* Drei Wege
fuehren zu einer Zahl, die man hinschreiben kann und die falsch ist, und keiner
von ihnen wirft einen Fehler - die vier Bedingungen an ``RATE_JE_STADT`` sagen,
welche es sind.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol

# Das Bezugsjahr der Raten kommt aus derselben Quelle wie das der
# Abgabedokumente. Eine zweite 2024 hier waere die Stelle, an der Dashboard und
# Dokument auseinanderlaufen, ohne dass jemand es merkt.
from gold_pipeline import RATENJAHR, STADT_SCHLUESSEL
from serving.load_clickhouse import LadeFehler
from serving.load_elasticsearch import NACH_NAME, aktuelles_release

#: Kibana liegt neben Elasticsearch; der Port ist aus demselben Grund
#: verschoben wie dort (5601 ist die Voreinstellung und oft belegt).
STANDARD_URL = "http://localhost:15601"

#: Die Variable, mit der die Umgebung diese Adresse ersetzt. Im Verbund heisst
#: der Dienst nicht ``localhost``, sondern so, wie das Compose-Netz ihn nennt -
#: und ein Container kann keine Kommandozeile tippen. Das Argument ``--url``
#: sticht sie weiterhin.
UMGEBUNGSVARIABLE = "KIBANA_URL"


def vorgabe_url(umgebung: Mapping[str, str] | None = None) -> str:
    """Die Adresse, mit der ohne ``--url`` gearbeitet wird."""
    umgebung = os.environ if umgebung is None else umgebung
    return (umgebung.get(UMGEBUNGSVARIABLE) or "").strip() or STANDARD_URL

#: Die Fassung, die in jedes Tafelobjekt geschrieben wird. Kibana wandert
#: gespeicherte Objekte anhand dieser Angabe auf neuere Staende. Sie muss
#: deshalb zu der Fassung passen, die ``docker-compose.yml`` startet - steht
#: hier eine aeltere, laesst Kibana bei jedem Laden eine Wanderung ueber die
#: Objekte laufen, die nichts zu tun hat.
FASSUNG = "8.19.22"

#: Kibanas Raster ist 48 Spalten breit. Halb heisst 24, ein Drittel 16.
RASTER = 48

#: Die Datenansicht, auf der alle Tafeln liegen. Feste Kennung, damit ein
#: zweiter Lauf dieselbe trifft statt eine zweite anzulegen.
#:
#: **Die ES|QL-Tafeln brauchen sie nicht**, um zu rechnen - ES|QL fragt den
#: Index direkt, und eine Datenansicht auf ``dim_tract_acs`` waere nutzlos
#: gewesen (die anfangs vermutete Luecke; die echte war der Indexmodus). Sie
#: tragen sie trotzdem als Verweis: Daran erkennt Kibana das Zeitfeld, und
#: ``pruefe_verweise`` prueft fuer jede Tafel dieselbe Frage.
ANSICHT = "crime-fact-offense"

#: Das Zeitfeld der Datenansicht - und die Achse, auf der das feste
#: Zeitfenster der Dashboards liegt.
ZEITFELD = "occurred_at_utc"

#: Lens nennt die Zeilenzahl so. Kein Feld im Index - ein Platzhalter.
ZEILEN = "___records___"

#: Das ``links``-Objekt, das auf jedem Brett oben liegt und auf die uebrigen
#: zeigt - Kibanas naechster Verwandter zur Reiterleiste des Entwurfs.
#: Einmal angelegt, von jedem Brett verwiesen.
NAVIGATION = "crime-navigation"

#: Wie die Navigationskachel auf jedem Brett heisst. Fest, weil jedes Brett
#: hoechstens eine traegt und zwei gleiche Kennungen auf einem Brett einander
#: wortlos ueberschrieben.
NAVIGATION_PANEL = "p-navigation"

NAVIGATION_TITEL = "Urban Crime — die Bretter"

#: Die Datenansicht auf die Tract-Umrisse. Eigene Ansicht und nicht ``ANSICHT``:
#: ``dim_tract_geo`` hat **kein Zeitfeld**, und eine Ansicht mit Zeitfeld
#: filterte jede Flaeche weg, sobald das Brett sein Fenster setzt.
ANSICHT_FLAECHEN = "crime-dim-tract-geo"

#: Je Stadt ein Ausschnitt - und deshalb je Stadt eine Karte.
#:
#: **Eine gemeinsame Karte waere das Naheliegende und ist unbrauchbar.** Am
#: 14.10.2026 im Browser gemessen: Zwischen Chicago und Detroit liegen 4,4
#: Laengengrade, jede Stadt ist aber nur 0,4 breit. Ein Ausschnitt, der beide
#: fasst, zeigt zwei Flecken von je 50 Pixeln - zu sehen ist, *dass* dort
#: etwas liegt, nicht *wo es hoeher ist*. Artans Entwurf stellt dieselben
#: zwei Karten nebeneinander, aus demselben Grund.
#:
#: Mitte und Zoom sind aus den gemessenen Grenzen der Umrisse gerechnet:
#: Chicago -87,96…-87,52 / 41,64…42,02, Detroit -83,29…-82,91 / 42,26…42,45.
#:
#: **Kein Eintrag, kein Bau.** Kommt eine dritte Stadt nach
#: ``silver_pipeline.STUDIENSTAEDTE``, bricht schon der Bau ihrer Tafel ab und
#: nennt sie - geraten wird hier nichts, und eine Karte mit falschem Ausschnitt
#: zeigt leere Flaechen statt einer Fehlermeldung.
KARTE_JE_STADT: dict[str, dict[str, float]] = {
    "chicago": {"lat": 41.83, "lon": -87.74, "zoom": 8},
    "detroit": {"lat": 42.35, "lon": -83.10, "zoom": 8},
}

#: Die Datenansicht auf die fertige Rate je Tract. Ebenfalls ohne Zeitfeld -
#: die Tabelle gilt fuer genau ein Bezugsjahr und traegt kein Datum.
ANSICHT_RATEN = "crime-rate-tract"

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

    @property
    def beleg(self) -> str | None:
        """Wo eine Lens-Kachel Zeilen ohne das gezaehlte Feld weglaesst.

        ``unique_count(tract_geoid)`` zaehlt keine Zeile ohne Tract - das
        ist ein Ausschluss, und dies ist seine Stelle (FR-27). ``count``
        zaehlt jede Zeile und laesst nichts weg.
        """
        return f"{self.operation}({self.feld})" if self.feld else None


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

    @property
    def beleg(self) -> str:
        """Die Stelle, an der dieser Eimer Zeilen weglaesst (FR-27).

        Jeder Eimer laesst die Zeilen ohne seinen Wert weg; ``terms``
        zusaetzlich alles jenseits der obersten ``groesse`` Werte. Die
        Groesse steht deshalb im Beleg, und ``Tafel`` verlangt sie auch im
        Text des Ausschlusses: *„die 15 haeufigsten"* ist eine andere
        Kachel als *„alle"*.
        """
        if self.operation == "date_histogram":
            return f"date_histogram({self.feldname})"
        return f"terms({self.feldname}, {self.groesse})"

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
    # Gestapelt auf 100 Prozent - die Frage "wie teilt sich das auf", nicht
    # "wie viel ist es". Der Entwurf stellt beide nebeneinander, und das ist
    # der Punkt: Detroit hat weniger Delikte und einen hoeheren Anteil
    # Diebstahl. Eine Kachel allein beantwortet immer nur eine der beiden
    # Fragen.
    "anteilsbalken": "lnsXY",
    "ring": "lnsPie",
    "tabelle": "lnsDatatable",
    # Dieselbe Darstellung wie ``tabelle``, aber eine andere Datenquelle:
    # ``textBased`` statt ``formBased``. Eine eigene Art und kein Schalter an
    # ``tabelle``, weil die beiden nichts gemeinsam haben ausser dem Aussehen.
    "esql_tabelle": "lnsDatatable",
    # Zwei Achsen und eine Farbe dazwischen - "Wochentag x Tagesstunde".
    #
    # **Warum nur als ES|QL-Art.** Die beiden Achsen stehen in zwei
    # Tabellen: ``hour_of_day`` in ``fact_offense``, ``day_name`` und
    # ``day_of_week`` in ``dim_date``. Genau dafuer gibt es die
    # Datumsdimension - nachgerechnet wird der Wochentag nirgends. Lens'
    # ``formBased`` liest aber **eine** Datenansicht und kann nicht
    # verbinden; ES|QL kann es mit ``LOOKUP JOIN dim_date ON date``. Eine
    # Eimer-Variante gaebe es also gar nicht zu fuellen.
    "esql_heatmap": "lnsHeatmap",
    # Kein Lens-Objekt, sondern ein eigener gespeicherter Typ. Eine Karte
    # verbindet zwei Indizes - Umriss und Rate - und das kann Lens nicht.
    "karte": "map",
}

#: Die Arten, die als eigener Objekttyp entstehen statt als Lens.
KARTEN_ARTEN = frozenset({"karte"})

#: Die Arten, die ihre Frage in ES|QL stellen statt in Eimern. Als Menge, weil
#: eine zweite dazukommen kann (ein ES|QL-Balken etwa) und dann jede
#: Verzweigung von selbst mitzieht.
ESQL_ARTEN = frozenset({"esql_tabelle", "esql_heatmap"})

#: Was eine Heatmap an Spalten braucht: x, y, Wert - in dieser Reihenfolge.
#: Als Konstante, damit die Pruefung und die Darstellung dieselbe Zahl lesen.
HEATMAP_SPALTEN = 3


@dataclass(frozen=True)
class Spalte:
    """Eine Spalte, die eine ES|QL-Abfrage zurueckgibt.

    ``kennung`` ist **der Name, unter dem ES|QL die Spalte liefert** - Lens
    bildet darueber ab (``idMap`` von ``fieldName`` auf ``columnId``). Steht
    hier ein anderer Name als in der Abfrage, importiert die Tafel sauber und
    bleibt leer; ``test_jede_esql_tafel_liefert_genau_die_spalten`` stellt
    deshalb die Abfrage und vergleicht die Namen.
    """

    kennung: str
    beschriftung: str
    #: Was Lens ueber die Spalte wissen muss. ``number`` oder ``string``;
    #: Elasticsearchs ``long``, ``double`` und ``integer`` sind alle
    #: ``number``, ``keyword`` ist ``string``.
    typ: str = "number"
    #: Ist diese Spalte eine Rate je 1'000 Einwohner?
    #:
    #: Nicht Kosmetik, sondern der Ausloeser einer Pflicht: Eine Tafel mit
    #: einer Rate muss ihren Nenner und ihr Jahr nennen (FR-27), und
    #: ``Tafel.__post_init__`` laesst sie sonst nicht entstehen. Am Datentyp
    #: liesse sich das nicht erkennen - eine Rate ist auch nur eine Zahl.
    ist_rate: bool = False

    @property
    def lens_spalte(self) -> dict[str, Any]:
        return {"columnId": self.kennung, "fieldName": self.kennung,
                "label": self.beschriftung, "customLabel": True,
                "meta": {"type": self.typ}}


@dataclass(frozen=True)
class Ausschluss:
    """Was eine Kachel **nicht** zeigt - und woran die Abfrage es vollzieht.

    Beides zusammen und nicht als blosser Text: Ein Ausschluss, der nur
    dasteht, ist eine Behauptung ueber die Abfrage. Am 11.10.2026 fuehrten
    alle drei Ratenkacheln dasselbe Tupel, und die Stadtkachel nannte darin
    *„Tracts ohne Einwohner"*, obwohl ``RATE_JE_STADT`` sie mitzaehlt -
    1'447 Chicagoer und 361 Detroiter Taten. Die Zahl war richtig, der Text
    war falsch, und niemand haette es gemerkt.

    ``beleg`` ist die Stelle in der Kachel, die den Ausschluss ausfuehrt,
    und ``Tafel._pruefe_fr27`` laesst die Kachel ohne sie nicht entstehen:

    - **ES|QL:** ein Stueck der Abfrage, etwa ``population > 0`` - gesucht
      als Teilzeichenkette in ``abfrage.esql``.
    - **Lens:** genau eine Stelle aus ``Tafel.belegstellen``, und zwar
      **gleich**, nicht enthalten: ein Teil des KQL-Filters
      (``counts_case: true``), der Beleg eines Eimers (``Eimer.beleg``, am
      einfachsten ueber ``ohne_wert``), der Beleg der Kennzahl
      (``unique_count(tract_geoid)``) oder ``ZEITFENSTER_BELEG``. Eine
      Teilzeichenkette wie ``counts`` genuegt dort nicht - sie stuende in
      jedem Filter, der irgendein Feld mit diesem Wortteil nennt.
    - **Karte:** keine Pruefung; sie hat keine Abfrage, siehe
      ``Tafel._pruefe_karte``.

    Ein leerer Beleg wird abgelehnt: ``"" in text`` ist immer wahr, und
    der Ausschluss gaelte damit als vollzogen, ohne dass irgendetwas ihn
    vollzieht. Ein **Vorbehalt** - etwas, das man beim Lesen wissen muss,
    ohne dass die Kachel es wegfiltert - gehoert deshalb nicht hierher,
    sondern nach ``Tafel.vorbehalte``.
    """

    text: str
    beleg: str

    def __post_init__(self) -> None:
        if not self.beleg.strip():
            raise LadeFehler(
                f"Ausschluss '{self.text[:60]}…' ohne Beleg - ein leerer "
                f"Beleg stuende in jeder Abfrage und belegte nichts.")


#: Der Beleg, den **jede** Lens-Kachel traegt: das Zeitfenster oben in der
#: Leiste, angewandt auf das Zeitfeld der Datenansicht. Kein Eimer und kein
#: Filter, aber eine Stelle, an der Zeilen wegfallen - wer den Zeitraum
#: verengt, sieht weniger. Bei einer Zahl ohne Gruppierung ist es der
#: einzige Ausschluss, den es gibt.
ZEITFENSTER_BELEG = f"zeitfenster({ZEITFELD})"


def ohne_wert(eimer: Eimer, was: str = "Delikte") -> Ausschluss:
    """Was ein Eimer weglaesst - mit seinem Beleg und seiner Groesse.

    Einmal formuliert statt achtzehnmal getippt: Der Text nennt das Feld
    und bei ``terms`` die Groesse, der Beleg ist ``Eimer.beleg``. So kann
    ein Text nicht "die 15 haeufigsten" sagen, waehrend der Eimer 20 zeigt.
    """
    text = f"{was} ohne `{eimer.feld}`"
    if eimer.operation == "terms":
        welche = (f"ersten {eimer.groesse}" if eimer.ordnung == "schluessel"
                  else f"{eimer.groesse} häufigsten")
        text += f"; gezeigt werden nur die {welche} Werte"
    return Ausschluss(text, eimer.beleg)


def im_zeitfenster(was: str = "Delikte") -> Ausschluss:
    """Der Ausschluss, den das Zeitfenster des Bretts vollzieht."""
    return Ausschluss(
        f"{was} ausserhalb des Zeitraums oben in der Leiste "
        f"(`{ZEITFELD}`) — voreingestellt ist der ganze Release, dann fällt "
        f"hier nichts weg", ZEITFENSTER_BELEG)


#: Ein KQL-Filter einer Lens-Kachel - nur in **dieser** Form.
#:
#: ``feld: true``, ``feld: false`` oder ``feld: "wert"``, mehrere mit
#: `` and `` verbunden. Enger als KQL, und das ist der Zweck: In dieser Form
#: laesst sich der Filter exakt in eine Elasticsearch-Abfrage uebersetzen
#: (``Tafel.filter_abfrage``), und die Pruefung gegen ein echtes
#: Elasticsearch stellt dieselbe Frage wie die Kachel. Ein freieres KQL
#: braeuchte Kibanas eigenen Uebersetzer, und den gibt es hier nicht.
_FILTERTEIL = re.compile(r'^([A-Za-z_][\w.]*): (true|false|"[^"\\]*")$')


def filterbedingungen(kql: str) -> tuple[tuple[str, Any], ...]:
    """``'counts_case: true'`` -> ``(("counts_case", True),)``."""
    teile = []
    for teil in kql.split(" and "):
        treffer = _FILTERTEIL.match(teil.strip())
        if treffer is None:
            raise LadeFehler(
                f"Filter '{kql}': '{teil}' hat nicht die Form feld: true, "
                f"feld: false oder feld: \"wert\" - nur diese Form laesst "
                f"sich gegen Elasticsearch nachpruefen.")
        feld, wert = treffer.groups()
        teile.append((feld, {"true": True, "false": False}.get(
            wert, wert.strip('"'))))
    return tuple(teile)


@dataclass(frozen=True)
class Abfrage:
    """Eine Frage in ES|QL - mit den Spalten, die sie zurueckgibt.

    **Warum der Nachschlagindex hier geprueft wird und nicht in Kibana.**
    ``LOOKUP JOIN`` verlangt, dass der rechte Index mit ``index.mode: lookup``
    angelegt wurde. Ist er es nicht, antwortet Elasticsearch mit *„Lookup Join
    requires a single lookup mode index"* - und zwar erst, wenn jemand das
    Dashboard oeffnet. Der Modus steht an ``load_elasticsearch.Index``; diese
    Klasse liest ihn dort und bricht beim Bauen ab statt beim Anschauen.
    """

    esql: str
    spalten: tuple[Spalte, ...]

    def __post_init__(self) -> None:
        if not self.spalten:
            raise LadeFehler(
                "Eine ES|QL-Tafel ohne Spalten zeigt nichts an - Lens braucht "
                "je Spalte eine Abbildung von Feldname auf Spaltenkennung.")
        for name in self.nachschlagindizes:
            index = NACH_NAME.get(name)
            if index is None:
                raise LadeFehler(
                    f"'{name}' steht in einem LOOKUP JOIN, ist aber kein "
                    f"geladener Index. Bekannt sind "
                    f"{', '.join(sorted(NACH_NAME))}.")
            if not index.nachschlag:
                raise LadeFehler(
                    f"'{name}' steht in einem LOOKUP JOIN, wird aber ohne "
                    f"index.mode 'lookup' geladen. Elasticsearch lehnt den "
                    f"Verbund ab, sobald jemand die Kachel oeffnet - "
                    f"nachschlag=True an load_elasticsearch.INDIZES setzen "
                    f"und neu laden.")

    @property
    def nachschlagindizes(self) -> tuple[str, ...]:
        """Welche Indizes die Abfrage ueber ``LOOKUP JOIN`` dazunimmt.

        Aus der Abfrage gelesen und nicht daneben gepflegt: Eine zweite Liste
        waere die Stelle, an der jemand einen Verbund ergaenzt und den
        Eintrag vergisst - und dann prueft niemand den Indexmodus.

        **Ohne Gross- und Kleinschreibung.** ES|QL nimmt ``lookup join``
        ebenso an wie ``LOOKUP JOIN``; ein Muster, das nur Grossbuchstaben
        kennt, findet den Verbund dann nicht und laesst den Indexmodus
        ungeprueft durch. Genau so liess sich der Waechter umgehen.
        """
        return tuple(re.findall(r"LOOKUP\s+JOIN\s+(\S+)", self.esql,
                                re.IGNORECASE))


@dataclass(frozen=True)
class Tafel:
    """Eine Kachel im Dashboard."""

    kennung: str
    titel: str
    art: str
    #: Nur fuer die Lens-Arten. Eine ES|QL-Tafel rechnet in der Abfrage; eine
    #: Kennzahl daneben waere eine zweite, die nichts tut.
    kennzahl: Kennzahl | None = None
    eimer: tuple[Eimer, ...] = ()
    breite: int = 24
    hoehe: int = 15
    #: Die Frage in ES|QL - nur und genau fuer die Arten aus ``ESQL_ARTEN``.
    abfrage: Abfrage | None = None
    #: **FR-27, die drei Angaben, ohne die eine Zahl irrefuehrt.** Sie stehen
    #: als Beschreibung am Lens-Objekt und damit im Informationsfeld der
    #: Kachel. ``docs/ausblick.md`` nennt den Grund: *„Ein Dashboard, das eine
    #: dieser Entscheidungen still trifft und eine Zahl hinstellt, macht die
    #: Arbeit dieses Projekts zunichte."*
    #:
    #: **Pflicht fuer jede Art** - Lens, ES|QL und Karte (``_pruefe_fr27``).
    #: Bis zum 17.11.2026 galt das nur fuer ES|QL und Karte; dabei fiel auf,
    #: dass drei Lens-Kacheln "Faelle" hiessen und Taten zaehlten. Eine
    #: reine Zaehlung nennt als Nenner ``_ZAEHLUNG`` ("keiner"), ein Anteil
    #: das Ganze, auf das er sich bezieht.
    frage: str = ""
    nenner: str = ""
    #: Was die Abfrage wegfiltert, je Kachel einzeln - nie ein geteiltes
    #: Tupel und nie ein Positionsschnitt daraus. Beides war dieselbe
    #: Wurzel: Wer die Reihenfolge aendert, aendert still, was eine andere
    #: Kachel als nicht enthalten ausweist.
    ausschluesse: tuple[Ausschluss, ...] = ()
    #: Was man beim Lesen wissen muss, ohne dass die Abfrage es wegfiltert -
    #: "Tatort ist nicht Wohnort", die Abweichung zu den Abgabedokumenten.
    #: Getrennt von ``ausschluesse``, weil dort jeder Eintrag einen Beleg in
    #: der Abfrage braucht und ein Vorbehalt keinen haben kann.
    vorbehalte: tuple[str, ...] = ()
    #: Welche Stadt diese Karte zeigt. Nur fuer ``art="karte"``; sie waehlt
    #: den Ausschnitt aus ``KARTE_JE_STADT`` und filtert die Schicht.
    stadt: str = ""
    #: Das Jahr, fuer das die Zahl gilt. Pflicht, sobald eine Rate dabei ist:
    #: Sechs Jahrgaenge auf einen Jahresnenner ergeben 500,7 je 1'000 - keine
    #: zu hohe Rate, sondern keine.
    jahr: int | None = None
    #: Der KQL-Filter einer Lens-Kachel - die Stelle, an der ihr Ausschluss
    #: vollzogen wird, so wie bei ES|QL das ``WHERE`` in der Abfrage. Er
    #: steht im Lens-Zustand (``state.query``) und nicht als Panel-Filter
    #: am Brett, der beim Umschalten der Kachel verloren ginge. Nur in der
    #: Form, die ``filterbedingungen`` kennt.
    filter: str = ""

    def __post_init__(self) -> None:
        if self.art not in ARTEN:
            raise LadeFehler(
                f"{self.kennung}: Art '{self.art}' ist nicht entschieden. "
                f"Bekannt sind {', '.join(sorted(ARTEN))}.")
        if self.filter and (self.ist_karte or self.ist_esql):
            raise LadeFehler(
                f"{self.kennung}: ein KQL-Filter gilt nur fuer Lens-Kacheln. "
                f"Eine ES|QL-Tafel filtert in ihrer Abfrage, eine Karte in "
                f"ihrer Schicht.")
        if self.filter:
            filterbedingungen(self.filter)
        if self.ist_karte:
            self._pruefe_karte()
        elif self.ist_esql:
            self._pruefe_esql()
        else:
            if self.abfrage is not None:
                raise LadeFehler(
                    f"{self.kennung}: '{self.art}' liest ueber Lens-Eimer, "
                    f"eine ES|QL-Abfrage bliebe unbenutzt. Art aus "
                    f"{', '.join(sorted(ESQL_ARTEN))} waehlen.")
            if self.kennzahl is None:
                raise LadeFehler(
                    f"{self.kennung}: '{self.art}' braucht eine Kennzahl - "
                    f"ohne sie weiss die Tafel nicht, was sie zaehlt.")
            if self.art == "zahl" and self.eimer:
                raise LadeFehler(
                    f"{self.kennung}: Eine Zahl zeigt einen Wert und "
                    f"gruppiert nicht.")
            if (self.art in ("balken", "linie", "ring", "anteilsbalken")
                    and not self.eimer):
                raise LadeFehler(
                    f"{self.kennung}: '{self.art}' braucht mindestens eine "
                    f"Gruppierung, sonst ist es ein einzelner Balken.")
        if self.breite > RASTER:
            raise LadeFehler(
                f"{self.kennung}: {self.breite} Spalten passen nicht in ein "
                f"Raster von {RASTER}.")
        self._pruefe_fr27()

    def _pruefe_fr27(self) -> None:
        """Frage, Nenner und Ausschluesse - fuer jede Art dieselbe Pflicht.

        Eine Zahl ohne Nenner und ohne Ausschluesse ist genau der Fall, den
        ``ausblick.md`` als "die Arbeit dieses Projekts zunichte machen"
        beschreibt - und sie faellt niemandem auf, denn sie sieht aus wie
        eine Zahl. Am 17.11.2026 hiessen drei Lens-Kacheln "Faelle" und
        zaehlten jede Zeile von ``fact_offense``, also Taten; keine Pruefung
        sah hin, weil Lens von FR-27 ausgenommen war.
        """
        if not self.frage:
            raise LadeFehler(
                f"{self.kennung}: ohne 'frage' sagt die Kachel nicht, was "
                f"sie beantwortet.")
        if not self.nenner:
            raise LadeFehler(
                f"{self.kennung}: ohne 'nenner' sagt die Kachel nicht, "
                f"wovon ihre Zahl ein Teil ist - bei einer reinen Zaehlung "
                f"heisst er ausdruecklich '{_ZAEHLUNG}'.")
        if not self.ausschluesse:
            raise LadeFehler(
                f"{self.kennung}: ohne 'ausschluesse' liest jemand die Zahl "
                f"als vollstaendig.")
        if self.ist_karte:
            # Eine Karte hat keine Abfrage, in der ein Beleg stehen koennte:
            # Sie faerbt nach ``rate_tract``, das ``build_comparison``
            # vorrechnet. Ihre Pflicht ist dafuer strenger - Nenner und
            # Jahr, siehe ``_pruefe_karte``.
            return
        stellen = self.belegstellen
        for a in self.ausschluesse:
            # Der Ausschluss muss in **dieser** Kachel vollzogen werden,
            # nicht in irgendeiner. Genau das fehlte, als drei Kacheln sich
            # ein Tupel teilten (siehe ``Ausschluss``).
            if self.ist_esql:
                vollzogen = any(a.beleg in s for s in stellen)
            else:
                # Gleich, nicht enthalten: siehe ``Ausschluss``.
                vollzogen = a.beleg in stellen
            if not vollzogen:
                wo = ("ihre Abfrage" if self.ist_esql
                      else "weder ihr Filter noch ein Eimer noch das "
                           "Zeitfenster")
                raise LadeFehler(
                    f"{self.kennung}: die Kachel nennt den Ausschluss "
                    f"'{a.text[:60]}…', {wo} vollzieht ihn aber nicht - "
                    f"'{a.beleg}' steht nicht darin.")
        if self.ist_esql:
            return
        # Ein Eimer laesst Zeilen ohne seinen Wert weg, ``terms`` dazu alles
        # jenseits der obersten N. Beides gehoert an die Kachel, und die
        # Groesse in den Text - sonst liest jemand "die haeufigsten
        # NIBRS-Codes" als alle.
        for e in self.eimer:
            belegt = [a for a in self.ausschluesse if a.beleg == e.beleg]
            if not belegt:
                raise LadeFehler(
                    f"{self.kennung}: der Eimer '{e.kennung}' laesst Zeilen "
                    f"ohne `{e.feld}` weg, kein Ausschluss nennt es - "
                    f"ohne_wert() benutzen.")
            if (e.operation == "terms"
                    and not any(str(e.groesse) in a.text for a in belegt)):
                raise LadeFehler(
                    f"{self.kennung}: der Eimer '{e.kennung}' zeigt nur die "
                    f"obersten {e.groesse} Werte, sein Ausschluss nennt die "
                    f"Zahl nicht.")

    @property
    def belegstellen(self) -> tuple[str, ...]:
        """Wo ein Ausschluss dieser Kachel vollzogen werden kann.

        ES|QL: die Abfrage. Lens: jeder Teil des KQL-Filters einzeln
        (``counts_case: true``), jeder Eimer (``Eimer.beleg``), das
        gezaehlte Feld (``Kennzahl.beleg``) und das Zeitfenster des Bretts.
        Eine Karte hat keine solche Stelle.
        """
        if self.ist_karte:
            return ()
        if self.ist_esql:
            assert self.abfrage is not None
            return (self.abfrage.esql,)
        stellen = ([t.strip() for t in self.filter.split(" and ")]
                   if self.filter else [])
        stellen += [e.beleg for e in self.eimer]
        if self.kennzahl is not None and self.kennzahl.beleg:
            stellen.append(self.kennzahl.beleg)
        stellen.append(ZEITFENSTER_BELEG)
        return tuple(stellen)

    @property
    def filter_abfrage(self) -> dict[str, Any] | None:
        """Der KQL-Filter als Elasticsearch-Abfrage - exakt, nicht ungefaehr.

        Moeglich, weil ``filterbedingungen`` nur ``feld: wert`` zulaesst;
        das ist in KQL und als ``term`` dasselbe.
        """
        if not self.filter:
            return None
        return {"bool": {"filter": [{"term": {feld: wert}} for feld, wert
                                    in filterbedingungen(self.filter)]}}

    def _pruefe_esql(self) -> None:
        """Was eine ES|QL-Tafel mitbringen muss, bevor sie entsteht."""
        if self.abfrage is None:
            raise LadeFehler(
                f"{self.kennung}: '{self.art}' braucht eine Abfrage - die "
                f"Frage steht in ES|QL und nicht in Eimern.")
        if self.eimer or self.kennzahl is not None:
            raise LadeFehler(
                f"{self.kennung}: Eine ES|QL-Tafel gruppiert und zaehlt in "
                f"der Abfrage. Kennzahl oder Eimer daneben waeren eine "
                f"zweite Beschreibung, die nichts bewirkt.")
        # Frage, Nenner und Ausschluesse prueft ``_pruefe_fr27`` fuer alle
        # Arten gemeinsam. Hier steht nur, was ES|QL eigen ist.
        #
        # Eine Heatmap ohne zweite Achse waere eine eingefaerbte Zeile, eine
        # mit vier Spalten liesse eine davon unsichtbar. Kibana importiert
        # beides klaglos; der Fehler faellt erst beim Oeffnen auf,
        # moeglicherweise vor Publikum.
        if (self.art == "esql_heatmap"
                and len(self.abfrage.spalten) != HEATMAP_SPALTEN):
            raise LadeFehler(
                f"{self.kennung}: eine Heatmap braucht genau "
                f"{HEATMAP_SPALTEN} Spalten (x, y, Wert), die Abfrage "
                f"liefert {len(self.abfrage.spalten)}.")
        if self.zeigt_rate and not (self.nenner and self.jahr):
            raise LadeFehler(
                f"{self.kennung}: eine Rate braucht ihren Nenner und ihr "
                f"Jahr. Ohne Jahr ist sie keine Rate, sondern ein Quotient "
                f"aus sechs Jahrgaengen und einem Jahresnenner.")

    def _pruefe_karte(self) -> None:
        """Was eine Karte mitbringen muss.

        Weder Kennzahl noch Eimer noch ES|QL: Eine Karte verbindet zwei
        Indizes und beschreibt das in ihrem eigenen Format. **FR-27 gilt
        trotzdem**, und hier besonders - die Karte zeigt eine Rate, und eine
        Flaeche ohne Nenner und ohne Jahr ist genau die Zahl, die
        ``ausblick.md`` als "die Arbeit dieses Projekts zunichte machen"
        beschreibt.
        """
        if self.kennzahl is not None or self.eimer or self.abfrage is not None:
            raise LadeFehler(
                f"{self.kennung}: eine Karte beschreibt ihre Frage als "
                f"Verbund zweier Indizes. Kennzahl, Eimer oder Abfrage "
                f"daneben waeren eine zweite Beschreibung, die nichts "
                f"bewirkt.")
        if not (self.nenner and self.jahr):
            raise LadeFehler(
                f"{self.kennung}: die Karte faerbt nach einer Rate und "
                f"braucht ihren Nenner und ihr Jahr.")
        if self.stadt not in KARTE_JE_STADT:
            raise LadeFehler(
                f"{self.kennung}: fuer '{self.stadt}' gibt es keinen "
                f"Ausschnitt. Bekannt sind "
                f"{', '.join(sorted(KARTE_JE_STADT))} - ein Eintrag in "
                f"KARTE_JE_STADT fehlt, und geraten wird er nicht.")

    @property
    def ist_karte(self) -> bool:
        return self.art in KARTEN_ARTEN

    @property
    def ist_esql(self) -> bool:
        return self.art in ESQL_ARTEN

    @property
    def zeigt_rate(self) -> bool:
        """Steht auf dieser Tafel eine Rate je 1'000 Einwohner?

        **Eine Karte zaehlt immer dazu.** Sie faerbt nach einer Rate, und
        ``_pruefe_karte`` laesst sie ohne Nenner und Jahr gar nicht
        entstehen. Haengte die Antwort nur an den Spalten einer Abfrage,
        traege die Karte eine Rate, ohne als Ratenkachel zu gelten - und
        jeder Waechter, der "wo stehen Raten" fragt, sähe sie nicht.
        """
        if self.ist_karte:
            return True
        return self.abfrage is not None and any(
            s.ist_rate for s in self.abfrage.spalten)

    @property
    def erlaeuterung(self) -> str:
        """Frage, Nenner, Jahr und Ausschluesse - als Text an der Kachel.

        Kibana zeigt die Beschreibung eines Lens-Objekts im Informationsfeld
        der Kachel. Das ist die Stelle, an der FR-27 ankommt: Wer die Zahl
        liest, liest daneben, wovon sie ein Anteil ist und was nicht
        mitgezaehlt wurde.
        """
        teile = []
        if self.frage:
            teile.append(f"Frage: {self.frage}")
        if self.nenner:
            teile.append(f"Nenner: {self.nenner}")
        if self.jahr:
            teile.append(f"Jahr: {self.jahr}")
        if self.ausschluesse:
            teile.append("Nicht enthalten: "
                         + "; ".join(a.text for a in self.ausschluesse))
        if self.vorbehalte:
            teile.append("Zu beachten: " + "; ".join(self.vorbehalte))
        return " · ".join(teile)

    @property
    def schicht(self) -> str:
        return f"schicht-{self.kennung}"

    @property
    def spalten(self) -> dict[str, Any]:
        """Alle Lens-Spalten - Gruppierungen zuerst, dann die Kennzahl.

        Fuer eine ES|QL-Tafel sind es die Spalten, die die Abfrage liefert,
        in der Reihenfolge, in der sie dastehen.
        """
        if self.ist_karte:
            raise LadeFehler(
                f"{self.kennung}: eine Karte hat keine Lens-Spalten - sie "
                f"beschreibt sich als Schicht mit Verbund (karte_objekt).")
        if self.ist_esql:
            assert self.abfrage is not None   # __post_init__ hat es geprueft
            return {s.kennung: s.lens_spalte for s in self.abfrage.spalten}
        assert self.kennzahl is not None
        spalten = {e.kennung: e.lens_spalte(self.kennzahl.kennung)
                   for e in self.eimer}
        spalten[self.kennzahl.kennung] = self.kennzahl.lens_spalte
        return spalten

    @property
    def reihenfolge(self) -> list[str]:
        if self.ist_esql:
            assert self.abfrage is not None
            return [s.kennung for s in self.abfrage.spalten]
        assert self.kennzahl is not None
        return [e.kennung for e in self.eimer] + [self.kennzahl.kennung]

    @property
    def darstellung(self) -> dict[str, Any]:
        """Der Teil, der sagt, welche Spalte wo hingehoert."""
        if self.ist_karte:
            raise LadeFehler(
                f"{self.kennung}: eine Karte hat keine Lens-Darstellung - "
                f"ihre Schichten stehen in karte_objekt.")
        if self.art == "zahl":
            assert self.kennzahl is not None
            return {"layerId": self.schicht, "layerType": "data",
                    "metricAccessor": self.kennzahl.kennung}
        if self.art in ("tabelle", "esql_tabelle"):
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
        if self.art == "esql_heatmap":
            assert self.abfrage is not None
            x, y, wert = (s.kennung for s in self.abfrage.spalten)
            return {
                "shape": "heatmap", "layerId": self.schicht,
                "layerType": "data",
                "xAccessor": x, "yAccessor": y, "valueAccessor": wert,
                "legend": {"isVisible": True, "position": "right",
                           "type": "heatmap_legend"},
                # Keine Zahl in jede Zelle: Bei 7 x 24 Zellen sind das 168
                # Beschriftungen, die das Muster zudecken, das die Kachel
                # zeigen soll.
                "gridConfig": {"type": "heatmap_grid",
                               "isCellLabelVisible": False,
                               "isXAxisLabelVisible": True,
                               "isYAxisLabelVisible": True,
                               "isXAxisTitleVisible": False,
                               "isYAxisTitleVisible": False},
            }
        reihe = {"balken": "bar_stacked",
                 "anteilsbalken": "bar_percentage_stacked",
                 "linie": "line"}[self.art]
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

        **Fuer eine ES|QL-Tafel gibt es die nicht**, und das wirft, statt
        ``{"size": 0}`` zurueckzugeben. Eine leere Aggregation waere der
        gefaehrlichere Weg: ``test_jede_tafel_bekommt_auch_wirklich_daten``
        stellte sie, bekaeme Treffer, und die Kachel waere damit als
        "zeigt Daten" durchgewinkt, ohne dass die Abfrage je gelaufen ist.
        """
        if self.ist_esql:
            raise LadeFehler(
                f"{self.kennung}: eine ES|QL-Tafel fragt ueber /_query und "
                f"nicht ueber /_search - ihre Abfrage steht in "
                f"'abfrage.esql'.")
        innen: dict[str, Any] = {}
        if (kz := self.kennzahl.aggregation) is not None:
            innen = {self.kennzahl.kennung: kz}
        for eimer in reversed(self.eimer):
            innen = {eimer.kennung: {**eimer.aggregation,
                                     **({"aggs": innen} if innen else {})}}
        frage: dict[str, Any] = {"size": 0}
        # Der Filter der Kachel gehoert in dieselbe Frage - sonst prueft
        # ``test_jede_tafel_bekommt_auch_wirklich_daten`` eine andere Zahl
        # als die, die Kibana zeigt.
        if (gefiltert := self.filter_abfrage) is not None:
            frage["query"] = gefiltert
        if innen:
            frage["aggs"] = innen
        return frage


@dataclass(frozen=True)
class Steuerung:
    """Ein Auswahlfeld ueber dem Brett - Kibanas ``optionsListControl``.

    Der Entwurf von Artan setzt drei davon ueber jedes Brett: *Stadt*,
    *Zeitraum*, *Kategorie*. Zwei davon sind hier; **den Zeitraum gibt es
    nicht als Steuerung**, weil Kibana ihn ohnehin oben in der Leiste fuehrt.
    Ein zweites Zeitfeld daneben waere eine zweite Wahrheit: Wer den einen
    stellt und den anderen vergisst, liest eine Zahl fuer einen Zeitraum, den
    er nicht gewaehlt hat.

    Eine Steuerung filtert **alle** Kacheln des Bretts gleichzeitig. Sie
    gehoert deshalb ans Brett und nicht an die Tafel.
    """

    kennung: str
    #: Das Feld, ueber das ausgewaehlt wird. Muss im Index stehen;
    #: ``pruefe_steuerung`` haelt es gegen ``load_elasticsearch``.
    feldname: str
    titel: str
    #: ``small``, ``medium`` oder ``large`` - Kibanas eigene Stufen.
    breite: str = "medium"

    @property
    def panel(self) -> dict[str, Any]:
        return {
            "type": "optionsListControl", "grow": True, "width": self.breite,
            "explicitInput": {
                "id": self.kennung, "fieldName": self.feldname,
                "title": self.titel, "enhancements": {},
                "searchTechnique": "prefix", "selectedOptions": [],
            },
        }

    @property
    def verweisname(self) -> str:
        return f"controlGroup_{self.kennung}:optionsListDataView"


@dataclass(frozen=True)
class Brett:
    """Ein Dashboard."""

    kennung: str
    titel: str
    beschreibung: str
    tafeln: tuple[Tafel, ...]
    #: Wird beim Bauen aus dem Release gefuellt, siehe ``zeitfenster``.
    #:
    #: **Bleibt das fuenfte Feld.** Mehrere Tests bauen ein ``Brett`` nach
    #: Position; ein neues Feld davor liesse das Zeitfenster still in der
    #: falschen Spalte landen. Alles Neue kommt dahinter.
    zeitraum: tuple[str, str] = ("", "")
    #: Die Auswahlfelder ueber den Kacheln. Leer heisst: kein Steuerbereich.
    steuerungen: tuple[Steuerung, ...] = ()
    #: Traegt dieses Brett die Navigation zu den anderen?
    #:
    #: Kibana kennt keine Reiterleiste ueber mehreren Dashboards, wie der
    #: Entwurf sie zeigt. Am naechsten kommt ein ``links``-Objekt (ab 8.15),
    #: das als Kachel auf jedem Brett liegt und auf die uebrigen zeigt. Es
    #: wird **einmal** angelegt und von jedem Brett verwiesen.
    #:
    #: **Vorgabe aus, an den Brettern eingeschaltet.** Eingeschaltet erzeugt
    #: ``dashboard_objekt`` einen Verweis auf ein Objekt, das nur
    #: ``objekte()`` mitliefert. Ein von Hand gebautes Brett zeigte damit ins
    #: Leere - und genau das hat ``test_kibana_nimmt_die_erzeugten_objekte_an``
    #: beim ersten Anlauf gemeldet, zu Recht.
    navigation: bool = False


# --------------------------------------------------------------------------
# Die Dashboards. Alles hier ist Entscheidung.
# --------------------------------------------------------------------------

_GESAMT = Kennzahl("anzahl", "Delikte", "count")
#: Dieselbe Zaehlung, unter ``counts_case: true`` gestellt - die Beschriftung
#: sagt es, damit die Achse nicht "Delikte" heisst, wo Faelle stehen.
_FAELLE = Kennzahl("anzahl", "Fälle", "count")

#: Der Nenner einer reinen Zaehlung - ausdruecklich keiner (FR-27). Daneben
#: steht immer ``_ERST_DIE_RATE``; ``test_build_kibana`` haelt beides
#: zusammen.
_ZAEHLUNG = "keiner, eine absolute Zahl"

#: Der Vorbehalt jeder reinen Zaehlung: Sie vergleicht die Staedte nicht.
_ERST_DIE_RATE = (
    "Erst die Rate je 1'000 Einwohner macht die Städte vergleichbar — "
    "Chicago ist die grössere Stadt und liegt absolut fast überall vorn. "
    "Die Rate steht im Brett »Raten je 1'000«"
)

#: Der Vorbehalt der Kacheln, die bewusst auf der Tatebene bleiben
#: (Entscheid vom 17.11.2026): Datensaetze und Datenqualitaet zaehlt man je
#: Zeile, einen Vergleich der Staedte nicht.
_TATEBENE = (
    "Gezählt werden Delikte (Tatebene), nicht Fälle: Chicago erfasst je Fall "
    "nur das schwerste Delikt, Detroit jedes. Für Datensätze und "
    "Datenqualität ist das die richtige Ebene; im Vergleich der Städte fällt "
    "Detroits Zahl dadurch höher aus — Fälle zählen die Bretter "
    "»Zeitverlauf« und »Deliktstruktur«"
)

#: Der Filter der Kacheln, die Faelle zaehlen, und sein Ausschluss.
#:
#: ``counts_case`` ist je Vorfall genau einmal gesetzt, an seinem
#: schwersten Delikt (die Hierarchieregel; ``reconcile`` bricht ab, wenn es
#: nicht so ist). Gemessen am 17.11.2026 an gold/fact_offense, 2021-2026:
#: 180 Chicagoer und 26'904 Detroiter Zeilen zaehlen nicht als eigener
#: Fall - daher "fast nur Detroit" und nicht "nur Detroit".
_NUR_FAELLE_FILTER = "counts_case: true"
_WEITERE_DELIKTE_DES_FALLS = Ausschluss(
    "die weiteren Delikte desselben Falls — ein Fall zählt einmal, mit "
    "seinem schwersten Delikt (`counts_case`). Das betrifft fast nur "
    "Detroit: Chicago erfasst je Fall ohnehin nur das schwerste Delikt",
    _NUR_FAELLE_FILTER)

#: Zaehler und Nenner, beide aus ``load_elasticsearch.INDIZES`` gelesen statt
#: getippt. Steht hier ein Name von Hand, laeuft die Abfrage ins Leere, sobald
#: ein Index umbenannt wird - und zwar erst beim Oeffnen der Kachel.
_ZAEHLER = NACH_NAME["fact_offense"].name
_NENNER = NACH_NAME["dim_tract_acs"].name

#: Der Ausschnitt, fuer den der Nenner gilt - und damit der einzige, fuer den
#: eine Rate definiert ist. Wortgleich in allen drei Abfragen, damit die drei
#: Kacheln dieselbe Grundmenge zeigen.
_IM_JAHR_UND_IN_DER_STADT = (
    f'| WHERE date >= "{RATENJAHR}-01-01" AND date <= "{RATENJAHR}-12-31"\n'
    f'    AND geo_status == "inside_city"'
)

# Die Ausschluesse, **einzeln benannt**. Jede Kachel waehlt die ihren aus;
# ein geteiltes Tupel oder ein Schnitt daraus (``[:2]``) waere beides
# dieselbe Falle: Die Stadtkachel fuehrte am 11.10.2026 "Tracts ohne
# Einwohner", obwohl ihre Abfrage sie mitzaehlt, und ein Umsortieren haette
# still geaendert, was die dritte Kachel ausweist.
#
# Der angezeigte Text traegt echte Umlaute: Er steht nicht im Quelltext,
# sondern in der Kachel. Genannt werden Spalten und Gruende, nicht Zahlen -
# eine Zahl im Kacheltext misst beim naechsten Release niemand nach. Welche
# Ausschluesse wie viele Zeilen treffen, steht im Brett "Datenqualität".
_AUSSERHALB = Ausschluss(
    "Taten ohne Koordinate, ausserhalb der Stadtgrenze oder ohne Tract "
    "(`geo_status` ungleich `inside_city`)",
    'geo_status == "inside_city"',
)
_ANDERE_JAHRGAENGE = Ausschluss(
    f"die Jahrgänge ausser {RATENJAHR} — `dim_date.year_is_complete` sagt, "
    f"welche überhaupt vollständig sind",
    f'date >= "{RATENJAHR}-01-01"',
)
_OHNE_EINWOHNER = Ausschluss(
    "Tracts ohne Einwohner — für sie ist keine Rate definiert; sie stehen "
    "in der Kachel darunter",
    "population > 0",
)
_MIT_EINWOHNERN = Ausschluss(
    "Tracts mit Einwohnern — die stehen in den beiden Kacheln darüber",
    "population == 0",
)

#: Der Vorbehalt, ohne den die Spitze der Tract-Liste falsch gelesen wird.
#: Kein Ausschluss: Die Abfrage filtert nichts weg, man muss es nur wissen.
_TATORT_NICHT_WOHNORT = (
    "**Tatort ist nicht Wohnort.** Ein Tract mit wenigen Bewohnern und viel "
    "Tagesbevölkerung (Innenstadt, Verkehrsknoten) steht hier oben, ohne "
    "dass seine Bewohner betroffener wären"
)

#: Die Abweichung zwischen Dashboard und Abgabe - auf der Kachel, auf der die
#: Zahl steht, nicht nur in der Brettbeschreibung. Ohne Zahlen: Eine Zahl
#: hier haette keinen Waechter, und die Kachel stellt zwanzig Zeilen weiter
#: oben selbst die Regel auf, dass das nicht geht. Die beiden Werte stehen
#: nebeneinander in der Kachel - wer den Unterschied sehen will, liest ihn
#: dort ab.
#:
#: **Warum die Fallebene vorn steht, und nicht nur "auch".** Bis zum
#: 11.10.2026 stand hier, beide Masse seien zwei Lesarten derselben Daten.
#: Das ist zu freundlich. Chicago erfasst **je Fall nur das schwerste
#: Delikt**, Detroit **jedes** (``docs/feldkatalog.md``, ``counts_case``;
#: ``counts_reason`` sagt es je Zeile). Gemessen fuer 2024: 1,0001 Taten je
#: Vorfall in Chicago, 1,0678 in Detroit. Ein Vergleich auf der Tatebene
#: stellt damit Detroits vollstaendige Anklagen gegen eine Chicagoer Zahl,
#: die nie alle Delikte enthielt - er misst den Erfassungsunterschied mit.
#: Die Tatebene ist deshalb nicht die zweite Lesart, sondern die schiefe,
#: und das gehoert auf die Kachel.
_FALLEBENE_VORN = (
    "**Fallebene vorn, Tatebene daneben** (Entscheid E5). Chicago erfasst je "
    "Fall nur das **schwerste** Delikt, Detroit **jedes**. Ein Vergleich auf "
    "der Tatebene stellt deshalb Detroits vollständige Anklagen gegen eine "
    "Chicagoer Zahl, die nie alle Delikte enthielt — er misst den "
    "Erfassungsunterschied mit, nicht die Kriminalität. Die Fallebene wendet "
    "dieselbe Hierarchieregel auf beide an und stellt erst her, was "
    "vergleichbar ist. Die Tatebene steht daneben, weil sie für Anteile je "
    "Deliktart gebraucht wird — und weil die Abgabedokumente sie bis auf "
    "Weiteres als kanonische Rate führen"
)

#: Woher der Nenner kommt, in einem Satz - samt dem, was fuer 2025 und 2026
#: gilt. ``population_vintage`` nennt je Tat ihren ACS-Jahrgang; einen
#: neueren als 2024 gibt es nicht, und eine Rate fuer 2026 ruht deshalb
#: weiter auf der Bevoelkerung von 2024.
_NENNERTEXT = (
    f"Einwohner je Tract aus `{_NENNER}`, je Tat mit dem Vintage, das "
    f"`population_vintage` für sie nennt — je Tract **einmal** gezählt, "
    f"nicht je Delikt. Für {RATENJAHR} ist das das Vintage {RATENJAHR}; "
    f"für {RATENJAHR + 1} und {RATENJAHR + 2} bleibt es dasselbe, weil es "
    f"kein neueres ACS gibt — die Rate dieser Jahre ruht also auf der "
    f"Bevölkerung von {RATENJAHR}."
)

# Vier Bedingungen, jede einzeln nachgewiesen am 11.10.2026 gegen
# Elasticsearch 8.19.22 - und drei davon so, dass ihr Bruch keinen Fehler
# wirft, sondern eine Zahl, die man hinschreiben kann:
#
# 1. Der Nennerindex braucht ``index.mode: lookup``; ohne ihn kein Verbund.
#    Das ist der eine Fall, der laut auffaellt (``Abfrage.__post_init__``
#    faengt ihn vorher ab).
# 2. ``LOOKUP JOIN`` verbindet nur **gleichnamige** Felder, darum das
#    ``RENAME tract_geoid AS geoid``.
# 3. Es verbindet ueber **ein** Feld und liefert vier Zeilen je Tat - vier
#    Vintages a 6'282 Tracts. Ohne ``WHERE vintage == population_vintage``
#    danach wird jede Tat vervierfacht: 356,1 statt 94,5 fuer Chicago.
# 4. ``MAX(population)`` je ``(Stadt, Tract)`` **vor** dem Summieren.
#    ``SUM`` an dieser Stelle ist der stille Fehler: Der Nenner waechst um
#    den Faktor "Delikte je Tract", und die Rate fiel auf 0,3.
#
# **Woran der Nenner haengt, und wann er von Gold abweicht.** Diese Abfrage
# summiert ueber die Tracts, die im Jahrgang **mindestens eine Tat** tragen;
# ``gold_pipeline.einwohner_je_stadt`` summiert ueber **jeden** Tract mit
# einer Stadtzuordnung. Am 11.10.2026 ist das dieselbe Menge - beide Seiten
# nennen 2'661'953 und 638'635 -, aber es ist keine Identitaet: Ein Tract
# ohne eine einzige Tat im Jahrgang faellt hier heraus und dort nicht, und
# der Brueckenwaechter wuerde rot, ohne von sich aus zu sagen, welche Seite
# recht hat. Seine Fehlermeldung nennt diesen Fall deshalb.
#
# Der dritte Weg zur falschen Zahl steht nicht in der Abfrage, sondern im
# Fehlen des Jahresfilters: sechs Jahrgaenge Zaehler auf einem Jahr Nenner
# ergeben 500,7. Darum ``_IM_JAHR_UND_IN_DER_STADT`` und darum ``jahr`` als
# Pflichtangabe an der Tafel.
RATE_JE_STADT = Abfrage(
    esql=f"""FROM {_ZAEHLER}
{_IM_JAHR_UND_IN_DER_STADT}
| RENAME tract_geoid AS geoid
| LOOKUP JOIN {_NENNER} ON geoid
| WHERE vintage == population_vintage
| STATS faelle = COUNT(*) WHERE counts_case, taten = COUNT(*),
        einwohner = MAX(population) BY stadt = reporting_city, geoid
| STATS faelle = SUM(faelle), taten = SUM(taten),
        einwohner = SUM(einwohner) BY stadt
| EVAL rate_fallebene = ROUND(faelle * 1000.0 / einwohner, 1),
       rate_tatebene = ROUND(taten * 1000.0 / einwohner, 1)
| KEEP stadt, faelle, rate_fallebene, taten, rate_tatebene, einwohner
| SORT stadt""",
    spalten=(
        Spalte("stadt", "Stadt", "string"),
        # Die Fallebene vorn (E5, entschieden am 5.10.2026): Die
        # Kriminalstatistik beantwortet traditionell "in wie vielen Faellen
        # ging es um X" und nicht "wie viele X gab es".
        Spalte("faelle", "Fälle"),
        Spalte("rate_fallebene", "Fälle je 1'000", ist_rate=True),
        # Die Tatebene daneben und nicht statt: Beide sind richtig, es sind
        # verschiedene Fragen (``docs/zaehlperspektiven.md``, Abschnitt 1).
        Spalte("taten", "Taten"),
        Spalte("rate_tatebene", "Taten je 1'000", ist_rate=True),
        Spalte("einwohner", "Einwohner"),
    ),
)

RATE_JE_TRACT = Abfrage(
    esql=f"""FROM {_ZAEHLER}
{_IM_JAHR_UND_IN_DER_STADT}
| RENAME tract_geoid AS geoid
| LOOKUP JOIN {_NENNER} ON geoid
| WHERE vintage == population_vintage AND population > 0
| STATS faelle = COUNT(*) WHERE counts_case, taten = COUNT(*),
        einwohner = MAX(population) BY stadt = reporting_city, geoid
| EVAL rate_fallebene = ROUND(faelle * 1000.0 / einwohner, 1),
       rate_tatebene = ROUND(taten * 1000.0 / einwohner, 1)
| KEEP stadt, geoid, faelle, rate_fallebene, taten, rate_tatebene, einwohner
| SORT rate_fallebene DESC
| LIMIT 20""",
    spalten=(
        Spalte("stadt", "Stadt", "string"),
        Spalte("geoid", "Tract", "string"),
        Spalte("faelle", "Fälle"),
        Spalte("rate_fallebene", "Fälle je 1'000", ist_rate=True),
        Spalte("taten", "Taten"),
        Spalte("rate_tatebene", "Taten je 1'000", ist_rate=True),
        Spalte("einwohner", "Einwohner"),
    ),
)

_KALENDER = NACH_NAME["dim_date"].name

#: Wann Faelle passieren - Wochentag mal Tagesstunde.
#:
#: **Der Wochentag wird nicht gerechnet, sondern nachgeschlagen.**
#: ``gold/dim_date`` traegt ``day_name`` und ``day_of_week``; genau dafuer
#: gibt es eine Datumsdimension. ``fact_offense.date`` zeigt darauf, und
#: ``LOOKUP JOIN`` verbindet beide ueber den gleichnamigen Schluessel.
#:
#: Sortiert wird nach ``day_of_week`` und nicht nach ``day_name``: Alphabetisch
#: begaenne die Woche am Freitag.
HEATMAP_WOCHE_STUNDE = Abfrage(
    esql=f"""FROM {_ZAEHLER}
| WHERE counts_case
| LOOKUP JOIN {_KALENDER} ON date
| STATS faelle = COUNT(*) BY day_name, day_of_week, hour_of_day
| SORT day_of_week, hour_of_day
| KEEP day_name, hour_of_day, faelle""",
    spalten=(
        Spalte("day_name", "Wochentag", "string"),
        Spalte("hour_of_day", "Lokale Tagesstunde"),
        Spalte("faelle", "Fälle"),
    ),
)

# Keine Division, sondern eine Zaehlung: ``population == 0`` heisst nicht
# "sichere Gegend", sondern "hier wohnt niemand" - Flughaefen, Parks, Gewerbe.
# Eine Rate waere dort nicht null, sondern undefiniert, und eine gezeigte Null
# liest sich als Sicherheit (``docs/ausblick.md``, Grundsatz 3).
TRACTS_OHNE_EINWOHNER = Abfrage(
    esql=f"""FROM {_ZAEHLER}
{_IM_JAHR_UND_IN_DER_STADT}
| RENAME tract_geoid AS geoid
| LOOKUP JOIN {_NENNER} ON geoid
| WHERE vintage == population_vintage AND population == 0
| STATS taten = COUNT(*) BY stadt = reporting_city, geoid
| STATS tracts = COUNT(*), taten = SUM(taten) BY stadt
| KEEP stadt, tracts, taten
| SORT stadt""",
    spalten=(
        Spalte("stadt", "Stadt", "string"),
        Spalte("tracts", "Tracts ohne Einwohner"),
        Spalte("taten", "Taten darin"),
    ),
)


#: Die Heatmap zaehlt Faelle, nicht Taten - ``counts_case`` vollzieht es.
_NUR_FAELLE = Ausschluss(
    "Taten, die nicht als eigener Fall zählen (Chicago erfasst je Fall nur "
    "das schwerste Delikt, Detroit jedes)",
    "counts_case")

#: Die Stunde ist **lokale** Tatzeit und nicht UTC. Zwischen Chicago und
#: Detroit liegt eine Stunde; auf einer UTC-Achse laege Detroits Abendspitze
#: eine Stunde neben Chicagos, ohne dass das etwas ueber die Staedte sagte.
_ORTSZEIT = (
    "Die Stunde ist lokale Tatzeit (gold/fact_offense.hour_of_day), nicht "
    "UTC — sonst läge Detroits Abendspitze eine Stunde neben Chicagos."
)

#: Mitternacht und Mittag sind ueberbesetzt - und zwar nicht, weil dann mehr
#: passiert.
#:
#: Gemessen am Release 2026-10-14T16-40-30Z ueber alle Faelle: Stunde 0 traegt
#: 128'595 (7,04 %), Stunde 12 traegt 106'277 (5,82 %); gleichverteilt waeren
#: 4,17 %. Beide Staedte zeigen es - Chicago 79'586 um 12 Uhr gegen 60'962 um
#: 11 und 62'537 um 13, Detroit 26'691 gegen 17'862 und 18'988. Das sind
#: Platzhalter fuer eine unbekannte Tatzeit, kein Tagesrhythmus.
#:
#: Ohne diesen Vermerk liest jemand aus der Heatmap "die meisten Taten
#: passieren um Mitternacht" - und das waere falsch.
_PLATZHALTERSTUNDEN = (
    "Mitternacht und Mittag sind überbesetzt: Stunde 0 trägt 7,0 % aller "
    "Fälle, Stunde 12 trägt 5,8 % — gleichverteilt wären 4,2 %. Beide Städte "
    "zeigen es. Das sind Platzhalter für eine unbekannte Tatzeit, kein "
    "Tagesrhythmus."
)

#: Die Rate je Tract ist ueber **alle** Delikte des Bezugsjahrs gerechnet.
#:
#: ``serving/rate_tract`` traegt keine Deliktfamilie - eine Karte "nur
#: Koerperverletzung" liesse sich daraus nicht faerben. Wer nach Deliktart
#: fragt, fragt auf den Brettern "Deliktstruktur" oder "Ueberblick".
_RATE_UEBER_ALLE_DELIKTE = (
    "Die Rate ist über alle Delikte des Bezugsjahrs gerechnet — "
    "serving/rate_tract trägt keine Deliktfamilie. Nach Deliktart fragen "
    "die Bretter »Deliktstruktur« und »Überblick«."
)

#: Eine Rate aus einem kleinen Nenner schwankt stark. Der kleinste Tract der
#: beiden Staedte hat 35 Einwohner; eine einzige Tat ergibt dort 28,6 je
#: 1'000 - mehr als die hoechste Stadtrate, und sie bedeutet nichts.
_KLEINE_NENNER = (
    "Kleine Nenner schwanken stark: Der kleinste Tract mit Einwohnern hat 35, "
    "der grösste 13'521 (2024). Eine einzelne Tat ergibt dort 28,6 je 1'000 — "
    "die Spalte »Einwohner« steht deshalb daneben."
)

#: Die zwei Auswahlfelder aus Artans Entwurf, die Kibana fuehren kann.
#: Den Zeitraum fuehrt Kibana oben in der Leiste; ein zweites Zeitfeld
#: daneben waere eine zweite Wahrheit.
_STEUERUNG = (
    Steuerung("stadt", "reporting_city", "Stadt", "small"),
    Steuerung("familie", "nibrs_family", "Deliktfamilie"),
)

#: Was der Entwurf an jeder Zeitreihe vermerkt und wir sonst unterschlagen
#: wuerden: Ein Teiljahr darf nicht neben ein ganzes gestellt werden.
#: ``dim_date.year_is_complete`` sagt je Tag, ob sein Jahrgang ganz vorliegt;
#: 2026 liegt es nicht.
_TEILJAHR = (
    "2026 ist ein Teiljahr — der letzte Monat ist unvollständig, und ein "
    "Rückgang am rechten Rand ist deshalb keiner. dim_date.year_is_complete "
    "sagt je Tag, ob sein Jahrgang ganz vorliegt."
)

#: Die Eimer der Lens-Kacheln, einmal benannt. Ihr Ausschluss entsteht aus
#: ihnen (``ohne_wert``), damit Text und Groesse nicht auseinanderlaufen.
_E_STADT = Eimer("stadt", "Stadt", "terms", "reporting_city", 5)
_E_MONAT = Eimer("monat", "Monat", "date_histogram", "occurred_at_utc",
                 intervall="1M")
#: Der Jahrgang ist das **lokale Tatdatum** (``date``), wie in ``dim_date``
#: und auf der Startseite - nicht das UTC-Jahr von ``occurred_at_utc``. Am
#: 17.11.2026 gemessen: Nach dem UTC-Jahr fielen 179 Chicagoer Faelle von
#: 2024 ins Jahr 2025 (die Silvesterabende nach 18 Uhr Ortszeit), und die
#: Kachel stimmte mit keiner Jahrgangszahl des Projekts ueberein.
_E_JAHR = Eimer("jahr", "Jahrgang", "date_histogram", "date", intervall="1y")
_E_FAMILIE_8 = Eimer("familie", "NIBRS-Familie", "terms", "nibrs_family", 8)
_E_FAMILIE_10 = Eimer("familie", "NIBRS-Familie", "terms", "nibrs_family", 10)
_E_CODE_15 = Eimer("art", "Delikt", "terms", "nibrs_code", 15)
_E_CODE_20 = Eimer("code", "NIBRS-Code", "terms", "nibrs_code", 20)
_E_ZUORDNUNG = Eimer("status", "Status", "terms", "mapping_status", 6)
_E_VERORTUNG = Eimer("status", "Status", "terms", "geo_status", 6)
#: Nach der Stunde sortiert, nicht nach der Haeufigkeit - sonst steht da eine
#: Rangliste statt eines Tagesverlaufs.
_E_STUNDE = Eimer("stunde", "Stunde", "terms", "hour_of_day", 24,
                  ordnung="schluessel")
#: Das Unterfeld ist Pflicht: Auf ``text`` laesst sich nicht gruppieren, und
#: die Tafel bliebe still leer.
_E_TEXT = Eimer("text", "Beschreibung", "terms", "source_offense_description",
                20, unterfeld_keyword=True)

#: Warum "Faelle je Jahrgang" nicht die Zahl der Startseite ist.
_NACH_MELDESTADT = (
    "Gezählt wird nach `reporting_city`, also auch Fälle ausserhalb der "
    "Stadtgrenze und ohne Koordinate. Die Startseite zählt nur Fälle in "
    "Tracts der Stadt und nennt deshalb für dasselbe Jahr weniger"
)

#: Kibana teilt Jahre in der Zeitzone des Browsers. ``date`` liegt als
#: Mitternacht UTC im Index; oestlich von UTC (Zuerich) faellt jeder Tag in
#: sein Jahr, westlich davon (Chicago) rutschte der 1. Januar ins Vorjahr.
_JAHRGANG_LOKAL = (
    "Der Jahrgang ist das lokale Tatdatum (`date`, wie in `dim_date`), nicht "
    "das UTC-Jahr. Kibana teilt die Jahre in der Zeitzone des Browsers — "
    "in Mitteleuropa stimmt das, westlich von UTC fiele der 1. Januar ins "
    "Vorjahr"
)

#: Der Vorbehalt fuer Faelle je Deliktfamilie. ``counts_case`` ordnet jeden
#: Fall genau einer Familie zu - der seines schwersten Delikts. Die Kachel
#: sagt damit, welche Familie Faelle anfuehrt, nicht wie oft sie vorkommt.
_FAMILIE_DES_SCHWERSTEN = (
    "Ein Fall zählt in der Familie seines schwersten Delikts. Die Kachel "
    "sagt deshalb, welche Familie Fälle anführt, nicht wie oft sie "
    "vorkommt — das zeigt der Anteilsbalken daneben, auf der Tatebene"
)

#: Der Vorbehalt fuer Anteile je Deliktart. E5 verlangt sie auf der
#: Tatebene, weil sich nur dort Kategorien addieren (``zaehlperspektiven.md``,
#: Abschnitt 2); der Plan hat das am 17.11.2026 so nachverhandelt.
_ANTEIL_TATEBENE = (
    "Anteile je Deliktart rechnen auf der Tatebene (Entscheid E5): Nur dort "
    "addieren sich Kategorien. Chicago erfasst je Fall nur das schwerste "
    "Delikt, Detroit jedes — Detroits Säule enthält deshalb auch die "
    "weiteren Delikte eines Falls"
)

#: Wie ``_NACH_MELDESTADT``, fuer eine Kachel auf der Tatebene.
_NACH_MELDESTADT_TATEN = (
    "Gezählt wird nach `reporting_city`, also auch Delikte ausserhalb der "
    "Stadtgrenze und ohne Koordinate"
)

#: Aus ``docs/zaehlperspektiven.md``, Abschnitt "Die Beschreibung ist nicht
#: das Delikt".
_BESCHREIBUNG_NICHT_DELIKT = (
    "Die Beschreibung ist nicht das Delikt: Der Text in "
    "`source_offense_description` identifiziert die Tat nicht, das tut der "
    "Code"
)

BRETTER: tuple[Brett, ...] = (
    Brett(
        kennung="crime-ueberblick",
        titel="Überblick — Chicago gegen Detroit",
        beschreibung=(
            "Der Einstieg. Absolute Zahlen sagen wenig, solange die Städte "
            "verschieden gross sind — die Rate je 1'000 Einwohner steht im "
            "Brett »Raten je 1'000«, für den Jahrgang "
            f"{RATENJAHR}."),
        # Die Kacheln dieses Bretts zeigen den Datenbestand und bleiben
        # deshalb auf der Tatebene (Entscheid vom 17.11.2026) - sie heissen
        # "Delikte" und sagen es im Vorbehalt.
        tafeln=(
            Tafel("gesamt", "Delikte insgesamt", "zahl", _GESAMT,
                  frage="Wie viele Delikte liegen im gewählten Zeitraum vor?",
                  nenner=_ZAEHLUNG,
                  ausschluesse=(im_zeitfenster(),),
                  vorbehalte=(_TATEBENE, _ERST_DIE_RATE),
                  breite=12, hoehe=8),
            Tafel("je_stadt", "Delikte je Stadt", "balken", _GESAMT,
                  eimer=(_E_STADT,),
                  frage="Wie viele Delikte trägt jede Stadt bei?",
                  nenner=_ZAEHLUNG,
                  ausschluesse=(ohne_wert(_E_STADT), im_zeitfenster()),
                  vorbehalte=(_TATEBENE, _ERST_DIE_RATE),
                  breite=36, hoehe=8),
            Tafel("verlauf", "Verlauf je Monat, getrennt nach Stadt", "balken",
                  _GESAMT,
                  eimer=(_E_MONAT, _E_STADT),
                  frage="Wie verteilen sich die Delikte über die Monate?",
                  nenner=_ZAEHLUNG,
                  ausschluesse=(ohne_wert(_E_MONAT), ohne_wert(_E_STADT),
                                im_zeitfenster()),
                  vorbehalte=(_TATEBENE, _ERST_DIE_RATE, _TEILJAHR),
                  breite=48, hoehe=15),
            Tafel("familien", "Anteil nach Deliktfamilie", "ring", _GESAMT,
                  eimer=(_E_FAMILIE_8,),
                  frage="Wie teilen sich die Delikte auf die NIBRS-Familien "
                        "auf?",
                  nenner=(f"die Delikte der {_E_FAMILIE_8.groesse} "
                          f"häufigsten NIBRS-Familien — der Ring rechnet "
                          f"seine Anteile über das, was er zeigt, nicht über "
                          f"alle Delikte"),
                  ausschluesse=(ohne_wert(_E_FAMILIE_8), im_zeitfenster()),
                  vorbehalte=(_TATEBENE,),
                  breite=24, hoehe=15),
            Tafel("delikte", "Häufigste Delikte", "tabelle", _GESAMT,
                  eimer=(_E_CODE_15, _E_STADT),
                  frage="Welche NIBRS-Codes kommen am häufigsten vor?",
                  nenner=_ZAEHLUNG,
                  ausschluesse=(ohne_wert(_E_CODE_15), ohne_wert(_E_STADT),
                                im_zeitfenster()),
                  vorbehalte=(_TATEBENE, _ERST_DIE_RATE),
                  breite=24, hoehe=15),
        ),
        navigation=True,
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
                  frage="Wie viele Delikte liegen im gewählten Zeitraum vor?",
                  nenner=_ZAEHLUNG,
                  ausschluesse=(im_zeitfenster(),),
                  vorbehalte=(_TATEBENE, _ERST_DIE_RATE),
                  breite=16, hoehe=8),
            Tafel("verortet", "Verschiedene Tracts", "zahl",
                  Kennzahl("tracts", "Tracts", "unique_count", "tract_geoid"),
                  frage="In wie vielen verschiedenen Census Tracts liegen "
                        "Delikte?",
                  nenner=_ZAEHLUNG,
                  ausschluesse=(
                      Ausschluss("Delikte ohne Tract (`tract_geoid` leer) — "
                                 "ohne Koordinate oder ausserhalb jedes "
                                 "Tracts; sie haben keinen, den man zählen "
                                 "könnte",
                                 "unique_count(tract_geoid)"),
                      im_zeitfenster()),
                  vorbehalte=(_ERST_DIE_RATE,),
                  breite=16, hoehe=8),
            Tafel("codes", "Verschiedene Quellcodes", "zahl",
                  Kennzahl("codes", "Codes", "unique_count",
                           "source_offense_code"),
                  frage="Wie viele verschiedene Deliktcodes der Quellen "
                        "kommen vor?",
                  nenner=_ZAEHLUNG,
                  ausschluesse=(
                      Ausschluss("Delikte ohne Quellcode "
                                 "(`source_offense_code` leer)",
                                 "unique_count(source_offense_code)"),
                      im_zeitfenster()),
                  vorbehalte=(_ERST_DIE_RATE,),
                  breite=16, hoehe=8),
            Tafel("zuordnung", "Zuordnung auf NIBRS, je Stadt", "balken",
                  _GESAMT,
                  eimer=(_E_ZUORDNUNG, _E_STADT),
                  frage="Wie viele Delikte sind wie sicher auf NIBRS "
                        "zugeordnet?",
                  nenner=_ZAEHLUNG,
                  ausschluesse=(
                      ohne_wert(_E_ZUORDNUNG),
                      ohne_wert(_E_STADT), im_zeitfenster()),
                  vorbehalte=(_TATEBENE, _ERST_DIE_RATE),
                  breite=24, hoehe=15),
            Tafel("verortung", "Verortung, je Stadt", "balken", _GESAMT,
                  eimer=(_E_VERORTUNG, _E_STADT),
                  frage="Wie viele Delikte liegen in einem Tract der Stadt, "
                        "und wie viele nicht?",
                  nenner=_ZAEHLUNG,
                  ausschluesse=(
                      ohne_wert(_E_VERORTUNG),
                      ohne_wert(_E_STADT), im_zeitfenster()),
                  vorbehalte=(_TATEBENE, _ERST_DIE_RATE),
                  breite=24, hoehe=15),
        ),
        navigation=True,
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
            Tafel("gesamt", "Treffer", "zahl", _GESAMT,
                  frage="Wie viele Delikte lässt die Suche oben übrig?",
                  nenner=_ZAEHLUNG,
                  ausschluesse=(im_zeitfenster(),),
                  # Kein Ausschluss, sondern der Zweck des Bretts: Die
                  # Suchleiste steht am Brett, nicht in der Kachel, und hat
                  # deshalb hier keinen Beleg.
                  vorbehalte=("Die Zahl folgt der Suchleiste oben — ohne "
                              "Suche ist es jedes Delikt im Zeitraum",
                              _TATEBENE, _ERST_DIE_RATE),
                  breite=12, hoehe=8),
            Tafel("stunde", "Nach Tagesstunde", "balken", _GESAMT,
                  eimer=(_E_STUNDE,),
                  frage="Zu welcher lokalen Tagesstunde liegen die Treffer?",
                  nenner=_ZAEHLUNG,
                  ausschluesse=(ohne_wert(_E_STUNDE), im_zeitfenster()),
                  vorbehalte=(_ORTSZEIT, _TATEBENE, _ERST_DIE_RATE),
                  breite=36, hoehe=8),
            Tafel("beschreibungen", "Beschreibungen der Quelle", "tabelle",
                  _GESAMT,
                  eimer=(_E_TEXT, _E_STADT),
                  frage="Welche Beschreibungen der Quellen treffen am "
                        "häufigsten?",
                  nenner=_ZAEHLUNG,
                  ausschluesse=(ohne_wert(_E_TEXT), ohne_wert(_E_STADT),
                                im_zeitfenster()),
                  vorbehalte=(_BESCHREIBUNG_NICHT_DELIKT, _TATEBENE,
                              _ERST_DIE_RATE),
                  breite=48, hoehe=20),
        ),
        navigation=True,
    ),
    Brett(
        kennung="crime-raten",
        titel="Raten je 1'000 — die zentrale Zahl",
        beschreibung=(
            f"Die Zahl, um die es in diesem Projekt geht, für den Jahrgang "
            f"{RATENJAHR}: Detroit liegt je Einwohner vorn, Chicago absolut. "
            "Gerechnet wird in der Kachel selbst, über ES|QL und "
            f"`LOOKUP JOIN` auf `{_NENNER}` — nicht in einer vorberechneten "
            "Tabelle. **Fallebene vorn, Tatebene daneben** (Entscheid E5 vom "
            "5.10.2026): Beide sind richtig, es sind verschiedene Fragen. "
            "Der Hinweis auf die Abgabedokumente steht auf der Kachel, auf "
            "der die Zahl steht."),
        tafeln=(
            Tafel("je_stadt", f"Rate je 1'000 Einwohner, {RATENJAHR}",
                  "esql_tabelle", abfrage=RATE_JE_STADT,
                  frage=("Wie viele Fälle und Taten kommen je 1'000 "
                         "Einwohner auf eine Stadt?"),
                  nenner=_NENNERTEXT,
                  # **Ohne** den Tract-Ausschluss: Diese Abfrage filtert
                  # ``population > 0`` nicht, sie zaehlt die Taten in
                  # unbewohnten Tracts im Zaehler mit - ebenso wie
                  # ``gold_pipeline.raten_je_stadt``, und nur deshalb ist
                  # der Brueckenwaechter gruen. Die Zahl ist richtig; falsch
                  # waere, hier etwas anderes zu behaupten.
                  ausschluesse=(_AUSSERHALB, _ANDERE_JAHRGAENGE),
                  vorbehalte=(_FALLEBENE_VORN,),
                  jahr=RATENJAHR, breite=48, hoehe=8),
            Tafel("je_tract",
                  f"Die zwanzig höchsten Raten je Tract, {RATENJAHR}",
                  "esql_tabelle", abfrage=RATE_JE_TRACT,
                  frage=("In welchen Census Tracts ist die Rate am "
                         "höchsten?"),
                  nenner=_NENNERTEXT,
                  # Hier **mit** dem Tract-Ausschluss: Diese Abfrage traegt
                  # ``population > 0``, weil eine Rate je Tract ohne
                  # Einwohner nicht definiert waere.
                  ausschluesse=(_AUSSERHALB, _ANDERE_JAHRGAENGE,
                                _OHNE_EINWOHNER),
                  vorbehalte=(_TATORT_NICHT_WOHNORT, _FALLEBENE_VORN),
                  jahr=RATENJAHR, breite=48, hoehe=24),
            Tafel("ohne_einwohner",
                  f"Tracts ohne Einwohner — ohne Rate, {RATENJAHR}",
                  "esql_tabelle", abfrage=TRACTS_OHNE_EINWOHNER,
                  frage=("Wie viele Taten liegen in Tracts, für die keine "
                         "Rate definiert ist?"),
                  nenner=(f"{_ZAEHLUNG} — ein Nenner wäre hier null, und "
                          f"genau deshalb fehlt diesen Tracts die Rate"),
                  ausschluesse=(_AUSSERHALB, _ANDERE_JAHRGAENGE,
                                _MIT_EINWOHNERN),
                  vorbehalte=(_ERST_DIE_RATE,),
                  jahr=RATENJAHR, breite=48, hoehe=8),
        ),
        navigation=True,
    ),

    # ----------------------------------------------------------------
    # Die drei Themen aus Artans Entwurf, die es noch nicht gab.
    # ----------------------------------------------------------------

    Brett(
        kennung="crime-zeitverlauf",
        titel="Zeitverlauf — wann es passiert",
        beschreibung=(
            "Saisonale Muster und die Tagesstunde. Gezählt werden **Fälle**, "
            "nicht Taten: Chicago erfasst je Fall nur das schwerste Delikt, "
            "Detroit jedes — ein Vergleich auf Tatebene misst diesen "
            "Unterschied mit."),
        tafeln=(
            # Bis zum 17.11.2026 zaehlte diese Kachel trotz ihres Titels jede
            # Zeile von ``fact_offense``, also Taten; der Lens-Zustand trug
            # ``"query": ""``. Seither filtert sie ``counts_case``.
            Tafel("verlauf", "Fälle je Monat, getrennt nach Stadt", "linie",
                  _FAELLE,
                  eimer=(_E_MONAT, _E_STADT),
                  frage="Wie verteilen sich die Fälle über die Monate?",
                  nenner=_ZAEHLUNG,
                  filter=_NUR_FAELLE_FILTER,
                  ausschluesse=(_WEITERE_DELIKTE_DES_FALLS,
                                ohne_wert(_E_MONAT, "Fälle"),
                                ohne_wert(_E_STADT, "Fälle"),
                                im_zeitfenster("Fälle")),
                  vorbehalte=(_TEILJAHR, _NACH_MELDESTADT, _ERST_DIE_RATE),
                  breite=48, hoehe=15),
            Tafel("woche_stunde", "Wochentag × lokale Tagesstunde",
                  "esql_heatmap", abfrage=HEATMAP_WOCHE_STUNDE,
                  frage=("Zu welcher Stunde welchen Wochentags passieren "
                         "Fälle?"),
                  nenner=(f"{_ZAEHLUNG}, über beide Städte zusammen — die "
                          f"Heatmap vergleicht Stunden, nicht Städte"),
                  ausschluesse=(_NUR_FAELLE,),
                  vorbehalte=(_ORTSZEIT, _PLATZHALTERSTUNDEN, _TEILJAHR,
                              _ERST_DIE_RATE),
                  breite=48, hoehe=20),
            Tafel("je_jahr", "Fälle je Jahrgang und Stadt", "balken", _FAELLE,
                  eimer=(_E_JAHR, _E_STADT),
                  frage="Wie viele Fälle trägt jeder Jahrgang je Stadt?",
                  nenner=_ZAEHLUNG,
                  filter=_NUR_FAELLE_FILTER,
                  ausschluesse=(_WEITERE_DELIKTE_DES_FALLS,
                                ohne_wert(_E_JAHR, "Fälle"),
                                ohne_wert(_E_STADT, "Fälle"),
                                im_zeitfenster("Fälle")),
                  vorbehalte=(_NACH_MELDESTADT, _JAHRGANG_LOKAL, _TEILJAHR,
                              _ERST_DIE_RATE),
                  breite=48, hoehe=15),
        ),
        steuerungen=_STEUERUNG,
        navigation=True,
    ),

    Brett(
        kennung="crime-geografie",
        titel="Geografie — wo die Rate höher liegt",
        beschreibung=(
            "Die Karte färbt nach der **Rate je 1'000 Einwohner**, nicht nach "
            "Fallzahlen, für den Jahrgang "
            f"{RATENJAHR}. Der Grund ist gemessen: Die Einwohnerzahl je Tract "
            "reicht von 35 bis 13'521 — eine Karte nach Fallzahlen zeigte vor "
            "allem, wo viele Menschen wohnen."),
        tafeln=(
            # Je Stadt eine Karte, nebeneinander - wie im Entwurf. Eine
            # gemeinsame zeigte zwei Flecken von je 50 Pixeln; die
            # Begruendung samt Messung steht an ``KARTE_JE_STADT``.
            # Die Staedte kommen aus ``STADT_SCHLUESSEL``, nicht aus
            # ``KARTE_JE_STADT``: sonst bekaeme eine dritte Stadt ohne
            # Ausschnitt still keine Karte, statt dass ihre Tafel abbricht
            # und sie nennt (FR-43).
            *(Tafel(f"karte_{stadt}",
                    f"{stadt.capitalize()} — Fälle je 1'000 Einwohner "
                    f"je Tract, {RATENJAHR}",
                    "karte", stadt=stadt,
                    frage=(f"In welchen Tracts {stadt.capitalize()}s liegt "
                           f"die Rate höher?"),
                    nenner=_NENNERTEXT,
                    ausschluesse=(_AUSSERHALB, _ANDERE_JAHRGAENGE,
                                  _OHNE_EINWOHNER),
                    vorbehalte=(_TATORT_NICHT_WOHNORT, _FALLEBENE_VORN,
                                _KLEINE_NENNER, _RATE_UEBER_ALLE_DELIKTE),
                    jahr=RATENJAHR, breite=24, hoehe=24)
              for stadt in sorted(STADT_SCHLUESSEL.values())),
            Tafel("hoechste", f"Die zwanzig höchsten Raten, {RATENJAHR}",
                  "esql_tabelle", abfrage=RATE_JE_TRACT,
                  frage=("Welche Tracts tragen die höchsten Raten — und mit "
                         "wie vielen Einwohnern?"),
                  nenner=_NENNERTEXT,
                  ausschluesse=(_AUSSERHALB, _ANDERE_JAHRGAENGE,
                                _OHNE_EINWOHNER),
                  vorbehalte=(_TATORT_NICHT_WOHNORT, _FALLEBENE_VORN,
                              _KLEINE_NENNER),
                  jahr=RATENJAHR, breite=48, hoehe=20),
        ),
        # **Kein Auswahlfeld auf diesem Brett.** Die Rate je Tract ist ueber
        # alle Delikte vorgerechnet; weder ``dim_tract_geo`` noch
        # ``rate_tract`` kennt eine Deliktfamilie. Ein Feld, das dasteht und
        # nichts bewirkt, ist schlimmer als keines - es sagt dem Lesenden,
        # die Karte zeige eine Auswahl, die sie nicht zeigt.
        steuerungen=(),
        navigation=True,
    ),

    Brett(
        kennung="crime-deliktstruktur",
        titel="Deliktstruktur — was sich unterscheidet",
        beschreibung=(
            "Zwei Fragen nebeneinander, weil eine Kachel immer nur eine "
            "beantwortet: **wie viel** es ist (Zahlen) und **wie es sich "
            "aufteilt** (Anteile). Detroit hat weniger Delikte und eine "
            "andere Mischung."),
        tafeln=(
            # Die Faelle-Kachel filtert ``counts_case`` (Entscheid vom
            # 17.11.2026); bis dahin zaehlte sie Taten.
            Tafel("je_familie", "Fälle je Deliktfamilie und Stadt", "balken",
                  _FAELLE,
                  eimer=(_E_FAMILIE_10, _E_STADT),
                  frage="Wie viele Fälle trägt jede NIBRS-Familie je Stadt?",
                  nenner=_ZAEHLUNG,
                  filter=_NUR_FAELLE_FILTER,
                  ausschluesse=(_WEITERE_DELIKTE_DES_FALLS,
                                ohne_wert(_E_FAMILIE_10, "Fälle"),
                                ohne_wert(_E_STADT, "Fälle"),
                                im_zeitfenster("Fälle")),
                  vorbehalte=(_FAMILIE_DES_SCHWERSTEN, _NACH_MELDESTADT,
                              _ERST_DIE_RATE),
                  breite=24, hoehe=20),
            # Auf der Tatebene, wie E5 es fuer Anteile je Deliktart verlangt:
            # Nur dort addieren sich Kategorien (Entscheid Christian,
            # 17.11.2026, im Plan nachverhandelt).
            Tafel("anteil", "Anteil je Stadt — auf 100 % gestapelt",
                  "anteilsbalken", _GESAMT,
                  eimer=(_E_STADT, _E_FAMILIE_10),
                  frage="Wie teilen sich die Delikte einer Stadt auf die "
                        "NIBRS-Familien auf?",
                  nenner=(f"die Delikte einer Stadt in ihren "
                          f"{_E_FAMILIE_10.groesse} häufigsten NIBRS-Familien "
                          f"— jede Säule ist 100 % ihrer Stadt"),
                  ausschluesse=(ohne_wert(_E_STADT),
                                ohne_wert(_E_FAMILIE_10),
                                im_zeitfenster()),
                  vorbehalte=(_ANTEIL_TATEBENE, _NACH_MELDESTADT_TATEN),
                  breite=24, hoehe=20),
            # Bleibt auf der Tatebene: Ein Code ist ein Delikt, und "welche
            # Delikte kommen vor" zaehlt jedes.
            Tafel("codes", "Die häufigsten NIBRS-Codes je Stadt (alle Delikte)",
                  "tabelle", _GESAMT,
                  eimer=(_E_CODE_20, _E_STADT),
                  frage="Welche NIBRS-Codes kommen in jeder Stadt am "
                        "häufigsten vor?",
                  nenner=_ZAEHLUNG,
                  ausschluesse=(ohne_wert(_E_CODE_20), ohne_wert(_E_STADT),
                                im_zeitfenster()),
                  vorbehalte=(_TATEBENE, _ERST_DIE_RATE),
                  breite=48, hoehe=20),
        ),
        steuerungen=_STEUERUNG,
        navigation=True,
    ),
)


# --------------------------------------------------------------------------
# Die erzeugten Objekte. Reine Funktionen - pruefbar ohne Kibana.
# --------------------------------------------------------------------------


def datenansicht(index: str = "fact_offense",
                 zeitfeld: str | None = ZEITFELD,
                 kennung: str = ANSICHT) -> dict[str, Any]:
    """Die Datenansicht - auf den **Alias**, nicht auf einen Release-Index.

    Damit zeigen die Dashboards nach jedem Ladelauf auf den neuen Stand,
    ohne dass hier etwas angefasst werden muss. Genau dafuer gibt es den
    Alias in ``load_elasticsearch``.
    """
    merkmale: dict[str, Any] = {"title": index}
    # Ohne Zeitfeld und nicht mit leerem: ``dim_tract_geo`` und
    # ``rate_tract`` tragen keines, und eine Ansicht, die trotzdem eines
    # nennt, filtert unter dem festen Zeitfenster des Bretts **alles** weg -
    # die Karte bliebe leer, ohne Fehlermeldung.
    if zeitfeld:
        merkmale["timeFieldName"] = zeitfeld
    return {"type": "index-pattern", "id": kennung,
            "attributes": merkmale, "references": []}


def pruefe_tafel(tafel: Tafel) -> None:
    """Zeigt jeder Verweis der Darstellung auf eine Spalte, die es gibt?

    Kibana prueft das nicht. Ein Verweis ins Leere importiert sauber und
    faellt erst auf, wenn jemand das Dashboard oeffnet und eine leere Kachel
    sieht - moeglicherweise in der Praesentation.
    """
    if tafel.ist_karte:
        # Eine Karte hat keine Lens-Spalten; ihre eigene Pruefung steht in
        # ``karte_objekt`` (Verbundfeld, Geofeld, beide Datenansichten).
        return
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

    **Zwei Datenquellen, ein Objekt.** Eine Lens-Tafel haengt unter
    ``formBased`` und bekommt ihre Abfrage von Kibana gebaut; eine
    ES|QL-Tafel haengt unter ``textBased`` und bringt sie mit. Beide gehen
    ueber **denselben** ``_bulk_create`` - nachgewiesen gegen Kibana 8.19.22,
    es braucht keinen zweiten Weg. Der Verweisname ist ein anderer, weil Lens
    die beiden Datenquellen verschieden benennt
    (``textBasedLanguages-datasource-layer-…``).
    """
    pruefe_tafel(tafel)
    if tafel.ist_esql:
        assert tafel.abfrage is not None
        zustand: dict[str, Any] = {
            "datasourceStates": {"textBased": {"layers": {tafel.schicht: {
                # Die Datenansicht zum Zeitfeld, nicht zum Lesen: ES|QL
                # nennt den Index in der Abfrage selbst.
                "index": ANSICHT,
                "query": {"esql": tafel.abfrage.esql},
                "columns": list(tafel.spalten.values()),
                "timeField": ZEITFELD}}}},
            "filters": [],
            # Dieselbe Abfrage noch einmal, und das ist nicht doppelt
            # gemoppelt: Lens liest sie aus der Schicht, die Abfragezeile
            # oben im Editor aus ``state.query``. Stehen dort zwei
            # verschiedene, zeigt die Kachel die eine und der Editor die
            # andere.
            "query": {"esql": tafel.abfrage.esql},
            "visualization": tafel.darstellung,
        }
        verweisname = f"textBasedLanguages-datasource-layer-{tafel.schicht}"
    else:
        zustand = {
            "datasourceStates": {"formBased": {"layers": {tafel.schicht: {
                "columns": tafel.spalten,
                "columnOrder": tafel.reihenfolge,
                "incompleteColumns": {}}}}},
            "filters": [],
            # Der Filter der Kachel, im Lens-Zustand und nicht als
            # Panel-Filter am Brett: Dort ginge er verloren, sobald jemand
            # die Kachel im Editor oeffnet oder ihre Art umschaltet - und die
            # Kachel "Faelle" zaehlte wieder Taten.
            "query": {"language": "kuery", "query": tafel.filter},
            "visualization": tafel.darstellung,
        }
        verweisname = f"indexpattern-datasource-layer-{tafel.schicht}"

    merkmale: dict[str, Any] = {
        "title": tafel.titel,
        "visualizationType": ARTEN[tafel.art],
        "state": zustand,
    }
    # Frage, Nenner, Jahr und Ausschluesse - dort, wo Kibana sie neben der
    # Zahl zeigt. Seit dem 17.11.2026 traegt jede Kachel sie
    # (``Tafel._pruefe_fr27``); das Feld ist also nie leer.
    merkmale["description"] = tafel.erlaeuterung

    return {
        "type": "lens", "id": f"lens-{brett}-{tafel.kennung}",
        "attributes": merkmale,
        "references": [{
            "type": "index-pattern", "id": ANSICHT, "name": verweisname}],
    }


#: Der Index mit den Umrissen - gelesen, nicht getippt. Das Geofeld steht
#: dort, wo es entschieden wurde (``Index.flaeche``); ein zweiter Name hier
#: liesse sich auseinanderlaufen, und die Karte faerbte nichts.
FLAECHEN_INDEX = NACH_NAME["dim_tract_geo"]
RATEN_INDEX = NACH_NAME["rate_tract"]


#: Welche Spalte die Karte einfaerbt, und wie sie aus ``rate_tract`` kommt.
#:
#: ``max`` und nicht ``avg``: ``rate_tract`` haelt **eine** Zeile je Tract,
#: beide liefern also denselben Wert. ``max`` sagt aber zusaetzlich, dass
#: nichts gemittelt wird - ein Mittel ueber Raten waere falsch, sobald die
#: Tabelle je Tract mehr als eine Zeile traegt, und dann faerbte die Karte
#: still etwas anderes.
KARTE_MASS = "max"
KARTE_FELD = "rate_fallebene"

#: Der Stamm der Verbundkennung. **Je Karte wird er verlaengert** - siehe
#: ``verbund_kennung``.
KARTE_VERBUND = "rate-je-tract"


def verbund_kennung(tafel: Tafel) -> str:
    """Die Kennung der rechten Verbundseite - **je Karte eine eigene**.

    Am 14.10.2026 trugen beide Karten des Bretts dieselbe (``rate-je-tract``),
    und Kibana zeigte unter der Beschriftung *Chicago* die Flaechen von
    Detroit: Zwei Karten auf einem Brett, die sich eine Verbundkennung
    teilen, teilen sich auch die Verbunddaten, und die zuletzt geladene
    gewinnt. Gespeichert war beides richtig - Mittelpunkte, Titel und
    Schichtkennungen waren verschieden -, nur diese eine Kennung nicht.

    Dieselbe Falle wie bei den Lens-Objekten, wo der Brettname seit jeher in
    der Kennung steht: *„Ohne den Brettnamen bekaemen sie dieselbe Kennung,
    und das letzte Anlegen ueberschriebe die anderen."*
    """
    return f"{KARTE_VERBUND}-{tafel.kennung}"


def verbundfeld(verbund: str, mass: str = KARTE_MASS,
                feld: str = KARTE_FELD) -> str:
    """Wie Kibana das verbundene Feld nennt.

    Gerechnet und nicht getippt: Der Name entsteht aus Mass, Feld und der
    Kennung der rechten Seite. Stuende er hier als Literal, liesse sich eines
    der drei aendern, ohne dass der Name mitzieht - und die Karte faerbte
    nach einem Feld, das es nicht gibt. Kibana meldet das nicht; die
    Flaechen bleiben einfach grau.
    """
    return f"__kbnjoin__{mass}_of_{feld}__{verbund}"


def karte_objekt(tafel: Tafel, brett: str) -> dict[str, Any]:
    """Die Choroplethenkarte: Umrisse aus dem einen Index, Rate aus dem anderen.

    **Warum ein Verbund und keine einzelne Quelle.** Kibana faerbt eine
    Flaeche nach **einem** Feld und kann zwischen zwei verbundenen Feldern
    nicht rechnen. Die Umrisse stehen in ``dim_tract_geo``, die fertige Rate
    in ``serving/rate_tract``; verbunden werden sie ueber ``geoid``.

    **Warum nicht nach Fallzahlen.** Das waere die irrefuehrende Karte, gegen
    die dieses Projekt sonst ueberall argumentiert: Die Einwohnerzahl je
    Tract reicht von 35 bis 13'521 (2024, Median 2'861) - Faktor 386 zwischen
    dem kleinsten und dem groessten Tract.

    **``applyGlobalTime`` steht auf ``false``, und das ist kein Detail.**
    Keiner der beiden Indizes traegt ein Zeitfeld; das feste Zeitfenster des
    Bretts wuerde jede Flaeche wegfiltern, und die Karte waere leer - ohne
    Fehlermeldung.
    """
    if not tafel.ist_karte:
        raise LadeFehler(f"{tafel.kennung}: keine Karte.")

    ausschnitt = KARTE_JE_STADT[tafel.stadt]
    # Die Hintergrundkarte - **ausdruecklich mitgegeben und nicht erwartet**.
    # Eine Karte, die in Kibanas Oberflaeche entsteht, bekommt sie
    # dazugelegt; eine ueber die Schnittstelle angelegte nimmt genau die
    # Schichten, die dastehen. Am 15.10.2026 fehlte sie deshalb, und ohne
    # sie schwebt eine Choroplethe im Weissen: Keine Strasse, kein Seeufer,
    # nichts, woran sich die Flaechen verorten liessen.
    #
    # ``isAutoSelect`` laesst Kibana den passenden Stil waehlen (hell oder
    # dunkel). Die Kacheln kommen vom Elastic Maps Service - ohne Netz
    # bleibt der Hintergrund leer, die Flaechen zeichnen trotzdem.
    hintergrund = {
        "id": "hintergrund",
        "label": None,
        "sourceDescriptor": {"type": "EMS_TMS", "isAutoSelect": True,
                             "lightModeDefault": "road_map_desaturated"},
        "type": "EMS_VECTOR_TILE",
        "minZoom": 0, "maxZoom": 24, "alpha": 1,
        "visible": True,
        "style": {"type": "TILE"},
    }
    quelle = "layer_1_source_index_pattern"
    verbund = "layer_1_join_0_index_pattern"
    schicht = {
        "id": f"schicht-{tafel.kennung}",
        "label": tafel.titel,
        # **Nur die Flaechen dieser Stadt.** Der Ausschnitt allein genuegt
        # nicht: Ohne Hintergrundkarte sieht man nur die Flaechen, und wenn
        # jede Karte alle 1'055 traegt, zeigen beide dasselbe, sobald der
        # Ausschnitt nicht greift - genau so stand am 15.10.2026 zweimal
        # Detroit unter zwei Beschriftungen.
        #
        # Der Filter war am 14.10. schon einmal hier und wurde entfernt,
        # weil die Karte danach leer blieb. Diese Beobachtung stammte aus
        # einem 240 Pixel breiten Browserfenster, in dem der Kartenbehaelter
        # die Hoehe null hat und **keine** Karte zeichnet. Sie bewies nichts.
        "query": {"language": "kuery", "query": f'city: "{tafel.stadt}"'},
        "sourceDescriptor": {
            "type": "ES_SEARCH",
            "id": f"umrisse-{tafel.kennung}",
            "indexPatternRefName": quelle,
            # Das Geofeld steht nicht hier getippt, sondern dort, wo es
            # entschieden wurde: am Index (``Index.flaeche``). Zwei Namen
            # liessen sich auseinanderlaufen.
            "geoField": FLAECHEN_INDEX.flaeche,
            "scalingType": "LIMIT",
            "filterByMapBounds": False,
            "tooltipProperties": ["tract_name", "city"],
            "sortField": "", "sortOrder": "desc",
            # **Nicht an der globalen Abfrage.** Weder dieser Index noch
            # der des Verbunds traegt eine Deliktfamilie oder eine
            # Tatzeit; ein Filter darauf ergaebe null Flaechen, und die
            # Karte waere leer statt unveraendert - ohne Fehlermeldung.
            # Was die Kachel zeigt, steht in ihrem Vorbehalt.
            "applyGlobalQuery": False,
            "applyGlobalTime": False,
            "applyForceRefresh": True,
        },
        "joins": [{
            "leftField": "geoid",
            "right": {
                "type": "ES_TERM_SOURCE",
                "id": verbund_kennung(tafel),
                "indexPatternRefName": verbund,
                "term": "geoid",
                "metrics": [{"type": KARTE_MASS, "field": KARTE_FELD,
                             "label": tafel.titel}],
                "applyGlobalQuery": False,
                "applyGlobalTime": False,
                "applyForceRefresh": True,
            },
        }],
        "style": {
            "type": "VECTOR",
            "properties": {
                "fillColor": {
                    "type": "DYNAMIC",
                    "options": {
                        "field": {"name": verbundfeld(verbund_kennung(tafel)),
                                  "origin": "join"},
                        "color": "Blues",
                        "type": "ORDINAL",
                        "fieldMetaOptions": {"isEnabled": True, "sigma": 3},
                    },
                },
                "lineColor": {"type": "STATIC", "options": {"color": "#3d3d3d"}},
                "lineWidth": {"type": "STATIC", "options": {"size": 0.5}},
            },
            "isTimeAware": False,
        },
        "type": "GEOJSON_VECTOR",
        "visible": True,
        "alpha": 0.75,
    }

    zustand = {
        # Der Ausschnitt ist der der einen Stadt dieser Karte
        # (``KARTE_JE_STADT``, dort die gemessenen Grenzen der Umrisse).
        #
        # **``autoFitToDataBounds`` waere das Naheliegende und ist falsch.**
        # Am 14.10.2026 im Browser gemessen: Damit zoomt Kibana so weit
        # hinaus, dass beide Staedte nur noch zwei Flecken sind. Ein fester,
        # gerechneter Ausschnitt ist hier besser als eine Automatik, die das
        # Falsche tut.
        "zoom": ausschnitt["zoom"],
        "center": {"lon": ausschnitt["lon"], "lat": ausschnitt["lat"]},
        "timeFilters": {"from": "now-15m", "to": "now"},
        "refreshConfig": {"isPaused": True, "interval": 0},
        "query": {"language": "kuery", "query": ""},
        "filters": [],
        "settings": {"autoFitToDataBounds": False},
    }

    return {
        "type": "map", "id": f"karte-{brett}-{tafel.kennung}",
        "attributes": {
            "title": tafel.titel,
            "description": tafel.erlaeuterung,
            # Hintergrund zuerst: Die Reihenfolge ist die Zeichenreihenfolge,
            # und eine Hintergrundkarte ueber den Flaechen deckte sie zu.
            "layerListJSON": json.dumps([hintergrund, schicht],
                                        ensure_ascii=False),
            "mapStateJSON": json.dumps(zustand),
            # Die Ebenenliste zugeklappt: Auf einem Dashboard mit **einer**
            # Ebene verdeckt sie ein Viertel der Karte und bietet nichts an,
            # was man dort entscheiden muesste.
            "uiStateJSON": json.dumps(
                {"isLayerTOCOpen": False, "openTOCDetails": []}),
        },
        "references": [
            {"type": "index-pattern", "id": ANSICHT_FLAECHEN, "name": quelle},
            {"type": "index-pattern", "id": ANSICHT_RATEN, "name": verbund},
        ],
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
    # Die Navigation liegt oben und ueber die volle Breite - sie ist die
    # Reiterleiste des Entwurfs, so weit Kibana sie zulaesst.
    if brett.navigation:
        tafeln.append({
            "version": FASSUNG, "type": "links",
            "gridData": {"x": 0, "y": 0, "w": RASTER, "h": 4,
                         "i": NAVIGATION_PANEL},
            "panelIndex": NAVIGATION_PANEL,
            "embeddableConfig": {"enhancements": {}},
            "panelRefName": f"panel_{NAVIGATION_PANEL}",
        })
        verweise.append({
            "name": f"{NAVIGATION_PANEL}:panel_{NAVIGATION_PANEL}",
            "type": "links", "id": NAVIGATION})
    versatz = 4 if brett.navigation else 0
    for tafel, platz in zip(brett.tafeln, raster(brett.tafeln)):
        platz = {**platz, "y": platz["y"] + versatz}
        nummer = f"p-{tafel.kennung}"
        objekt = (karte_objekt(tafel, brett.kennung) if tafel.ist_karte
                  else lens_objekt(tafel, brett.kennung))
        art = objekt["type"]
        einstellungen: dict[str, Any] = {"enhancements": {}}
        if tafel.ist_karte:
            # Kibana liest auf einem Brett **nur** das hier und nicht den
            # Ausschnitt im Kartenobjekt - ohne diese Zeilen oeffnet die
            # Karte irgendwo. Die Ebenenliste bleibt zugeklappt: Bei einer
            # Ebene verdeckt sie ein Viertel der Karte und bietet nichts an.
            einstellungen |= {
                "mapCenter": dict(KARTE_JE_STADT[tafel.stadt]),
                "isLayerTOCOpen": False,
                "openTOCDetails": [],
                "hiddenLayers": [],
                # **Keine gemeinsame Bewegung.** Kibana bewegt mehrere
                # Karten eines Bretts vorgabemaessig im Gleichschritt - das
                # ist richtig fuer zwei Blickwinkel auf dieselbe Gegend und
                # falsch fuer zwei Staedte: Wer Chicago zurechtrueckt,
                # schiebt Detroit aus dem Bild. Am 15.10.2026 im Browser
                # gesehen.
                "isMovementSynchronized": False,
            }
        tafeln.append({
            "version": FASSUNG, "type": art,
            "gridData": {**platz, "i": nummer}, "panelIndex": nummer,
            "embeddableConfig": einstellungen,
            "panelRefName": f"panel_{nummer}", "title": tafel.titel,
        })
        verweise.append({"name": f"{nummer}:panel_{nummer}", "type": art,
                         "id": objekt["id"]})

    merkmale: dict[str, Any] = {
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
    }

    if brett.steuerungen:
        merkmale["controlGroupInput"] = {
            # HIERARCHICAL: Die zweite Auswahl zeigt nur noch, was zur ersten
            # passt. Waehlt jemand Detroit, bietet "Kategorie" keine
            # Deliktart an, die es dort nicht gibt - eine leere Kachel nach
            # zwei Klicks waere sonst der Normalfall.
            "chainingSystem": "HIERARCHICAL",
            "controlStyle": "oneLine",
            # Sofort filtern statt auf einen Knopf zu warten: Bei zwei
            # Feldern ist ein Bestaetigen mehr Weg als Nutzen.
            "showApplySelections": False,
            "ignoreParentSettingsJSON": json.dumps(
                {"ignoreFilters": False, "ignoreQuery": False,
                 "ignoreTimerange": False, "ignoreValidations": False}),
            "panelsJSON": json.dumps(
                {s.kennung: {**s.panel, "order": i}
                 for i, s in enumerate(brett.steuerungen)},
                ensure_ascii=False),
        }
        verweise.extend(
            {"name": s.verweisname, "type": "index-pattern", "id": ANSICHT}
            for s in brett.steuerungen)

    return {
        "type": "dashboard", "id": brett.kennung,
        "attributes": merkmale,
        "references": verweise,
    }


def navigation_objekt(bretter: tuple[Brett, ...]) -> dict[str, Any]:
    """Die Reiterleiste, so weit Kibana sie kann.

    Ein ``links``-Objekt mit einem Eintrag je Brett, waagerecht, als Kachel
    oben auf jedem Brett. Es ersetzt die Kopfleiste des Entwurfs nicht - es
    nimmt ihr aber den Zweck ab, naemlich mit einem Klick auf dem naechsten
    Thema zu sein statt ueber die Dashboard-Liste.

    **Einmal angelegt, von allen verwiesen.** Je Brett ein eigenes Objekt
    haette dieselbe Liste fuenfmal gefuehrt; wer ein Brett umbenennt, haette
    vier Stellen zu pflegen und drei davon vergessen.
    """
    eintraege, verweise = [], []
    for nummer, brett in enumerate(bretter):
        kennung = f"link-{brett.kennung}"
        ziel = f"{kennung}_dashboard"
        eintraege.append({
            "id": kennung, "type": "dashboardLink", "order": nummer,
            "destinationRefName": ziel,
            # Der Titel des Bretts, nicht ein zweiter daneben: Sonst heisst
            # der Reiter anders als die Seite, auf der man landet.
            "label": brett.titel.split(" — ")[0],
        })
        verweise.append({"name": ziel, "type": "dashboard",
                         "id": brett.kennung})
    return {
        "type": "links", "id": NAVIGATION,
        "attributes": {"title": NAVIGATION_TITEL, "links": eintraege,
                       "layout": "horizontal"},
        "references": verweise,
    }


def zeitfenster(datenwurzel: Path) -> tuple[str, str]:
    """Das Fenster kommt aus dem Release, nicht aus einer Voreinstellung."""
    from storage.duckdb import verbinde

    _, verzeichnis = aktuelles_release(datenwurzel)
    parquet = verzeichnis / "gold/dataset=fact_offense/part-0001.parquet"
    con = verbinde()
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
    """Alles, was angelegt wird - Datenansicht, Navigation, Tafeln, Bretter."""
    alle: list[dict[str, Any]] = [datenansicht()]
    # Die beiden zeitlosen Ansichten nur, wenn eine Karte sie braucht - ein
    # Objekt ohne Verwender waere eine Kachel in Kibanas Liste, die nichts
    # tut, und ``pruefe_verweise`` sieht nur die andere Richtung.
    if any(t.ist_karte for b in bretter for t in b.tafeln):
        alle.append(datenansicht(FLAECHEN_INDEX.name, None, ANSICHT_FLAECHEN))
        alle.append(datenansicht(RATEN_INDEX.name, None, ANSICHT_RATEN))
    # Die Navigation zeigt auf alle Bretter, und jedes Brett zeigt auf sie
    # zurueck. Der Ring ist Absicht und kein Versehen: Kibana prueft Verweise
    # beim Anlegen nicht, und ``pruefe_verweise`` sieht beide Seiten in
    # derselben Ladung.
    if any(b.navigation for b in bretter):
        alle.append(navigation_objekt(bretter))
    for brett in bretter:
        alle.extend(
            karte_objekt(t, brett.kennung) if t.ist_karte
            else lens_objekt(t, brett.kennung)
            for t in brett.tafeln)
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


def kommandozeile() -> argparse.ArgumentParser:
    """Die Kommandozeile - eigen, damit ihre Vorgaben pruefbar sind.

    Die Vorgabe von ``--url`` kommt aus der Umgebung und wird deshalb
    **beim Aufruf** gelesen, nicht beim Import. Ein getipptes ``--url``
    sticht sie; ``tests/serving/test_dienst_urls.py`` haelt beides fest.
    """
    zerleger = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    zerleger.add_argument("--data-root", type=Path, default=None)
    # Die Vorgabe wird hier gelesen, nicht beim Import: So sieht sie die
    # Umgebung des Aufrufs, und ein getipptes --url sticht sie trotzdem.
    zerleger.add_argument("--url", default=vorgabe_url(),
                          help=f"Kibana (Standard: {UMGEBUNGSVARIABLE} "
                               f"oder {STANDARD_URL})")
    zerleger.add_argument("--trocken", action="store_true",
                          help="nur zeigen, was entstuende")
    return zerleger


def main(argv: list[str] | None = None) -> int:
    args = kommandozeile().parse_args(argv)
    from storage import for_root
    from storage.verwaltet import sperre
    sperre(for_root(args.data_root).local_root, worker_erlaubt=True)
    from contextlib import nullcontext
    from storage.analysesitzung import schreibzugriff
    # Serving schreibt nicht nach bronze/silver/gold: Die Sperre haelt
    # Analysen fern, der Herkunftsnachweis (.analyse/stand.json) bleibt gueltig.
    # Der Trockenlauf schreibt nichts, auch keine Sperrdatei.
    with (schreibzugriff(for_root(args.data_root).local_root, invalidieren=False)
          if not args.trocken else nullcontext()):

        fenster = zeitfenster(for_root(args.data_root).local_root)
        # Mit Namen und nicht nach Position: Ein Feld mehr an ``Brett`` liesse
        # das Zeitfenster sonst still in der falschen Spalte landen - und ein
        # Brett ohne Zeitfenster faellt erst beim Oeffnen auf.
        bretter = tuple(replace(b, zeitraum=fenster) for b in BRETTER)
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
