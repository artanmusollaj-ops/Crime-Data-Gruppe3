"""Detroits Delta-Ladeweg: Jahrgang nach Tatzeit, Auswahl nach Aenderungszeit.

Bis zum 18.9.2026 lud Detroit den Jahrgang 2024 bei jedem Gesamtlauf ganz -
88'686 Zeilen fuer die paar Dutzend, die sich geaendert hatten. Chicago machte
es laengst anders. Der Grund fuer den Unterschied war ein gemessener: **54,6 %**
des Jahrgangs 2024 wurden mehr als ein Jahr nach der Tat noch geaendert
(Notebook 13, Schritt 12) - ein Delta nach *Tatdatum* haette keine dieser
Korrekturen gesehen.

Diese Messung ist weiterhin wahr; sie sagt nur nicht, dass kein Delta geht,
sondern **worauf** es gehen muss. Die zweite Messung (18.9.2026, vier
Schnappschuesse) sagt es: 1'270 Zeilen aenderten sich inhaltlich, **jede
einzelne** mit einem neuen ``updated_at``, keine ohne. Vier Zeilen tragen
ueberhaupt keinen Stempel - die kommen deshalb immer mit.

Was hier geprueft wird, ist genau diese Konstruktion: dass beide Bedingungen
in der Abfrage stehen, dass die Zeilen ohne Stempel nicht durchfallen, dass das
Wasserzeichen aus den eigenen Manifesten kommt und nie zurueckrueckt, und dass
kein Modus versehentlich die Zeitachse des anderen benutzt.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import re

import pytest

from detroit_pipeline.detroit_arcgis import (
    ArcGISLayerInfo,
    DataQualityError,
    build_delta_where,
    build_year_where,
    delta_bedingung,
)
from detroit_pipeline.extract_detroit import (
    LOOKBACK_DAYS,
    delta_start,
    extract_delta,
    extract_year,
    previous_watermark,
)


# --------------------------------------------------------------------------
# Eine Quelle, die auf die WHERE-Klausel hoert
# --------------------------------------------------------------------------


def ms(text: str) -> int:
    """ISO-Zeitpunkt -> Millisekunden seit Epoch, wie ArcGIS sie liefert."""
    return int(datetime.fromisoformat(text).timestamp() * 1000)


class FakeQuelle:
    """Ein ArcGIS-Doppelgaenger, der den Delta-Filter wirklich anwendet.

    Ein Fake, der immer alle Zeilen zurueckgibt, wuerde jeden Delta-Test
    bestehen - auch einen, dessen WHERE-Klausel nichts einschraenkt. Dieser
    liest den Stempel aus der Klausel und liefert nur, was dazu passt.
    """

    layer_url = "https://example.invalid/FeatureServer/0"

    def __init__(self, stempel: dict[int, str | None]) -> None:
        self.aufzeichner = None
        self.stempel = {oid: (ms(w) if w else None) for oid, w in stempel.items()}
        self.gefragt: list[str] = []

    # -- Auswahl ----------------------------------------------------------
    def _ids(self, where: str) -> list[int]:
        treffer = re.search(r"updated_at >= TIMESTAMP '([^']+)'", where)
        if treffer is None:
            return sorted(self.stempel)
        ab = ms(treffer.group(1).replace(" ", "T") + "+00:00")
        # "OR updated_at IS NULL" - die Stempellosen kommen immer mit.
        return sorted(o for o, s in self.stempel.items() if s is None or s >= ab)

    # -- Client-Schnittstelle ---------------------------------------------
    def get_layer_info(self) -> ArcGISLayerInfo:
        return ArcGISLayerInfo(
            object_id_field="ESRI_OID", max_record_count=2000,
            schema_fingerprint="test-schema",
            fields=("ESRI_OID", "offense_category", "incident_occurred_at",
                    "updated_at"),
        )

    def get_count(self, where: str, *, name: str = "count") -> int:
        self.gefragt.append(where)
        return len(self._ids(where))

    def get_object_ids(self, where: str) -> tuple[str, list[int]]:
        self.gefragt.append(where)
        return "ESRI_OID", self._ids(where)

    def iter_features(self, object_ids, **kwargs):
        for oid in object_ids:
            yield {
                "attributes": {
                    "ESRI_OID": oid,
                    "incident_entry_id": f"ENTRY-{oid}",
                    "offense_category": "ASSAULT",
                    "updated_at": self.stempel[oid],
                },
                "geometry": {"x": -83.05, "y": 42.35},
            }


BESTAND = {
    1: "2026-09-01T10:00:00+00:00",
    2: "2026-09-10T10:00:00+00:00",
    3: "2026-09-17T10:00:00+00:00",
    4: None,                            # die Zeile ohne Stempel
}


def manifest_von(pfad: Path) -> dict:
    return json.loads(pfad.read_text(encoding="utf-8"))


def ziel(tmp_path: Path) -> Path:
    """Genau das Verzeichnis, in dem ``previous_watermark`` spaeter sucht."""
    return tmp_path / "bronze/city=detroit/full/year=2024"


# --------------------------------------------------------------------------
# Die Abfrage
# --------------------------------------------------------------------------


def test_ohne_wasserzeichen_ist_es_der_ganze_jahrgang():
    """Der erste Lauf hat nichts, hinter das er zurueckgreifen koennte."""
    assert build_delta_where(2024, None) == build_year_where(2024)
    assert "updated_at" not in build_delta_where(2024, None)


def test_mit_wasserzeichen_stehen_beide_bedingungen_darin():
    ab = datetime(2026, 9, 3, 10, 33, 22, tzinfo=timezone.utc)
    where = build_delta_where(2024, ab)
    assert where.startswith(build_year_where(2024) + " AND ")
    assert "updated_at >= TIMESTAMP '2026-09-03 10:33:22'" in where
    assert "OR updated_at IS NULL" in where


def test_der_jahresfilter_bleibt_auf_der_tatzeit():
    """Sonst kaemen Faelle aus jedem Tatjahr - 2024 ist der Gegenstand."""
    where = build_delta_where(2024, datetime(2026, 9, 3, tzinfo=timezone.utc))
    assert "incident_occurred_at >= TIMESTAMP '2024-01-01 05:00:00'" in where
    assert "incident_occurred_at < TIMESTAMP '2025-01-01 05:00:00'" in where


def test_ein_wasserzeichen_ohne_zeitzone_wird_abgelehnt():
    """Eine Stunde Unterschied sind hier ein paar hundert verpasste Zeilen."""
    with pytest.raises(ValueError, match="Zeitzone"):
        build_delta_where(2024, datetime(2026, 9, 3, 10, 0, 0))


def test_eine_andere_zeitzone_wird_nach_utc_gerechnet():
    ab = datetime(2026, 9, 3, 6, 33, 22,
                  tzinfo=timezone(timedelta(hours=-4)))     # Detroit im Sommer
    assert "TIMESTAMP '2026-09-03 10:33:22'" in delta_bedingung(ab)


# --------------------------------------------------------------------------
# Das Wasserzeichen
# --------------------------------------------------------------------------


def test_ohne_wasserzeichen_gibt_es_keinen_startpunkt():
    assert delta_start(None) is None


def test_der_rueckgriff_sind_vierzehn_tage():
    ab = delta_start("2026-09-17T10:33:22.317+00:00")
    assert ab == datetime(2026, 9, 3, 10, 33, 22, 317000, tzinfo=timezone.utc)
    assert (datetime(2026, 9, 17, 10, 33, 22, 317000, tzinfo=timezone.utc) - ab
            == timedelta(days=LOOKBACK_DAYS))


def test_ein_wasserzeichen_ohne_zone_gilt_als_utc():
    assert delta_start("2026-09-17T10:33:22").tzinfo is timezone.utc


def test_ein_unlesbares_wasserzeichen_bricht_ab():
    """Lieber kein Lauf als einer, der still den ganzen Jahrgang zieht."""
    with pytest.raises(DataQualityError, match="Unlesbares Wasserzeichen"):
        delta_start("vorgestern")


def lege_manifest(data_root: Path, run: str, **felder) -> None:
    verzeichnis = data_root / "bronze/city=detroit/full/year=2024" / f"run_{run}"
    verzeichnis.mkdir(parents=True, exist_ok=True)
    manifest = {"status": "SUCCESS", "year": 2024, "max_records": None,
                "pipeline_run_id": run}
    manifest.update(felder)
    (verzeichnis / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_das_wasserzeichen_ist_das_hoechste_aller_eigenen_laeufe(tmp_path):
    lege_manifest(tmp_path, "a", watermark={"maximum_seen": "2026-09-10T00:00:00+00:00"})
    lege_manifest(tmp_path, "b", watermark={"maximum_seen": "2026-09-17T10:33:22+00:00"})
    lege_manifest(tmp_path, "c", watermark={"maximum_seen": "2026-09-14T00:00:00+00:00"})
    assert previous_watermark(tmp_path, 2024) == "2026-09-17T10:33:22+00:00"


def test_ohne_vorlauf_gibt_es_kein_wasserzeichen(tmp_path):
    assert previous_watermark(tmp_path, 2024) is None


def test_laeufe_anderer_jahre_zaehlen_nicht(tmp_path):
    lege_manifest(tmp_path, "a", year=2023,
                  watermark={"maximum_seen": "2026-09-17T10:33:22+00:00"})
    assert previous_watermark(tmp_path, 2024) is None


def test_ein_gekuerzter_lauf_zaehlt_nicht(tmp_path):
    """``--max-records`` ist ein Probelauf; sein Maximum ist kein Bestand."""
    lege_manifest(tmp_path, "a", max_records=50,
                  watermark={"maximum_seen": "2026-09-17T10:33:22+00:00"})
    assert previous_watermark(tmp_path, 2024) is None


def test_ein_lauf_ohne_wasserzeichen_zaehlt_nicht(tmp_path):
    """Die Laeufe vor dem 18.9.2026 tragen den Block nicht."""
    lege_manifest(tmp_path, "alt")
    assert previous_watermark(tmp_path, 2024) is None


# --------------------------------------------------------------------------
# Der Lauf
# --------------------------------------------------------------------------


def test_der_erste_lauf_ist_ein_vollschnappschuss(tmp_path):
    quelle = FakeQuelle(BESTAND)
    _, manifest_pfad = extract_delta(2024, ziel(tmp_path), data_root=tmp_path,
                                     client=quelle, pause_seconds=0)
    manifest = manifest_von(manifest_pfad)

    assert manifest["extraction_mode"] == "FULL"
    assert manifest["date_field"] == "incident_occurred_at"
    assert manifest["downloaded_count"] == len(BESTAND)
    assert manifest["watermark"]["previous_maximum"] is None
    assert manifest["watermark"]["delta_from_utc"] is None
    assert manifest["watermark"]["maximum_seen"] == "2026-09-17T10:00:00.000+00:00"


def test_der_zweite_lauf_holt_nur_das_geaenderte(tmp_path):
    quelle = FakeQuelle(BESTAND)
    extract_delta(2024, ziel(tmp_path), data_root=tmp_path,
                  client=quelle, pause_seconds=0)
    _, manifest_pfad = extract_delta(2024, ziel(tmp_path), data_root=tmp_path,
                                     client=quelle, pause_seconds=0)
    manifest = manifest_von(manifest_pfad)

    assert manifest["extraction_mode"] == "DELTA"
    assert manifest["date_field"] == "updated_at"
    assert manifest["selection_basis"] == "SOURCE_LAST_UPDATED_TIME_WITHIN_INCIDENT_YEAR"
    # Wasserzeichen 17.9. minus 14 Tage = 3.9.: Zeile 1 (1.9.) faellt weg,
    # Zeile 2 und 3 liegen darin, Zeile 4 hat keinen Stempel und kommt immer.
    assert manifest["watermark"]["delta_from_utc"] == "2026-09-03T10:00:00+00:00"
    assert manifest["downloaded_count"] == 3


def test_die_zeile_ohne_stempel_faellt_nie_heraus(tmp_path):
    """Vier von 88'686 am 18.9.2026 - sie haetten sonst nie wieder eine Chance."""
    quelle = FakeQuelle(BESTAND)
    extract_delta(2024, ziel(tmp_path), data_root=tmp_path,
                  client=quelle, pause_seconds=0)
    # Ein Wasserzeichen weit in der Zukunft: nichts liegt mehr im Fenster.
    _, manifest_pfad = extract_delta(2024, ziel(tmp_path), data_root=tmp_path,
                                     client=quelle, pause_seconds=0,
                                     watermark="2027-01-01T00:00:00+00:00")
    assert manifest_von(manifest_pfad)["downloaded_count"] == 1


