"""Das eigene Dashboard - Brett fuer Brett der Ersatz fuer Kibana.

    python -m serving.dashboard [--data-root data] [--port 8050]

Kibana und Elasticsearch belegen auf ``srv01`` zusammen 2,75 GiB, und fuer
die Fragen dieses Projekts - je Stadt, Monat und Kategorie - liegen die
Antworten laengst vorberechnet in ``serving/comparison_month``. Das Dashboard
liest diese Tabelle und den Stern direkt mit DuckDB; einen Suchindex braucht
es dafuer nicht. Die Vorlage sind Artans Entwuerfe unter
``docs/bilder/dashboard_*.png``; dieses Modul baut das erste davon,
»Kriminalität im Überblick«.

**Zwei Zaehlweisen, mit Absicht.** Gezaehlt wird nach meldender Stadt
(``reporting_city``) - dieselbe Zahl wie in Kibana und in
``comparison_month``. Seit Stufe 3 (24.11.2026) zaehlt das Dashboard sie
selbst aus den Taten (``serving.dashboard.taten``), auf den Tag genau; je
Stadt, Monat und Kategorie sind es dieselben 3'511 Zahlen wie in
``comparison_month``, nachgezaehlt am Release vom 20.11.2026. Die Tabelle
liefert noch Jahrgaenge und Kategorien der Leiste und den Datenstand. Die
**Rate** dagegen zaehlt nur Taten in Tracts, die
der Stadt zugeordnet sind, und teilt durch deren Einwohner: genau die Regel
von ``gold_pipeline.raten_je_stadt``, aus der die Abgabedokumente ihre
94,5 und 133,1 je 1'000 nehmen. Eine Rate ueber alle gemeldeten Taten haette
Taten jenseits der Stadtgrenze durch die Einwohner innerhalb geteilt.

**Je 1'000, nicht je 100'000.** Der Entwurf rechnet je 100'000; die Dokumente,
Kibana und die Hypothesen rechnen je 1'000. Eine zweite Einheit waere eine
zweite Wahrheit.

**Ein Zeitraum ist ein Tagesbereich** (``Auswahl``), seit dem 23.11.2026.
Die Bretter rechnen ihn erst, wenn sie in ``FREIE_BRETTER`` stehen; bis
dahin nehmen sie nur ganze Monate eines Jahres an. Der Grund war der Nenner:
Eine Rate teilt durch das ACS-Vintage des Jahres (``population_vintage``),
und ueber Jahresgrenzen gibt es zwei. Ein freies Brett rechnet darum je Tag
mit dem Vintage dieses Tages und gibt die Rate je Jahr an.

**Beim Laden einmal gelesen, danach im Speicher.** Das Dashboard haelt die
Taten selbst schlank im Speicher, rund 1,9 Mio. Zeilen ohne Text, und die
Monatssichten der Bretter darueber (``serving.dashboard.taten``, seit dem
23.11.2026; vorher verdichtete es beim Start auf sieben Monatstabellen).
Aendert sich der Datenstand, laedt es nach (``Bestand.aktuell``).

**Gelesen wird das aktive Release, nicht die Arbeitsschicht** (seit dem
1.11.2026). ``releases/AKTUELL.json`` sagt, was gilt - derselbe Massstab wie
bei ``load_elasticsearch`` und ``pruefe_stand``. Der Anlass war ``srv01``: Im
Modus ``s3`` liegt ``serving/`` gar nicht im Eimer, nur im Release, und die
Arbeitsschicht traegt waehrend eines Laufs ohnehin einen halben Stand. Ein
Release ist unveraenderlich; nachgeladen wird also genau dann, wenn
``AKTUELL.json`` auf ein anderes zeigt.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from gold_pipeline import RATENJAHR, STADT_SCHLUESSEL, einwohner_je_stadt
from silver_pipeline import STUDIENSTAEDTE
from serving.dashboard.zeitraum import vor_einem_jahr
from storage import for_root
from storage import duckdb as storage_duckdb

PARQUET_FILE = "part-0001.parquet"
#: Die Studienstaedte, abgeleitet aus ``silver_pipeline.STUDIENSTAEDTE`` wie
#: Gold und Kibana. Bis zum 22.11.2026 standen sie hier fest (FR-43): Jedes
#: Brett filtert mit ``stadt IN $staedte``, und eine dritte Stadt, die hier
#: fehlte, waere auf allen Brettern still herausgefallen.
STAEDTE: tuple[str, ...] = tuple(STADT_SCHLUESSEL[g] for g in STUDIENSTAEDTE)
STADTNAMEN: dict[str, str] = {STADT_SCHLUESSEL[g]: n for g, n in STUDIENSTAEDTE.items()}
#: Die Auswahl aller Staedte. ``beide`` steht in alten Links und gilt als ``alle``.
ALLE = "alle"
MASSE = ("anzahl", "anteil", "rate")
#: Zaehlebene der »Deliktstruktur«: Faelle vorn (Entscheid E5), Delikte auf Wunsch.
EBENEN = ("faelle", "delikte")

#: Wie viele Kategorien die Balken einzeln zeigen; der Rest steht unter UEBRIGE.
KATEGORIEN_IM_BALKEN = 6
#: Nicht »Übrige Straftaten«: So hiesse auf Deutsch auch NIBRS 90Z.
UEBRIGE = "Übrige Kategorien"
#: Wie oft hoechstens nachgesehen wird, ob ein neuer Stand vorliegt.
PRUEFABSTAND_S = 60.0
#: Die Regel fuer eine Platzhalter-Tatzeit: Ortszeit genau 00:00:00 oder
#: 12:00:00 (build_kibana._PLATZHALTERSTUNDEN). Sie gilt fuer die Heatmap und
#: fuer die Tafel »Tag und Nacht« - einmal hier, damit beide dieselben Faelle
#: als unsicher fuehren. Erwartet ``fact_offense`` unter dem Alias ``f``.
PLATZHALTER_SQL = ("(f.hour_of_day IN (0, 12) AND minute(f.occurred_at_local) = 0 "
                   "AND second(f.occurred_at_local) = 0)")

#: Deutsche Namen der NIBRS-Kategorien. Die Kategorien selbst stammen aus dem
#: FBI NIBRS User Manual 2025.0 (``config/nibrs_offense_categories_2025.csv``,
#: in Gold ``dim_offense``); die
#: Uebersetzung ist unsere. Fehlt ein Name, steht der englische da - eine
#: neue Kategorie verschwindet also nicht, sie ist nur unuebersetzt.
KATEGORIE_DE = {
    "All Other Offenses": "Sonstige (NIBRS 90Z)",
    "Animal Cruelty": "Tierquälerei",
    "Arson": "Brandstiftung",
    "Assault Offenses": "Körperverletzung",
    "Bad Checks": "Ungedeckte Schecks",
    "Bribery": "Bestechung",
    "Bond Default": "Kautionsverstoss",
    "Burglary/Breaking & Entering": "Einbruch",
    "Counterfeiting/Forgery": "Fälschung",
    "Destruction/Damage/Vandalism of Property": "Sachbeschädigung",
    "Disorderly Conduct": "Ordnungsstörung",
    "Driving Under the Influence": "Fahren unter Einfluss",
    "Drug/Narcotic Offenses": "Betäubungsmittel",
    "Drunkenness": "Trunkenheit",
    "Embezzlement": "Veruntreuung",
    "Extortion/Blackmail": "Erpressung",
    "Family Offenses, Nonviolent": "Familiendelikte ohne Gewalt",
    "Fraud Offenses": "Betrug",
    "Gambling Offenses": "Glücksspiel",
    "Homicide Offenses": "Tötungsdelikte",
    "Human Trafficking": "Menschenhandel",
    "Kidnapping/Abduction": "Entführung",
    "Larceny/Theft Offenses": "Diebstahl",
    "Liquor Law Violations": "Alkoholgesetz",
    "Motor Vehicle Theft": "Fahrzeugdiebstahl",
    "Pornography/Obscene Material": "Pornografie",
    "Prostitution Offenses": "Prostitution",
    "Robbery": "Raub",
    "Runaway": "Ausreisser",
    "Sex Offenses": "Sexualdelikte",
    "Stolen Property Offenses": "Hehlerei",
    "Trespass of Real Property": "Hausfriedensbruch",
    "Weapon Law Violations": "Waffengesetz",
    "Commerce Violations": "Handelsverstösse",
    "Curfew/Loitering/Vagrancy Violations": "Ausgangssperre/Herumlungern",
    "Espionage": "Spionage",
    "Federal Resource Violation": "Verstoss gegen Bundesressourcen",
    "Fugitive Offenses": "Flucht vor der Justiz",
    "Immigration Violations": "Einwanderungsrecht",
    "Peeping Tom": "Voyeurismus",
    "Perjury": "Meineid",
    "Treason": "Landesverrat",
    "unmapped": "Nicht zugeordnet",
}


class EingabeFehler(ValueError):
    """Eine Auswahl, die es nicht gibt - die Antwort ist 400, nicht 500."""


def kategorie_de(name: str) -> str:
    return KATEGORIE_DE.get(name, name)


def staedte_aus(wert: str | None) -> tuple[str, ...]:
    """Welche Staedte eine Auswahl meint, in der Reihenfolge von ``STAEDTE``.

    ``alle``, das alte ``beide`` und ein leerer Wert meinen alle Staedte.
    Sonst eine Liste mit Komma, etwa ``chicago,detroit``. Eine unbekannte
    Stadt ist ein Eingabefehler, kein stilles Weglassen.
    """
    wert = (wert or ALLE).strip().lower()
    if wert in (ALLE, "beide"):
        return STAEDTE
    gewaehlt = {s.strip() for s in wert.split(",") if s.strip()}
    unbekannt = sorted(gewaehlt - set(STAEDTE))
    if unbekannt:
        raise EingabeFehler(f"Unbekannte Stadt: {', '.join(unbekannt)}")
    if not gewaehlt:
        raise EingabeFehler("Keine Stadt gewaehlt")
    return tuple(s for s in STAEDTE if s in gewaehlt)


#: Trenner zwischen Kategorien in ``kategorie=``. Kein Komma: NIBRS kennt
#: »Family Offenses, Nonviolent«.
KATEGORIE_TRENNER = "|"


def kategorien_aus(wert: str | None, bekannte: list[str]) -> tuple[str, ...] | None:
    """Welche Kategorien eine Auswahl meint, oder ``None`` fuer alle.

    ``alle`` und ein leerer Wert meinen alle. Sonst eine Liste mit ``|``,
    etwa ``Robbery|Arson``. Eine unbekannte Kategorie ist ein Eingabefehler.
    Die Folge ist die von ``bekannte`` (nach Haeufigkeit), damit dieselbe
    Auswahl gleich heisst. Sind alle gewaehlt, heisst das ``alle``.
    """
    wert = (wert or ALLE).strip()
    if wert.lower() == ALLE:
        return None
    gewaehlt = {k.strip() for k in wert.split(KATEGORIE_TRENNER) if k.strip()}
    unbekannt = sorted(gewaehlt - set(bekannte))
    if unbekannt:
        raise EingabeFehler(f"Unbekannte Kategorie: {', '.join(unbekannt)}")
    if not gewaehlt:
        raise EingabeFehler("Keine Kategorie gewaehlt")
    if gewaehlt == set(bekannte):
        return None
    return tuple(k for k in bekannte if k in gewaehlt)


def stadtwert(staedte: tuple[str, ...]) -> str:
    """Die kanonische Schreibweise: ``alle`` oder die Liste in fester Folge."""
    return ALLE if set(staedte) == set(STAEDTE) else ",".join(staedte)


#: Welche Bretter einen freien Zeitraum rechnen: auf den Tag genau und ueber
#: Jahresgrenzen. Ein Brett, das hier fehlt, rechnet ganze Monate eines Jahres
#: und lehnt alles andere ab, statt es still auf Monate zu runden. Seit Stufe 3
#: (24.11.2026) alle sieben; die Regeln stehen in ``serving.dashboard.zeitraum``.
FREIE_BRETTER: frozenset[str] = frozenset({
    "ueberblick", "zeitverlauf", "geografie", "sozial", "deliktstruktur",
    "datenqualitaet", "wetter"})

#: Ein Datum in der Adresse, und nur so. ``date.fromisoformat`` naehme auch
#: ``20240101`` und ``2024-W01-1``; dieselbe Auswahl haette dann mehrere Namen.
_DATUM = re.compile(r"\d{4}-\d{2}-\d{2}")


def monatsende(tag: date) -> date:
    """Der letzte Tag im Monat von ``tag``."""
    return date(tag.year + tag.month // 12, tag.month % 12 + 1, 1) - timedelta(days=1)


@dataclass(frozen=True)
class Auswahl:
    """Was oben in der Leiste steht.

    Der Zeitraum ist ein Tagesbereich, beide Enden eingeschlossen. Jahr und
    Monate sind daraus abgeleitet und gelten nur, solange er aus ganzen
    Monaten eines Jahres besteht (``ganze_monate``) - so rechnen die Bretter,
    die noch nicht in ``FREIE_BRETTER`` stehen.
    """

    stadt: str = ALLE
    tag_von: date = date(RATENJAHR, 1, 1)
    tag_bis: date = date(RATENJAHR, 12, 31)
    kategorie: str = "alle"
    mass: str = "anzahl"
    ebene: str = "faelle"

    @property
    def ganze_monate(self) -> bool:
        """Ganze Monate eines Jahres, wie es die Leiste bis Stufe 2 nur kannte."""
        return (self.tag_von.year == self.tag_bis.year and self.tag_von.day == 1
                and self.tag_bis == monatsende(self.tag_bis))

    @property
    def jahr(self) -> int:
        return self.tag_von.year

    @property
    def von(self) -> int:
        """Der erste Monat; nur bei ``ganze_monate`` ein Zeitraum."""
        return self.tag_von.month

    @property
    def bis(self) -> int:
        """Der letzte Monat; nur bei ``ganze_monate`` ein Zeitraum."""
        return self.tag_bis.month

    @property
    def tage(self) -> int:
        return (self.tag_bis - self.tag_von).days + 1

    @property
    def json(self) -> dict[str, Any]:
        """Die Auswahl in der Antwort: Jahr und Monate wie bisher, dazu die Tage.

        Bei einem freien Zeitraum stehen Jahr und Monate auf ``None`` - ein
        Brett, das sie dann noch liest, zeigt einen Fehler statt einer
        falschen Beschriftung.
        """
        monate = self.ganze_monate
        return {"stadt": self.stadt,
                "jahr": self.jahr if monate else None,
                "von": self.von if monate else None,
                "bis": self.bis if monate else None,
                "tag_von": self.tag_von.isoformat(), "tag_bis": self.tag_bis.isoformat(),
                "ganze_monate": monate, "tage": self.tage,
                "kategorie": self.kategorie, "mass": self.mass, "ebene": self.ebene}

    @property
    def staedte(self) -> tuple[str, ...]:
        return staedte_aus(self.stadt)

    @property
    def kategorien(self) -> tuple[str, ...] | None:
        """Die gewaehlten Kategorien, ``None`` fuer alle. Nach ``pruefe`` kanonisch."""
        if self.kategorie == ALLE:
            return None
        return tuple(self.kategorie.split(KATEGORIE_TRENNER))

    @property
    def kat_sql(self) -> str:
        """Der Filter fuer jede Abfrage mit einer Spalte ``kategorie`` - leer fuer alle."""
        return "" if self.kategorien is None else "AND kategorie IN $kat"

    @property
    def kat_param(self) -> dict[str, list[str]]:
        """Der Wert zu ``kat_sql``; leer, wenn kein Filter gilt."""
        return {} if self.kategorien is None else {"kat": list(self.kategorien)}

    def pruefe(self, jahre: list[int], kategorien: list[str]) -> Auswahl:
        staedte = staedte_aus(self.stadt)
        kategorien = kategorien_aus(self.kategorie, kategorien)
        if self.tag_von > self.tag_bis:
            raise EingabeFehler("Der Zeitraum braucht von <= bis")
        for tag in (self.tag_von, self.tag_bis):
            if tag.year not in jahre:
                raise EingabeFehler(f"Kein Jahrgang {tag.year}")
        if self.mass not in MASSE:
            raise EingabeFehler(f"Unbekanntes Mass: {self.mass}")
        if self.ebene not in EBENEN:
            raise EingabeFehler(f"Unbekannte Ebene: {self.ebene}")
        # Kanonisch: Alte Links mit ``beide`` und eine vollstaendige Liste
        # heissen ``alle``, damit dieselbe Auswahl gleich heisst.
        return replace(self, stadt=stadtwert(staedte),
                       kategorie=(ALLE if kategorien is None
                                  else KATEGORIE_TRENNER.join(kategorien)))


def _quelle(ablage, release: str, schicht: str, tabelle: str) -> tuple[str, str]:
    """Lesepfad und Manifesttext einer Tabelle im Release - lokal oder S3."""
    rel = f"{release}/{schicht}/dataset={tabelle}"
    if not ablage.exists(rel, "manifest.json"):
        raise FileNotFoundError(f"{rel} fehlt - das Release ist unvollstaendig")
    return ablage.resolve_read_path(rel, PARQUET_FILE), ablage.read_text(rel, "manifest.json")


def _aktuell_text(ablage) -> str:
    """``releases/AKTUELL.json`` als Text, leer ohne Release."""
    try:
        return ablage.read_text("releases", "AKTUELL.json")
    except (OSError, ValueError, FileNotFoundError):
        return ""


def _release(text: str) -> str | None:
    try:
        return json.loads(text).get("release_id")
    except ValueError:
        return None


class Bestand:
    """Der verdichtete Datenstand, aus dem jede Anfrage beantwortet wird."""

    def __init__(self, data_root: Path | str):
        self.data_root = Path(data_root)
        self._sperre = threading.Lock()
        # Nur ein Thread prueft und laedt nach; die anderen warten darauf.
        self._pruefsperre = threading.Lock()
        self._geprueft = 0.0
        self._lade()

    # -- Laden -------------------------------------------------------------

    def _abdruck(self) -> str:
        # Ein Release aendert sich nicht; ein neuer Stand ist ein neuer Zeiger.
        return _aktuell_text(for_root(self.data_root))

    def _lade(self) -> None:
        ablage = for_root(self.data_root)
        aktuell = _aktuell_text(ablage)
        kennung = _release(aktuell)
        if not kennung:
            raise FileNotFoundError(
                "Kein aktives Release (releases/AKTUELL.json) - zuerst "
                "python -m orchestration.release")
        release = f"releases/release={kennung}"
        monat, monat_manifest = _quelle(ablage, release, "serving", "comparison_month")
        fakten, _ = _quelle(ablage, release, "gold", "fact_offense")
        delikte, _ = _quelle(ablage, release, "gold", "dim_offense")
        tracts, _ = _quelle(ablage, release, "gold", "dim_tract")
        acs, _ = _quelle(ablage, release, "gold", "dim_tract_acs")
        con = storage_duckdb.connect(ablage.config)
        # **Je Ladung ein eigenes Auslagerungsverzeichnis.** Beim Nachladen
        # leben alte und neue Verbindung kurz nebeneinander. Ohne eigenes
        # Verzeichnis lagern beide nach ``.tmp/duckdb_temp_storage_DEFAULT-0.tmp``
        # im Arbeitsverzeichnis aus; schliesst die alte, nimmt sie die Datei
        # der neuen mit. Am 25.11.2026 auf srv01: Nach dem neuen Release
        # antwortete jede Anfrage mit 500, *„Could not read enough bytes from
        # file .tmp/duckdb_temp_storage_DEFAULT-0.tmp"*, bis zum Neustart.
        # Das Dashboard lagert schon in Ruhe rund 9 MB aus (256 MB Grenze).
        basis = os.getenv("DUCKDB_TEMP_DIRECTORY") or tempfile.gettempdir()
        os.makedirs(basis, exist_ok=True)
        auslagerung = tempfile.mkdtemp(prefix="dashboard-duckdb-", dir=basis)
        con.execute("SET temp_directory = $d", {"d": auslagerung})
        # Spalten ausgeschrieben: Ein SELECT * nimmt die Hive-Spalte aus dem
        # Pfad mit (AGENTS.md, »Known pitfalls«).
        con.execute(f"""
            CREATE TABLE monate AS
            SELECT reporting_city AS stadt, month AS monat, nibrs_category AS kategorie,
                   offenses AS delikte, cases AS faelle,
                   days_in_period AS tage, days_in_window AS tage_im_fenster
            FROM read_parquet('{monat}', hive_partitioning=false)""")
        geo, _ = _quelle(ablage, release, "gold", "dim_tract_geo")
        # Die Taten selbst, schlank, und die Monatssichten darueber
        # (serving.dashboard.taten, seit dem 23.11.2026).
        from serving.dashboard.taten import lade_taten
        # Der Sonnenstand fuer ``fakt.dunkel``, wenn das Release ihn fuehrt.
        stadttage = None
        rel = f"{release}/gold/dataset=dim_city_day"
        if ablage.exists(rel, "manifest.json"):
            kandidat = ablage.resolve_read_path(rel, PARQUET_FILE)
            sonne = {r[0] for r in con.execute(
                f"DESCRIBE SELECT * FROM read_parquet('{kandidat}', hive_partitioning=false)"
            ).fetchall()}
            if {"sunrise_utc", "sunset_utc"} <= sonne:
                stadttage = kandidat
        lade_taten(con, fakten, delikte, tracts, stadttage)
        con.execute(f"""
            CREATE TABLE tract_geo AS
            SELECT geoid, city, tract_name
            FROM read_parquet('{geo}', hive_partitioning=false)""")
        con.execute(f"""
            CREATE TABLE tract_einwohner AS
            SELECT geoid, vintage, population
            FROM read_parquet('{acs}', hive_partitioning=false)
            WHERE geoid IN (SELECT geoid FROM tract_geo)""")
        # Fuer »Soziales Umfeld«: Armutsquote und Einkommen je Tract und Vintage.
        from serving.dashboard.sozial import lade_sozial
        lade_sozial(con, acs)
        # Fuer »Datenqualität«: die Zeilen jeder Delikt-ID, die je Stadt mehr
        # als einmal vorkommt. Die Faktentabelle fuehrt die ID nicht. Ueber
        # einen Zeitraum sind es dann ``count(*) - count(DISTINCT id)`` - jede
        # einmalige ID truege 1 - 1 bei. Bis Stufe 3 je Monat gezaehlt; eine ID
        # in zwei Monaten fiel dort nicht auf.
        con.execute(f"""
            CREATE TABLE doppelte AS
            SELECT reporting_city AS stadt, date AS tag, offense_id AS id
            FROM read_parquet('{fakten}', hive_partitioning=false)
            QUALIFY count(*) OVER (PARTITION BY reporting_city, offense_id) > 1""")
        # Fuer »Deliktstruktur«: je Kategorie die drei haeufigsten NIBRS-Delikte
        # ueber den ganzen Bestand - Beispiele, keine Auswahl.
        beispiele: dict[str, list[str]] = {}
        for k, name in con.execute(f"""
                SELECT d.nibrs_category, d.nibrs_description
                FROM read_parquet('{fakten}', hive_partitioning=false) f
                JOIN read_parquet('{delikte}', hive_partitioning=false) d USING (nibrs_code)
                GROUP BY ALL ORDER BY 1, count(*) DESC, 2""").fetchall():
            if len(beispiele.setdefault(k, [])) < 3:
                beispiele[k].append(name)
        from serving.dashboard.geografie import pfade
        karten = pfade(con.execute(f"""
            SELECT geoid, city, tract_name, boundary_wkt
            FROM read_parquet('{geo}', hive_partitioning=false) ORDER BY geoid""").fetchall())
        # Fuer »Geografie«: die Polizeibezirke (seit Gold-Vertrag 11). Ein
        # aelteres Release fuehrt sie nicht - dann None, und das Brett sagt es.
        from serving.dashboard.bezirke import lade_bezirke
        karten_bezirke = lade_bezirke(con, ablage, release, acs)
        vintages = [r[0] for r in con.execute("""
            SELECT DISTINCT f.vintage FROM fakt f JOIN tract_nr n ON n.nr = f.tract
            WHERE n.city IS NOT NULL AND f.vintage IS NOT NULL""").fetchall()]
        con.execute("CREATE TABLE einwohner (stadt VARCHAR, vintage INTEGER, n BIGINT)")
        for v in vintages:
            con.execute(f"INSERT INTO einwohner SELECT city, {int(v)}, n FROM ("
                        + einwohner_je_stadt(f"read_parquet('{tracts}', hive_partitioning=false)",
                                             f"read_parquet('{acs}', hive_partitioning=false)",
                                             str(int(v))) + ")")
        # Je Kalenderjahr das Vintage der Taten nach der Regel von
        # raten_je_stadt; ein Jahr mit zwei Vintages hat keines (None) und
        # damit keine Rate (serving.dashboard.zeitraum).
        vintage_je_jahr = {j: (vs[0] if len(vs) == 1 else None) for j, vs in con.execute("""
            SELECT year(f.tag), list(DISTINCT f.vintage)
            FROM fakt f JOIN tract_nr n ON n.nr = f.tract
            WHERE n.city IS NOT NULL AND f.vintage IS NOT NULL GROUP BY 1""").fetchall()}
        # Fuer »Quellbewegung«: die Bewegung der Quellen, mit der NIBRS-Kategorie
        # ueber dieselbe Dimension wie die Taten. Ein aelteres Release fuehrt
        # die Tabelle nicht - dann bleibt das Brett leer und sagt warum, statt
        # dass das ganze Dashboard nicht laedt.
        from serving.dashboard.quellbewegung import lade_bewegung
        bewegung = lade_bewegung(con, ablage, release, delikte)
        # Fuer »Wetter«: das Wetter je Stadt und Tag neben den Faellen je Tag.
        from serving.dashboard.wetter import lade_wetter
        mit_wetter = lade_wetter(con, ablage, release, fakten, delikte)
        # Fuer »Zeitverlauf«, Tafel »Tag und Nacht«: Faelle nach Sonnenstand.
        # Ein Release mit Vertrag <= 8 fuehrt keinen - dann nennt die Tafel
        # den Grund, und das Dashboard laedt trotzdem.
        from serving.dashboard.zeitverlauf import lade_licht
        ohne_licht = lade_licht(con, ablage, release, fakten, delikte)
        stand = json.loads(monat_manifest)
        with self._sperre:
            alt = getattr(self, "_con", None)
            alt_auslagerung = getattr(self, "auslagerung", None)
            self._con = con
            self.auslagerung = auslagerung
            self._abdruck_jetzt = aktuell
            self.stand = {
                "gebaut": stand.get("built_at_utc"),
                "release": kennung,
            }
            self.karten = karten
            self.karten_bezirke = karten_bezirke
            self.beispiele = beispiele
            self.bewegung = bewegung
            self.wetter = mit_wetter
            self.ohne_licht = ohne_licht
            self.vintage_je_jahr = vintage_je_jahr
            self.jahre = [r[0] for r in con.execute(
                "SELECT DISTINCT year(monat) FROM monate ORDER BY 1").fetchall()]
            self.kategorien = [r[0] for r in con.execute(
                "SELECT kategorie FROM monate GROUP BY 1 ORDER BY sum(delikte) DESC").fetchall()]
        if alt is not None:
            alt.close()
        if alt_auslagerung:
            shutil.rmtree(alt_auslagerung, ignore_errors=True)

    def aktuell(self) -> None:
        """Laedt nach, wenn sich der Stand geaendert hat - hoechstens einmal je Minute."""
        with self._pruefsperre:
            jetzt = time.monotonic()
            if jetzt - self._geprueft < PRUEFABSTAND_S:
                return
            self._geprueft = jetzt
            if self._abdruck() != self._abdruck_jetzt:
                self._lade()

    def _cursor(self):
        with self._sperre:
            return self._con.cursor()

    # -- Auswahl -----------------------------------------------------------

    def optionen(self) -> dict[str, Any]:
        cur = self._cursor()
        letzter = {s: m.isoformat() for s, m in cur.execute(
            "SELECT stadt, max(monat) FROM monate GROUP BY 1").fetchall()}
        return {
            # Je Stadt eine Checkbox; »Alle« baut die Oberflaeche selbst.
            "staedte": [{"wert": s, "name": STADTNAMEN[s]} for s in STAEDTE],
            "jahre": self.jahre,
            # Je Kategorie eine Checkbox; »Alle« baut die Oberflaeche selbst.
            "kategorien": sorted(({"wert": k, "name": kategorie_de(k)} for k in self.kategorien),
                                 key=lambda k: k["name"]),
            "vorgabe": {"stadt": ALLE, "jahr": RATENJAHR if RATENJAHR in self.jahre
                        else self.jahre[-1], "von": 1, "bis": 12,
                        "kategorie": "alle", "mass": "anzahl", "ebene": "faelle",
                        # »Quellbewegung«: Zeitstempel vorgabemaessig ausgeblendet.
                        "felder": "inhalt",
                        # »Soziales Umfeld«: die beiden Karten nebeneinander.
                        "karte": "nebeneinander",
                        # »Geografie«: die Rate je Tract.
                        "raum": "tract", "kennzahl": "rate"},
            "letzter_monat": letzter,
            # Fuer die erweiterte Zeitwahl: welche Bretter Tage rechnen, das
            # Fenster mit Daten und die Vorgaben dazu.
            "frei": sorted(FREIE_BRETTER),
            **self._tagesfenster(cur),
            "stand": self.stand,
        }

    @staticmethod
    def _tagesfenster(cur) -> dict[str, Any]:
        """Erster und letzter Tag mit Daten, und die Vorgaben der Zeitwahl.

        Die Vorgaben haengen am letzten Tag mit Daten irgendeiner Stadt, nicht
        am Kalender: »Letzte 30 Tage« zeigt sonst bei einem Datenstand von
        gestern einen halb leeren Zeitraum.
        """
        erster, letzter = cur.execute("SELECT min(von), max(bis) FROM fenster").fetchone()
        if letzter is None:
            return {"tage": None, "vorgaben": []}
        sommer = letzter.year if letzter >= date(letzter.year, 8, 31) else letzter.year - 1
        try:
            vor_einem_jahr = letzter.replace(year=letzter.year - 1)
        except ValueError:  # 29. Februar
            vor_einem_jahr = letzter.replace(year=letzter.year - 1, day=28)
        roh = [
            ("Letzter Tag", letzter, letzter),
            ("Letzte 7 Tage", letzter - timedelta(days=6), letzter),
            ("Letzte 30 Tage", letzter - timedelta(days=29), letzter),
            ("Letzte 12 Monate", vor_einem_jahr + timedelta(days=1), letzter),
            ("Laufendes Jahr", date(letzter.year, 1, 1), letzter),
            (f"Sommer {sommer}", date(sommer, 6, 1), date(sommer, 8, 31)),
            ("Ganzer Bestand", erster, letzter),
        ]
        return {
            "tage": {"erster": erster.isoformat(), "letzter": letzter.isoformat()},
            "vorgaben": [{"name": n, "von": max(v, erster).isoformat(), "bis": b.isoformat()}
                         for n, v, b in roh if b >= erster],
        }

    def auswahl(self, werte: dict[str, str], brett: str | None = None) -> Auswahl:
        """Die Auswahl aus der Adresse, geprueft fuer ``brett``.

        Zwei Schreibweisen fuer den Zeitraum. Die alte, ``jahr=2024&von=3&bis=5``,
        meint ganze Monate eines Jahres; jeder Link von vor Stufe 2 bleibt so
        gueltig und liefert dieselben Zahlen. Die neue, ``von=2024-06-01&bis=
        2024-08-31``, meint Tage; ``jahr`` gilt dann nicht. Ein Brett, das nicht
        in ``FREIE_BRETTER`` steht, nimmt die neue nur fuer ganze Monate eines
        Jahres an.
        """
        von, bis = werte.get("von", "1"), werte.get("bis", "12")
        if "-" in von or "-" in bis:
            if not (_DATUM.fullmatch(von) and _DATUM.fullmatch(bis)):
                raise EingabeFehler("Ein Datum braucht die Form JJJJ-MM-TT")
            try:
                tag_von, tag_bis = date.fromisoformat(von), date.fromisoformat(bis)
            except ValueError as fehler:  # etwa der 30. Februar
                raise EingabeFehler(f"Kein Datum: {von} oder {bis}") from fehler
        else:
            try:
                jahr, m_von, m_bis = int(werte.get("jahr", RATENJAHR)), int(von), int(bis)
            except ValueError as fehler:
                raise EingabeFehler("Jahr und Monate muessen Zahlen sein") from fehler
            if jahr not in self.jahre:
                raise EingabeFehler(f"Kein Jahrgang {jahr}")
            if not 1 <= m_von <= m_bis <= 12:
                raise EingabeFehler("Der Zeitraum braucht 1 <= von <= bis <= 12")
            tag_von = date(jahr, m_von, 1)
            tag_bis = monatsende(date(jahr, m_bis, 1))
        a = Auswahl(
            stadt=werte.get("stadt", ALLE),
            tag_von=tag_von, tag_bis=tag_bis,
            kategorie=werte.get("kategorie", "alle"),
            mass=werte.get("mass", "anzahl"),
            ebene=werte.get("ebene", "faelle"),
        ).pruefe(self.jahre, self.kategorien)
        if not a.ganze_monate and brett not in FREIE_BRETTER:
            raise EingabeFehler(
                "Dieses Brett zeigt bisher nur ganze Monate eines Jahres, "
                f"nicht {a.tag_von:%d.%m.%Y}–{a.tag_bis:%d.%m.%Y}")
        return a

    # -- Das Brett »Datenqualität« -------------------------------------------

    def datenqualitaet(self, a: Auswahl) -> dict[str, Any]:
        from serving.dashboard.datenqualitaet import datenqualitaet
        return datenqualitaet(self, a)

    def referenz(self, a: Auswahl) -> dict[str, Any]:
        """Was eine Auswertung des Zeitraums an Referenzdaten braucht - und ob es da ist."""
        cur = self._cursor()
        vintages = sorted(r[0] for r in cur.execute(
            "SELECT DISTINCT f.vintage FROM fakt f JOIN tract_nr n ON n.nr = f.tract "
            "WHERE n.city IS NOT NULL AND f.tag BETWEEN $von AND $bis AND f.vintage IS NOT NULL",
            {"von": a.tag_von, "bis": a.tag_bis}).fetchall())
        tracts = dict(cur.execute("SELECT city, count(*) FROM tract_geo GROUP BY 1").fetchall())
        return {
            "acs_vintage": vintages[0] if len(vintages) == 1 else None,
            "acs_vintages": sorted(vintages),
            "kategorien": len([k for k in self.kategorien if k != "unmapped"]),
            "tracts": {s: int(tracts.get(s, 0)) for s in STAEDTE},
            "release": self.stand.get("release"),
        }

    # -- Das Brett »Soziales Umfeld« -------------------------------------------

    def sozialbrett(self, werte: dict[str, str]) -> dict[str, Any]:
        from serving.dashboard.sozial import sozial
        return sozial(self, self.auswahl(werte, "sozial"), werte.get("karte") or "nebeneinander")

    # -- Das Brett »Wetter« ---------------------------------------------------

    def wetterbrett(self, a: Auswahl) -> dict[str, Any]:
        from serving.dashboard.wetter import wetter
        return wetter(self, a)

    # -- Das Brett »Quellbewegung« ------------------------------------------

    def quellbewegung(self, werte: dict[str, str]) -> dict[str, Any]:
        from serving.dashboard.quellbewegung import quellbewegung
        return quellbewegung(self, werte)

    # -- Das Brett »Deliktstruktur« ------------------------------------------

    def deliktstruktur(self, a: Auswahl) -> dict[str, Any]:
        from serving.dashboard.deliktstruktur import deliktstruktur
        return deliktstruktur(self, a)

    # -- Das Brett »Geografie« -----------------------------------------------

    def geografie(self, a: Auswahl, ansicht: str | None = None, *,
                  raum: str | None = None, kennzahl: str | None = None) -> dict[str, Any]:
        from serving.dashboard.geografie import geografie
        return geografie(self, a, ansicht, raum=raum, kennzahl=kennzahl)

    # -- Das Brett »Zeitverlauf« ---------------------------------------------

    def zeitverlauf(self, a: Auswahl) -> dict[str, Any]:
        from serving.dashboard.zeitverlauf import zeitverlauf
        return zeitverlauf(self, a)

    # -- Das Brett »Überblick« -----------------------------------------------

    def ueberblick(self, a: Auswahl) -> dict[str, Any]:
        cur = self._cursor()
        staedte = list(a.staedte)
        z = self.zeitraum(cur, a, staedte)
        kat = a.kat_sql
        p = {"staedte": staedte, **z.param, **a.kat_param}

        def summe(spalte: str, von, bis) -> int:
            zaehler = "count(*)" if spalte == "delikte" else "count(*) FILTER (fall)"
            return cur.execute(
                f"SELECT {zaehler} FROM fakt WHERE stadt IN $staedte "
                f"AND tag BETWEEN $a AND $b {kat}",
                {"staedte": staedte, "a": von, "b": bis, **a.kat_param}).fetchone()[0]

        abdeckung = self._abdeckung(z)
        # Zum Vorjahr nur ueber Tage, die in beiden Jahren fuer jede gewaehlte
        # Stadt vorliegen (serving.dashboard.zeitraum): Neun Monate 2026 gegen
        # zwoelf Monate 2025 waeren ein Rueckgang, der keiner ist.
        vergleich = z.vergleich()
        jetzt_v = summe("delikte", *vergleich) if vergleich else 0
        vorher_v = (summe("delikte", vor_einem_jahr(vergleich[0]), vor_einem_jahr(vergleich[1]))
                    if vergleich else 0)

        # Eine Periode ohne Daten ist eine Luecke (None), keine Null. Hohl
        # zeichnet die Seite, was nur zum Teil vorliegt oder angeschnitten ist.
        im_diagramm = {s: z.status(s) for s in staedte}
        verlauf = {s: [None if st == "fehlt" else 0 for st in im_diagramm[s]] for s in staedte}
        for s, start, n in cur.execute(
                f"SELECT stadt, {z.periode_sql('tag')}, count(*) FROM fakt "
                f"WHERE stadt IN $staedte AND tag BETWEEN $von AND $bis {kat} GROUP BY 1, 2",
                p).fetchall():
            verlauf[s][z.index(start)] = int(n)

        perioden = len(z.perioden)
        voll = sum(all(abdeckung[s]["monate"][i] == "voll" for s in staedte)
                   for i in range(perioden))
        return {
            "auswahl": a.json,
            "achse": z.json(),
            "kennzahlen": {
                "delikte": int(summe("delikte", z.von, z.bis)),
                "faelle": int(summe("faelle", z.von, z.bis)),
                "vorjahr_prozent": (round((jetzt_v - vorher_v) * 100.0 / vorher_v, 1)
                                    if vorher_v else None),
                "vorjahr_tage": (vergleich[1] - vergleich[0]).days + 1 if vergleich else 0,
                "vorjahr_moeglich": z.vergleich_moeglich,
                "vollstaendige_monate": voll,
                "monate": perioden,
                "tage": a.tage,
            },
            "verlauf": {"monate": [m.isoformat() for m in z.starts],
                        "reihen": [{"stadt": s, "name": STADTNAMEN[s], "werte": verlauf[s],
                                    "status": im_diagramm[s]}
                                   for s in staedte]},
            "kategorien": self._kategorien(cur, a, z),
            "raten": self._raten(cur, a, z),
            "abdeckung": [{"stadt": s, "name": STADTNAMEN[s], **abdeckung[s]}
                          for s in staedte],
            "stand": self.stand,
        }

    # -- Gemeinsam fuer die Bretter ------------------------------------------

    def zeitraum(self, cur, a: Auswahl, staedte: list[str]):
        from serving.dashboard.zeitraum import Zeitraum
        return Zeitraum(cur, a, staedte)

    def _kategorien(self, cur, a: Auswahl, z) -> dict[str, Any]:
        """Delikte je Kategorie und Stadt - als Anzahl, Anteil oder Rate."""
        zeilen = cur.execute(
            f"SELECT stadt, kategorie, count(*) FROM fakt WHERE stadt IN $staedte "
            f"AND tag BETWEEN $von AND $bis {a.kat_sql} GROUP BY 1, 2",
            {"staedte": z.staedte, **z.param, **a.kat_param}).fetchall()
        gesamt: dict[str, int] = {}
        for _, k, n in zeilen:
            gesamt[k] = gesamt.get(k, 0) + int(n)
        oben = [k for k, _ in sorted(gesamt.items(), key=lambda kv: (-kv[1], kv[0]))]
        einzeln, rest = oben[:KATEGORIEN_IM_BALKEN], oben[KATEGORIEN_IM_BALKEN:]
        werte = {s: {k: 0 for k in einzeln} for s in z.staedte}
        for s, k, n in zeilen:
            ziel = k if k in einzeln else UEBRIGE
            werte[s][ziel] = werte[s].get(ziel, 0) + int(n)
        namen = einzeln + ([UEBRIGE] if rest else [])
        if a.mass == "anteil":
            for s in z.staedte:
                summe = sum(werte[s].values()) or 1
                werte[s] = {k: round(v * 100.0 / summe, 1) for k, v in werte[s].items()}
        elif a.mass == "rate":
            werte = self._raten_je(cur, z, einzeln, rest)
        return {
            "mass": a.mass,
            "zeilen": [{"kategorie": k, "name": kategorie_de(k),
                        "werte": {s: werte[s].get(k, 0) for s in z.staedte}} for k in namen],
        }

    def _einwohner(self, cur, stadt: str) -> dict[int, int]:
        return dict(cur.execute("SELECT vintage, n FROM einwohner WHERE stadt = $s",
                                {"s": stadt}).fetchall())

    def _nenner(self, cur, z) -> dict[str, float]:
        """Personenjahre je Stadt (``Zeitraum.personenjahre``); fehlt eine, keine Rate."""
        nenner = {s: z.personenjahre(s, self._einwohner(cur, s), self.vintage_je_jahr)
                  for s in z.staedte}
        return {s: n for s, n in nenner.items() if n}

    def _raten_sql(self, z, kat: str) -> str:
        """Taten in Tracts mit Stadtzuordnung, wie ``gold_pipeline.raten_je_stadt``.

        Die Stadt ist die des Tracts, nicht die meldende; und gezaehlt nur an
        Tagen im Fenster dieser Stadt, wie der Nenner.
        """
        return (f"FROM fakt f JOIN tract_nr n ON n.nr = f.tract "
                f"JOIN fenster x ON x.stadt = n.city AND f.tag BETWEEN x.von AND x.bis "
                f"WHERE n.city IN $staedte AND f.tag BETWEEN $von AND $bis {kat}")

    def _raten_je(self, cur, z, einzeln, rest) -> dict[str, dict[str, float]]:
        nenner = self._nenner(cur, z)
        werte: dict[str, dict[str, float]] = {s: {} for s in z.staedte}
        for s, k, n in cur.execute(
                f"SELECT n.city, f.kategorie, count(*) {self._raten_sql(z, '')} GROUP BY 1, 2",
                {"staedte": z.staedte, **z.param}).fetchall():
            ziel = k if k in einzeln else (UEBRIGE if k in rest else None)
            if ziel is not None:
                werte[s][ziel] = werte[s].get(ziel, 0) + int(n)
        return {s: {k: (round(v * 1000.0 / nenner[s], 1) if s in nenner else None)
                    for k, v in werte[s].items()} for s in z.staedte}

    def _raten(self, cur, a: Auswahl, z) -> dict[str, Any]:
        """Faelle je 1'000 Einwohner und Jahr, fuer alle Faelle oder die Kategorie.

        **Fallebene vorn, Tatebene daneben** (E5), wie ``raten_je_stadt``
        mit ``rate_fallebene`` und ``rate``: Chicago erfasst je Fall nur das
        schwerste Delikt, Detroit jedes - auf der Tatebene misst ein Vergleich
        den Erfassungsunterschied mit. **Keine Zeile je Kategorie:** Nach E5
        rechnen Kategorien auf der Tatebene, weil sie sich nur dort addieren;
        die Rate je Kategorie zeigt die Tafel »nach Kategorie« (``_raten_je``).

        **Je Jahr:** Der Nenner sind Personenjahre (``serving.dashboard.
        zeitraum``). Ueber ein ganzes Jahr ist das die Einwohnerzahl.
        """
        nenner = self._nenner(cur, z)
        summen = {s: (int(f), int(d)) for s, f, d in cur.execute(
            f"SELECT n.city, count(*) FILTER (f.fall), count(*) "
            f"{self._raten_sql(z, a.kat_sql.replace('kategorie', 'f.kategorie'))} GROUP BY 1",
            {"staedte": z.staedte, **z.param, **a.kat_param}).fetchall()}

        def rate(s: str, i: int) -> float | None:
            n = summen.get(s, (0, 0))[i]
            return round(n * 1000.0 / nenner[s], 1) if s in nenner else None

        # Die Bevoelkerung, wenn der Zeitraum ein Vintage hat; sonst steht sie
        # je Jahr verschieden und die Seite nennt nur die Personenjahre.
        vintages = {self.vintage_je_jahr.get(j) for j in range(z.von.year, z.bis.year + 1)}
        einwohner = ({s: n for s, n in cur.execute(
            "SELECT stadt, n FROM einwohner WHERE vintage = $v AND stadt IN $staedte",
            {"v": next(iter(vintages)), "staedte": z.staedte}).fetchall() if s in nenner}
            if len(vintages) == 1 and None not in vintages else {})
        # Mehrere Namen passen nicht als Beschriftung eines Balkens; welche es
        # sind, zeigt die Leiste als aktiven Filter.
        name = ("Alle Fälle" if a.kategorien is None
                else kategorie_de(a.kategorien[0]) if len(a.kategorien) == 1
                else f"{len(a.kategorien)} Kategorien")
        return {"einwohner": einwohner,
                "personenjahre": {s: round(n) for s, n in nenner.items()},
                "tage": {s: z.tage_mit_daten(s) for s in z.staedte},
                "zeilen": [{"kategorie": a.kategorie, "name": name,
                            "werte": {s: rate(s, 0) for s in z.staedte}}],
                "tatebene": {s: rate(s, 1) for s in z.staedte}}

    @staticmethod
    def _abdeckung(z) -> dict[str, dict[str, Any]]:
        """Je Stadt und Periode: voll, teilweise oder fehlend - und der letzte Tag.

        Gemessen am Fenster **dieser** Stadt (Tabelle ``fenster``), nicht am
        gemeinsamen von ``comparison_month``. ``monate`` heisst die Liste aus
        der Zeit vor Stufe 3; sie hat je Periode der Achse einen Eintrag.
        """
        ergebnis = {}
        for s in z.staedte:
            je_periode = z.status(s, rand=False)
            mit_daten = [m for m, st in zip(z.starts, je_periode) if st != "fehlt"]
            f = z.fenster.get(s)
            ergebnis[s] = {
                "monate": je_periode,
                "vollstaendig": je_periode.count("voll"),
                "von": mit_daten[0].isoformat() if mit_daten else None,
                "bis": mit_daten[-1].isoformat() if mit_daten else None,
                "letzter_monat": date(f[1].year, f[1].month, 1).isoformat() if f else None,
                "letzter_tag": f[1].isoformat() if f else None,
                "status": ("vollstaendig" if je_periode and all(st == "voll" for st in je_periode)
                           else "keine_daten" if not mit_daten else "unvollstaendig"),
            }
        return ergebnis
