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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

# Das Bezugsjahr der Raten kommt aus derselben Quelle wie das der
# Abgabedokumente. Eine zweite 2024 hier waere die Stelle, an der Dashboard und
# Dokument auseinanderlaufen, ohne dass jemand es merkt.
from gold_pipeline import RATENJAHR
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
    # Dieselbe Darstellung wie ``tabelle``, aber eine andere Datenquelle:
    # ``textBased`` statt ``formBased``. Eine eigene Art und kein Schalter an
    # ``tabelle``, weil die beiden nichts gemeinsam haben ausser dem Aussehen.
    "esql_tabelle": "lnsDatatable",
}

#: Die Arten, die ihre Frage in ES|QL stellen statt in Eimern. Als Menge, weil
#: eine zweite dazukommen kann (ein ES|QL-Balken etwa) und dann jede
#: Verzweigung von selbst mitzieht.
ESQL_ARTEN = frozenset({"esql_tabelle"})


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

    ``beleg`` ist die Stelle in der Abfrage, die den Ausschluss ausfuehrt.
    ``Tafel.__post_init__`` sucht sie dort und laesst die Kachel sonst nicht
    entstehen. Ein **Vorbehalt** - etwas, das man beim Lesen wissen muss,
    ohne dass die Abfrage es wegfiltert - gehoert deshalb nicht hierher,
    sondern nach ``Tafel.vorbehalte``.
    """

    text: str
    beleg: str


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
    #: Fuer die vierzehn vorhandenen Kacheln der drei alten Bretter sind sie
    #: zurueckgestellt (reine Zaehlungen und Anteile); Pflicht sind sie fuer
    #: jede ES|QL-Tafel. FR-27 ist damit halb erfuellt und nicht ganz.
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
    #: Das Jahr, fuer das die Zahl gilt. Pflicht, sobald eine Rate dabei ist:
    #: Sechs Jahrgaenge auf einen Jahresnenner ergeben 500,7 je 1'000 - keine
    #: zu hohe Rate, sondern keine.
    jahr: int | None = None

    def __post_init__(self) -> None:
        if self.art not in ARTEN:
            raise LadeFehler(
                f"{self.kennung}: Art '{self.art}' ist nicht entschieden. "
                f"Bekannt sind {', '.join(sorted(ARTEN))}.")
        if self.ist_esql:
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
            if self.art in ("balken", "linie", "ring") and not self.eimer:
                raise LadeFehler(
                    f"{self.kennung}: '{self.art}' braucht mindestens eine "
                    f"Gruppierung, sonst ist es ein einzelner Balken.")
        if self.breite > RASTER:
            raise LadeFehler(
                f"{self.kennung}: {self.breite} Spalten passen nicht in ein "
                f"Raster von {RASTER}.")

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
        # FR-27. Eine Zahl ohne Nenner und ohne Ausschluesse ist genau der
        # Fall, den ``ausblick.md`` als "die Arbeit dieses Projekts zunichte
        # machen" beschreibt - und sie faellt niemandem auf, denn sie sieht
        # aus wie eine Zahl.
        if not self.frage:
            raise LadeFehler(
                f"{self.kennung}: ohne 'frage' sagt die Kachel nicht, was "
                f"sie beantwortet.")
        if not self.ausschluesse:
            raise LadeFehler(
                f"{self.kennung}: ohne 'ausschluesse' liest jemand die Zahl "
                f"als vollstaendig.")
        for a in self.ausschluesse:
            # Der Ausschluss muss in **dieser** Abfrage stehen, nicht in
            # irgendeiner. Genau das fehlte, als drei Kacheln sich ein
            # Tupel teilten (siehe ``Ausschluss``).
            if a.beleg not in self.abfrage.esql:
                raise LadeFehler(
                    f"{self.kennung}: die Kachel nennt den Ausschluss "
                    f"'{a.text[:60]}…', ihre Abfrage vollzieht ihn aber "
                    f"nicht - '{a.beleg}' steht nicht darin.")
        if self.zeigt_rate and not (self.nenner and self.jahr):
            raise LadeFehler(
                f"{self.kennung}: eine Rate braucht ihren Nenner und ihr "
                f"Jahr. Ohne Jahr ist sie keine Rate, sondern ein Quotient "
                f"aus sechs Jahrgaengen und einem Jahresnenner.")

    @property
    def ist_esql(self) -> bool:
        return self.art in ESQL_ARTEN

    @property
    def zeigt_rate(self) -> bool:
        """Steht auf dieser Tafel eine Rate je 1'000 Einwohner?"""
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
_FALLEBENE_VORN = (
    "**Fallebene vorn, Tatebene daneben** (Entscheid E5). Die "
    "Abgabedokumente führen bis auf Weiteres die *Tatebene* als kanonische "
    "Rate; das Dashboard stellt die Fallebene voran. Für Chicago ist das "
    "dieselbe Zahl, für Detroit nicht — beide Spalten stehen deshalb "
    "nebeneinander"
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


BRETTER: tuple[Brett, ...] = (
    Brett(
        kennung="crime-ueberblick",
        titel="Überblick — Chicago gegen Detroit",
        beschreibung=(
            "Der Einstieg. Absolute Zahlen sagen wenig, solange die Städte "
            "verschieden gross sind — die Rate je 1'000 Einwohner steht im "
            "Brett »Raten je 1'000«, für den Jahrgang "
            f"{RATENJAHR}."),
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
                  ausschluesse=(_AUSSERHALB, _ANDERE_JAHRGAENGE,
                                _MIT_EINWOHNERN),
                  jahr=RATENJAHR, breite=48, hoehe=8),
        ),
    ),
)


# --------------------------------------------------------------------------
# Die erzeugten Objekte. Reine Funktionen - pruefbar ohne Kibana.
# --------------------------------------------------------------------------


def datenansicht(index: str = "fact_offense",
                 zeitfeld: str = ZEITFELD) -> dict[str, Any]:
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
            "query": {"language": "kuery", "query": ""},
            "visualization": tafel.darstellung,
        }
        verweisname = f"indexpattern-datasource-layer-{tafel.schicht}"

    merkmale: dict[str, Any] = {
        "title": tafel.titel,
        "visualizationType": ARTEN[tafel.art],
        "state": zustand,
    }
    # Frage, Nenner, Jahr und Ausschluesse - dort, wo Kibana sie neben der
    # Zahl zeigt. Leer bleibt das Feld nur bei den vierzehn alten Kacheln,
    # deren FR-27-Angaben zurueckgestellt sind.
    if tafel.erlaeuterung:
        merkmale["description"] = tafel.erlaeuterung

    return {
        "type": "lens", "id": f"lens-{brett}-{tafel.kennung}",
        "attributes": merkmale,
        "references": [{
            "type": "index-pattern", "id": ANSICHT, "name": verweisname}],
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