def test_das_wasserzeichen_rueckt_nie_zurueck(tmp_path):
    """Ein Lauf, der nichts Neueres sieht, laesst es stehen."""
    quelle = FakeQuelle(BESTAND)
    extract_delta(2024, ziel(tmp_path), data_root=tmp_path,
                  client=quelle, pause_seconds=0)
    _, manifest_pfad = extract_delta(2024, ziel(tmp_path), data_root=tmp_path,
                                     client=quelle, pause_seconds=0)
    watermark = manifest_von(manifest_pfad)["watermark"]
    assert watermark["maximum_seen"] == watermark["previous_maximum"]
    assert watermark["maximum_seen"] == "2026-09-17T10:00:00.000+00:00"


def test_ein_neuer_stempel_schiebt_das_wasserzeichen_vor(tmp_path):
    quelle = FakeQuelle(BESTAND)
    extract_delta(2024, ziel(tmp_path), data_root=tmp_path,
                  client=quelle, pause_seconds=0)
    quelle.stempel[5] = ms("2026-09-20T08:00:00+00:00")
    _, manifest_pfad = extract_delta(2024, ziel(tmp_path), data_root=tmp_path,
                                     client=quelle, pause_seconds=0)
    watermark = manifest_von(manifest_pfad)["watermark"]
    assert watermark["maximum_seen"] == "2026-09-20T08:00:00.000+00:00"
    assert watermark["previous_maximum"] == "2026-09-17T10:00:00.000+00:00"


