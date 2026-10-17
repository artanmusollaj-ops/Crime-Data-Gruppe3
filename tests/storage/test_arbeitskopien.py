"""Der Aufschub des lokalen Aufraeumens - und seine zwei Grenzen.

Am 16.10.2026 war die Strecke auf ``srv01`` **gruen** und das Release
gescheitert: *"es fehlt: gold/dataset=fact_offense, ..."*, sieben Tabellen.
Alle lagen oben, keine unten. ``publish_table`` entfernt im Modus ``s3`` die
lokale Arbeitskopie sofort, ``storage.release.sammle`` liest aber das
Dateisystem - und die Modus-Tabelle in ``docs/storage-architektur.md`` sagt
fuer ``s3`` ausdruecklich *"lokal gebildet, hochgebracht, lokale Kopie
**danach** entfernt"*. Die Reihenfolge war beschrieben, nur nicht umgesetzt.

Kein Test hier braucht SeaweedFS - S3 ist ``FakeS3Client``, ein dict.
"""

from __future__ import annotations

import json
from pathlib import Path

from storage import Config, FakeS3Client, Storage


def ablage(tmp_path: Path, backend: str, *,
           keep_local: bool = False) -> tuple[Storage, FakeS3Client]:
    fake = FakeS3Client()
    config = Config(backend=backend, local_root=tmp_path / "data",
                    s3_access_key="k", s3_secret_key="s",
                    keep_local=keep_local)
    return Storage(config, fake), fake


def lege_tabelle(storage: Storage, rel: str, *, zeilen: int = 3) -> Path:
    verzeichnis = storage.local_path(rel)
    verzeichnis.mkdir(parents=True, exist_ok=True)
    (verzeichnis / "part-0001.parquet").write_bytes(b"x" * zeilen)
    (verzeichnis / "manifest.json").write_text(
        json.dumps({"status": "complete", "row_count": zeilen}), encoding="utf-8")
    return verzeichnis


GOLD = "gold/dataset=fact_offense"


# --------------------------------------------------------------------------
# Der Aufschub
# --------------------------------------------------------------------------


def test_ohne_schalter_geht_die_kopie_wie_bisher_sofort_weg(tmp_path):
    storage, _ = ablage(tmp_path, "s3")
    verzeichnis = lege_tabelle(storage, GOLD)
    storage.publish_table(GOLD)
    assert not verzeichnis.exists(), \
        "ohne Schalter bleibt das Verhalten, wie es war"


def test_mit_schalter_bleibt_die_kopie_liegen(tmp_path):
    """Genau das, was dem Release gefehlt hat."""
    storage, _ = ablage(tmp_path, "s3", keep_local=True)
    verzeichnis = lege_tabelle(storage, GOLD)
    storage.publish_table(GOLD)
    assert (verzeichnis / "part-0001.parquet").is_file(), \
        "mit Schalter muss die Kopie bleiben - sonst findet sammle() nichts"


def test_der_schalter_haelt_keinen_lauf_lokal(tmp_path):
    """Die erste Grenze: nur Tabellen, nie Laeufe.

    Ein Lauf ist unveraenderlich und jederzeit wieder zu holen. Ihn lokal zu
    behalten haeuft nur an - 141 Bronze-Laeufe waren der Grund, warum der
    Silver-Bau erstickte. Auch ein global gesetzter Schalter darf das nicht
    koennen.
    """
    storage, _ = ablage(tmp_path, "s3", keep_local=True)
    rel = "bronze/city=chicago/ingest_date=2026-10-16/run_A"
    verzeichnis = storage.local_path(rel)
    verzeichnis.mkdir(parents=True)
    (verzeichnis / "part-0001.parquet").write_bytes(b"x")
    (verzeichnis / "manifest.json").write_text('{"status": "complete"}',
                                               encoding="utf-8")
    storage.publish_run(rel)
    assert not verzeichnis.exists(), (
        "ein Lauf darf den Schalter nicht sehen - sonst haeuft sich Bronze "
        "lokal an, und genau daran ist der Silver-Bau erstickt")


# --------------------------------------------------------------------------
# Das Nachraeumen
# --------------------------------------------------------------------------


