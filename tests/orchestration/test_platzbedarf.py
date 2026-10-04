"""Die Messung und die vier Regeln - jede Zeile der I/O-Matrix von FR-40.

Kein Test hier braucht Netz, einen ``CENSUS_API_KEY`` oder SeaweedFS: S3 ist
``FakeS3Client``, ein dict. Gemessen wird in ``tmp_path``, nicht unter ``data/``
- die Zahlen des echten Bestands haelt ``tests/test_platzbedarf_dokumente.py``,
und der traegt den Marker ``referenzstand``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestration import platzbedarf as pb
from storage import Config, FakeS3Client, Storage


SCHICHTEN = ("raw", "bronze", "silver", "gold", "serving", "releases")

# Dieselben Zeilen wie in config/zeilen_je_jahrgang.csv, am 3.10.2026 an beiden
# APIs gemessen. Hier als Literal, damit ein Test nicht stillschweigend etwas
# anderes prueft als die Datei - test_die_datei_in_config_wird_gelesen haelt
# beides zusammen.
ZEILEN = {
    ("chicago", 2021): 210_004, ("detroit", 2021): 78_953,
    ("chicago", 2022): 240_498, ("detroit", 2022): 83_818,
    ("chicago", 2023): 263_850, ("detroit", 2023): 90_598,
    ("chicago", 2024): 259_642, ("detroit", 2024): 88_699,
    ("chicago", 2025): 238_105, ("detroit", 2025): 85_745,
    ("chicago", 2026): 170_838, ("detroit", 2026): 63_667,
}
JAHRE = tuple(range(2021, 2027))


@pytest.fixture
def zeilen() -> pb.Zeilen:
    return pb.Zeilen(dict(ZEILEN), "2026-10-03", {"chicago": "socrata",
                                                  "detroit": "arcgis"})


def ablage(tmp_path: Path, backend: str = "local") -> tuple[Storage, FakeS3Client]:
    fake = FakeS3Client()
    config = Config(backend=backend, local_root=tmp_path / "data",
                    s3_access_key="k", s3_secret_key="s")
    return Storage(config, fake), fake


def schreibe(storage: Storage, rel: str, bytes_: int) -> Path:
    pfad = storage.local_path(rel)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(b"x" * bytes_)
    return pfad


def lauf(storage: Storage, rel_dir: str, *, bytes_: int) -> None:
    """Ein fertiger Lauf: Nutzlast plus Manifest, wie die Pipelines ihn legen."""
    schreibe(storage, f"{rel_dir}/part-0001.parquet", bytes_)
    schreibe(storage, f"{rel_dir}/manifest.json", 0).write_text(
        json.dumps({"status": "complete", "run_id": rel_dir.rsplit("/", 1)[-1]}),
        encoding="utf-8")


def tabelle(storage: Storage, rel_dir: str, *, bytes_: int) -> None:
    schreibe(storage, f"{rel_dir}/part-0001.parquet", bytes_)


def release_(storage: Storage, kennung: str, *, bytes_: int) -> None:
    schreibe(storage, f"releases/release={kennung}/gold/dataset=fact_offense/"
                      f"part-0001.parquet", bytes_)
    schreibe(storage, f"releases/release={kennung}/release.json", 10)


# --------------------------------------------------------------------------
# Belegung je Schicht
# --------------------------------------------------------------------------


def test_belegung_nennt_bytes_und_dateizahl_je_schicht(tmp_path):
    storage, _ = ablage(tmp_path)
    lauf(storage, "raw/city=chicago/ingest_date=2026-09-05/run_a", bytes_=1000)
    tabelle(storage, "silver/dataset=crime_offense", bytes_=500)
    release_(storage, "2026-10-03T10-00-00Z", bytes_=300)

    je_name = {s.name: s for s in pb.belegung(storage)}
    assert tuple(s.name for s in pb.belegung(storage)) == SCHICHTEN, \
        "die Reihenfolge ist die der Strecke, nicht die des Dateisystems"
    assert je_name["raw"].bytes == 1000 + len(json.dumps(
        {"status": "complete", "run_id": "run_a"}))
    assert je_name["raw"].dateien == 2
    assert je_name["silver"] == pb.Schicht("silver", 500, 1)
    assert je_name["releases"].bytes == 310


def test_eine_fehlende_schicht_ist_null_und_kein_abbruch(tmp_path):
    """Ein frischer Klon hat data/serving noch nicht - das ist der Anfang."""
    storage, _ = ablage(tmp_path)
    tabelle(storage, "gold/dataset=fact_offense", bytes_=100)
    je_name = {s.name: s for s in pb.belegung(storage)}
    assert je_name["serving"] == pb.Schicht("serving", 0, 0)
    assert not (tmp_path / "data" / "serving").exists(), \
        "messen darf nichts anlegen"


def test_ein_part_verzeichnis_zaehlt_nicht_mit(tmp_path):
    """Ein abgebrochener Lauf ist nichts Veroeffentlichtes - wie ueberall sonst."""
    storage, _ = ablage(tmp_path)
    tabelle(storage, "silver/dataset=crime_offense", bytes_=100)
    schreibe(storage, "silver/.part-dataset=crime_offense/part-0001.parquet", 9999)
    je_name = {s.name: s for s in pb.belegung(storage)}
    assert je_name["silver"] == pb.Schicht("silver", 100, 1)


def test_die_summe_ist_die_summe(tmp_path):
    storage, _ = ablage(tmp_path)
    tabelle(storage, "silver/dataset=crime_offense", bytes_=100)
    tabelle(storage, "gold/dataset=fact_offense", bytes_=250)
    schichten = pb.belegung(storage)
    assert pb.summe(schichten) == pb.Schicht("data/", 350, 2)


# --------------------------------------------------------------------------
# Basis je Jahrgang: der groesste Lauf, nicht die Summe
# --------------------------------------------------------------------------


def test_basis_je_quelle_ist_der_groesste_lauf_nicht_die_summe(tmp_path):
    """Zwei Volladungen und drei Deltas - ein Jahrgang kostet die groesste.

    Die Summe zu nehmen waere die Falle aus AGENTS.md ("den Bestand aus Bronze
    lesen"), diesmal in der Basis einer Hochrechnung: 452'980 Zeilen fuer einen
    Jahrgang von 88'686 sahen plausibel aus.
    """
    storage, _ = ablage(tmp_path)
    for name, groesse in (("run_a", 1000), ("run_b", 1000),
                          ("run_c", 20), ("run_d", 30), ("run_e", 40)):
        lauf(storage, f"raw/city=chicago/ingest_date=2026-09-05/{name}",
             bytes_=groesse)
    chicago = [b for b in pb.basis_je_jahrgang(storage)
               if b.schicht == "raw" and b.quelle == "city=chicago"]
    assert len(chicago) == 1
    assert chicago[0].laeufe == 5
    assert chicago[0].bytes < 1200, (
        f"{chicago[0].bytes} Bytes - das ist die Summe aller fuenf Laeufe, "
        "nicht der groesste")


def test_ein_lauf_ueber_zwei_partitionen_ist_ein_lauf(tmp_path):
    """Ein ACS-Lauf liegt unter state=17 und state=26 - zusammen eine Einheit."""
    storage, _ = ablage(tmp_path)
    for staat in ("17", "26"):
        lauf(storage, f"raw/dataset=acs5_tract/vintage=2024/state={staat}/run_a",
             bytes_=500)
    lauf(storage, "raw/dataset=acs5_tract/vintage=2024/state=17/run_b", bytes_=100)
    acs = [b for b in pb.basis_je_jahrgang(storage)
           if b.quelle == "dataset=acs5_tract"][0]
    assert acs.laeufe == 2, "run_a ueber zwei Staaten ist ein Lauf"
    assert acs.bytes > 1000, "beide Partitionen von run_a gehoeren zur Basis"


def test_die_tabellenschichten_sind_schon_ein_stand(tmp_path):
    """Silver, Gold und Serving werden ersetzt, nicht angehaeuft."""
    storage, _ = ablage(tmp_path)
    tabelle(storage, "silver/dataset=crime_offense", bytes_=700)
    crime = [b for b in pb.basis_je_jahrgang(storage)
             if b.quelle == "dataset=crime_offense"][0]
    assert crime == pb.Basis("silver", "dataset=crime_offense", pb.TATEN, 700)


def test_zwei_vintages_in_raw_kosten_zusammen_einen_jahrgang(tmp_path):
    """``bytes`` muss in beiden Pfaden dasselbe bedeuten - ueber alle Vintages.

    Die erste Fassung von ``_laufschicht`` nahm den groessten Lauf *ueber alle*
    Vintages und zaehlte die Vintages trotzdem alle. ``_regel`` teilt fuer
    Census ``bytes / vintages`` und rechnet auf die noetigen Vintages hoch -
    bei zwei geladenen Vintages kam dadurch das Doppelte **eines** Vintages
    heraus statt des Vierfachen, und die gedruckte Regel nannte die halben
    Kosten je Vintage. ``_tabellenschicht`` war richtig, weil sein ``bytes``
    alle ``vintage=``-Partitionen spannt.
    """
    storage, _ = ablage(tmp_path)
    for vintage, groesse in ((2023, 1000), (2024, 3000)):
        lauf(storage, f"raw/dataset=tiger_tract/vintage={vintage}/state=17/run_a{vintage}",
             bytes_=groesse)
        # Ein zweiter, kleinerer Lauf desselben Vintages darf nichts addieren.
        lauf(storage, f"raw/dataset=tiger_tract/vintage={vintage}/state=17/run_b{vintage}",
             bytes_=groesse // 2)

    tiger = [b for b in pb.basis_je_jahrgang(storage)
             if b.quelle == "dataset=tiger_tract"][0]
    assert tiger.vintages == 2
    assert tiger.laeufe == 4
    # Der groesste Lauf **je Vintage**, summiert - nicht der groesste von allen.
    assert 3900 < tiger.bytes < 4200, (
        f"{tiger.bytes} Bytes: erwartet rund 4000 (1000 + 3000, je Vintage der "
        "groessere Lauf), nicht 3000 (der groesste ueberhaupt) und nicht 6000 "
        "(die Summe aller vier)")


def test_zwei_vintages_rechnen_auf_die_noetigen_vintages_hoch(tmp_path, zeilen):
    """Vier noetige Vintages aus zwei geladenen sind das Doppelte, nicht das Vierfache."""
    storage, _ = ablage(tmp_path)
    for vintage in (2023, 2024):
        lauf(storage, f"raw/dataset=tiger_tract/vintage={vintage}/state=17/run_a{vintage}",
             bytes_=2000)
    tiger = [h for h in pb.hochrechnung(pb.basis_je_jahrgang(storage), JAHRE, zeilen)
             if h.basis.quelle == "dataset=tiger_tract"][0]
    assert tiger.faktor == 2.0, "4 noetige / 2 geladene"
    je_vintage = tiger.basis.bytes / tiger.basis.vintages
    assert f"{je_vintage / 1e6:.1f} MB je Vintage" in tiger.wie
    assert abs(tiger.bytes - 4 * je_vintage) < 1.0


def test_der_vintage_eines_tabellenstands_wird_erkannt(tmp_path):
    storage, _ = ablage(tmp_path)
    for vintage in (2023, 2024):
        tabelle(storage, f"silver/dataset=tract/vintage={vintage}", bytes_=100)
    tract = [b for b in pb.basis_je_jahrgang(storage)
             if b.quelle == "dataset=tract"][0]
    assert tract.vintages == 2, "zwei Vintages liegen da, also kostet einer die Haelfte"


def test_ein_release_wird_nach_seinem_inhalt_aufgeschluesselt(tmp_path):
    """Ein Release ist kein Fass - sein Inhalt waechst mit."""
    storage, _ = ablage(tmp_path)
    release_(storage, "2026-10-01T10-00-00Z", bytes_=100)
    release_(storage, "2026-10-02T10-00-00Z", bytes_=300)
    releases = [b for b in pb.basis_je_jahrgang(storage) if b.schicht == "releases"]
    quellen = {b.quelle: b for b in releases}
    assert "gold/dataset=fact_offense" in quellen
    assert quellen["gold/dataset=fact_offense"].bytes == 300, "der groesste Stand"
    assert quellen["gold/dataset=fact_offense"].staende == pb.RELEASES_N
    assert quellen["release.json"].regel == pb.KONSTANT


def test_eine_unbekannte_tabelle_bricht_ab_und_wird_genannt(tmp_path):
    """Derselbe Umweg wie beim Feldkatalog: geraten wird nichts.

    Eine geratene Regel faellt niemandem auf - ein Abbruch, der die Tabelle
    nennt, schon.
    """
    storage, _ = ablage(tmp_path)
    tabelle(storage, "gold/dataset=dim_wetterlage", bytes_=100)
    with pytest.raises(SystemExit) as fehler:
        pb.basis_je_jahrgang(storage)
    assert "dataset=dim_wetterlage" in str(fehler.value)
    assert "REGEL_JE_QUELLE" in str(fehler.value)


# --------------------------------------------------------------------------
# Die Backends
# --------------------------------------------------------------------------


def test_im_s3_modus_kommen_die_groessen_aus_objekt_size(tmp_path):
    storage, fake = ablage(tmp_path, "s3")
    fake.put("silver/dataset=crime_offense/part-0001.parquet", b"y" * 4096)
    je_name = {s.name: s for s in pb.belegung(storage)}
    assert je_name["silver"] == pb.Schicht("silver", 4096, 1)


def test_im_hybridmodus_wird_dieselbe_datei_einmal_gezaehlt(tmp_path):
    """Lokal und oben ist **eine** Datei - lokal gewinnt, wie beim Lesen.

    Zweimal zu zaehlen waere die Sorte Fehler, die plausibel aussieht: Die
    Zahl ist zu gross, aber in der richtigen Groessenordnung.
    """
    storage, fake = ablage(tmp_path, "hybrid")
    rel = "silver/dataset=crime_offense/part-0001.parquet"
    schreibe(storage, rel, 1000)
    fake.put(rel, b"y" * 4096)
    je_name = {s.name: s for s in pb.belegung(storage)}
    assert je_name["silver"] == pb.Schicht("silver", 1000, 1), \
        "lokal gewinnt, und die Datei zaehlt einmal"


def test_im_hybridmodus_kommen_beide_seiten_zusammen(tmp_path):
    storage, fake = ablage(tmp_path, "hybrid")
    schreibe(storage, "silver/dataset=crime_offense/part-0001.parquet", 1000)
    fake.put("silver/dataset=tract/part-0001.parquet", b"y" * 500)
    je_name = {s.name: s for s in pb.belegung(storage)}
    assert je_name["silver"] == pb.Schicht("silver", 1500, 2)


def test_ein_fehler_von_s3_wird_durchgereicht(tmp_path):
    from storage import PublishError

    class Kaputt(FakeS3Client):
        def list(self, prefix):
            raise PublishError("SeaweedFS antwortet nicht")

    config = Config(backend="s3", local_root=tmp_path / "data",
                    s3_access_key="k", s3_secret_key="s")
    storage = Storage(config, Kaputt())
    with pytest.raises(PublishError):
        pb.belegung(storage)


def test_nur_lokal_sieht_s3_nicht_an(tmp_path, monkeypatch):
    """Was ``tools/build_platzbedarf.py`` misst, haengt nicht an der Umgebung."""
    monkeypatch.setenv("STORAGE_BACKEND", "hybrid")
    monkeypatch.setenv("S3_ACCESS_KEY", "k")
    monkeypatch.setenv("S3_SECRET_KEY", "s")
    lokal = pb.nur_lokal(tmp_path / "data")
    assert lokal.backend == "local"
    assert lokal.local_root == tmp_path / "data"


# --------------------------------------------------------------------------
# Die vier Regeln
# --------------------------------------------------------------------------


def test_taten_rechnen_mit_zeilen_und_bytes_je_zeile(tmp_path, zeilen):
    """Je Stadt mit ihren eigenen Bytes je Zeile, nicht mit einem Faktor."""
    storage, _ = ablage(tmp_path)
    lauf(storage, "bronze/city=chicago/ingest_date=2026-09-05/run_a",
         bytes_=259_642 * 10)
    basis = pb.basis_je_jahrgang(storage)
    chicago = [h for h in pb.hochrechnung(basis, JAHRE, zeilen)
               if h.basis.quelle == "city=chicago"][0]
    erwartet = sum(ZEILEN[("chicago", j)] for j in JAHRE) * 10
    assert abs(chicago.bytes - erwartet) <= erwartet * 0.001
    assert "Bytes je Zeile" in chicago.wie


def test_eine_abgeleitete_tabelle_rechnet_mit_beiden_staedten(tmp_path, zeilen):
    """crime_offense traegt beide Staedte - mit einer allein waere das Verhaeltnis falsch."""
    storage, _ = ablage(tmp_path)
    tabelle(storage, "silver/dataset=crime_offense", bytes_=1000)
    crime = [h for h in pb.hochrechnung(pb.basis_je_jahrgang(storage), JAHRE, zeilen)
             if h.basis.quelle == "dataset=crime_offense"][0]
    beide = sum(ZEILEN[(stadt, 2024)] for stadt in ("chicago", "detroit"))
    alle = sum(v for (_, jahr), v in ZEILEN.items() if jahr in JAHRE)
    assert abs(crime.faktor - alle / beide) < 1e-9


def test_census_rechnet_mit_vintages_und_nicht_mit_jahren(tmp_path, zeilen):
    """2021-2026 brauchen vier Vintages, nicht sechs: 2025 und 2026 borgen 2024."""
    storage, _ = ablage(tmp_path)
    lauf(storage, "raw/dataset=tiger_tract/vintage=2024/state=17/run_a", bytes_=1000)
    tiger = [h for h in pb.hochrechnung(pb.basis_je_jahrgang(storage), JAHRE, zeilen)
             if h.basis.quelle == "dataset=tiger_tract"][0]
    assert tiger.faktor == 4.0
    assert "4 Vintages" in tiger.wie and "2024" in tiger.wie


def test_noaa_bleibt_konstant(tmp_path, zeilen):
    """GHCN-Daily liefert immer die ganze Reihe - sechs Jahre kosten nichts dazu."""
    storage, _ = ablage(tmp_path)
    lauf(storage, "raw/dataset=noaa_ghcnd/station=USW00094846/run_a", bytes_=1000)
    noaa = [h for h in pb.hochrechnung(pb.basis_je_jahrgang(storage), JAHRE, zeilen)
            if h.basis.quelle == "dataset=noaa_ghcnd"][0]
    assert noaa.faktor == 1.0
    assert noaa.bytes == noaa.basis.bytes


def test_releases_nehmen_den_hochgerechneten_stand_mal_acht(tmp_path, zeilen):
    storage, _ = ablage(tmp_path)
    release_(storage, "2026-10-01T10-00-00Z", bytes_=1000)
    fakt = [h for h in pb.hochrechnung(pb.basis_je_jahrgang(storage), JAHRE, zeilen)
            if h.basis.quelle == "gold/dataset=fact_offense"][0]
    beide = sum(ZEILEN[(stadt, 2024)] for stadt in ("chicago", "detroit"))
    alle = sum(v for (_, jahr), v in ZEILEN.items() if jahr in JAHRE)
    assert abs(fakt.faktor - alle / beide * pb.RELEASES_N) < 1e-6
    assert f"x {pb.RELEASES_N} Staende" in fakt.wie


def test_ein_jahrgang_aendert_nichts_ausser_den_staenden(tmp_path, zeilen):
    """Die Rechnung fuer das Basisjahr ist die Vergleichsgroesse im Dokument."""
    storage, _ = ablage(tmp_path)
    lauf(storage, "bronze/city=detroit/full/year=2024/run_a", bytes_=1000)
    einer = pb.hochrechnung(pb.basis_je_jahrgang(storage), (pb.BASISJAHR,), zeilen)
    assert einer[0].faktor == 1.0
    assert einer[0].bytes == einer[0].basis.bytes


# --------------------------------------------------------------------------
# Was fehlt, wird genannt
# --------------------------------------------------------------------------


def test_ein_jahr_ohne_zeilenzahl_bricht_ab_und_nennt_es(tmp_path, zeilen):
    """Ein stillschweigend uebersprungenes Jahr waere eine zu kleine Zahl."""
    storage, _ = ablage(tmp_path)
    lauf(storage, "bronze/city=chicago/ingest_date=2026-09-05/run_a", bytes_=1000)
    basis = pb.basis_je_jahrgang(storage)
    with pytest.raises(SystemExit) as fehler:
        pb.hochrechnung(basis, (2019, 2020) + JAHRE, zeilen)
    satz = str(fehler.value)
    assert "2019" in satz and "2020" in satz
    assert pb.ZEILEN_DATEI in satz


def test_eine_dritte_stadt_ohne_zeilen_bricht_ab(tmp_path, zeilen, monkeypatch):
    """Die Staedte kommen aus STUDIENSTAEDTE - die Zeilen muessen mitkommen."""
    monkeypatch.setattr(pb, "STAEDTE", pb.STAEDTE + ("milwaukee",))
    storage, _ = ablage(tmp_path)
    lauf(storage, "bronze/city=chicago/ingest_date=2026-09-05/run_a", bytes_=1000)
    with pytest.raises(SystemExit) as fehler:
        pb.hochrechnung(pb.basis_je_jahrgang(storage), JAHRE, zeilen)
    assert "milwaukee" in str(fehler.value)


def test_ohne_jahre_wird_nichts_gerechnet(tmp_path, zeilen):
    with pytest.raises(SystemExit):
        pb.hochrechnung((), (), zeilen)


def test_ein_leeres_data_gibt_einen_hinweis_statt_einer_division(tmp_path, capsys,
                                                                zeilen):
    """Ein frischer Klon: alle Schichten 0, Hochrechnung uebersprungen."""
    storage, _ = ablage(tmp_path)
    schichten = pb.belegung(storage)
    assert pb.summe(schichten).bytes == 0
    assert pb.basis_je_jahrgang(storage) == ()
    pb.zeige(schichten, (), JAHRE, zeilen)
    ausgabe = capsys.readouterr().out
    assert "Keine Hochrechnung" in ausgabe
    assert "run_all" in ausgabe


# --------------------------------------------------------------------------
# Die gemessenen Zeilen und die CLI
# --------------------------------------------------------------------------


def test_die_datei_in_config_wird_gelesen():
    """Die Zeilen sind gemessene Fremddaten - mit Datum und Adresse."""
    gelesen = pb.zeilen_je_jahrgang(Path(__file__).resolve().parents[2] / "config")
    assert gelesen.je_stadt_und_jahr == ZEILEN, (
        "config/zeilen_je_jahrgang.csv und das Literal in diesem Test sind "
        "auseinandergelaufen")
    assert gelesen.gemessen_am == "2026-10-03"
    for stadt in ("chicago", "detroit"):
        assert gelesen.quellen[stadt].startswith("https://"), \
            f"{stadt} nennt keine Adresse"


def test_eine_fehlende_zeilendatei_wird_benannt(tmp_path):
    with pytest.raises(SystemExit) as fehler:
        pb.zeilen_je_jahrgang(tmp_path)
    assert pb.ZEILEN_DATEI in str(fehler.value)


@pytest.mark.parametrize("text, erwartet", [
    ("2024", (2024,)),
    ("2021-2026", tuple(range(2021, 2027))),
    (" 2021 - 2023 ", (2021, 2022, 2023)),
])
def test_jahre_aus_versteht_bereich_und_einzelnes_jahr(text, erwartet):
    assert pb.jahre_aus(text) == erwartet


@pytest.mark.parametrize("text", ["2026-2021", "2021-2022-2023", "zweitausend",
                                  "", "2021-"])
def test_ein_unsinniger_bereich_wird_abgelehnt(text):
    """Immer ``SystemExit`` mit Grund, nie ein nackter ``ValueError``.

    Ein Traceback aus ``int()`` fuer einen Tippfehler an der Befehlszeile waere
    zwei Sorten Fehler fuer dieselbe Sache - und die eine ohne Satz dazu.
    """
    with pytest.raises(SystemExit) as fehler:
        pb.jahre_aus(text)
    assert "--jahre" in str(fehler.value)


def test_die_cli_nennt_schichten_und_regeln(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(Path(__file__).resolve().parents[2])
    storage, _ = ablage(tmp_path)
    lauf(storage, "bronze/city=chicago/ingest_date=2026-09-05/run_a", bytes_=1000)
    lauf(storage, "raw/dataset=noaa_ghcnd/station=USW00094846/run_a", bytes_=50)
    assert pb.main(["--data-root", str(tmp_path / "data")]) == 0
    ausgabe = capsys.readouterr().out
    for pflicht in SCHICHTEN:
        assert pflicht in ausgabe
    assert "Dateien" in ausgabe
    for regel in (pb.TATEN, pb.KONSTANT):
        assert regel in ausgabe
    assert "Bytes je Zeile" in ausgabe


def test_die_cli_kann_json(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(Path(__file__).resolve().parents[2])
    storage, _ = ablage(tmp_path)
    lauf(storage, "bronze/city=chicago/ingest_date=2026-09-05/run_a", bytes_=1000)
    assert pb.main(["--data-root", str(tmp_path / "data"), "--json"]) == 0
    gelesen = json.loads(capsys.readouterr().out)
    assert gelesen["jahre"] == list(JAHRE)
    assert gelesen["basisjahr"] == pb.BASISJAHR
    assert {s["name"] for s in gelesen["belegung"]} == set(SCHICHTEN)
    assert gelesen["regeln"] == pb.ERKLAERUNG


def test_jede_regel_hat_eine_erklaerung():
    """Eine Regel ohne Satz daneben ist eine Zahl ohne Begruendung."""
    assert set(pb.REGEL_JE_QUELLE.values()) <= set(pb.ERKLAERUNG)
    assert set(pb.ERKLAERUNG) == {pb.TATEN, pb.CENSUS, pb.KONSTANT, pb.RELEASES}


def test_jede_studienstadt_steht_in_den_staedten():
    """Eine dritte Stadt kommt aus STUDIENSTAEDTE und sonst nirgends."""
    from silver_pipeline import STUDIENSTAEDTE

    assert set(pb.STAEDTE) == {n.lower() for n in STUDIENSTAEDTE.values()}
    for stadt in pb.STAEDTE:
        assert f"city={stadt}" in pb.REGEL_JE_QUELLE, (
            f"{stadt} steht in STUDIENSTAEDTE, aber nicht in REGEL_JE_QUELLE")