def test_der_zweite_lauf_liest_sein_wasserzeichen_selbst(tmp_path):
    """Ohne ``watermark=`` muss er es im eigenen Bronze finden."""
    quelle = FakeQuelle(BESTAND)
    _, erster = extract_delta(2024, tmp_path / "bronze/city=detroit/full/year=2024",
                              data_root=tmp_path, client=quelle, pause_seconds=0)
    assert previous_watermark(tmp_path, 2024) == \
        manifest_von(erster)["watermark"]["maximum_seen"]


# --------------------------------------------------------------------------
# Die Zeitachsen duerfen sich nicht vertauschen
# --------------------------------------------------------------------------


def test_full_bleibt_auf_der_tatzeit(tmp_path):
    """``--mode full`` kennt kein Wasserzeichen und zieht immer alles."""
    quelle = FakeQuelle(BESTAND)
    _, manifest_pfad = extract_year(2024, tmp_path / "bronze", client=quelle,
                                    pause_seconds=0)
    manifest = manifest_von(manifest_pfad)
    assert manifest["extraction_mode"] == "FULL"
    assert "updated_at >=" not in manifest["where"]
    assert manifest["downloaded_count"] == len(BESTAND)
    assert manifest["watermark"]["delta_from_utc"] is None


def test_eine_delta_abfrage_ohne_startzeitpunkt_wird_abgewiesen(tmp_path):
    """Der Waechter in _extract_where: Modus und Startzeitpunkt gehoeren zusammen."""
    from detroit_pipeline import extract_detroit as ed

    with pytest.raises(DataQualityError, match="nur zu DELTA"):
        ed._extract_where(
            build_year_where(2024), tmp_path / "bronze", file_stem="x",
            extraction_mode="DELTA", date_field="updated_at",
            window_start=date(2024, 1, 1), window_end_exclusive=date(2025, 1, 1),
            year=2024, client=FakeQuelle(BESTAND), pause_seconds=0,
        )


