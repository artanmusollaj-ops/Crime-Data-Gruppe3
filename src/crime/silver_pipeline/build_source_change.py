"""Was die Quelle zwischen zwei Schnappschuessen geaendert hat.

    python -m silver_pipeline.build_source_change
    python -m silver_pipeline.build_source_change --trocken   # nur zeigen

**Warum es diese Tabelle gibt.** Fuer die Auswertung zaehlt der aktuelle
Stand. Die Quellen bewegen sich aber: Detroit aendert Eintraege noch Jahre
nach der Tat, Chicago liefert Deltas. Diese Bewegung ist selbst ein
Gegenstand - *was aendert sich, wie oft, welcher Art, und was verschwindet.*
Heute steckt sie implizit in den Bronze-Laeufen, und sobald
``orchestration.aufraeumen`` einen loescht, ist sie weg.

``docs/intern/datenhistorie.md`` hat das Verhaeltnis ausgerechnet: **31,9 MB
Schnappschuesse fuer 102 geaenderte Zeilen.** Dieses Modul zieht den
Unterschied heraus, bevor die Laeufe entbehrlich werden - danach bleibt eine
schmale Tabelle statt zweier Vollbestaende.

**Was verglichen wird und was nicht.**

``ESRI_OID`` steht in ``RAUSCHEN`` und wird nie aufgezeichnet: Es ist die
Zeilennummer der ArcGIS-Antwort und bewegte sich bei **88'677 von 88'685**
Zeilen. Wer es mitvergleicht, erzeugt ein Protokoll, in dem die hundert
echten Aenderungen nicht zu finden sind - Faktor 870 Rauschen.

Text wird vor dem Vergleich getrimmt. Von 160 Aenderungen an
``offense_description`` waren **150 reine Leerzeichen**, weil die Quelle
inzwischen auf feste Breite auffuellt. Echt waren zehn.

**Zwei Arten von Beruehrung, und das ist eine Entscheidung.** Das Papier
nennt unter 5.1 die Option *"ohne Zeitstempel"*, begruendet die Empfehlung
aber damit, dass eine Zeile, die die Quelle **ohne** fachliche Aenderung
angefasst hat, "eine eigene Beobachtung" sei - 147 solche Zeilen gab es im
gemessenen Paar. Beides zusammen geht nicht. Aufgeloest wird es so: Die
Zeitstempel zaehlen nicht als *Inhaltsaenderung*, werden aber aufgezeichnet.
Eine Zeile ist

``geaendert``
    wenn sich etwas ausserhalb von ``RAUSCHEN`` und ``STEMPEL`` bewegt hat,

``beruehrt``
    wenn sich **nur** Stempel bewegt haben - die Quelle hat die Zeile
    angefasst, ohne dass sich fachlich etwas aenderte,

``neu`` / ``verschwunden``
    wenn der Schluessel im einen Schnappschuss steht und im anderen nicht.

**Nur Vollschnappschuesse.** Verglichen werden ausschliesslich Laeufe, die
``manifeste.Lauf.vollabzug`` bejaht: Ein Delta enthaelt nur die bewegten
Zeilen, und *was fehlt* laesst sich daraus nicht von *was sich nicht geaendert
hat* unterscheiden. Verschwundene Zeilen waeren dort nicht Abwesenheit,
sondern Ruhe.

Dass die Pruefung im gemeinsamen Manifestleser wohnt und nicht hier, hat einen
Grund: Die beiden Staedte sagen dasselbe in zwei Schluesseln und zwei
Vokabularen - Chicago ``mode = full_snapshot``, Detroit
``extraction_mode = FULL``. Dieses Modul las nur Detroits Fassung und haette
Chicagos Vollabzuege auch dann nicht gefunden, wenn zwei dagelegen haetten.
Dieselbe Asymmetrie gilt fuer den Startzeitpunkt (``started_at`` gegen
``started_at_utc``), nach dem die Schnappschuesse geordnet werden.

**Beide Staedte, seit dem 3.10.2026.** Chicago hatte lange genau einen
Vollschnappschuss (5.9.2026) und seither nur Deltas; ein Paar braucht zwei.
Mit dem Entscheid, je Stadt und Monat einen Vollabzug zu fahren (Papier 5.2),
und einem zweiten Chicago-Abzug ist die Tabelle zweistaedtig. Vorher stand
hier, dass nach den fuenf Detroit-Schnappschuessen kein neues Paar mehr
entsteht - das war die Grenze, und sie ist mit dem Takt weggefallen.

Entsteht trotzdem kein Paar, sagt das Modul es beim Lauf, statt eine Tabelle
zu schreiben, die still aufhoert zu wachsen.
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

from manifeste import code_stand
from silver_pipeline import (
    BRONZE_LAYER,
    PARQUET_FILE,
    SILVER_LAYER,
    TransformError,
    connect,
    publish,
    schema_of,
)
from storage import StorageError, for_root
from storage import duckdb as storage_duckdb
from storage.duckdb import verbinde

log = logging.getLogger(__name__)

TABLE = "source_change"
#: 2 seit dem 3.10.2026: Die Deltas datieren, was die Vollabzuege finden
#: (``zuerst_gesehen_in``, ``zuerst_gesehen_am``, ``datierung``).
#: 3 am selben Tag: Die Datierung **klebt**. Sie nennt nicht den heutigen
#: Befund, sondern den besten, der je bestimmt wurde - sonst haette das
#: Aufraeumen der Deltas sie wieder gelöscht. Die Spalten sind dieselben, ihre
#: Bedeutung ist es nicht, und deshalb steigt die Zahl.
CONTRACT_VERSION = 3

#: Die Spalten, in dieser Reihenfolge. Ausgeschrieben und nicht ``SELECT *``:
#: DuckDB leitet aus dem Pfad ``dataset=source_change`` eine Hive-Spalte
#: ``dataset`` ab, die in keiner Datei steht. Beim Anhaengen passten die
#: Spaltenzahlen dann nicht mehr - und beim Lesen haette die Tabelle eine
#: Spalte mehr gehabt, als sie hat.
#: Die Tatsachenspalten - das, was ``ziehe`` aus einem Paar herausholt.
SPALTEN_ROH = ("city", "offense_id", "vorher_run_id", "run_id",
               "vorher_am", "beobachtet_am", "art", "feld",
               "wert_alt", "wert_neu")

#: Dazu die Datierung aus den Deltas. Sie ist **keine** Tatsache des Paares,
#: sondern eine Annotation: Sie wird nachgerechnet, solange sie **besser**
#: werden kann, und nie schlechter. Ein aufgeraeumtes Delta loescht sie nicht
#: mehr - siehe ``DATIERUNG_SQL``. Drei Zustaende statt einer Leerstelle,
#: Begruendung in ``datiere``.
SPALTEN_DATIERUNG = ("zuerst_gesehen_in", "zuerst_gesehen_am", "datierung")

SPALTEN = SPALTEN_ROH + SPALTEN_DATIERUNG



@dataclass(frozen=True)
class Quelle:
    """Eine Stadt, und woran sich ihre Zeilen wiedererkennen lassen."""

    stadt: str
    praefix: str
    #: Das Feld, das die **fachliche** Identitaet traegt. Dieselbe Wahl wie in
    #: ``build_crime_offense``: nicht ``ESRI_OID``.
    schluessel: str
    #: Wo die Quellfelder in der Bronze-Datei liegen. Detroits ArcGIS-Antwort
    #: verschachtelt sie in einem Struct ``attributes``; Chicagos Socrata-Zeilen
    #: liegen flach als Spalten. ``None`` heisst flach.
    struct: str | None = "attributes"
    #: Felder, die nie aufgezeichnet werden. Reine Transportartefakte.
    rauschen: frozenset[str] = frozenset()
    #: Felder, deren Bewegung keine Inhaltsaenderung ist - aber eine
    #: Beobachtung.
    stempel: frozenset[str] = frozenset()


QUELLEN: tuple[Quelle, ...] = (
    Quelle(
        stadt="detroit",
        praefix=f"{BRONZE_LAYER}/city=detroit",
        schluessel="incident_entry_id",
        # Gemessen am Paar 11.9./12.9.: bewegt sich bei 88'677 von 88'685
        # Zeilen und sagt nichts. Absprache 8.1 haelt ohnehin fest, dass die
        # fachliche Identitaet nicht daran haengt.
        rauschen=frozenset({"ESRI_OID"}),
        stempel=frozenset({"updated_at", "updated_in_ibr_at",
                           "case_status_updated_at"}),
    ),
    Quelle(
        stadt="chicago",
        praefix=f"{BRONZE_LAYER}/city=chicago",
        # Dieselbe Wahl wie in build_crime_offense: die fachliche Identitaet,
        # nicht die Zeilennummer der Antwort.
        schluessel="id",
        # Socrata liefert flache Spalten, kein attributes-Struct.
        struct=None,
        # Leer, und das ist gemessen: Im Paar 5.9./3.10. bewegten sich genau
        # sieben Felder - updated_on (19), arrest (15), fbi_code, description,
        # iucr, primary_type, date. ``location``, ``latitude``, ``longitude``
        # und ``_extra`` ruehrten sich nicht, obwohl location die Koordinaten
        # doppelt fuehrt und als Rauschkandidat gehandelt wurde. Chicago hat
        # auch kein Gegenstueck zu Detroits ESRI_OID: Socratas eigene
        # ":"-Spalten verwirft schon die Ingestion, und eine Zeilennummer
        # liefert die API nicht mit.
        rauschen=frozenset(),
        # Das Feld, an dem auch die Delta-Ingestion ihr Wasserzeichen fuehrt.
        stempel=frozenset({"updated_on"}),
    ),
)


@dataclass(frozen=True)
class Schnappschuss:
    run_id: str
    pfad: str
    beobachtet_am: str
    #: Der Jahrgang, den dieser Abzug traegt. Leer heisst: Das Manifest nennt
    #: keinen - dann steht der Abzug fuer sich und wird nur mit anderen
    #: jahrgangslosen verglichen.
    jahrgang: str = ""

    def __str__(self) -> str:
        jahr = f" {self.jahrgang}" if self.jahrgang else ""
        return f"{self.run_id[:8]}{jahr} ({self.beobachtet_am[:19]})"


# --------------------------------------------------------------------------
# Reine Funktionen - pruefbar ohne Bestand
# --------------------------------------------------------------------------


def schnappschuesse(laeufe: list[Any]) -> list[Schnappschuss]:
    """Die vergleichbaren Laeufe, aelteste zuerst.

    Sortiert wird nach ``started_at`` und nicht nach dem Laufnamen: Detroits
    Laufverzeichnisse heissen nach einer UUID, und die sagt nichts ueber die
    Reihenfolge. Chicagos Namen traegen zwar einen Zeitstempel, aber eine
    Sortierregel, die nur fuer eine Stadt stimmt, ist keine.
    """
    gefunden = []
    for lauf in laeufe:
        if not lauf.vollabzug:
            continue
        wann = lauf.begonnen_um or lauf.manifest.get("finished_at")
        if not wann:
            raise TransformError(
                f"{lauf.run_id}: Manifest ohne Zeitstempel - ohne ihn laesst "
                f"sich die Reihenfolge nicht bestimmen.")
        gefunden.append(Schnappschuss(lauf.run_id, lauf.relativ, str(wann),
                                      lauf.jahrgang))
    return sorted(gefunden, key=lambda s: (s.beobachtet_am, s.run_id))


def paare(alle: list[Schnappschuss]) -> list[tuple[Schnappschuss, Schnappschuss]]:
    """Aufeinanderfolgende Paare **je Jahrgang** - nicht jedes gegen jedes.

    Jedes gegen jedes waere quadratisch und saehe dieselbe Aenderung mehrfach:
    Was sich zwischen dem ersten und dem zweiten Schnappschuss bewegt hat,
    stuende auch im Vergleich des ersten mit dem dritten. Die Kette zaehlt
    jede Bewegung genau einmal.

    **Je Jahrgang, und das war der Fehler.** Bis zum 17.10.2026 bildete diese
    Funktion eine einzige Kette je Stadt, nach Zeit geordnet. Seit beide
    Staedte am 4.10.2026 anfingen, **je Jahrgang** zu laden, sind
    aufeinanderfolgende Abzuege aber verschiedene Jahrgaenge - und der
    Vergleich meldete jede Zeile des einen als ``verschwunden`` und jede des
    anderen als ``neu``:

        chicago  2024er Abzug -> 2021er Abzug   weg=259'638  neu=210'005

    **1,64 Mio. erfundene "verschwunden"** und 1,53 Mio. erfundene "neu"
    standen so in der Tabelle - in jener Tabelle, die der Gegenstand der
    Arbeit ist. Ein Vollabzug sagt nicht "das ist der ganze Bestand", sondern
    "das ist der ganze Jahrgang 2024"; nur innerhalb eines Jahrgangs bedeutet
    Abwesenheit etwas.

    Jahrgangslose Abzuege bilden ihre eigene Kette: Bestaende aus der Zeit
    vor der Jahrgangstrennung sollen weiter vergleichbar bleiben.
    """
    je_jahrgang: dict[str, list[Schnappschuss]] = {}
    for abzug in alle:
        je_jahrgang.setdefault(abzug.jahrgang, []).append(abzug)
    gebildet: list[tuple[Schnappschuss, Schnappschuss]] = []
    for _, kette in sorted(je_jahrgang.items()):
        gebildet.extend(zip(kette, kette[1:]))
    return gebildet


def delta_laeufe(laeufe: list[Any]) -> list[Schnappschuss]:
    """Die Deltas, aelteste zuerst - das Gegenstueck zu ``schnappschuesse``.

    Verglichen wird weiter nur zwischen Vollabzuegen. Die Deltas tragen hier
    eine andere Aufgabe: Sie **datieren**, was die Vollabzuege finden. Ein
    Monatsabstand sagt nur *irgendwann in diesen dreissig Tagen*; das erste
    Delta, das den Schluessel enthaelt, macht daraus wenige Tage.
    """
    gefunden = []
    for lauf in laeufe:
        if lauf.vollabzug:
            continue
        wann = lauf.begonnen_um or lauf.manifest.get("finished_at")
        if not wann:
            raise TransformError(
                f"{lauf.run_id}: Delta ohne Zeitstempel - ohne ihn laesst sich "
                f"nicht sagen, in welches Fenster es gehoert.")
        gefunden.append(Schnappschuss(lauf.run_id, lauf.relativ, str(wann)))
    return sorted(gefunden, key=lambda s: (s.beobachtet_am, s.run_id))


def datiere(con: duckdb.DuckDBPyConnection, quelle: Quelle, ablage: Any,
            deltas: list[Schnappschuss]) -> int:
    """Traegt die Schluessel aller lesbaren Deltas dieser Quelle nach.

    Schreibt in die Tabelle ``delta_schluessel``, die der Aufrufer **einmal**
    anlegt. Sie hier anzulegen war der erste Entwurf und falsch: Ein
    ``CREATE OR REPLACE`` je Quelle liess nur die letzte uebrig, und Detroits
    Deltas verschwanden, sobald Chicago dran war. Die Tests haben es gefangen,
    weil sie die Datierung je Quelle pruefen und nicht nur die Gesamtzahl.

    Gibt zurueck, wie viele Deltas tatsaechlich gelesen werden konnten. Eines,
    dessen Datei aufgeraeumt ist, wird uebersprungen - was damit frueher
    bestimmt wurde, bleibt trotzdem stehen, denn die Datierung klebt.

    **Warum die Datierung drei Zustaende hat.** Eine Leerstelle waere
    mehrdeutig: Sie koennte heissen *kein Delta trug diesen Schluessel* oder
    *es lag ueberhaupt keines vor*. Dieselbe Unterscheidung, aus der es die
    Markierungszeile ``art = 'unveraendert'`` gibt.

    ``delta``
        Mindestens ein lesbares Delta im Fenster trug den Schluessel; genannt
        wird das **erste**.
    ``kein_delta``
        Deltas lagen im Fenster, aber keines trug den Schluessel. Das hat
        **drei** moegliche Ursachen, und sie sind von hier aus nicht zu
        trennen: Die Quelle hat die Aenderung nicht angemeldet - so wie die
        acht Korrekturen an ``nearest_intersection``, bei denen sich kein
        Stempel bewegte. Oder sie geschah erst **nach** dem letzten Delta;
        Chicagos 26 undatierte Aenderungen sind von dieser Sorte, die Deltas
        enden am 18.9. und das Fenster am 3.10. Oder die Zeile war, bei
        ``art = 'verschwunden'``, schon nicht mehr da.
    ``nicht_datierbar``
        Kein lesbares Delta liegt im Fenster. Detroits Paare sind alle so: die
        drei Deltas vom 18.9. liegen nach dem letzten Paar.

    Bei einer Zeile ohne Schluessel - der Markierungszeile - bleibt die
    Datierung leer; es gibt nichts zu datieren.
    """
    gelesen = 0
    for delta in deltas:
        try:
            pfad = ablage.resolve_read_path(delta.pfad, PARQUET_FILE)
        except Exception as fehler:          # noqa: BLE001 - Ablage, nicht Logik
            log.warning("  %s: Delta %s nicht lesbar (%s) - wird fuer die "
                        "Datierung uebersprungen", quelle.stadt, delta, fehler)
            continue
        con.execute(f"""
            INSERT INTO delta_schluessel
            SELECT '{quelle.stadt}', '{delta.run_id}',
                   TIMESTAMP '{delta.beobachtet_am[:19]}',
                   {vergleichbar(quelle.schluessel, quelle)}
            FROM read_parquet('{pfad}')
            WHERE {vergleichbar(quelle.schluessel, quelle)} IS NOT NULL
        """)
        gelesen += 1
    return gelesen


#: Wie viel eine Datierung aussagt. Gebraucht, damit eine schon bestimmte
#: nicht durch eine schlechtere ersetzt wird.
RANG_SQL = """
    CREATE OR REPLACE TEMP MACRO rang(d) AS
        CASE d WHEN 'delta' THEN 3
               WHEN 'kein_delta' THEN 2
               WHEN 'nicht_datierbar' THEN 1
               ELSE 0 END
