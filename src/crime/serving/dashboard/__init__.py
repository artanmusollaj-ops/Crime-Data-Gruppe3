"""Das eigene Dashboard - Brett fuer Brett der Ersatz fuer Kibana.

    python -m serving.dashboard [--data-root data] [--port 8050]

Kibana und Elasticsearch belegen auf ``srv01`` zusammen 2,75 GiB, und fuer
die Fragen dieses Projekts - je Stadt, Monat und Kategorie - liegen die
Antworten laengst vorberechnet in ``serving/comparison_month``. Das Dashboard
liest diese Tabelle und den Stern direkt mit DuckDB; einen Suchindex braucht
es dafuer nicht. Die Vorlage sind Artans Entwuerfe unter
``docs/bilder/dashboard_*.png``; dieses Modul baut das erste davon,
»Kriminalität im Überblick«.

**Zwei Quellen, mit Absicht.** Gezaehlt wird aus ``comparison_month``, nach
meldender Stadt (``reporting_city``) - dieselbe Zahl wie in Kibana und in
der Vergleichstabelle. Die **Rate** dagegen zaehlt nur Taten in Tracts, die
der Stadt zugeordnet sind, und teilt durch deren Einwohner: genau die Regel
von ``gold_pipeline.raten_je_stadt``, aus der die Abgabedokumente ihre
94,5 und 133,1 je 1'000 nehmen. Eine Rate ueber alle gemeldeten Taten haette
Taten jenseits der Stadtgrenze durch die Einwohner innerhalb geteilt.

**Je 1'000, nicht je 100'000.** Der Entwurf rechnet je 100'000; die Dokumente,
Kibana und die Hypothesen rechnen je 1'000. Eine zweite Einheit waere eine
zweite Wahrheit.

**Ein Zeitraum liegt in einem Jahr.** Eine Rate braucht einen Nenner, und
der Nenner ist das ACS-Vintage des Jahres (``population_vintage``). Ueber
Jahresgrenzen gaebe es zwei - siehe ``gold_pipeline.RATENJAHR``.

**Beim Laden einmal gerechnet, danach im Speicher.** Die Faktentabelle hat
1,85 Mio. Zeilen; das Dashboard verdichtet sie beim Start auf Stadt x Monat x
Kategorie (rund 3'500 Zeilen) und beantwortet jede Anfrage daraus. Aendert
sich der Datenstand, laedt es nach (``Bestand.aktuell``).

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
import threading
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from gold_pipeline import RATENJAHR, einwohner_je_stadt
from storage import for_root
from storage import duckdb as storage_duckdb

PARQUET_FILE = "part-0001.parquet"
STAEDTE = ("chicago", "detroit")
STADTNAMEN = {"chicago": "Chicago", "detroit": "Detroit"}
MASSE = ("anzahl", "anteil", "rate")
#: Zaehlebene der »Deliktstruktur«: Faelle vorn (Entscheid E5), Delikte auf Wunsch.
EBENEN = ("faelle", "delikte")

#: Wie viele Kategorien die Balken einzeln zeigen; der Rest steht unter UEBRIGE.
KATEGORIEN_IM_BALKEN = 6
#: Nicht »Übrige Straftaten«: So hiesse auf Deutsch auch NIBRS 90Z.
UEBRIGE = "Übrige Kategorien"
#: Wie viele Kategorien neben »Alle Delikte« eine eigene Rate bekommen.
KATEGORIEN_IN_DER_RATE = 4
#: Wie oft hoechstens nachgesehen wird, ob ein neuer Stand vorliegt.
PRUEFABSTAND_S = 60.0

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


@dataclass(frozen=True)
class Auswahl:
    """Was oben in der Leiste steht."""

    stadt: str = "beide"
    jahr: int = RATENJAHR
    von: int = 1
    bis: int = 12
    kategorie: str = "alle"
    mass: str = "anzahl"
    ebene: str = "faelle"

    @property
    def staedte(self) -> tuple[str, ...]:
        return STAEDTE if self.stadt == "beide" else (self.stadt,)

    def pruefe(self, jahre: list[int], kategorien: list[str]) -> Auswahl:
        if self.stadt not in ("beide", *STAEDTE):
            raise EingabeFehler(f"Unbekannte Stadt: {self.stadt}")
        if self.jahr not in jahre:
            raise EingabeFehler(f"Kein Jahrgang {self.jahr}")
        if not 1 <= self.von <= self.bis <= 12:
            raise EingabeFehler("Der Zeitraum braucht 1 <= von <= bis <= 12")
        if self.kategorie != "alle" and self.kategorie not in kategorien:
            raise EingabeFehler(f"Unbekannte Kategorie: {self.kategorie}")
        if self.mass not in MASSE:
            raise EingabeFehler(f"Unbekanntes Mass: {self.mass}")
        if self.ebene not in EBENEN:
            raise EingabeFehler(f"Unbekannte Ebene: {self.ebene}")
        return self


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
        # Spalten ausgeschrieben: Ein SELECT * nimmt die Hive-Spalte aus dem
        # Pfad mit (AGENTS.md, »Known pitfalls«).
        con.execute(f"""
            CREATE TABLE monate AS
            SELECT reporting_city AS stadt, month AS monat, nibrs_category AS kategorie,
                   offenses AS delikte, cases AS faelle,
                   days_in_period AS tage, days_in_window AS tage_im_fenster
            FROM read_parquet('{monat}', hive_partitioning=false)""")
        # Die Regel von gold_pipeline.raten_je_stadt: nur Taten in einem Tract
        # mit Stadtzuordnung, Kategorie ueber dim_offense wie in
        # build_comparison, das Vintage je Tat.
        con.execute(f"""
            CREATE TABLE raten AS
            SELECT t.city AS stadt, date_trunc('month', f.date)::DATE AS monat,
                   CASE WHEN f.nibrs_code IS NULL THEN 'unmapped'
                        ELSE d.nibrs_category END AS kategorie,
                   f.population_vintage AS vintage,
                   count(*) AS delikte
            FROM read_parquet('{fakten}', hive_partitioning=false) f
            JOIN read_parquet('{tracts}', hive_partitioning=false) t ON t.geoid = f.tract_geoid
            LEFT JOIN read_parquet('{delikte}', hive_partitioning=false) d USING (nibrs_code)
            WHERE t.city IS NOT NULL
            GROUP BY ALL""")
        # Das Fenster je Stadt, selbst gerechnet. comparison_month tut es seit
        # Vertrag 3 auch (C-10, 1.11.2026), aber das Dashboard liest das
        # aktive Release - und ein Release mit Vertrag 2 rechnet noch am
        # gemeinsamen Fenster beider Staedte: Chicagos Daten enden am
        # 26.9.2026, Detroits am 4.10., also hiesse dort Chicagos September
        # vollstaendig, obwohl vier Tage fehlen.
        con.execute(f"""
            CREATE TABLE fenster AS
            SELECT reporting_city AS stadt, min(date) AS von, max(date) AS bis
            FROM read_parquet('{fakten}', hive_partitioning=false) GROUP BY 1""")
        # Fuer »Zeitverlauf«: Faelle je Wochentag und lokaler Stunde.
        # Genau 00:00 und 12:00 sind ueberbesetzt - Platzhalter fuer eine
        # unbekannte Tatzeit (build_kibana._PLATZHALTERSTUNDEN); sie werden
        # mitgezaehlt, aber markiert, damit die Heatmap sie ausweisen kann.
        con.execute(f"""
            CREATE TABLE stunden AS
            SELECT f.reporting_city AS stadt, date_trunc('month', f.date)::DATE AS monat,
                   isodow(f.date) AS wochentag, f.hour_of_day AS stunde,
                   CASE WHEN f.nibrs_code IS NULL THEN 'unmapped'
                        ELSE d.nibrs_category END AS kategorie,
                   (f.hour_of_day IN (0, 12) AND minute(f.occurred_at_local) = 0
                    AND second(f.occurred_at_local) = 0) AS platzhalter,
                   count(*) FILTER (f.counts_case) AS faelle
            FROM read_parquet('{fakten}', hive_partitioning=false) f
            LEFT JOIN read_parquet('{delikte}', hive_partitioning=false) d USING (nibrs_code)
            GROUP BY ALL""")
        # Der Nenner der Heatmap: wie viele Montage, Dienstage ... ein Monat je
        # Stadt mit Daten hat.
        con.execute(f"""
            CREATE TABLE tage AS
            SELECT reporting_city AS stadt, date_trunc('month', date)::DATE AS monat,
                   isodow(date) AS wochentag, count(DISTINCT date) AS n
            FROM read_parquet('{fakten}', hive_partitioning=false) GROUP BY ALL""")
        # Fuer »Geografie«: Faelle je Tract und Monat nach der Regel von
        # gold_pipeline.raten_je_tract, dazu Einwohner und Umrisse der Tracts
        # und je Stadt, wie viele Faelle keinen Ort in der Stadt haben.
        geo, _ = _quelle(ablage, release, "gold", "dim_tract_geo")
        con.execute(f"""
            CREATE TABLE tract_monat AS
            SELECT f.reporting_city AS stadt, f.tract_geoid AS geoid,
                   date_trunc('month', f.date)::DATE AS monat,
                   CASE WHEN f.nibrs_code IS NULL THEN 'unmapped'
                        ELSE d.nibrs_category END AS kategorie,
                   f.population_vintage AS vintage,
                   count(*) FILTER (f.counts_case) AS faelle, count(*) AS delikte
            FROM read_parquet('{fakten}', hive_partitioning=false) f
            LEFT JOIN read_parquet('{delikte}', hive_partitioning=false) d USING (nibrs_code)
            WHERE f.geo_status = 'inside_city'
            GROUP BY ALL""")
        con.execute(f"""
            CREATE TABLE verortung AS
            SELECT f.reporting_city AS stadt, date_trunc('month', f.date)::DATE AS monat,
                   CASE WHEN f.nibrs_code IS NULL THEN 'unmapped'
                        ELSE d.nibrs_category END AS kategorie,
                   f.geo_status, count(*) FILTER (f.counts_case) AS faelle
            FROM read_parquet('{fakten}', hive_partitioning=false) f
            LEFT JOIN read_parquet('{delikte}', hive_partitioning=false) d USING (nibrs_code)
            GROUP BY ALL""")
        con.execute(f"""
            CREATE TABLE tract_geo AS
            SELECT geoid, city, tract_name
            FROM read_parquet('{geo}', hive_partitioning=false)""")
        con.execute(f"""
            CREATE TABLE tract_einwohner AS
            SELECT geoid, vintage, population
            FROM read_parquet('{acs}', hive_partitioning=false)
            WHERE geoid IN (SELECT geoid FROM tract_geo)""")
        # Fuer »Datenqualität«: Taten je Zuordnung, Verortung und Ortszeit,
        # und je Stadt und Monat, wie viele Delikt-IDs mehrfach vorkommen.
        con.execute(f"""
            CREATE TABLE qualitaet AS
            SELECT f.reporting_city AS stadt, date_trunc('month', f.date)::DATE AS monat,
                   CASE WHEN f.nibrs_code IS NULL THEN 'unmapped'
                        ELSE d.nibrs_category END AS kategorie,
                   f.mapping_status, f.geo_status,
                   coalesce(f.local_time_ambiguous, false) AS ortszeit_mehrdeutig,
                   count(*) AS delikte
            FROM read_parquet('{fakten}', hive_partitioning=false) f
            LEFT JOIN read_parquet('{delikte}', hive_partitioning=false) d USING (nibrs_code)
            GROUP BY ALL""")
        con.execute(f"""
            CREATE TABLE doppelte AS
            SELECT reporting_city AS stadt, date_trunc('month', date)::DATE AS monat,
                   count(*) - count(DISTINCT offense_id) AS doppelt
            FROM read_parquet('{fakten}', hive_partitioning=false) GROUP BY ALL""")
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
        vintages = [r[0] for r in con.execute(
            "SELECT DISTINCT vintage FROM raten WHERE vintage IS NOT NULL").fetchall()]
        con.execute("CREATE TABLE einwohner (stadt VARCHAR, vintage INTEGER, n BIGINT)")
        for v in vintages:
            con.execute(f"INSERT INTO einwohner SELECT city, {int(v)}, n FROM ("
                        + einwohner_je_stadt(f"read_parquet('{tracts}', hive_partitioning=false)",
                                             f"read_parquet('{acs}', hive_partitioning=false)",
                                             str(int(v))) + ")")
        # Fuer »Quellbewegung«: die Bewegung der Quellen, mit der NIBRS-Kategorie
        # ueber dieselbe Dimension wie die Taten. Ein aelteres Release fuehrt
        # die Tabelle nicht - dann bleibt das Brett leer und sagt warum, statt
        # dass das ganze Dashboard nicht laedt.
        from serving.dashboard.quellbewegung import lade_bewegung
        bewegung = lade_bewegung(con, ablage, release, delikte)
        stand = json.loads(monat_manifest)
        with self._sperre:
            alt = getattr(self, "_con", None)
            self._con = con
            self._abdruck_jetzt = aktuell
            self.stand = {
                "gebaut": stand.get("built_at_utc"),
                "release": kennung,
            }
            self.karten = karten
            self.beispiele = beispiele
            self.bewegung = bewegung
            self.jahre = [r[0] for r in con.execute(
                "SELECT DISTINCT year(monat) FROM monate ORDER BY 1").fetchall()]
            self.kategorien = [r[0] for r in con.execute(
                "SELECT kategorie FROM monate GROUP BY 1 ORDER BY sum(delikte) DESC").fetchall()]
        if alt is not None:
            alt.close()

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
            "staedte": [{"wert": "beide", "name": "Beide"}]
            + [{"wert": s, "name": STADTNAMEN[s]} for s in STAEDTE],
            "jahre": self.jahre,
            "kategorien": [{"wert": "alle", "name": "Alle"}]
            + sorted(({"wert": k, "name": kategorie_de(k)} for k in self.kategorien),
                     key=lambda k: k["name"]),
            "vorgabe": {"stadt": "beide", "jahr": RATENJAHR if RATENJAHR in self.jahre
                        else self.jahre[-1], "von": 1, "bis": 12,
                        "kategorie": "alle", "mass": "anzahl", "ebene": "faelle",
                        # »Quellbewegung«: Zeitstempel vorgabemaessig ausgeblendet.
                        "felder": "inhalt"},
            "letzter_monat": letzter,
            "stand": self.stand,
        }

    def auswahl(self, werte: dict[str, str]) -> Auswahl:
        try:
            a = Auswahl(
                stadt=werte.get("stadt", "beide"),
                jahr=int(werte.get("jahr", RATENJAHR)),
                von=int(werte.get("von", 1)),
                bis=int(werte.get("bis", 12)),
                kategorie=werte.get("kategorie", "alle"),
                mass=werte.get("mass", "anzahl"),
                ebene=werte.get("ebene", "faelle"),
            )
        except ValueError as fehler:
            raise EingabeFehler("Jahr und Monate muessen Zahlen sein") from fehler
        return a.pruefe(self.jahre, self.kategorien)

    # -- Das Brett »Datenqualität« -------------------------------------------

    def datenqualitaet(self, a: Auswahl) -> dict[str, Any]:
        from serving.dashboard.datenqualitaet import datenqualitaet
        return datenqualitaet(self, a)

    def referenz(self, jahr: int) -> dict[str, Any]:
        """Was eine Auswertung des Jahres an Referenzdaten braucht - und ob es da ist."""
        cur = self._cursor()
        vintages = [r[0] for r in cur.execute(
            "SELECT DISTINCT vintage FROM raten WHERE year(monat) = $j AND vintage IS NOT NULL",
            {"j": jahr}).fetchall()]
        tracts = dict(cur.execute("SELECT city, count(*) FROM tract_geo GROUP BY 1").fetchall())
        return {
            "acs_vintage": vintages[0] if len(vintages) == 1 else None,
            "acs_vintages": sorted(vintages),
            "kategorien": len([k for k in self.kategorien if k != "unmapped"]),
            "tracts": {s: int(tracts.get(s, 0)) for s in STAEDTE},
            "release": self.stand.get("release"),
        }

    # -- Das Brett »Quellbewegung« ------------------------------------------

    def quellbewegung(self, werte: dict[str, str]) -> dict[str, Any]:
        from serving.dashboard.quellbewegung import quellbewegung
        return quellbewegung(self, werte)

    # -- Das Brett »Deliktstruktur« ------------------------------------------

    def deliktstruktur(self, a: Auswahl) -> dict[str, Any]:
        from serving.dashboard.deliktstruktur import deliktstruktur
        return deliktstruktur(self, a)

    # -- Das Brett »Geografie« -----------------------------------------------

    def geografie(self, a: Auswahl) -> dict[str, Any]:
        from serving.dashboard.geografie import geografie
        return geografie(self, a)

    # -- Das Brett »Zeitverlauf« ---------------------------------------------

    def zeitverlauf(self, a: Auswahl) -> dict[str, Any]:
        from serving.dashboard.zeitverlauf import zeitverlauf
        return zeitverlauf(self, a)

    # -- Das Brett »Überblick« -----------------------------------------------

    def ueberblick(self, a: Auswahl) -> dict[str, Any]:
        cur = self._cursor()
        von, bis = date(a.jahr, a.von, 1), date(a.jahr, a.bis, 1)
        staedte = list(a.staedte)
        kat = "" if a.kategorie == "alle" else "AND kategorie = $kat"
        p = {"staedte": staedte, "von": von, "bis": bis}
        if kat:
            p["kat"] = a.kategorie

        def summe(spalte: str, monate: list[date]) -> int:
            return cur.execute(
                f"SELECT coalesce(sum({spalte}), 0) FROM monate WHERE stadt IN $staedte "
                f"AND monat IN $monate {kat}",
                {k: v for k, v in p.items() if k in ("staedte", "kat")} | {"monate": monate}
            ).fetchone()[0]

        monate = [date(a.jahr, m, 1) for m in range(a.von, a.bis + 1)]
        vormonate = [date(a.jahr - 1, m, 1) for m in range(a.von, a.bis + 1)]
        abdeckung = self._abdeckung(cur, staedte, monate)
        voriges = self._abdeckung(cur, staedte, vormonate)

        def voll(abd, i: int) -> bool:
            return all(abd[s]["monate"][i] == "voll" for s in staedte)

        vollstaendig = sum(voll(abdeckung, i) for i in range(len(monate)))
        # Zum Vorjahr nur Monate, die in beiden Jahren ganz vorliegen: Neun
        # Monate 2026 gegen zwoelf Monate 2025 waeren ein Rueckgang, der keiner
        # ist (build_kibana._TEILJAHR).
        vergleichbar = [i for i in range(len(monate)) if voll(abdeckung, i) and voll(voriges, i)]
        jetzt_v = summe("delikte", [monate[i] for i in vergleichbar]) if vergleichbar else 0
        vorher_v = summe("delikte", [vormonate[i] for i in vergleichbar]) if vergleichbar else 0

        # Ein Monat ohne Daten ist eine Luecke (None), keine Null.
        verlauf = {s: [None if abdeckung[s]["monate"][i] == "fehlt" else 0
                       for i in range(len(monate))] for s in staedte}
        for s, m, n in cur.execute(
                f"SELECT stadt, monat, sum(delikte) FROM monate WHERE stadt IN $staedte "
                f"AND monat BETWEEN $von AND $bis {kat} GROUP BY 1, 2", p).fetchall():
            verlauf[s][monate.index(m)] = int(n)

        return {
            "auswahl": a.__dict__,
            "kennzahlen": {
                "delikte": int(summe("delikte", monate)),
                "faelle": int(summe("faelle", monate)),
                "vorjahr_prozent": (round((jetzt_v - vorher_v) * 100.0 / vorher_v, 1)
                                    if vorher_v else None),
                "vorjahr_monate": len(vergleichbar),
                "vollstaendige_monate": vollstaendig,
                "monate": len(monate),
            },
            "verlauf": {"monate": [m.isoformat() for m in monate],
                        "reihen": [{"stadt": s, "name": STADTNAMEN[s], "werte": verlauf[s],
                                    "status": abdeckung[s]["monate"]}
                                   for s in staedte]},
            "kategorien": self._kategorien(cur, a, staedte, p, kat),
            "raten": self._raten(cur, a, staedte, von, bis),
            "abdeckung": [{"stadt": s, "name": STADTNAMEN[s], **abdeckung[s]}
                          for s in staedte],
            "stand": self.stand,
        }

    def _kategorien(self, cur, a: Auswahl, staedte, p, kat) -> dict[str, Any]:
        """Delikte je Kategorie und Stadt - als Anzahl, Anteil oder Rate."""
        zeilen = cur.execute(
            f"SELECT stadt, kategorie, sum(delikte) FROM monate WHERE stadt IN $staedte "
            f"AND monat BETWEEN $von AND $bis {kat} GROUP BY 1, 2", p).fetchall()
        gesamt: dict[str, int] = {}
        for _, k, n in zeilen:
            gesamt[k] = gesamt.get(k, 0) + int(n)
        oben = [k for k, _ in sorted(gesamt.items(), key=lambda kv: (-kv[1], kv[0]))]
        einzeln, rest = oben[:KATEGORIEN_IM_BALKEN], oben[KATEGORIEN_IM_BALKEN:]
        werte = {s: {k: 0 for k in einzeln} for s in staedte}
        for s, k, n in zeilen:
            ziel = k if k in einzeln else UEBRIGE
            werte[s][ziel] = werte[s].get(ziel, 0) + int(n)
        namen = einzeln + ([UEBRIGE] if rest else [])
        if a.mass == "anteil":
            for s in staedte:
                summe = sum(werte[s].values()) or 1
                werte[s] = {k: round(v * 100.0 / summe, 1) for k, v in werte[s].items()}
        elif a.mass == "rate":
            werte = self._raten_je(cur, a, staedte, einzeln, rest)
        return {
            "mass": a.mass,
            "zeilen": [{"kategorie": k, "name": kategorie_de(k),
                        "werte": {s: werte[s].get(k, 0) for s in staedte}} for k in namen],
        }

    def _nenner(self, cur, a: Auswahl, staedte) -> dict[str, int]:
        vintages = [r[0] for r in cur.execute(
            "SELECT DISTINCT vintage FROM raten WHERE year(monat) = $j AND vintage IS NOT NULL",
            {"j": a.jahr}).fetchall()]
        if len(vintages) != 1:
            # Wie raten_je_stadt: gemischte Vintages ergeben keine Rate.
            return {}
        return {s: n for s, n in cur.execute(
            "SELECT stadt, n FROM einwohner WHERE vintage = $v AND stadt IN $staedte",
            {"v": vintages[0], "staedte": staedte}).fetchall()}

    def _raten_je(self, cur, a: Auswahl, staedte, einzeln, rest) -> dict[str, dict[str, float]]:
        nenner = self._nenner(cur, a, staedte)
        p = {"staedte": staedte, "von": date(a.jahr, a.von, 1), "bis": date(a.jahr, a.bis, 1)}
        werte: dict[str, dict[str, float]] = {s: {} for s in staedte}
        for s, k, n in cur.execute(
                "SELECT stadt, kategorie, sum(delikte) FROM raten WHERE stadt IN $staedte "
                "AND monat BETWEEN $von AND $bis GROUP BY 1, 2", p).fetchall():
            ziel = k if k in einzeln else (UEBRIGE if k in rest else None)
            if ziel is not None:
                werte[s][ziel] = werte[s].get(ziel, 0) + int(n)
        return {s: {k: (round(v * 1000.0 / nenner[s], 1) if s in nenner else None)
                    for k, v in werte[s].items()} for s in staedte}

    def _raten(self, cur, a: Auswahl, staedte, von, bis) -> dict[str, Any]:
        """Delikte je 1'000 Einwohner: alle Delikte und die haeufigsten Kategorien."""
        nenner = self._nenner(cur, a, staedte)
        p = {"staedte": staedte, "von": von, "bis": bis}
        je = cur.execute(
            "SELECT stadt, kategorie, sum(delikte) FROM raten WHERE stadt IN $staedte "
            "AND monat BETWEEN $von AND $bis GROUP BY 1, 2", p).fetchall()
        gesamt: dict[str, int] = {}
        for _, k, n in je:
            gesamt[k] = gesamt.get(k, 0) + int(n)
        if a.kategorie != "alle":
            auswahl = [a.kategorie]
        else:
            auswahl = [k for k, _ in sorted(gesamt.items(), key=lambda kv: (-kv[1], kv[0]))
                       ][:KATEGORIEN_IN_DER_RATE]

        def rate(s: str, n: int) -> float | None:
            return round(n * 1000.0 / nenner[s], 1) if s in nenner else None

        zeilen = [{"kategorie": "alle", "name": "Alle Delikte",
                   "werte": {s: rate(s, sum(int(n) for st, _, n in je if st == s))
                             for s in staedte}}]
        for k in auswahl:
            zeilen.append({"kategorie": k, "name": kategorie_de(k),
                           "werte": {s: rate(s, sum(int(n) for st, kk, n in je
                                                   if st == s and kk == k))
                                     for s in staedte}})
        return {"einwohner": nenner, "zeilen": zeilen}

    @staticmethod
    def _abdeckung(cur, staedte, monate: list[date]) -> dict[str, dict[str, Any]]:
        """Je Stadt und Monat: voll, teilweise oder fehlend - und der letzte Monat.

        Gemessen am Fenster **dieser** Stadt (Tabelle ``fenster``), nicht am
        gemeinsamen von ``comparison_month``.
        """
        fenster = {s: (v, b) for s, v, b in cur.execute(
            "SELECT stadt, von, bis FROM fenster WHERE stadt IN $staedte",
            {"staedte": staedte}).fetchall()}
        ergebnis = {}
        for s in staedte:
            je_monat = []
            for m in monate:
                ende = date(m.year + m.month // 12, m.month % 12 + 1, 1) - timedelta(days=1)
                v, b = fenster.get(s, (None, None))
                if v is None or b < m or v > ende:
                    je_monat.append("fehlt")
                else:
                    je_monat.append("voll" if v <= m and b >= ende else "teil")
            letzter = (date(fenster[s][1].year, fenster[s][1].month, 1)
                       if s in fenster else None)
            mit_daten = [m for m, z in zip(monate, je_monat) if z != "fehlt"]
            ergebnis[s] = {
                "monate": je_monat,
                "vollstaendig": je_monat.count("voll"),
                "von": mit_daten[0].isoformat() if mit_daten else None,
                "bis": mit_daten[-1].isoformat() if mit_daten else None,
                "letzter_monat": letzter.isoformat() if letzter else None,
                "letzter_tag": fenster[s][1].isoformat() if s in fenster else None,
                "status": ("vollstaendig" if je_monat and all(z == "voll" for z in je_monat)
                           else "keine_daten" if not mit_daten else "unvollstaendig"),
            }
        return ergebnis
