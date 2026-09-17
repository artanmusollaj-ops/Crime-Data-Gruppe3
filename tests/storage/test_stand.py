"""Der veraltete lokale Stand - die scharfe Kante von "lokal zuerst".

Wer eine Silver- oder Gold-Tabelle von letzter Woche herumliegen hat, liest
sie: leise, ohne Hinweis, mit der Zahl von letzter Woche. Und veroeffentlicht
er sie, verdraengt sein alter Stand den neuen fuer alle. Beides faellt
niemandem auf - genau deshalb steht es hier als Test.

Zwei Regeln, und der Unterschied zwischen ihnen ist Absicht:

* **Lesen** warnt und liest trotzdem lokal. "lokal zuerst" bleibt die Regel;
  wer offline arbeitet, soll weiterarbeiten koennen.
* **Publizieren** sagt ab. Ein Rueckschritt im gemeinsamen Bestand ist
  nichts, was man aus Versehen tun darf.

Laeufe unter ``bronze/`` und ``raw/`` sind davon nicht betroffen: Sie sind
unveraenderlich und ergaenzen einander, statt sich zu verdraengen.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest

from storage import (
    Config,
    FakeS3Client,
    PublishError,
    Standvergleich,
    Storage,
    eingaben,
    zeitpunkt,
)


ALT = "2026-09-08T10:00:00+00:00"
NEU = "2026-09-13T14:06:41.712320+00:00"
TABELLE = "silver/dataset=crime_offense"


def ablage(tmp_path: Path, backend: str = "hybrid") -> tuple[Storage, FakeS3Client]:
    fake = FakeS3Client()
    return Storage(Config(backend=backend, local_root=tmp_path / "data",
                          s3_access_key="k", s3_secret_key="s"), fake), fake


def manifest(gebaut: str | None = None, chicago: tuple[str, ...] = ()) -> dict:
    inhalt: dict = {"status": "complete", "row_count": 42}
    if gebaut:
        inhalt["built_at_utc"] = gebaut
    if chicago:
        inhalt["derived_from"] = {"chicago_bronze_runs": list(chicago)}
    return inhalt


def lege_an(storage: Storage, fake: FakeS3Client, *, hier: dict | None,
            dort: dict | None, tabelle: str = TABELLE) -> None:
    if hier is not None:
        ordner = storage.local_path(tabelle)
        ordner.mkdir(parents=True, exist_ok=True)
        (ordner / "part-0001.parquet").write_bytes(b"HIER")
        (ordner / "manifest.json").write_text(json.dumps(hier), encoding="utf-8")
    if dort is not None:
        fake.put(f"{tabelle}/part-0001.parquet", b"DORT")
        fake.put(f"{tabelle}/manifest.json", json.dumps(dort).encode())


# --------------------------------------------------------------------------
# Die beiden Vergleichsgroessen
# --------------------------------------------------------------------------


@pytest.mark.parametrize("roh, erwartet", [
    ("2026-09-13T14:06:45.948494Z", datetime(2026, 9, 13, 14, 6, 45, 948494, tzinfo=timezone.utc)),
    ("2026-09-13T14:06:41+00:00", datetime(2026, 9, 13, 14, 6, 41, tzinfo=timezone.utc)),
    ("2026-09-13T14:06:41", datetime(2026, 9, 13, 14, 6, 41, tzinfo=timezone.utc)),
])
def test_beide_schreibweisen_von_built_at_utc(roh, erwartet):
    """Silver schreibt +00:00, Gold ein Z - beides ist derselbe Zeitpunkt."""
    assert zeitpunkt({"built_at_utc": roh}) == erwartet


@pytest.mark.parametrize("manifest_, erwartet", [
    ({}, frozenset()),
    ({"built_at_utc": "kaputt"}, frozenset()),
    ({"derived_from": {"chicago_bronze_runs": ["a", "b"],
                       "detroit_bronze_runs": ["c"],
                       "silver_tract": "data/..."}}, frozenset({"a", "b", "c"})),
    ({"derived_from": [{"layer": "bronze", "run_id": "x"},
                       {"layer": "bronze", "run_id": "y"}]}, frozenset({"x", "y"})),
    ({"derived_from": [{"layer": "silver", "table": "crime_offense",
                        "path": "data/..."}]}, frozenset()),
])
def test_die_drei_formen_von_derived_from(manifest_, erwartet):
    """crime_offense fuehrt Listen je Stadt, die uebrigen Silver-Tabellen
    Eintraege mit run_id - und Gold nennt Silver-Tabellen statt Laeufe.
    Fuer Gold bleibt die Menge leer, dort zaehlt allein der Zeitpunkt."""
    assert eingaben(manifest_) == erwartet


def test_zeitpunkt_ohne_angabe_ist_none():
    assert zeitpunkt({}) is None and zeitpunkt({"built_at_utc": "vorgestern"}) is None


# --------------------------------------------------------------------------
# Lesen: warnen, aber lesen
# --------------------------------------------------------------------------


def test_der_aeltere_lokale_stand_wird_gemeldet_und_trotzdem_gelesen(tmp_path, caplog):
    storage, fake = ablage(tmp_path)
    lege_an(storage, fake, hier=manifest(ALT), dort=manifest(NEU))
    with caplog.at_level(logging.WARNING, logger="storage"):
        pfad = storage.resolve_read_path(TABELLE, "part-0001.parquet")
    assert not pfad.startswith("s3://"), "gelesen wird weiter lokal - das ist die Regel"
    assert "Lokaler Stand ist aelter" in caplog.text
    assert "08.09.2026" in caplog.text and "13.09.2026" in caplog.text
    assert "run_all --ohne-ingestion" in caplog.text


def test_weniger_bronze_laeufe_sind_auch_ein_aelterer_stand(tmp_path, caplog):
    """Der Fall, den die Uhrzeit nicht faengt: heute gebaut, aber ohne den
    Lauf, den ein anderer laengst geladen hat."""
    storage, fake = ablage(tmp_path)
    lege_an(storage, fake,
            hier=manifest(NEU, chicago=("run_A",)),
            dort=manifest(ALT, chicago=("run_A", "run_B", "run_C")))
    with caplog.at_level(logging.WARNING, logger="storage"):
        storage.resolve_read_path(TABELLE, "part-0001.parquet")
    assert "2 Bronze-Lauf/Laeufe, die hier fehlen (run_B, run_C)" in caplog.text


def test_der_neuere_lokale_stand_schweigt(tmp_path, caplog):
    storage, fake = ablage(tmp_path)
    lege_an(storage, fake, hier=manifest(NEU), dort=manifest(ALT))
    with caplog.at_level(logging.WARNING, logger="storage"):
        storage.resolve_read_path(TABELLE, "part-0001.parquet")
    assert caplog.text == ""


def test_gewarnt_wird_einmal_je_tabelle(tmp_path, caplog):
    """Gold liest crime_offense fuenfmal - fuenf gleiche Warnungen waeren Laerm."""
    storage, fake = ablage(tmp_path)
    lege_an(storage, fake, hier=manifest(ALT), dort=manifest(NEU))
    with caplog.at_level(logging.WARNING, logger="storage"):
        for _ in range(5):
            storage.resolve_read_path(TABELLE, "part-0001.parquet")
    assert caplog.text.count("Lokaler Stand ist aelter") == 1


def test_ein_ausfall_von_seaweedfs_haelt_das_lesen_nicht_auf(tmp_path, caplog):
    """Lokal lesen muss gehen, wenn das Netz weg ist - sonst waere der
    Hybridmodus schlechter als der lokale."""
    from storage import StorageError

    storage, fake = ablage(tmp_path)
    lege_an(storage, fake, hier=manifest(ALT), dort=manifest(NEU))

    class Tot(FakeS3Client):
        def head(self, key):
            raise StorageError("SeaweedFS nicht erreichbar: https://…")

    storage._client = Tot()
    with caplog.at_level(logging.WARNING, logger="storage"):
        pfad = storage.resolve_read_path(TABELLE, "part-0001.parquet")
    assert not pfad.startswith("s3://") and "Lokaler Stand" not in caplog.text


def test_laeufe_werden_nie_verglichen(tmp_path, caplog):
    """bronze/ und raw/ sind unveraenderlich: Zwei Laeufe verdraengen einander
    nicht, sie ergaenzen sich."""
    storage, fake = ablage(tmp_path)
    rel = "bronze/city=chicago/ingest_date=2026-09-05/run_a"
    lege_an(storage, fake, hier=manifest(ALT), dort=manifest(NEU), tabelle=rel)
    with caplog.at_level(logging.WARNING, logger="storage"):
        storage.resolve_read_path(rel, "part-0001.parquet")
    assert caplog.text == ""


def test_im_local_modus_wird_nichts_verglichen(tmp_path, caplog):
    storage, _ = ablage(tmp_path, "local")
    ordner = storage.local_path(TABELLE)
    ordner.mkdir(parents=True)
    (ordner / "manifest.json").write_text(json.dumps(manifest(ALT)))
    (ordner / "part-0001.parquet").write_bytes(b"x")
    with caplog.at_level(logging.WARNING, logger="storage"):
        storage.resolve_read_path(TABELLE, "part-0001.parquet")
    assert caplog.text == ""


# --------------------------------------------------------------------------
# Publizieren: absagen
# --------------------------------------------------------------------------


def test_ein_aelterer_stand_wird_nicht_publiziert(tmp_path):
    storage, fake = ablage(tmp_path)
    lege_an(storage, fake, hier=manifest(ALT), dort=manifest(NEU))
    fake.uploads.clear()
    with pytest.raises(PublishError, match="Rueckschritt"):
        storage.publish_table(TABELLE)
    assert fake.uploads == []
    assert fake.objekte[f"{TABELLE}/part-0001.parquet"] == b"DORT", "der gute Stand steht noch"


def test_ein_stand_auf_weniger_laeufen_wird_nicht_publiziert(tmp_path):
    storage, fake = ablage(tmp_path)
    lege_an(storage, fake,
            hier=manifest(NEU, chicago=("run_A",)),
            dort=manifest(ALT, chicago=("run_A", "run_B")))
    fake.uploads.clear()
    with pytest.raises(PublishError, match="run_B"):
        storage.publish_table(TABELLE)
    assert fake.uploads == []


def test_der_neuere_stand_geht_durch(tmp_path):
    storage, fake = ablage(tmp_path)
    lege_an(storage, fake, hier=manifest(NEU, chicago=("run_A", "run_B")),
            dort=manifest(ALT, chicago=("run_A",)))
    fake.uploads.clear()
    assert storage.publish_table(TABELLE)
    assert fake.objekte[f"{TABELLE}/part-0001.parquet"] == b"HIER"


def test_erzwingen_dreht_bewusst_zurueck(tmp_path):
    storage, fake = ablage(tmp_path)
    lege_an(storage, fake, hier=manifest(ALT), dort=manifest(NEU))
    assert storage.publish_table(TABELLE, erzwingen=True)
    assert fake.objekte[f"{TABELLE}/part-0001.parquet"] == b"HIER"


def test_die_erste_veroeffentlichung_hat_nichts_zu_vergleichen(tmp_path):
    storage, fake = ablage(tmp_path)
    lege_an(storage, fake, hier=manifest(ALT), dort=None)
    assert storage.publish_table(TABELLE)


def test_ohne_zeitangaben_wird_nicht_blockiert(tmp_path):
    """Ein Manifest aus der Zeit vor built_at_utc darf niemanden aussperren."""
    storage, fake = ablage(tmp_path)
    lege_an(storage, fake, hier=manifest(), dort=manifest())
    assert storage.publish_table(TABELLE)


def test_der_vergleich_liest_beim_publizieren_frisch(tmp_path):
    """Zwischen Lesen und Publizieren kann jemand anders publiziert haben."""
    storage, fake = ablage(tmp_path)
    lege_an(storage, fake, hier=manifest(ALT), dort=None)
    storage.resolve_read_path(TABELLE, "part-0001.parquet")   # fuellt den Cache: nichts oben
    fake.put(f"{TABELLE}/manifest.json", json.dumps(manifest(NEU)).encode())
    with pytest.raises(PublishError, match="Rueckschritt"):
        storage.publish_table(TABELLE)


def test_ein_lauf_bleibt_von_der_regel_unberuehrt(tmp_path):
    """publish_run kennt nur seine eigene Regel: identisch ja, anders nein."""
    storage, fake = ablage(tmp_path)
    rel = "bronze/city=chicago/ingest_date=2026-09-05/run_a"
    lege_an(storage, fake, hier=manifest(ALT), dort=None, tabelle=rel)
    assert storage.publish_run(rel)


# --------------------------------------------------------------------------
# Und wie es in einer Pipeline ankommt
# --------------------------------------------------------------------------


def test_die_silver_pipeline_baut_lokal_fertig_und_meldet_die_absage(tmp_path, monkeypatch, caplog):
    """Der lokale Bau ist echte Arbeit und bleibt stehen; nur das Hochladen
    unterbleibt - mit einem Satz, nicht mit einem Traceback."""
    import build_tract as bt
    import storage as st
    from tests.silver_pipeline.test_build_tract import (
        VINTAGE,
        acs_table,
        bronze_fuer_illinois,
        tiger_table,
    )

    storage, fake = ablage(tmp_path)
    st.set_storage(storage)
    data_root = storage.local_root
    bronze_fuer_illinois(data_root, tiger=tiger_table(), acs=acs_table())
    ziel = f"silver/dataset=tract/vintage={VINTAGE}"
    # Der Stand oben ruht auf einem Bronze-Lauf, den es hier nicht gibt. Das
    # ist der zeitunabhaengige Teil der Regel - der Bau stempelt ``jetzt``.
    fake.put(f"{ziel}/manifest.json", json.dumps({
        "built_at_utc": "2027-01-01T00:00:00+00:00",
        "derived_from": [{"layer": "bronze", "dataset": "tiger_tract",
                          "run_id": "run_20261231T235959000000Z"}],
    }).encode())
    fake.put(f"{ziel}/part-0001.parquet", b"NEUERER STAND")
    fake.uploads.clear()

    monkeypatch.setattr(bt, "arguments", lambda: bt.argparse.Namespace(
        data_root=None, vintage=VINTAGE, state=["17"], verbose=False))
    with caplog.at_level(logging.ERROR, logger="build_tract"):
        assert bt.main() == 1
    assert "Rueckschritt" in caplog.text
    assert (data_root / ziel / "part-0001.parquet").exists(), "lokal ist die Tabelle fertig"
    assert fake.objekte[f"{ziel}/part-0001.parquet"] == b"NEUERER STAND"
    assert fake.uploads == []


def test_python_m_storage_zeigt_den_alten_stand(tmp_path, capsys, monkeypatch):
    import storage as st
    from storage import __main__ as befehl

    storage, fake = ablage(tmp_path)
    st.set_storage(storage)
    lege_an(storage, fake, hier=manifest(ALT), dort=manifest(NEU))
    lege_an(storage, fake, hier=manifest(NEU), dort=manifest(ALT),
            tabelle="gold/dataset=fact_offense")
    monkeypatch.setattr(befehl.socket, "getaddrinfo",
                        lambda *a, **kw: [(0, 0, 0, "", ("10.0.0.1", 0))])
    assert befehl.main([]) == 0
    out = capsys.readouterr().out
    assert "silver/dataset=crime_offense" in out and "ALT - " in out
    assert "gold/dataset=fact_offense" in out and "aktuell" in out
    assert "1 lokale Tabelle(n) sind aelter" in out


def test_standvergleich_ohne_unterschied_ist_nicht_veraltet():
    gleich = Standvergleich("silver/x", zeitpunkt({"built_at_utc": NEU}),
                            zeitpunkt({"built_at_utc": NEU}), frozenset())
    assert not gleich.veraltet and not gleich.aelter


# --------------------------------------------------------------------------
# Ein abgeloester Vollschnappschuss ist kein Rueckschritt
# --------------------------------------------------------------------------
# Am 17.9.2026 um 21:30 brach ein Gesamtlauf ab:
#
#   silver/dataset=weather_day: hier gebaut 19:30 UTC, auf SeaweedFS 16:05 UTC;
#   dort stecken 1 Bronze-Lauf/Laeufe, die hier fehlen (run_20260908...)
#
# Der hiesige Stand war neuer und ruhte auf einem neueren NOAA-Lauf. NOAA
# liefert Vollschnappschuesse, und ``build_weather_day`` nimmt nur den
# juengsten - der Lauf vom 8.9. war nicht verloren, sondern abgeloest, und lag
# die ganze Zeit unter ``data/bronze``.


def bronze_lauf(storage: Storage, rel_dir: str, run_id: str, *,
                schluessel: str = "run_id") -> None:
    """Ein fertiger Bronze-Lauf in der lokalen Wurzel."""
    ordner = storage.local_path(rel_dir)
    ordner.mkdir(parents=True, exist_ok=True)
    (ordner / "part-0001.parquet").write_bytes(b"PAR1")
    (ordner / "manifest.json").write_text(
        json.dumps({"status": "complete", schluessel: run_id}), encoding="utf-8")


def wetter(gebaut: str, runs: tuple[str, ...]) -> dict:
    """Ein weather_day-Manifest - Liste von Eintraegen mit ``run_id``."""
    return {"status": "complete", "row_count": 55_000, "built_at_utc": gebaut,
            "derived_from": [{"layer": "bronze", "dataset": "noaa_ghcnd",
                              "run_id": r} for r in runs]}


WETTER = "silver/dataset=weather_day"


def test_ein_abgeloester_vollschnappschuss_ist_kein_rueckschritt(tmp_path):
    """Der Fall vom 17.9.2026, als Test.

    Der alte Lauf liegt noch in Bronze - er fehlt also nicht, er wurde
    abgeloest. Ohne diese Unterscheidung laesst sich eine Quelle, die
    Vollschnappschuesse liefert, nach dem ersten Neuladen nie mehr
    publizieren.
    """
    storage, fake = ablage(tmp_path)
    bronze_lauf(storage, "bronze/dataset=noaa_ghcnd/station=A/run_alt", "run_alt")
    bronze_lauf(storage, "bronze/dataset=noaa_ghcnd/station=A/run_neu", "run_neu")
    lege_an(storage, fake, tabelle=WETTER,
            hier=wetter(NEU, ("run_neu",)),
            dort=wetter(ALT, ("run_alt",)))

    befund = storage.vergleiche_stand(WETTER, frisch=True)
    assert befund is not None and not befund.veraltet, befund.satz()
    assert storage.publish_table(WETTER), "der neuere Stand muss hochgehen"


def test_ein_wirklich_fehlender_lauf_blockiert_weiterhin(tmp_path):
    """Die Absicht der Regel bleibt: derselbe Aufbau, nur ohne den alten Lauf."""
    storage, fake = ablage(tmp_path)
    bronze_lauf(storage, "bronze/dataset=noaa_ghcnd/station=A/run_neu", "run_neu")
    lege_an(storage, fake, tabelle=WETTER,
            hier=wetter(NEU, ("run_neu",)),
            dort=wetter(ALT, ("run_alt",)))

    fake.uploads.clear()
    with pytest.raises(PublishError, match="run_alt"):
        storage.publish_table(WETTER)
    assert fake.uploads == []


def test_ein_lauf_der_nur_auf_seaweedfs_liegt_zaehlt_als_erreichbar(tmp_path):
    """Im Hybridmodus liest ein Bau ihn ohnehin - er fehlt nicht."""
    storage, fake = ablage(tmp_path)
    bronze_lauf(storage, "bronze/dataset=noaa_ghcnd/station=A/run_neu", "run_neu")
    fake.put("bronze/dataset=noaa_ghcnd/station=A/run_alt/manifest.json",
             json.dumps({"status": "complete", "run_id": "run_alt"}).encode())
    lege_an(storage, fake, tabelle=WETTER,
            hier=wetter(NEU, ("run_neu",)),
            dort=wetter(ALT, ("run_alt",)))
    assert not storage.vergleiche_stand(WETTER, frisch=True).veraltet


def test_detroits_eigene_kennung_wird_erkannt(tmp_path):
    """Detroit nennt sie ``pipeline_run_id`` - gelesen wird das Manifest."""
    storage, _ = ablage(tmp_path)
    bronze_lauf(storage, "bronze/city=detroit/full/run_x", "abc-123",
                schluessel="pipeline_run_id")
    assert "abc-123" in storage.verfuegbare_laeufe()


def test_ein_geholter_lauf_zaehlt_sofort(tmp_path):
    """Der Zwischenstand darf nach dem Holen nicht veralten."""
    storage, fake = ablage(tmp_path)
    assert storage.verfuegbare_laeufe() == frozenset()
    fake.put("bronze/city=chicago/ingest_date=2026-09-17/run_neu/part-0001.parquet", b"PAR1")
    fake.put("bronze/city=chicago/ingest_date=2026-09-17/run_neu/manifest.json",
             json.dumps({"status": "complete", "run_id": "run_neu"}).encode())
    storage.hole_lauf("bronze/city=chicago/ingest_date=2026-09-17/run_neu")
    assert "run_neu" in storage.verfuegbare_laeufe()
