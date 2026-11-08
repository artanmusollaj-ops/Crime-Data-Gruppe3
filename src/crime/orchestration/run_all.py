"""Faehrt die ganze Strecke in der richtigen Reihenfolge.

    python -m orchestration.run_all                  # alles, inklusive Ingestion
    python -m orchestration.run_all --ohne-ingestion # nur neu ableiten
    python -m orchestration.run_all --bis silver     # bis zu einer Stufe
    python -m orchestration.run_all --trocken        # nur zeigen, was liefe
    python -m orchestration.run_all --jahre 2021-2026 --bis silver

``--jahre`` nimmt einen Jahrgang, einen Bereich oder eine Liste; Vorgabe ist
2024. Die Kriminalquellen laufen je Jahrgang, die Census-Stufen je Vintage,
alles andere einmal. Ab 2025 bleibt es beim 2024er Vintage - ein neueres gibt
es nicht. Mehrere Vintages **und** Gold im Lauf lehnt der Controller ab, weil
``build_gold`` noch ein einzelnes ``--vintage`` nimmt.

Am Ende steht ``data/pipeline_run.json``: welche Stufen liefen, wie lange, auf
**welchen Bronze-Laeufen** das Ergebnis ruht, und ein Fingerabdruck darueber.
Zwei Laeufe auf denselben Eingaben tragen denselben Fingerabdruck - damit
laesst sich eine Zahl einem Stand zuordnen, statt ihn zu vermuten.

Warum die Stufen als Unterprozesse laufen: Ihre Kommandozeile **ist** die
Schnittstelle, und sie ist getestet. Sie zu importieren und die ``main`` zu
rufen waere ein zweiter Weg in denselben Code - und der zweite Weg ist der, der
irgendwann anders funktioniert als der erste.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections.abc import Iterable
from typing import NamedTuple

from census_pipeline import NEWEST_VINTAGE, vintage_for, vintages_for
from manifeste import WURZEL_VARIABLE, WURZELZEICHEN
from manifeste import fingerabdruck as manifeste_fingerabdruck
from manifeste import projektwurzel
from orchestration import LAUF_MANIFEST
from storage import StorageError, for_root


LOG = logging.getLogger("run_all")


class Stufe(NamedTuple):
    """Ein Aufruf, der genau eine Sache tut."""

    gruppe: str          # ingestion | silver | gold | serving
    name: str
    modul: str
    argumente: tuple[str, ...] = ()
    # Welchen Bronze-Bestand diese Stufe fuellt, so wie ``aktualitaet`` ihn
    # benennt. Nur Ingestion-Stufen haben einen. Damit ist die Liste der
    # *erwarteten* Quellen abgeleitet statt gepflegt - und eine Quelle, die
    # gar nicht da ist, faellt auf. Vorher wurde nur geprueft, was schon
    # existierte: Ein leerer Bestand galt als frisch.
    quelle: str = ""
    # Worueber diese Stufe sich wiederholt, wenn mehrere Jahrgaenge laufen:
    # "jahr" (die Kriminalquellen), "vintage" (Census und seine Silver-Tabellen),
    # "alle" (einmal, bekommt aber alle Vintages als Liste - so macht es Gold)
    # oder "" (einmal, ohne Jahresangabe). ``flagge`` ist die Option, mit der
    # die Stufe die Zahl annimmt - sie heisst nicht ueberall gleich.
    je: str = ""
    flagge: str = ""

    def befehl(self, data_root: Path | None = None) -> list[str]:
        """Der Aufruf, mit dem diese Stufe laeuft.

        ``--data-root`` wird **immer** mitgegeben, nicht nur wenn jemand es
        getippt hat. Bis zum 15.9.2026 wurde es gar nicht weitergereicht: Der
        Gesamtlauf inventarisierte und protokollierte im gewaehlten
        Verzeichnis, die dreizehn Unterprozesse arbeiteten im Standardordner.
        Eine externe Pruefung hat die abgefangenen Befehlszeilen gezeigt -
        keine einzige trug die Option.

        Auch ohne ``--data-root`` steht hier jetzt der aufgeloeste Pfad. Das
        ist kein Mehraufwand und beseitigt eine zweite Fehlerquelle: Vater und
        Kind lesen dieselbe Umgebung, aber nicht mehr notwendigerweise
        gleich - etwa wenn ein Unterprozess eine andere ``.env`` faende.
        """
        wurzel = [] if data_root is None else ["--data-root", str(data_root)]
        return [sys.executable, "-m", self.modul, *self.argumente, *wurzel]


# Die Reihenfolge ist die Aussage dieses Moduls. Alles andere ist Buchhaltung.
#
# Zwei Stellen darin sind nicht offensichtlich und haben schon Zeit gekostet:
#   * TIGER braucht **zwei** Aufrufe. Ohne ``place`` bekommt dim_tract keine
#     Stadtzuordnung - und der Bau scheitert dabei nicht.
#   * ``build_crime_offense`` liest ``silver/tract``, muss also nach ihm laufen.
#   * ``build_source_change`` laeuft zuletzt in Silver: Es zieht den
#     Unterschied zweier Schnappschuesse heraus, und erst danach darf
#     ``orchestration.aufraeumen`` sie wegnehmen.
STUFEN: tuple[Stufe, ...] = (
    Stufe("ingestion", "chicago", "chicago_pipeline.download_chicago",
          quelle="city=chicago", je="jahr", flagge="--year"),
    # Seit dem 18.9.2026 ein Delta wie bei Chicago: Der erste Aufruf laedt den
    # Jahrgang voll, spaetere nur, was sich seit dem Wasserzeichen geaendert
    # hat. Der Filter geht ueber ``updated_at``, nicht ueber das Tatdatum -
    # ein Delta nach Tatdatum saehe keine einzige Korrektur.
    Stufe("ingestion", "detroit", "detroit_pipeline.extract_detroit",
          ("--mode", "delta"), quelle="city=detroit",
          je="jahr", flagge="--years"),
    Stufe("ingestion", "tiger_tract", "census_pipeline.download_tiger",
          ("--auslieferung", "tract"), quelle="dataset=tiger_tract",
          je="vintage", flagge="--vintage"),
    Stufe("ingestion", "tiger_place", "census_pipeline.download_tiger",
          ("--auslieferung", "place"), quelle="dataset=tiger_place",
          je="vintage", flagge="--vintage"),
    Stufe("ingestion", "acs", "census_pipeline.download_acs",
          quelle="dataset=acs5_tract", je="vintage", flagge="--vintage"),
    Stufe("ingestion", "noaa", "weather_pipeline.download_noaa",
          quelle="dataset=noaa_ghcnd"),

    Stufe("silver", "tract", "silver_pipeline.build_tract",
          je="vintage", flagge="--vintage"),
    Stufe("silver", "place", "silver_pipeline.build_place",
          je="vintage", flagge="--vintage"),
    Stufe("silver", "weather_day", "silver_pipeline.build_weather_day"),
    Stufe("silver", "crime_offense", "silver_pipeline.build_crime_offense"),
    # **Die Historisierung gehoert in den Lauf, nicht in einen Merkzettel.**
    # Bis zum 16.10.2026 stand ``build_source_change`` hier nicht, und kein
    # Skript und kein Zeitplan rief es - es lief nur, wenn jemand daran
    # dachte. Zwei Folgen, beide schlecht: Der Unterschied zweier
    # Schnappschuesse wurde nie herausgezogen, und ``orchestration.aufraeumen``
    # hielt nach seiner Regel 4 jeden Vollschnappschuss fest. Auf ``srv01``
    # lagen deshalb 141 Bronze-Laeufe, an denen der Silver-Bau erstickte.
    #
    # Sie laeuft **nach** ``crime_offense``: Beide lesen dieselben
    # Schnappschuesse, und was die Falldaten nicht tragen, soll zuerst
    # gebaut sein. Vor dem Aufraeumen muss sie gelaufen sein - danach ist
    # der Rohstoff entbehrlich, vorher nicht.
    Stufe("silver", "source_change", "silver_pipeline.build_source_change"),

    # Einmal, aber mit **allen** Vintages: Gold legt ``dim_tract_acs`` je
    # Vintage an und gibt jeder Tat mit ``population_vintage`` ihren Nenner.
    Stufe("gold", "gold", "gold_pipeline.build_gold",
          je="alle", flagge="--acs-vintages"),

    # Die Vergleichstabellen vor der Datenbank, damit sie Sichten bekommen.
    Stufe("serving", "comparison", "serving.build_comparison"),
    # Die Quellbewegung fuer das Brett gleichen Namens - aus silver/
    # source_change, das deshalb vorher in Silver gelaufen sein muss.
    Stufe("serving", "source_movement", "serving.build_source_movement"),
    Stufe("serving", "analyse_db", "serving.build_analysis_db"),
    Stufe("serving", "tracts_geojson", "serving.export_geojson"),
)

GRUPPEN = ("ingestion", "silver", "gold", "serving")

# Die Bestaende, die nach einer vollstaendigen Ingestion dasein muessen.
ERWARTETE_QUELLEN: tuple[str, ...] = tuple(
    sorted({s.quelle for s in STUFEN if s.quelle})
)


# ---------------------------------------------------------------------------
# Jahrgaenge und Vintages
# ---------------------------------------------------------------------------

# Der Jahrgang, auf dem das Projekt bis zum 3.10.2026 stand. Vorgabe bleibt er,
# damit ein Aufruf ohne ``--jahre`` dasselbe tut wie vorher - ein Mehrjahreslauf
# ist eine Ansage, kein Nebeneffekt eines Updates.
VORGABE_JAHRE: tuple[int, ...] = (2024,)

# Die Vintage-Regel wohnt in ``census_pipeline``: Sie ist eine Tatsache ueber
# die ACS-Quelle, und Gold braucht sie genauso. Hier stehen nur die deutschen
# Namen, unter denen dieses Modul sie fuehrt - eine zweite Fassung waere eine
# zweite zu pflegen.
JUENGSTES_VINTAGE = NEWEST_VINTAGE
vintage_fuer = vintage_for
vintages_fuer = vintages_for

# Chicago reicht bis 2001 zurueck; frueher gibt es keinen Jahrgang.
FRUEHESTES_JAHR = 2001


def jahre_aus_text(text: str) -> tuple[int, ...]:
    """``2024``, ``2021-2026`` oder ``2021,2023,2024`` - immer aufsteigend.

    Doppelte Angaben fallen weg: Ein Jahrgang zweimal zu laden ergaebe zwei
    Laeufe mit demselben Inhalt, und die Entdoppelung in Silver verbirgt das.
    """
    gefunden: set[int] = set()
    for teil in text.split(","):
        teil = teil.strip()
        if not teil:
            continue
        if "-" in teil.lstrip("-"):
            von_bis = teil.split("-", 1)
            try:
                von, bis = int(von_bis[0]), int(von_bis[1])
            except ValueError:
                raise ValueError(f"{teil!r} ist kein Jahresbereich") from None
            if von > bis:
                raise ValueError(f"{teil!r} laeuft rueckwaerts")
            gefunden.update(range(von, bis + 1))
        else:
            try:
                gefunden.add(int(teil))
            except ValueError:
                raise ValueError(f"{teil!r} ist kein Jahr") from None

    if not gefunden:
        raise ValueError("kein Jahr angegeben")
    obergrenze = datetime.now(timezone.utc).year + 1
    daneben = sorted(j for j in gefunden if not FRUEHESTES_JAHR <= j <= obergrenze)
    if daneben:
        raise ValueError(
            f"{', '.join(str(j) for j in daneben)} liegt ausserhalb von "
            f"{FRUEHESTES_JAHR} bis {obergrenze}"
        )
    return tuple(sorted(gefunden))


def jahre_argument(text: str) -> tuple[int, ...]:
    """``jahre_aus_text`` fuer argparse - mit erhaltener Begruendung.

    Argparse faengt ``ValueError`` aus einem ``type=``-Aufruf und ersetzt die
    Meldung durch *"invalid ... value"*. Der Benutzer erfuehre damit, dass
    seine Angabe falsch ist, aber nicht warum - und das Warum ist der ganze
    Sinn der Pruefung. ``ArgumentTypeError`` reicht argparse durch.
    """
    try:
        return jahre_aus_text(text)
    except ValueError as fehler:
        raise argparse.ArgumentTypeError(str(fehler)) from None


def entfalte(stufe: Stufe, jahre: Iterable[int]) -> list[Stufe]:
    """Eine Stufe, so oft wie ihre Achse es verlangt.

    Der Name bekommt die Zahl angehaengt, damit das Protokoll in
    ``pipeline_run.json`` sagt, welcher Jahrgang wie lange brauchte, und ein
    Abbruch die Stelle nennt statt nur die Stufe.
    """
    if not stufe.je:
        return [stufe]
    if stufe.je == "alle":
        liste = ",".join(str(v) for v in vintages_fuer(jahre))
        return [stufe._replace(argumente=(*stufe.argumente, stufe.flagge, liste))]
    zahlen = (tuple(sorted(set(jahre))) if stufe.je == "jahr"
              else vintages_fuer(jahre))
    return [
        stufe._replace(name=f"{stufe.name}_{z}",
                       argumente=(*stufe.argumente, stufe.flagge, str(z)))
        for z in zahlen
    ]


# ---------------------------------------------------------------------------
# Herkunft
# ---------------------------------------------------------------------------


def bronze_laeufe(data_root: Path) -> dict[str, list[str]]:
    """Jeder fertige Bronze-Lauf, nach Quelle geordnet.

    Das ist die Antwort auf *"auf welchem Stand beruht diese Zahl?"*. Gelesen
    werden die Manifeste selbst und nicht die Verzeichnisnamen: Ein Lauf, der
    unterwegs abgebrochen ist, liegt zwar da, gilt aber nicht.
    """
    gefunden: dict[str, list[str]] = {}
    for lauf in for_root(data_root).laeufe("bronze", "**/manifest.json"):
        # Der erste Pfadteil unter bronze/ benennt die Quelle:
        # city=chicago, dataset=tiger_tract, dataset=noaa_ghcnd ...
        quelle = lauf.relativ.split("/")[1]
        gefunden.setdefault(quelle, []).append(lauf.run_id)
    return {k: sorted(set(v)) for k, v in sorted(gefunden.items())}


# Derselbe Abdruck wie in den Tabellenmanifesten - er kommt aus manifeste,
# damit "derselbe Stand" ueberall dasselbe heisst.
fingerabdruck = manifeste_fingerabdruck


def aktualitaet(data_root: Path) -> dict[str, str]:
    """Wann jede Quelle zuletzt geladen wurde.

    Keine Alarmierung - nur die Zahl, ohne die man sie nicht bauen kann. Wer
    sehen will, ob eine Quelle veraltet, sieht hier nach.
    """
    juengste: dict[str, str] = {}
    for lauf in for_root(data_root).laeufe("bronze", "**/manifest.json"):
        quelle = lauf.relativ.split("/")[1]
        wann = lauf.abgeschlossen_um
        if wann and wann > juengste.get(quelle, ""):
            juengste[quelle] = wann
    return dict(sorted(juengste.items()))


def veraltete_quellen(
    data_root: Path, maximal_alter_tage: float, *, jetzt: datetime | None = None,
    erwartet: Iterable[str] | None = None,
) -> dict[str, float | None]:
    """Quellen, die zu alt sind oder ganz fehlen - mit ihrem Alter in Tagen.

    Bis hierher wurde die Aktualitaet nur **aufgezeichnet**: Das Gesamtmanifest
    nannte je Quelle den juengsten Lauf, und niemand las es. Eine Zahl, die
    niemand gegen etwas haelt, ist keine Kontrolle. Hier wird sie gegen eine
    Schwelle gehalten.

    Eine Quelle ohne einzigen fertigen Lauf steht mit ``None`` da - sie ist
    nicht "frisch", sie ist nicht da. Der Docstring sagte das schon, der Code
    tat es nicht: Geprueft wurde nur, was ``aktualitaet`` gefunden hatte, und
    das sind genau die vorhandenen Quellen. Bei leerem Bestand kam ``{}``
    heraus, also "alles in Ordnung". Eine externe Pruefung hat das am
    15.9.2026 vorgerechnet.

    ``erwartet`` kommt aus ``ERWARTETE_QUELLEN`` und damit aus den Stufen
    selbst. Eine sechste Quelle taucht hier auf, sobald sie eine Stufe hat.
    """
    jetzt = jetzt or datetime.now(timezone.utc)
    erwartet = ERWARTETE_QUELLEN if erwartet is None else erwartet
    vorhanden = aktualitaet(data_root)
    zu_alt: dict[str, float | None] = {}
    for quelle in sorted(set(erwartet) | set(vorhanden)):
        wann = vorhanden.get(quelle)
        if wann is None:
            zu_alt[quelle] = None
            continue
        stempel = datetime.fromisoformat(wann.replace("Z", "+00:00"))
        if stempel.tzinfo is None:
            stempel = stempel.replace(tzinfo=timezone.utc)
        alter = (jetzt - stempel) / timedelta(days=1)
        if alter > maximal_alter_tage:
            zu_alt[quelle] = round(alter, 1)
    return zu_alt


def alterssatz(quelle: str, tage: float | None, schwelle: float) -> str:
    """Eine Zeile fuer Log und Zusammenfassung - fehlend liest sich anders als alt."""
    if tage is None:
        return f"{quelle}: kein fertiger Lauf vorhanden"
    return f"{quelle}: {tage:.1f} Tage alt, erlaubt sind {schwelle}"


def zeilenzahlen(data_root: Path) -> dict[str, int]:
    """Was am Ende dasteht - je Tabelle eine Zahl aus ihrem Manifest."""
    return {
        f"{t.schicht}/{t.name}": t.zeilen
        for t in for_root(data_root).tabellen()
        if t.zeilen is not None
    }


# ---------------------------------------------------------------------------
# Der Lauf
# ---------------------------------------------------------------------------


def auswahl(ohne_ingestion: bool, bis: str | None,
            jahre: Iterable[int] = VORGABE_JAHRE) -> list[Stufe]:
    """Welche Stufen laufen, in welcher Reihenfolge, fuer welche Jahrgaenge.

    Mit einem einzigen Jahrgang ist die Entfaltung die Identitaet: Es kommen
    genau die vierzehn Stufen heraus, die ``STUFEN`` nennt. ``STUFEN``
    beschreibt die **Form** der Strecke - daraus entstehen das Architekturbild
    und die Referenz-Startseite, und die zaehlen vierzehn. Wie oft eine Stufe
    laeuft, ist dagegen eine Eigenschaft des Laufs und steht hier.
    """
    stufen = [s for s in STUFEN
              if not (ohne_ingestion and s.gruppe == "ingestion")]
    if bis:
        grenze = GRUPPEN.index(bis)
        stufen = [s for s in stufen if GRUPPEN.index(s.gruppe) <= grenze]
    return [entfaltet for s in stufen for entfaltet in entfalte(s, jahre)]


def fahre(stufen: list[Stufe], projekt_root: Path,
          data_root: Path | None = None, *,
          behalte_lokal: bool = False) -> list[dict]:
    """Eine Stufe nach der anderen. Beim ersten Fehler ist Schluss.

    Weiterzulaufen waere schlimmer als abzubrechen: Die naechste Stufe baute
    auf einem halben Stand und meldete Erfolg.

    **``behalte_lokal`` muss ueber die Umgebung gehen und nicht im Prozess.**
    Jede Stufe ist ein eigener Prozess (``sys.executable -m ...``), und was
    hier an einer ``Config`` gesetzt wuerde, saehe keine von ihnen. Gesetzt
    wird es, wenn ein Release folgt: Dann brauchen die Stufen ihre lokalen
    Arbeitskopien noch, weil ``storage.release.sammle`` das Dateisystem liest.
    Am 16.10.2026 fehlten dem Release sieben Gold-Tabellen bei einer gruenen
    Strecke, weil jede Stufe ihre Kopie sofort entfernt hatte.
    """
    umgebung = None
    if behalte_lokal:
        umgebung = dict(os.environ, STORAGE_KEEP_LOCAL="1")
    protokoll: list[dict] = []
    for i, stufe in enumerate(stufen, 1):
        LOG.info("[%d/%d] %s · %s", i, len(stufen), stufe.gruppe, stufe.name)
        befehl = stufe.befehl(data_root)
        start = time.perf_counter()
        fertig = subprocess.run(befehl, cwd=projekt_root, env=umgebung)
        dauer = round(time.perf_counter() - start, 1)
        protokoll.append({
            "gruppe": stufe.gruppe,
            "name": stufe.name,
            "befehl": " ".join(befehl[1:]),
            "sekunden": dauer,
            "exit": fertig.returncode,
        })
        if fertig.returncode != 0:
            LOG.error(
                "%s · %s ist mit %d gescheitert. Abgebrochen - jede weitere "
                "Stufe baute sonst auf einem halben Stand.",
                stufe.gruppe, stufe.name, fertig.returncode,
            )
            break
        LOG.info("      fertig in %.1f s", dauer)
    return protokoll


def schreibe_manifest(data_root: Path, manifest: dict) -> Path:
    ziel = data_root / LAUF_MANIFEST
    ziel.parent.mkdir(parents=True, exist_ok=True)
    arbeit = ziel.with_name(f".{ziel.name}.part")
    arbeit.write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    arbeit.replace(ziel)
    return ziel


def lauf(data_root: Path, projekt_root: Path, *,
         ohne_ingestion: bool = False, bis: str | None = None,
         maximal_alter_tage: float | None = None,
         release: bool | None = None, holen: bool = True,
         jahre: Iterable[int] = VORGABE_JAHRE) -> dict:
    """Die ganze Strecke - und am Ende, wenn alles gruen ist, ein Release.

    ``release``: ``None`` heisst *wenn die Ablage publiziert* (hybrid, s3),
    ``True`` erzwingt eines auch lokal, ``False`` unterlaesst es. Ein Release
    entsteht nur nach einem vollstaendigen, gruenen Lauf bis einschliesslich
    Serving - ein halber Stand bekommt keine Kennung. Scheitert das Release,
    ist der Lauf gescheitert: Ein publizierender Modus, der nicht publiziert,
    hat sein Versprechen nicht gehalten.

    ``holen``: Im Hybridmodus werden zuerst alle Raw- und Bronze-Laeufe
    geholt, die oben liegen und lokal fehlen - jeder Rechner soll den ganzen
    Bestand haben, und Laeufe sind unveraenderlich, eine Kopie kann nicht
    veralten. Scheitert das Holen, laeuft nichts weiter: Silver auf einem
    halben Bronze waere genau der Stand, den niemand erklaeren kann. Im
    ``s3``-Modus wird **nicht** geholt: Er ist als *ohne lokalen Bestand*
    definiert, und ein Lauf, der ihn fuellte, widerspraeche seiner eigenen
    Definition - dort liest Silver Bronze direkt von S3. Von Hand geht es
    trotzdem (``python -m storage holen --wirklich``).
    """
    from storage.verwaltet import sperre
    sperre(data_root)
    from storage.analysesitzung import schreibzugriff
    with schreibzugriff(data_root, invalidieren=True):
        jahre = tuple(sorted(set(jahre)))
        stufen = auswahl(ohne_ingestion, bis, jahre)
        begonnen = datetime.now(timezone.utc)
        zu_alt: dict[str, float | None] = {}

        geholt: list[str] = []
        holen_gescheitert: str | None = None
        ablage = for_root(data_root)
        if holen and ablage.backend == "hybrid":
            try:
                geholt = ablage.hole_fehlende_laeufe(("raw", "bronze"))
            except StorageError as fehler:
                holen_gescheitert = str(fehler)
                LOG.error("Laeufe nicht geholt: %s. Nichts gebaut.", fehler)

        # Ohne Ingestion werden die Daten nicht frischer. Sind sie schon zu alt,
        # lohnt sich keine Stufe - und ein Gold auf veraltetem Bronze waere genau
        # die Zahl, die dann auf einer Folie landet.
        if maximal_alter_tage is not None and ohne_ingestion:
            zu_alt = veraltete_quellen(data_root, maximal_alter_tage)
            for quelle, tage in zu_alt.items():
                LOG.error("%s. Nichts gebaut.",
                          alterssatz(quelle, tage, maximal_alter_tage))

        # Mit Ingestion in zwei Schritten: erst laden, dann pruefen, dann ableiten.
        #
        # Bis zum 15.9.2026 lief die Pruefung nach **allen** dreizehn Stufen. Der
        # Lauf endete dann zwar mit "failed", aber Gold und Serving waren gebaut -
        # aus Daten, die der Lauf selbst als zu alt erkannt hatte. Eine externe
        # Pruefung hat genau das vorgefuehrt. Eine Kontrolle, die erst nach der
        # Veroeffentlichung greift, ist ein Protokoll, keine Kontrolle.
        geladen = [s for s in stufen if s.gruppe == "ingestion"]
        abgeleitet = [s for s in stufen if s.gruppe != "ingestion"]

        # Folgt ein Release, brauchen die abgeleiteten Stufen ihre lokalen
        # Arbeitskopien noch: ``storage.release.sammle`` liest das Dateisystem.
        # Nur sie - die Ingestion publiziert Laeufe, und die sollen weiterhin
        # sofort weg (``Storage._lokal_entfernen_falls_s3``).
        folgt_release = bis is None and (
            release is True or (release is None and ablage.config.publiziert))
        behalte_lokal = folgt_release and ablage.backend == "s3"

        protokoll: list[dict] = []
        if not zu_alt and holen_gescheitert is None:
            protokoll = fahre(geladen, projekt_root, data_root)
            ingestion_ok = (all(s["exit"] == 0 for s in protokoll)
                            and len(protokoll) == len(geladen))

            if maximal_alter_tage is not None and not ohne_ingestion and ingestion_ok:
                zu_alt = veraltete_quellen(data_root, maximal_alter_tage)
                for quelle, tage in zu_alt.items():
                    LOG.error("%s. Nichts abgeleitet.",
                              alterssatz(quelle, tage, maximal_alter_tage))

            if ingestion_ok and not zu_alt:
                protokoll += fahre(abgeleitet, projekt_root, data_root,
                                   behalte_lokal=behalte_lokal)

        gelaufen = all(s["exit"] == 0 for s in protokoll) and len(protokoll) == len(stufen)

        geschafft = gelaufen and not zu_alt and holen_gescheitert is None

        freigabe: dict | None = None
        if geschafft and folgt_release:
            from orchestration import release as release_modul
            try:
                freigabe = release_modul.bilde_und_publiziere(
                    data_root, ablage, jahre)
                LOG.info("Release %s: %d Dateien%s", freigabe["release_id"],
                         freigabe["files"],
                         ", publiziert" if freigabe["published"] else ", nur lokal")
            except StorageError as fehler:
                LOG.error("Release gescheitert: %s", fehler)
                freigabe = {"status": "failed", "error": str(fehler)}
                geschafft = False

        # Jetzt, und nicht in den Stufen: Was ``behalte_lokal`` aufgeschoben hat,
        # geht hier weg - aber nur, was oben wirklich liegt **und dasselbe ist**
        # (``Storage.arbeitskopien_entfernen`` vergleicht je Tabelle die
        # Manifeste).
        #
        # **Nicht nach einem gescheiterten Release.** Hier stand das Gegenteil,
        # mit der Begruendung "oben liegt er vollstaendig". Am 17.10.2026 hat ein
        # ``InternalError`` von SeaweedFS den Upload beim 26. von 28 Objekten
        # abgebrochen - und danach waren die Kopien weg, obwohl genau sie fuer den
        # zweiten Versuch gebraucht wurden. Ein Lauf von zwoelf Minuten, nur um
        # wiederherzustellen, was dalag. Die Begruendung stimmte nicht: Ist der
        # Upload gescheitert, liegt oben *nicht* alles.
        gescheitert = (freigabe or {}).get("status") == "failed"
        if behalte_lokal and gescheitert:
            LOG.info("Lokale Arbeitskopien bleiben: Das Release ist gescheitert, "
                     "und ohne sie braeuchte der zweite Versuch einen neuen Bau.")
        if behalte_lokal and not gescheitert:
            weg = ablage.arbeitskopien_entfernen()
            if weg:
                LOG.info("%d lokale Arbeitskopie(n) nach dem Release entfernt",
                         len(weg))

        # Der Bestand fuer das Manifest liest im Hybridmodus auch S3. Faellt die
        # Ablage aus, ist das kein Grund fuer einen Traceback: Der Lauf ist dann
        # ohnehin gescheitert, und das Protokoll soll trotzdem geschrieben werden -
        # mit dem, was lokal sichtbar ist, und mit dem Grund. Am 17.9.2026 hat
        # genau hier ein Netzausfall sechzig Zeilen botocore-Stapel gedruckt,
        # obwohl die Zeile darueber schon "Nichts gebaut" gemeldet hatte.
        bestand_fehler: str | None = None
        try:
            laeufe = bronze_laeufe(data_root)
            frische = aktualitaet(data_root)
        except StorageError as fehler:
            bestand_fehler = str(fehler)
            LOG.error("Bestand nicht aufnehmbar: %s", fehler)
            laeufe, frische = {}, {}
            geschafft = False

        manifest = {
            "status": "complete" if geschafft else "failed",
            "years": list(jahre),
            "vintages": list(vintages_fuer(jahre)),
            "fetched_runs": geholt,
            "fetch_error": holen_gescheitert,
            "inventory_error": bestand_fehler,
            "release": freigabe,
            "started_at_utc": begonnen.isoformat(),
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "stages": protokoll,
            "input_bronze_runs": laeufe,
            "input_fingerprint": fingerabdruck(laeufe),
            "source_freshness": frische,
            "freshness_check": {
                "max_age_days": maximal_alter_tage,
                "stale": zu_alt,
            },
            # Liest ebenfalls die Ablage; nach einem gescheiterten Lauf wird es
            # ohnehin uebersprungen, und wenn nicht, gilt dasselbe wie oben.
            "output_rows": zeilenzahlen(data_root) if geschafft else {},
        }
        import uuid
        from storage.analysesitzung import bestaetige
        manifest["run_id"] = uuid.uuid4().hex
        schreibe_manifest(data_root, manifest)
        if geschafft and any(s.gruppe == "silver" for s in stufen):
            bestaetige(data_root, run_id=manifest["run_id"], projekt_root=projekt_root,
                       release_id=(freigabe or {}).get("release_id"),
                       bereiche=sorted({s.gruppe for s in stufen}))
        return manifest


def arguments() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Faehrt Ingestion, Silver, Gold und Serving in der "
                    "richtigen Reihenfolge."
    )
    p.add_argument("--data-root", type=Path, default=None,
                   help="Wurzel der Schichten (Vorgabe: LOCAL_DATA_ROOT oder data)")
    p.add_argument("--ohne-ingestion", action="store_true",
                   help="nur neu ableiten, ohne die Quellen anzufassen")
    p.add_argument("--bis", choices=GRUPPEN,
                   help="nach dieser Gruppe aufhoeren")
    p.add_argument("--jahre", type=jahre_argument, default=VORGABE_JAHRE,
                   metavar="JAHRE",
                   help="Jahrgaenge: 2024, 2021-2026 oder 2021,2023 "
                        f"(Vorgabe {VORGABE_JAHRE[0]}). Die Census-Vintages "
                        f"folgen daraus; ab {JUENGSTES_VINTAGE + 1} bleibt es "
                        f"beim {JUENGSTES_VINTAGE}er")
    p.add_argument("--trocken", action="store_true",
                   help="nur zeigen, was liefe")
    p.add_argument("--ohne-holen", dest="holen", action="store_false",
                   help="fehlende Raw- und Bronze-Laeufe nicht von SeaweedFS holen")
    freigabe = p.add_mutually_exclusive_group()
    freigabe.add_argument("--release", dest="release", action="store_true", default=None,
                          help="nach gruenem Lauf ein Release bilden, auch im local-Modus")
    freigabe.add_argument("--ohne-release", dest="release", action="store_false",
                          help="kein Release, auch wenn die Ablage publiziert")
    p.add_argument("--maximal-alter-tage", type=float, default=None, metavar="TAGE",
                   help="scheitern, wenn der juengste Lauf einer Quelle aelter ist "
                        "(ohne Angabe wird die Aktualitaet nur aufgezeichnet)")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def main() -> int:
    args = arguments()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    # Das Arbeitsverzeichnis **jedes** Unterprozesses (siehe ``fahre``), und
    # damit die Stelle, gegen die ``config/`` und ``docs/intern/`` aufgeloest
    # werden. Bis zum 6.10.2026 stand hier ``parents[3]`` - eine Formel, die
    # nur bei der editierbaren Installation im Projekt stimmt und sonst still
    # auf ein beliebiges Verzeichnis zeigt. Jetzt kommt die Wurzel aus einer
    # ausdruecklichen Quelle, und wo sie fehlt, ist hier Schluss: Ein Lauf im
    # falschen Verzeichnis scheitert nicht, er baut ein Gold ohne Crosswalks.
    projekt_root = projektwurzel()
    if projekt_root is None:
        raise SystemExit(
            f"Die Projektwurzel ist nicht ableitbar. {WURZEL_VARIABLE} auf das "
            f"Verzeichnis setzen, das {' und '.join(WURZELZEICHEN)} traegt - "
            "oder das Paket editierbar installieren "
            "('python -m pip install -e .')."
        )

    stufen = auswahl(args.ohne_ingestion, args.bis, args.jahre)
    if args.trocken:
        jahrtext = ", ".join(str(j) for j in args.jahre)
        vintagetext = ", ".join(str(v) for v in vintages_fuer(args.jahre))
        print(f"Jahrgaenge {jahrtext}; Census-Vintages {vintagetext}")
        print(f"\n{len(stufen)} Stufen, in dieser Reihenfolge:\n")
        for i, s in enumerate(stufen, 1):
            print(f"  {i:>2}. {s.gruppe:<10} {s.name:<16} "
                  f"python -m {s.modul} {' '.join(s.argumente)}".rstrip())
        return 0

    try:
        manifest = lauf(for_root(args.data_root).local_root, projekt_root,
                        ohne_ingestion=args.ohne_ingestion, bis=args.bis,
                        maximal_alter_tage=args.maximal_alter_tage,
                        release=args.release, holen=args.holen,
                        jahre=args.jahre)
    except StorageError as fehler:
        # Der Schlussfang. Was die Ablage angeht, ist innen schon abgefangen;
        # hier steht er, damit kein Weg uebrigbleibt, der einen botocore-Stapel
        # druckt - das README sagt "ein Satz statt eines Tracebacks" zu.
        print(f"\nDie Ablage antwortet nicht: {fehler}")
        print("'python -m storage' prueft die Verbindung. Lokal weiterarbeiten: "
              "STORAGE_BACKEND=local in .env.")
        return 1

    print()
    if manifest["status"] != "complete":
        zu_alt = manifest["freshness_check"]["stale"]
        if zu_alt:
            alt_ = ", ".join(
                f"{q} (fehlt)" if t is None else f"{q} ({t} Tage)"
                for q, t in zu_alt.items()
            )
            print(f"Zu alt: {alt_}. Erlaubt: {args.maximal_alter_tage} Tage.")
        elif manifest.get("fetch_error") or manifest.get("inventory_error"):
            print(f"Die Ablage antwortet nicht: "
                  f"{manifest.get('fetch_error') or manifest['inventory_error']}")
            print("Ohne SeaweedFS baut nichts. Entweder die Verbindung "
                  "herstellen ('python -m storage' prueft sie), oder lokal "
                  "weiterarbeiten: STORAGE_BACKEND=local in .env.")
        elif (manifest.get("release") or {}).get("status") == "failed":
            print(f"Strecke gruen, Release gescheitert: {manifest['release']['error']}")
        else:
            gescheitert = next(s for s in manifest["stages"] if s["exit"] != 0)
            print(f"Abgebrochen bei {gescheitert['gruppe']} · {gescheitert['name']}.")
        return 1
    gesamt = sum(s["sekunden"] for s in manifest["stages"])
    if manifest.get("fetched_runs"):
        print(f"{len(manifest['fetched_runs'])} Lauf/Laeufe von SeaweedFS geholt.")
    print(f"{len(manifest['stages'])} Stufen in {gesamt:.0f} s.")
    print(f"Fingerabdruck der Eingaben: {manifest['input_fingerprint'][:16]}")
    if manifest.get("release"):
        r = manifest["release"]
        print(f"Release {r['release_id']}: {r['files']} Dateien, "
              f"{'publiziert' if r['published'] else 'nur lokal'} "
              f"({for_root(args.data_root).local_root / 'releases'})")
    print(f"Protokoll: {for_root(args.data_root).local_root / LAUF_MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