"""

#: Die Datierung, als Abfrage ueber die rohe Tabelle. Je Fenster - also je
#: Paar und Stadt - das **erste** Delta, das den Schluessel trug.
#:
#: ``arg_min`` nimmt den Lauf zum kleinsten Zeitpunkt; ein Delta genau auf der
#: Grenze des aelteren Vollabzugs gehoert nicht ins Fenster (``>``), eines auf
#: der Grenze des neueren schon (``<=``) - es ist die letzte Gelegenheit, die
#: Aenderung gesehen zu haben.
#:
#: **Und sie klebt.** Was einmal bestimmt war, bleibt stehen; neu gerechnet
#: wird nur, was besser wird. Der erste Entwurf rechnete bei jedem Bau frisch,
#: und das war ein Mangel: Loeschte man die Deltas - und Aufraeumen ist ein
#: Ziel, nicht ein Unfall -, wurde aus ``delta`` wieder ``nicht_datierbar``.
#: Die Aenderungszeile blieb, ihre Datierung war weg. Genau das, wogegen diese
#: Tabelle gebaut ist: den Unterschied herausziehen, **bevor** der Rohstoff
#: entbehrlich wird. Fuer die zehn Tatsachenspalten galt das von Anfang an,
#: fuer die Datierung erst seit dem 3.10.2026 nachmittags.
DATIERUNG_SQL = """
    WITH fenster AS (
        SELECT DISTINCT city, offense_id, vorher_run_id, run_id,
               vorher_am, beobachtet_am
        FROM roh WHERE offense_id IS NOT NULL
    ),
    vorrat AS (
        SELECT f.city, f.offense_id, f.vorher_run_id, f.run_id,
               count(DISTINCT d.run_id) AS deltas_im_fenster
        FROM fenster f LEFT JOIN delta_schluessel d
          ON d.city = f.city
         AND d.am > f.vorher_am AND d.am <= f.beobachtet_am
        GROUP BY 1, 2, 3, 4
    ),
    treffer AS (
        SELECT f.city, f.offense_id, f.vorher_run_id, f.run_id,
               arg_min(d.run_id, d.am) AS zuerst_gesehen_in,
               min(d.am) AS zuerst_gesehen_am
        FROM fenster f JOIN delta_schluessel d
          ON d.city = f.city AND d._id = f.offense_id
         AND d.am > f.vorher_am AND d.am <= f.beobachtet_am
        GROUP BY 1, 2, 3, 4
    ),
    frisch AS (
        SELECT r.*,
               t.zuerst_gesehen_in AS f_in, t.zuerst_gesehen_am AS f_am,
               CASE
                   WHEN r.offense_id IS NULL              THEN NULL
                   WHEN t.zuerst_gesehen_in IS NOT NULL   THEN 'delta'
                   WHEN coalesce(v.deltas_im_fenster, 0) > 0 THEN 'kein_delta'
                   ELSE 'nicht_datierbar'
               END AS f_datierung,
               a.zuerst_gesehen_in AS a_in, a.zuerst_gesehen_am AS a_am,
               a.datierung AS a_datierung
        FROM roh r
        LEFT JOIN vorrat v USING (city, offense_id, vorher_run_id, run_id)
        LEFT JOIN treffer t USING (city, offense_id, vorher_run_id, run_id)
        LEFT JOIN alt_datierung a USING (city, offense_id, vorher_run_id, run_id)
    )
    SELECT city, offense_id, vorher_run_id, run_id,
           vorher_am, beobachtet_am, art, feld, wert_alt, wert_neu,
           CASE WHEN rang(a_datierung) > rang(f_datierung)
                THEN a_in ELSE f_in END AS zuerst_gesehen_in,
           CASE WHEN rang(a_datierung) > rang(f_datierung)
                THEN a_am ELSE f_am END AS zuerst_gesehen_am,
           CASE WHEN rang(a_datierung) > rang(f_datierung)
                THEN a_datierung ELSE f_datierung END AS datierung
    FROM frisch