def test_ein_startzeitpunkt_ohne_delta_wird_abgewiesen(tmp_path):
    from detroit_pipeline import extract_detroit as ed

    with pytest.raises(DataQualityError, match="nur zu DELTA"):
        ed._extract_where(
            build_year_where(2024), tmp_path / "bronze", file_stem="x",
            extraction_mode="FULL", date_field="incident_occurred_at",
            window_start=date(2024, 1, 1), window_end_exclusive=date(2025, 1, 1),
            year=2024, client=FakeQuelle(BESTAND), pause_seconds=0,
            delta_ab=datetime(2026, 9, 3, tzinfo=timezone.utc),
        )


def test_eine_fremde_where_klausel_wird_abgewiesen(tmp_path):
    """Die Abfrage muss genau die zum Fenster und Wasserzeichen passende sein."""
    from detroit_pipeline import extract_detroit as ed

    ab = datetime(2026, 9, 3, tzinfo=timezone.utc)
    with pytest.raises(DataQualityError, match="passt nicht zum Detroit-Zeitfenster"):
        ed._extract_where(
            build_delta_where(2024, ab - timedelta(days=1)),
            tmp_path / "bronze", file_stem="x",
            extraction_mode="DELTA", date_field="updated_at",
            window_start=date(2024, 1, 1), window_end_exclusive=date(2025, 1, 1),
            year=2024, client=FakeQuelle(BESTAND), pause_seconds=0, delta_ab=ab,
        )


def test_delta_muss_updated_at_verwenden(tmp_path):
    from detroit_pipeline import extract_detroit as ed

    ab = datetime(2026, 9, 3, tzinfo=timezone.utc)
    with pytest.raises(DataQualityError, match="DELTA muss updated_at verwenden"):
        ed._extract_where(
            build_delta_where(2024, ab), tmp_path / "bronze", file_stem="x",
            extraction_mode="DELTA", date_field="incident_occurred_at",
            window_start=date(2024, 1, 1), window_end_exclusive=date(2025, 1, 1),
            year=2024, client=FakeQuelle(BESTAND), pause_seconds=0, delta_ab=ab,
        )