def test_nach_dem_release_gehen_die_aufgeschobenen_kopien_weg(tmp_path):
    storage, _ = ablage(tmp_path, "s3", keep_local=True)
    gold = lege_tabelle(storage, GOLD)
    silber = lege_tabelle(storage, "silver/dataset=crime_offense")
    storage.publish_table(GOLD)
    storage.publish_table("silver/dataset=crime_offense")

    weg = storage.arbeitskopien_entfernen()

    assert sorted(weg) == ["gold/dataset=fact_offense",
                           "silver/dataset=crime_offense"]
    assert not gold.exists() and not silber.exists()


def test_was_oben_fehlt_bleibt_liegen(tmp_path):
    """Die zweite Grenze, und die wichtigere.

    Eine Tabelle, deren Upload scheiterte, liegt nur lokal. Sie hier zu
    entfernen hiesse, sie zu verlieren - der Unterschied zwischen Aufraeumen
    und Datenverlust. Er kostet eine Abfrage je Tabelle.
    """
    storage, fake = ablage(tmp_path, "s3", keep_local=True)
    gold = lege_tabelle(storage, GOLD)
    storage.publish_table(GOLD)
    # Der Upload sei misslungen: Oben liegt nichts.
    for schluessel in list(fake.objekte):
        if schluessel.startswith(GOLD):
            del fake.objekte[schluessel]

    weg = storage.arbeitskopien_entfernen()

    assert weg == [], "was oben fehlt, darf hier nicht verschwinden"
    assert (gold / "part-0001.parquet").is_file()


def test_ausserhalb_von_s3_raeumt_es_nichts_weg(tmp_path):
    """In ``local`` gibt es kein Oben, in ``hybrid`` ist die Kopie der Bestand."""
    for backend in ("local", "hybrid"):
        storage, _ = ablage(tmp_path / backend, backend, keep_local=True)
        verzeichnis = lege_tabelle(storage, GOLD)
        if backend == "hybrid":
            storage.publish_table(GOLD)
        assert storage.arbeitskopien_entfernen() == []
        assert verzeichnis.exists(), f"{backend}: die Kopie ist der Bestand"


# --------------------------------------------------------------------------
# Welche Schichten ueberhaupt gefragt werden
# --------------------------------------------------------------------------


def test_serving_wird_nicht_gefragt_und_warnt_deshalb_nicht(tmp_path, caplog):
    """Eine Warnung, die immer kommt, erzieht zum Ueberlesen.

    Am 17.10.2026 meldete der erste Lauf mit dem neuen Aufraeumen fuenfmal
    *"Nicht oben, lokale Kopie bleibt: serving/dataset=..."*. Die Sicherung
    tat das Richtige - keine Serving-Tabelle wird je einzeln publiziert, also
    liegt keine oben. Nur war die Frage falsch gestellt.
    """
    storage, _ = ablage(tmp_path, "s3", keep_local=True)
    serving = lege_tabelle(storage, "serving/dataset=comparison_day")
    gold = lege_tabelle(storage, GOLD)
    storage.publish_table(GOLD)

    with caplog.at_level("WARNING"):
        weg = storage.arbeitskopien_entfernen()

    assert weg == ["gold/dataset=fact_offense"]
    assert serving.exists(), "die lokale Kopie der Serving-Tabelle ist der Bestand"
    assert not gold.exists()
    serving_warnungen = [s for s in caplog.messages if "serving/" in s]
    assert not serving_warnungen, (
        f"gewarnt wird ueber eine Schicht, die nie einzeln publiziert wird: "
        f"{serving_warnungen}")