"""


def felder(con: duckdb.DuckDBPyConnection, pfad: str,
           quelle: Quelle) -> list[str]:
    """Die Quellfelder - aus der Datei, nicht aus einer Liste.

    Zwei Formen. Detroits ArcGIS-Antwort liegt in einem Struct
    ``attributes``, und ``unnest`` nennt dessen Felder. Chicagos
    Socrata-Zeilen liegen flach; dort sind die Spalten der Datei die Felder.

    Flach wird ueber ``storage.parquet_spalten`` gelesen und **nicht** ueber
    ``DESCRIBE``: Der Pfad traegt ``city=`` und ``ingest_date=``, und DuckDB
    haette daraus zwei Hive-Spalten abgeleitet, die in keiner Datei stehen.
    Sie waeren als Quellfelder in den Vergleich gegangen - zwei Felder, die
    sich je Lauf aendern und nichts bedeuten.
    """
    if quelle.struct:
        zeilen = con.execute(
            f"SELECT unnest({quelle.struct}) FROM read_parquet('{pfad}') "
            f"LIMIT 0").description
        if zeilen:
            return [z[0] for z in zeilen]
        raise TransformError(f"{pfad}: kein {quelle.struct}-Struct")
    from storage import parquet_spalten
    namen = list(parquet_spalten(pfad))
    if namen:
        return namen
    raise TransformError(f"{pfad}: keine Spalten")


def vergleichbar(name: str, quelle: Quelle) -> str:
    """Wie ein Feld vor dem Vergleich normalisiert wird.

    Getrimmt wird jedes Feld, nicht nur die, von denen man es erwartet: Die
    Quelle hat angefangen, ``offense_description`` auf feste Breite
    aufzufuellen, und niemand hatte das angekuendigt.
    """
    spalte = f'{quelle.struct}."{name}"' if quelle.struct else f'"{name}"'
    return f"nullif(trim(CAST({spalte} AS VARCHAR)), '')"


def vergleich_sql(a: str, b: str, namen: list[str], quelle: Quelle) -> str:
    """Die Abfrage, die aus zwei Schnappschuessen Aenderungszeilen macht.

    Lang, aber geradeaus: zwei normalisierte Sichten, ein voller Aussenjoin,
    und je Feld ein ``UNION ALL``-Zweig fuer *hat sich bewegt*. Die
    Alternative - ``attributes`` in Schluessel/Wert-Paare entfalten - waere
    kuerzer und muesste jeden Wert durch ``VARCHAR`` schicken, bevor sie
    weiss, ob sie ihn braucht.
    """
    aufgezeichnet = [n for n in namen if n not in quelle.rauschen]
    if quelle.schluessel not in namen:
        raise TransformError(
            f"{quelle.stadt}: Schluesselfeld {quelle.schluessel} steht nicht "
            f"in der Quelle")

    def sicht(pfad: str) -> str:
        spalten = ", ".join(
            f"{vergleichbar(n, quelle)} AS \"{n}\"" for n in aufgezeichnet)
        return (f"SELECT {vergleichbar(quelle.schluessel, quelle)} AS _id, "
                f"{spalten} FROM read_parquet('{pfad}') "
                f"WHERE {vergleichbar(quelle.schluessel, quelle)} IS NOT NULL")

    zweige = [
        f'SELECT _id, \'{n}\' AS feld, alt."{n}" AS wert_alt, '
        f'neu."{n}" AS wert_neu FROM beide '
        f'WHERE alt._id IS NOT NULL AND neu._id IS NOT NULL '
        f'AND alt."{n}" IS DISTINCT FROM neu."{n}"'
        for n in aufgezeichnet if n != quelle.schluessel
    ]
    return f"""
        WITH alt AS ({sicht(a)}), neu AS ({sicht(b)}),
        beide AS (
            SELECT coalesce(alt._id, neu._id) AS _id, alt, neu
            FROM alt FULL OUTER JOIN neu ON alt._id = neu._id
        ),
        bewegt AS ({' UNION ALL '.join(zweige)}),
        fehlt AS (
            SELECT _id, NULL AS feld, NULL AS wert_alt, NULL AS wert_neu,
                   CASE WHEN alt._id IS NULL THEN 'neu' ELSE 'verschwunden' END AS art
            FROM beide WHERE alt._id IS NULL OR neu._id IS NULL
        ),
        eingestuft AS (
            SELECT _id,
                   CASE WHEN count(*) FILTER (
                            WHERE feld NOT IN ({_liste(quelle.stempel)})) > 0
                        THEN 'geaendert' ELSE 'beruehrt' END AS art
            FROM bewegt GROUP BY 1
        )
        SELECT b._id AS offense_id, e.art, b.feld, b.wert_alt, b.wert_neu
        FROM bewegt b JOIN eingestuft e USING (_id)
        UNION ALL
        SELECT _id, art, feld, wert_alt, wert_neu FROM fehlt
    """


def _liste(werte: frozenset[str]) -> str:
    """Eine SQL-Liste - auch wenn sie leer ist."""
    return ", ".join(f"'{w}'" for w in sorted(werte)) or "''"


# --------------------------------------------------------------------------
# Der Ablauf
# --------------------------------------------------------------------------


def tabellenverzeichnis(data_root: Path) -> Path:
    return for_root(data_root).local_path(f"{SILVER_LAYER}/dataset={TABLE}")


def abgelegtes_manifest(ablage: Any, rel: str) -> dict[str, Any]:
    """Das Manifest der abgelegten Tabelle - leer, wenn keines da ist.

    **Ueber die Ablage, nicht ueber das Dateisystem.** ``Storage`` hat dafuer
    ``tabellen_manifest`` (seit dem 15.10.2026), und aus demselben Grund:
    ``publish_table`` entfernt im ``s3``-Modus die lokale Arbeitskopie, der
    lokale Pfad zeigt danach ins Leere. Las man ihn trotzdem, lautete die
    Antwort immer "es gibt nichts".
    """
    if not ablage.exists(rel, "manifest.json"):
        return {}
    try:
        return ablage.tabellen_manifest(rel) or {}
    except (StorageError, TransformError, OSError, TypeError, ValueError):
        return {}


def abgelegtes_schema(ablage: Any, rel: str) -> set[str]:
    """Die Spalten, die das abgelegte Manifest nennt - leer, wenn keines da ist.

    Gebraucht, weil diese Tabelle append-only ist und ohne neues Paar sonst
    nie wieder geschrieben wuerde. Genau daran blieb das Schema zuerst aus:
    Der Vertrag stand schon auf 2, die Datierung hatte sich nicht bewegt, und
    der Lauf meinte, es gaebe nichts zu tun.
    """
    return set(abgelegtes_manifest(ablage, rel).get("schema") or {})


def abgelegter_vertrag(ablage: Any, rel: str) -> int | None:
    """Welche Vertragsversion in der abgelegten Tabelle steht - oder ``None``."""
    m = abgelegtes_manifest(ablage, rel)
    if not m:
        return None
    try:
        return int(m.get("contract_version", 0))
    except (TypeError, ValueError):
        return None


def gelesene_datierung(ablage: Any, rel: str) -> dict[str, int] | None:
    """Die Datierungsverteilung der abgelegten Tabelle - oder ``None``.

    ``None`` heisst: Es gibt keine abgelegte Tabelle, oder sie kennt die
    Spalte noch nicht und stammt aus Vertrag 1. Dann ist jede Datierung neu,
    und die Tabelle wird geschrieben.

    Die Spalten kommen ueber ``storage.parquet_spalten`` statt ueber
    ``DESCRIBE``: Der Pfad traegt ``dataset=source_change``, und daraus
    leitete DuckDB eine Spalte ``dataset`` ab, die in keiner Datei steht.

    **Und die Verbindung muss S3 kennen.** Hier stand ``verbinde()`` - die
    Verbindung *ohne* Ablage - und ein lokaler Pfad. Im ``s3``-Modus traf das
    beides nicht zu.
    """
    from storage import parquet_spalten
    if not ablage.exists(rel, PARQUET_FILE):
        return None
    datei = ablage.resolve_read_path(rel, PARQUET_FILE)
    if "datierung" not in parquet_spalten(datei):
        return None
    con = verbinde()
    try:
        if ablage.config.remote:
            storage_duckdb.s3_einrichten(con, ablage.config)
        return dict(con.execute(
            f"SELECT coalesce(datierung, 'ohne_schluessel'), count(*) "
            f"FROM read_parquet('{datei}') GROUP BY 1 ORDER BY 1").fetchall())
    finally:
        con.close()


def bereits_gezogen(verzeichnis: Path,
                    data_root: Path | None = None) -> set[tuple[str, str]]:
    """Welche Paare schon in der Tabelle stehen.

    Der Grund, warum diese Tabelle **nicht** einfach neu gebaut wird wie die
    uebrigen Silver-Tabellen: Ihr Rohstoff verschwindet. Ist ein Lauf
    aufgeraeumt, laesst sich sein Vergleich nicht wiederherstellen - was
    einmal herausgezogen wurde, bleibt deshalb stehen.

    **Gelesen wird ueber die Ablage.** Bis zum 16.10.2026 stand hier
    ``verzeichnis / PARQUET_FILE`` und ``is_file()`` - im ``s3``-Modus eine
    Datei, die es lokal nicht gibt, weil die Arbeitskopie nach dem
    Publizieren entfernt wird. Die Antwort war dann **immer** "noch nichts
    gezogen", und die Regel, die daran haengt
    (``orchestration.aufraeumen``, Regel 4), hielt jeden Schnappschuss fest.
    Das war die ungefaehrliche Richtung des Fehlers - sie macht das
    Aufraeumen wirkungslos statt gefaehrlich -, aber eine Auskunft, die
    immer dasselbe sagt, ist keine.
    """
    # Ohne ausdrueckliche Wurzel sagt sie das Verzeichnis selbst: Es liegt
    # als ``<wurzel>/silver/dataset=source_change``. Geraten wird nichts -
    # passt die Form nicht, bleibt es bei der Vorgabe der Ablage.
    if data_root is None and verzeichnis.parent.name == SILVER_LAYER:
        data_root = verzeichnis.parent.parent
    ablage = for_root(data_root)
    rel = ablage.relativ(verzeichnis) or f"{SILVER_LAYER}/dataset={TABLE}"
    if not ablage.exists(rel, PARQUET_FILE):
        return set()
    quelle = ablage.resolve_read_path(rel, PARQUET_FILE)
    con = verbinde()
    try:
        if ablage.config.remote:
            storage_duckdb.s3_einrichten(con, ablage.config)
        return {(a, b) for a, b in con.execute(
            f"SELECT DISTINCT vorher_run_id, run_id "
            f"FROM read_parquet('{quelle}')").fetchall()}
    finally:
        con.close()


def ungezogene_laeufe(data_root: Path) -> set[str]:
    """Vollschnappschuesse, deren Vergleich noch nicht herausgezogen ist.

    Die Auskunft, die ``orchestration.aufraeumen`` fuer ihre letzte Regel braucht. Sie
    steht hier und nicht dort, weil hier bekannt ist, was ein Paar ist: Ein
    Lauf bleibt unersetzlich, solange **irgendein** Paar, an dem er beteiligt
    ist, noch nicht in der Tabelle steht - als aelterer wie als juengerer.

    Der juengste Schnappschuss einer Stadt ist nie gezogen (er hat noch keinen
    Nachfolger) und steht hier trotzdem nicht: Ihn haelt bereits Regel 1.
    Sonst waere diese Regel eine, die nie etwas freigibt.
    """
    ablage = for_root(data_root)
    schon = bereits_gezogen(tabellenverzeichnis(data_root), data_root)
    offen: set[str] = set()
    for quelle in QUELLEN:
        try:
            alle = schnappschuesse(ablage.laeufe(quelle.praefix,
                                                 fehler=TransformError))
        except TransformError:
            continue
        for vorher, nachher in paare(alle):
            if (vorher.run_id, nachher.run_id) not in schon:
                offen.update({vorher.run_id, nachher.run_id})
    return offen


def ziehe(con: duckdb.DuckDBPyConnection, quelle: Quelle, ablage: Any,
          vorher: Schnappschuss, nachher: Schnappschuss) -> int:
    """Ein Paar vergleichen und als Zeilen in ``neue_zeilen`` legen.

    **Auch ein Paar ohne Aenderung wird festgehalten.** Sonst waere *nichts
    gefunden* nicht von *noch nicht verglichen* zu unterscheiden, und die
    beiden Laeufe blieben nach Regel 2a fuer immer gesperrt. Genau das ist
    beim ersten Lauf passiert: Zwischen den beiden Schnappschuessen vom
    18.9. (07:51 und 11:02) hatte sich in drei Stunden nichts bewegt, und die
    Tabelle kannte danach nur drei der vier Paare. Die Markierungszeile
    traegt ``art = 'unveraendert'`` und keine ``offense_id`` - sie ist selbst
    eine Beobachtung: *in diesem Zeitraum hat die Quelle nichts angefasst.*
    """
    a = ablage.resolve_read_path(vorher.pfad, PARQUET_FILE)
    b = ablage.resolve_read_path(nachher.pfad, PARQUET_FILE)
    sql = vergleich_sql(a, b, felder(con, a, quelle), quelle)
    kopf = (f"'{quelle.stadt}' AS city", f"'{vorher.run_id}' AS vorher_run_id",
            f"'{nachher.run_id}' AS run_id",
            f"TIMESTAMP '{vorher.beobachtet_am[:19]}' AS vorher_am",
            f"TIMESTAMP '{nachher.beobachtet_am[:19]}' AS beobachtet_am")
    vorher_zahl = con.execute("SELECT count(*) FROM neue_zeilen").fetchone()[0]
    con.execute(f"""
        INSERT INTO neue_zeilen
        SELECT {kopf[0]}, offense_id, {', '.join(kopf[1:])},
               art, feld, wert_alt, wert_neu
        FROM ({sql})
    """)
    gefunden = con.execute(
        "SELECT count(*) FROM neue_zeilen").fetchone()[0] - vorher_zahl
    if gefunden == 0:
        con.execute(f"""
            INSERT INTO neue_zeilen
            SELECT {kopf[0]}, NULL, {', '.join(kopf[1:])},
                   'unveraendert', NULL, NULL, NULL
        """)
    return gefunden


def baue(data_root: Path, *, trocken: bool = False) -> dict[str, Any]:
    begonnen = datetime.now(timezone.utc)
    ablage = for_root(data_root)
    verzeichnis = tabellenverzeichnis(data_root)
    # Derselbe Ablagepfad, den ``bereits_gezogen`` ableitet - einmal bestimmt
    # und zweimal gebraucht: fuer die gezogenen Paare und fuer das Bestehende.
    rel_tabelle = ablage.relativ(verzeichnis) or f"{SILVER_LAYER}/dataset={TABLE}"
    schon = bereits_gezogen(verzeichnis, data_root)

    con = connect()
    try:
        con.execute("""
            CREATE TABLE neue_zeilen (
                city VARCHAR, offense_id VARCHAR,
                vorher_run_id VARCHAR, run_id VARCHAR,
                vorher_am TIMESTAMP, beobachtet_am TIMESTAMP,
                art VARCHAR, feld VARCHAR, wert_alt VARCHAR, wert_neu VARCHAR)
        """)
        bericht: dict[str, Any] = {"quellen": [], "paare": 0, "uebersprungen": 0}
        vorrat: list[tuple[Quelle, list[Schnappschuss]]] = []
        for quelle in QUELLEN:
            laeufe = ablage.laeufe(quelle.praefix, fehler=TransformError)
            alle = schnappschuesse(laeufe)
            deltas = delta_laeufe(laeufe)
            vorrat.append((quelle, deltas))
            offen = [(a, b) for a, b in paare(alle)
                     if (a.run_id, b.run_id) not in schon]
            bericht["quellen"].append({
                "stadt": quelle.stadt, "schnappschuesse": len(alle),
                "deltas": len(deltas),
                "paare_gesamt": len(paare(alle)), "paare_neu": len(offen)})
            bericht["uebersprungen"] += len(paare(alle)) - len(offen)
            for vorher, nachher in offen:
                log.info("  %s: %s -> %s", quelle.stadt, vorher, nachher)
                if not trocken:
                    ziehe(con, quelle, ablage, vorher, nachher)
                bericht["paare"] += 1

        if trocken:
            return bericht

        # Das Bestehende kommt dazu, nicht weg: Sein Rohstoff ist moeglicher-
        # weise schon aufgeraeumt.
        #
        # **Ueber die Ablage, nicht ueber das Dateisystem.** Bis zum
        # 17.10.2026 stand hier ``alt.is_file()``. Im ``s3``-Modus ist die
        # lokale Arbeitskopie nach dem Publizieren entfernt, die Antwort war
        # also immer "es gibt nichts" - und damit kam das Bestehende **nicht**
        # dazu. Jeder Lauf schrieb nur, was er selbst gezogen hatte, und schob
        # alles Aeltere weg.
        #
        # Gemessen am selben Tag: 29 Paare und 39'650 Zeilen wurden zu 7
        # Paaren und 23'078. Die Vergleiche, deren Schnappschuesse der
        # Aufraeumlauf danach entfernte, sind damit endgueltig weg - und das
        # trifft genau die Zusage, mit der das Aufraeumen begruendet ist:
        # *"Was einmal herausgezogen wurde, bleibt stehen."*
        #
        # ``bereits_gezogen`` liest seit dem 16.10.2026 richtig; diese Stelle
        # liegt zwanzig Zeilen daneben und wurde uebersehen. Sechster Fall
        # derselben Familie in drei Tagen.
        roh = ", ".join(SPALTEN_ROH)
        if ablage.exists(rel_tabelle, PARQUET_FILE):
            quelle_alt = ablage.resolve_read_path(rel_tabelle, PARQUET_FILE)
            bestand = f"SELECT {roh} FROM read_parquet('{quelle_alt}') UNION ALL "
        else:
            bestand = ""
        con.execute(f"CREATE TEMP TABLE roh AS {bestand} "
                    f"SELECT {roh} FROM neue_zeilen")

        # Die Datierung laeuft ueber die **ganze** Tabelle, nicht nur ueber die
        # neuen Paare: Ein Paar, das beim ersten Mal nicht datierbar war, wird
        # es, sobald ein Delta dazukommt. Umgekehrt gilt es nicht - wird ein
        # Delta aufgeraeumt, bleibt die einmal bestimmte Datierung stehen. Die
        # Tatsachenspalten bleiben in beiden Faellen unberuehrt.
        # Was schon datiert war, kommt mit - die Datierung klebt. Steht die
        # Spalte noch nicht in der Datei, stammt sie aus Vertrag 1, und es
        # gibt nichts zu bewahren.
        con.execute("""
            CREATE TEMP TABLE alt_datierung (
                city VARCHAR, offense_id VARCHAR,
                vorher_run_id VARCHAR, run_id VARCHAR,
                zuerst_gesehen_in VARCHAR, zuerst_gesehen_am TIMESTAMP,
                datierung VARCHAR)
        """)
        if (ablage.exists(rel_tabelle, PARQUET_FILE)
                and SPALTEN_DATIERUNG[2] in abgelegtes_schema(ablage, rel_tabelle)):
            con.execute(f"""
                INSERT INTO alt_datierung
                SELECT DISTINCT city, offense_id, vorher_run_id, run_id,
                       zuerst_gesehen_in, zuerst_gesehen_am, datierung
                FROM read_parquet('{quelle_alt}') WHERE offense_id IS NOT NULL
            """)

        con.execute(RANG_SQL)
        con.execute("""
            CREATE OR REPLACE TEMP TABLE delta_schluessel (
                city VARCHAR, run_id VARCHAR, am TIMESTAMP, _id VARCHAR)
        """)
        gelesen = 0
        for quelle, deltas in vorrat:
            gelesen += datiere(con, quelle, ablage, deltas)
        bericht["deltas_gelesen"] = gelesen
        con.execute(f"CREATE TABLE {TABLE} AS {DATIERUNG_SQL}")

        bericht["row_count"] = con.execute(
            f"SELECT count(*) FROM {TABLE}").fetchone()[0]
        bericht["datierung"] = dict(con.execute(
            f"SELECT coalesce(datierung, 'ohne_schluessel'), count(*) "
            f"FROM {TABLE} GROUP BY 1 ORDER BY 1").fetchall())

        # Auch ohne neues Paar kann sich die Datierung bewegt haben - und ein
        # neuer Vertrag muss ankommen, selbst wenn sich keine Zahl bewegt.
        # Letzteres fehlte zuerst: Das Schema im Manifest blieb aus, weil der
        # Lauf nichts zu publizieren meinte.
        datierung_neu = bericht["datierung"] != (
            gelesene_datierung(ablage, rel_tabelle))
        vertrag_neu = abgelegter_vertrag(ablage, rel_tabelle) != CONTRACT_VERSION
        schema_neu = abgelegtes_schema(ablage, rel_tabelle) != set(SPALTEN)
        if (bericht["paare"]
                or not ablage.exists(rel_tabelle, PARQUET_FILE)
                or datierung_neu or vertrag_neu or schema_neu):
            ziel = publish(con, TABLE, verzeichnis,
                            manifest(con, bericht, begonnen))
            # **Und hinauf.** Bis zum 17.10.2026 fehlte diese Zeile, und damit
            # erreichte die Tabelle SeaweedFS nie: Jeder andere Silver-Bau
            # ruft ``publish_table``, dieser schrieb nur lokal. Im ``s3``-Modus
            # lag oben deshalb der Stand vom 3.10.2026 - eingefroren, waehrend
            # jeder Lauf unten eine neue Fassung baute und wieder verlor.
            #
            # Aufgefallen ist es erst, als das Aufraeumen nach dem Release die
            # lokale Kopie entfernte (``Storage.arbeitskopien_entfernen``):
            # 21,4 Mio. Zeilen gebaut, nie publiziert, dann geloescht. Falsche
            # Zeilen, wie sich zeigte - aber richtige waeren genauso weg.
            for_root(data_root).publish_table(ziel)
        return bericht
    finally:
        con.close()


def manifest(con: duckdb.DuckDBPyConnection, bericht: dict[str, Any],
             begonnen: datetime) -> dict[str, Any]:
    arten = dict(con.execute(
        f"SELECT art, count(*) FROM {TABLE} GROUP BY 1 ORDER BY 1").fetchall())
    return {
        "status": "complete",
        "contract_version": CONTRACT_VERSION,
        # Bis zum 3.10.2026 fehlte das hier, und es fiel niemandem auf: Der
        # Feldkatalog leitet Spalten und Typen aus dem Manifest ab, und ohne
        # ``schema`` blieb der Abschnitt dieser Tabelle **leer** - eine
        # Ueberschrift mit einer Tabellenkopfzeile und nichts darunter. Auch
        # der Waechter, der jede gebaute Spalte auf eine Beschreibung haelt,
        # pruefte dadurch nichts. Die einzige Silver-Tabelle ohne Schema.
        "schema": schema_of(con, TABLE),
        "code_version": code_stand(),
        "layer": SILVER_LAYER,
        "table": TABLE,
        "grain": "ein geaendertes Feld einer Zeile zwischen zwei Schnappschuessen",
        "built_at_utc": begonnen.isoformat().replace("+00:00", "Z"),
        "tool": f"duckdb {duckdb.__version__}",
        "format": "parquet (snappy)",
        "row_count": bericht["row_count"],
        "append_only": True,
        "arten": arten,
        "quellen": bericht["quellen"],
        "hinweis": (
            "Append-only: Was einmal herausgezogen wurde, bleibt stehen, auch "
            "wenn die Bronze-Laeufe aufgeraeumt sind. Verglichen werden nur "
            "Vollabzuege (manifeste.Lauf.vollabzug)."),
    }


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    zerleger = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    zerleger.add_argument("--data-root", type=Path, default=None)
    zerleger.add_argument("--trocken", action="store_true",
                          help="nur zeigen, welche Paare gezogen wuerden")
    args = zerleger.parse_args(argv)

    wurzel = for_root(args.data_root).local_root
    bericht = baue(wurzel, trocken=args.trocken)

    for q in bericht["quellen"]:
        log.info("%s: %s Schnappschuesse, %s Paare (%s neu)",
                 q["stadt"], q["schnappschuesse"], q["paare_gesamt"],
                 q["paare_neu"])
        if q["schnappschuesse"] < 2:
            log.warning(
                "  %s hat weniger als zwei Vollschnappschuesse - ohne einen "
                "zweiten laesst sich nichts vergleichen.", q["stadt"])

    if args.trocken:
        log.info("Trockenlauf: %s Paare waeren zu ziehen.", bericht["paare"])
        return 0

    log.info("%s: %s Zeilen (%s Paare neu, %s schon gezogen)",
             TABLE, f"{bericht['row_count']:,}", bericht["paare"],
             bericht["uebersprungen"])
    if bericht["paare"]:
        # Ueber die Ablage und nicht ueber den Pfad - dasselbe wie in den
        # uebrigen Stufenmodulen: Im s3-Modus ist die lokale Arbeitskopie
        # nach dem Publizieren weg. Siehe ``Storage.tabellen_manifest``.
        gelesen = for_root(args.data_root).tabellen_manifest(
            tabellenverzeichnis(wurzel))
        for art, n in sorted(gelesen.get("arten", {}).items()):
            log.info("  %-14s %s", art, f"{n:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
