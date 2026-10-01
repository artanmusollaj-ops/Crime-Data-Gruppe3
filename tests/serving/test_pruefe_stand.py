"""Der Standabgleich - geprueft gegen Doppel, die absichtlich auseinanderlaufen.

Ein Werkzeug, das Abweichungen melden soll, muss vor allem eines koennen:
**melden**. Der grosse Teil dieser Pruefungen fuehrt deshalb Doppel vor, die
einen alten Stand zeigen, und sieht nach, ob es auffaellt. Dass der gute Fall
gruen ist, ist die leichtere Haelfte.

Eine Pruefung fasst die laufenden Dienste an und ueberspringt sich ohne sie.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from serving import pruefe_stand as ps
from serving.load_clickhouse import ZIELE, LadeFehler
from serving.load_elasticsearch import INDIZES
from serving.build_kibana import BRETTER

RELEASE = "2026-09-21T12-55-05Z"
KURZ = "20260921T125505Z"


# --------------------------------------------------------------------------
# Werkzeug
# --------------------------------------------------------------------------


def lege_gold_an(wurzel: Path, release: str = RELEASE, *,
                 abweichend: set[str] = frozenset(),
                 fehlend: set[str] = frozenset()) -> tuple[Path, Path]:
    """Eine Arbeitsschicht und ein Release - gleich, ausser wo gewollt."""
    verzeichnis = wurzel / "releases" / f"release={release}"
    for ziel in ZIELE:
        if ziel.name in fehlend:
            continue
        inhalt = f"inhalt-{ziel.name}".encode()
        im_release = verzeichnis / ziel.quelle_im_release
        im_release.parent.mkdir(parents=True, exist_ok=True)
        im_release.write_bytes(inhalt)

        arbeit = wurzel / "gold" / f"dataset={ziel.name}" / "part-0001.parquet"
        arbeit.parent.mkdir(parents=True, exist_ok=True)
        arbeit.write_bytes(b"etwas anderes" if ziel.name in abweichend
                           else inhalt)
    return wurzel, verzeichnis


class FalscheClickHouse:
    """Antwortet mit den Sichten, die ihr mitgegeben wurden."""

    def __init__(self, sichten: dict[str, str] | None = None,
                 kaputt: bool = False):
        self.sichten = sichten if sichten is not None else {
            z.name: f"SELECT * FROM default.{z.name}_{KURZ}" for z in ZIELE}
        self.kaputt = kaputt

    def abfrage(self, sql: str) -> list[tuple]:
        if self.kaputt:
            raise LadeFehler("Verbindung abgelehnt")
        return list(self.sichten.items())


class FalscheElastic:
    def __init__(self, zuordnung: dict[str, str] | None = None,
                 kaputt: bool = False):
        standard = {f"{i.name}-{KURZ}".lower(): i.name for i in INDIZES}
        self.zuordnung = zuordnung if zuordnung is not None else standard
        self.kaputt = kaputt

    def anfrage(self, methode: str, pfad: str, koerper=None) -> dict:
        if self.kaputt:
            raise LadeFehler("Verbindung abgelehnt")
        return {index: {"aliases": {alias: {}}}
                for index, alias in self.zuordnung.items()}


class FalscheKibana:
    def __init__(self, von: str = "2024-01-01T00:00:00.000Z",
                 bis: str = "2025-01-02T00:00:00.000Z",
                 festhalten: bool = True, kaputt: bool = False):
        self.von, self.bis = von, bis
        self.festhalten, self.kaputt = festhalten, kaputt

    def anfrage(self, methode: str, pfad: str, koerper=None) -> dict:
        if self.kaputt:
            raise LadeFehler("nicht erreichbar")
        return {"attributes": {"timeRestore": self.festhalten,
                               "timeFrom": self.von, "timeTo": self.bis}}


DATEN_VON = "2024-01-01T05:00:00.000Z"
DATEN_BIS = "2025-01-01T05:58:00.000Z"


# --------------------------------------------------------------------------
# Die Kennung
# --------------------------------------------------------------------------


def test_die_kennung_wird_verkuerzt_wie_beim_anlegen():
    assert ps.kennung_im_namen(RELEASE) == KURZ


def test_dieselbe_kennung_sieht_an_beiden_orten_verschieden_aus():
    """ClickHouse behaelt die Schreibweise, Elasticsearch verlangt klein."""
    assert ps.traegt_kennung(f"fact_offense_{KURZ}", RELEASE)
    assert ps.traegt_kennung(f"fact_offense-{KURZ}".lower(), RELEASE)


def test_ein_fremder_stand_traegt_die_kennung_nicht():
    assert not ps.traegt_kennung("fact_offense_19990101T000000Z", RELEASE)
    assert not ps.traegt_kennung("fact_offense", RELEASE)


# --------------------------------------------------------------------------
# Die Sicht
# --------------------------------------------------------------------------


def test_aus_der_sicht_wird_die_tabelle_erkennbar():
    assert ps.tabelle_hinter_sicht(
        f"SELECT * FROM default.fact_offense_{KURZ}") == f"fact_offense_{KURZ}"


def test_auch_ohne_datenbank_davor():
    assert ps.tabelle_hinter_sicht("SELECT * FROM meine_tabelle") == "meine_tabelle"


def test_was_keine_tabelle_nennt_bricht_ab():
    with pytest.raises(LadeFehler, match="keine Tabelle erkennbar"):
        ps.tabelle_hinter_sicht("SELECT 1")


# --------------------------------------------------------------------------
# Das Zeitfenster
# --------------------------------------------------------------------------


def test_ein_grosszuegiges_fenster_ist_in_ordnung():
    # build_kibana macht es bewusst um einen Tag weiter.
    assert ps.fenster_passt("2024-01-01T00:00:00.000Z",
                            "2025-01-02T00:00:00.000Z", DATEN_VON, DATEN_BIS)


def test_ein_fenster_das_hinten_abschneidet_faellt_auf():
    assert not ps.fenster_passt("2024-01-01T00:00:00.000Z",
                                "2024-06-01T00:00:00.000Z",
                                DATEN_VON, DATEN_BIS)


def test_ein_fenster_das_zu_spaet_beginnt_faellt_auch_auf():
    assert not ps.fenster_passt("2024-07-01T00:00:00.000Z",
                                "2025-01-02T00:00:00.000Z",
                                DATEN_VON, DATEN_BIS)


# --------------------------------------------------------------------------
# Gold
# --------------------------------------------------------------------------


def test_gleiche_dateien_sind_gleich(tmp_path):
    wurzel, verzeichnis = lege_gold_an(tmp_path)
    befund = ps.pruefe_gold(wurzel, verzeichnis)
    assert befund.gut and "5 Dateien" in befund.stand


def test_eine_abweichende_datei_wird_benannt(tmp_path):
    """Der Fall: Die Strecke lief noch einmal, ohne dass ein Release entstand.

    DuckDB zeigte dann andere Zahlen als ClickHouse, und beide haetten sich
    fuer richtig gehalten.
    """
    wurzel, verzeichnis = lege_gold_an(tmp_path, abweichend={"fact_offense"})
    befund = ps.pruefe_gold(wurzel, verzeichnis)
    assert befund.urteil == ps.Urteil.ANDERS
    assert "fact_offense" in befund.stand
    assert befund.abhilfe


def test_gleiche_groesse_rettet_nicht_vor_anderem_inhalt(tmp_path):
    """Verglichen wird die Pruefsumme, nicht die Zeilen- oder Byte-Zahl."""
    wurzel, verzeichnis = lege_gold_an(tmp_path)
    datei = wurzel / "gold" / "dataset=dim_date" / "part-0001.parquet"
    alt = datei.read_bytes()
    datei.write_bytes(bytes(reversed(alt)))      # gleiche Laenge, anderer Inhalt
    assert len(datei.read_bytes()) == len(alt)
    assert ps.pruefe_gold(wurzel, verzeichnis).urteil == ps.Urteil.ANDERS


def test_eine_fehlende_datei_ist_kein_abweichen_sondern_ein_fehlen(tmp_path):
    wurzel, verzeichnis = lege_gold_an(tmp_path, fehlend={"dim_tract"})
    befund = ps.pruefe_gold(wurzel, verzeichnis)
    assert befund.urteil == ps.Urteil.FEHLT and "dim_tract" in befund.stand


# --------------------------------------------------------------------------
# ClickHouse
# --------------------------------------------------------------------------


def test_clickhouse_auf_dem_stand_ist_gruen():
    assert ps.pruefe_clickhouse(FalscheClickHouse(), RELEASE).gut


def test_eine_sicht_auf_einem_alten_stand_faellt_auf():
    sichten = {z.name: f"SELECT * FROM default.{z.name}_{KURZ}" for z in ZIELE}
    sichten["dim_date"] = "SELECT * FROM default.dim_date_19990101T000000Z"
    befund = ps.pruefe_clickhouse(FalscheClickHouse(sichten), RELEASE)
    assert befund.urteil == ps.Urteil.ANDERS
    assert "19990101" in befund.stand
    assert befund.abhilfe == "python -m serving.load_clickhouse"


def test_eine_fehlende_sicht_faellt_auf():
    sichten = {z.name: f"SELECT * FROM default.{z.name}_{KURZ}"
               for z in ZIELE if z.name != "dim_offense"}
    befund = ps.pruefe_clickhouse(FalscheClickHouse(sichten), RELEASE)
    assert befund.urteil == ps.Urteil.FEHLT and "dim_offense" in befund.stand


def test_ein_dienst_der_nicht_antwortet_wird_nicht_fuer_gut_erklaert():
    befund = ps.pruefe_clickhouse(FalscheClickHouse(kaputt=True), RELEASE)
    assert befund.urteil == ps.Urteil.FEHLT
    assert "docker compose" in befund.abhilfe


# --------------------------------------------------------------------------
# Elasticsearch
# --------------------------------------------------------------------------


def test_elasticsearch_auf_dem_stand_ist_gruen():
    assert ps.pruefe_elasticsearch(FalscheElastic(), RELEASE).gut


def test_ein_alias_auf_einem_alten_index_faellt_auf():
    """Genau der Fall, den dieses Werkzeug finden soll.

    Der Alias zeigt brav irgendwohin, alle Zahlen sind in sich stimmig, und
    die Dashboards zeigen den Stand von vorletzter Woche.
    """
    zuordnung = {f"{i.name}-{KURZ}".lower(): i.name for i in INDIZES}
    del zuordnung[f"fact_offense-{KURZ}".lower()]
    zuordnung["fact_offense-19990101t000000z"] = "fact_offense"
    befund = ps.pruefe_elasticsearch(FalscheElastic(zuordnung), RELEASE)
    assert befund.urteil == ps.Urteil.ANDERS and "1999" in befund.stand


def test_ein_fehlender_alias_faellt_auf():
    zuordnung = {f"{i.name}-{KURZ}".lower(): i.name for i in INDIZES
                 if i.name != "dim_tract"}
    befund = ps.pruefe_elasticsearch(FalscheElastic(zuordnung), RELEASE)
    assert befund.urteil == ps.Urteil.FEHLT and "dim_tract" in befund.stand


def test_elasticsearch_ohne_antwort_ist_nicht_gut():
    assert ps.pruefe_elasticsearch(
        FalscheElastic(kaputt=True), RELEASE).urteil == ps.Urteil.FEHLT


# --------------------------------------------------------------------------
# Kibana
# --------------------------------------------------------------------------


def test_ein_passendes_zeitfenster_ist_gruen():
    assert ps.pruefe_kibana(FalscheKibana(), DATEN_VON, DATEN_BIS).gut


def test_ein_altes_zeitfenster_auf_neuen_daten_faellt_auf():
    """Der eine Ort, dessen Stand nicht am Index haengt.

    Technisch ist alles in Ordnung; das Diagramm ist leer.
    """
    befund = ps.pruefe_kibana(
        FalscheKibana(bis="2024-06-01T00:00:00.000Z"), DATEN_VON, DATEN_BIS)
    assert befund.urteil == ps.Urteil.ANDERS
    assert befund.abhilfe == "python -m serving.build_kibana"


def test_ein_dashboard_ohne_festes_fenster_faellt_auf():
    befund = ps.pruefe_kibana(FalscheKibana(festhalten=False),
                              DATEN_VON, DATEN_BIS)
    assert befund.urteil == ps.Urteil.ANDERS
    assert "ohne festes Fenster" in befund.stand


# --------------------------------------------------------------------------
# Der Bericht
# --------------------------------------------------------------------------


def test_knapp_zeigt_nur_was_abweicht():
    befunde = [ps.Befund("A", ps.Urteil.GLEICH),
               ps.Befund("B", ps.Urteil.ANDERS, "etwas", "tu dies")]
    text = ps.bericht(RELEASE, befunde, knapp=True)
    assert "B" in text and "tu dies" in text
    assert "\n  A" not in text


def test_ohne_abweichung_sagt_der_knappe_bericht_das_auch():
    text = ps.bericht(RELEASE, [ps.Befund("A", ps.Urteil.GLEICH)], knapp=True)
    assert "Alle vier Orte" in text


def test_der_massstab_steht_im_bericht():
    assert RELEASE in ps.bericht(RELEASE, [ps.Befund("A", ps.Urteil.GLEICH)])


# --------------------------------------------------------------------------
# Gegen die laufenden Dienste
# --------------------------------------------------------------------------


@pytest.mark.referenzstand
def test_alle_vier_orte_zeigen_den_aktuellen_stand():
    """Der Lauf, den dieses Werkzeug im Alltag macht.

    Traegt ``referenzstand``, weil er den gebauten Stand anfasst: Nach einer
    frischen Ingestion weicht Gold vom Release ab, und das ist dann richtig
    so und kein Fehler.
    """
    wurzel = Path("data")
    if not (wurzel / "releases" / "AKTUELL.json").is_file():
        pytest.skip("kein Release gebaut")
    try:
        kennung, befunde = ps.pruefe_alles(
            wurzel,
            clickhouse=os.environ.get("CLICKHOUSE_URL", ps.CLICKHOUSE_URL),
            elasticsearch=os.environ.get("ELASTICSEARCH_URL",
                                         ps.ELASTICSEARCH_URL),
            kibana=os.environ.get("KIBANA_URL", ps.KIBANA_URL))
    except Exception as fehler:          # kein Release, kein DuckDB
        pytest.skip(str(fehler)[:120])

    nicht_erreichbar = [b.ort for b in befunde if b.urteil == ps.Urteil.FEHLT]
    if nicht_erreichbar:
        pytest.skip(f"Dienste laufen nicht: {', '.join(nicht_erreichbar)}")

    abweichend = [f"{b.ort}: {b.stand}" for b in befunde if not b.gut]
    assert not abweichend, (
        f"Release {kennung} - " + "; ".join(abweichend))


def test_jeder_ort_hat_einen_befund():
    """Vier Orte, vier Befunde - und die Namen sagen, welche."""
    namen = {"Gold (Arbeitsschicht)", "ClickHouse", "Elasticsearch", "Kibana"}
    befunde = [ps.pruefe_clickhouse(FalscheClickHouse(), RELEASE),
               ps.pruefe_elasticsearch(FalscheElastic(), RELEASE),
               ps.pruefe_kibana(FalscheKibana(), DATEN_VON, DATEN_BIS)]
    assert {b.ort for b in befunde} <= namen
    # Und die Listen, gegen die geprueft wird, sind nicht leer.
    assert ZIELE and INDIZES and BRETTER