def test_kein_serving_modul_publiziert_einzeln():
    """Faengt eines damit an, ist ``PUBLIZIERTE_SCHICHTEN`` zu kurz.

    Dann blieben die Arbeitskopien dieser Tabellen nach dem Release liegen,
    und zwar lautlos - ``arbeitskopien_entfernen`` schaut die Schicht dann
    gar nicht an. Dieser Test sagt es, statt dass das Volume waechst.

    Geprueft wird der Quelltext, nicht ein Lauf: Ein echter Serving-Bau
    braeuchte gebautes Gold, und der Test liefe genau dort nicht, wo die
    Suite laeuft.
    """
    from storage import Storage

    serving = Path(__file__).resolve().parents[2] / "src" / "crime" / "serving"
    publizierend = [
        datei.name for datei in sorted(serving.glob("*.py"))
        if "publish_table" in datei.read_text(encoding="utf-8")
    ]
    assert not publizierend, (
        f"{publizierend} ruft publish_table - dann gehoert 'serving' in "
        f"Storage.PUBLIZIERTE_SCHICHTEN, sonst bleiben die Arbeitskopien "
        f"nach dem Release liegen. Heute: {Storage.PUBLIZIERTE_SCHICHTEN}")


def test_wer_eine_schicht_nennt_bekommt_genau_die(tmp_path):
    """Das Argument sticht die Vorgabe - fuer einen Aufrufer, der es weiss."""
    storage, _ = ablage(tmp_path, "s3", keep_local=True)
    lege_tabelle(storage, GOLD)
    silber = lege_tabelle(storage, "silver/dataset=crime_offense")
    storage.publish_table(GOLD)
    storage.publish_table("silver/dataset=crime_offense")

    weg = storage.arbeitskopien_entfernen(("silver",))

    assert weg == ["silver/dataset=crime_offense"]
    assert not silber.exists()
    assert storage.local_path(GOLD).exists(), "gold war nicht gefragt"


# --------------------------------------------------------------------------
# Oben liegt nicht irgendwas, sondern dasselbe
# --------------------------------------------------------------------------


def test_ein_anderer_stand_oben_schuetzt_die_lokale_kopie(tmp_path, caplog):
    """Der Fehler vom 17.10.2026, und zwar mein eigener.

    Die erste Fassung fragte nur, *ob* oben etwas liegt. Damit hat sie eine
    frisch gebaute ``source_change`` geloescht, deren Gegenstueck oben zwei
    Wochen alt war: ``build_source_change`` rief damals kein
    ``publish_table``, baute also unten eine neue Fassung, die nie hinaufkam.
    21,4 Mio. Zeilen, gebaut und verloren. Dass sie falsch waren, war Glueck.
    """
    storage, _ = ablage(tmp_path, "s3", keep_local=True)
    rel = "silver/dataset=source_change"
    verzeichnis = lege_tabelle(storage, rel, zeilen=3)
    storage.publish_table(rel)

    # Ein neuer Bau unten, der nie hinaufkommt.
    (verzeichnis / "manifest.json").write_text(
        json.dumps({"status": "complete", "row_count": 21_384_112}),
        encoding="utf-8")

    with caplog.at_level("WARNING"):
        weg = storage.arbeitskopien_entfernen()

    assert weg == [], "ein nicht publizierter Stand darf nicht geloescht werden"
    assert (verzeichnis / "part-0001.parquet").is_file()
    assert any("anderer Stand" in s for s in caplog.messages), \
        "das gehoert gemeldet, nicht verschwiegen"


def test_derselbe_stand_oben_gibt_die_kopie_frei(tmp_path):
    """Die Gegenprobe: Der Vergleich darf nicht alles festhalten."""
    storage, _ = ablage(tmp_path, "s3", keep_local=True)
    verzeichnis = lege_tabelle(storage, GOLD)
    storage.publish_table(GOLD)
    assert storage.arbeitskopien_entfernen() == [GOLD]
    assert not verzeichnis.exists()


def test_ein_unlesbares_manifest_oben_schuetzt_die_kopie(tmp_path, caplog):
    """Eine Unsicherheit darf nicht zum Loeschen fuehren."""
    storage, fake = ablage(tmp_path, "s3", keep_local=True)
    verzeichnis = lege_tabelle(storage, GOLD)
    storage.publish_table(GOLD)
    fake.put(f"{GOLD}/manifest.json", b"{kein json")

    with caplog.at_level("WARNING"):
        weg = storage.arbeitskopien_entfernen()

    assert weg == []
    assert verzeichnis.exists()
    assert any("nicht vergleichbar" in s for s in caplog.messages)
