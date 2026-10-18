"""Der Sicherungssatz ist vollstaendig, klein und wiederholbar.

**Warum er existiert.** Am 18.10.2026 lief die Serversicherung nach
Backblaze voll - 7,3 GB je Nacht, davon 7,1 GB unsere, und fast alles davon
woechentlich wechselnde Rechenergebnisse. Unersetzlich sind **382,2 MiB**:
21 gepinnte Laeufe (127,8 MiB - der eingefrorene Stand, auf den die
LN1-Zahlen zeigen), zwei gepinnte Releases (80,7 MiB) und das aktuelle
Release (173,6 MiB). Alles andere entsteht neu.

Drei Zusagen werden hier gehalten:

* **Vollstaendig** - jeder gepinnte Lauf des Registers ist drin, und das
  aktuelle Release.
* **Klein** - nichts, was sich nachrechnen laesst: kein Silver, kein Gold,
  kein aelteres Release.
* **Wiederholbar** - ein zweiter Lauf holt nichts. Wuerde er neu schreiben,
  legte restic jede Nacht eine weitere Fassung desselben Standes ab, und das
  war genau der Fehler, der das Kontingent gefuellt hat.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src" / "crime"))

from orchestration import sicherungssatz as s   # noqa: E402
from storage import Config, FakeS3Client, Storage, release, set_storage   # noqa: E402


def ablage(tmp_path: Path) -> tuple[Storage, FakeS3Client]:
    fake = FakeS3Client()
    hier = Storage(Config(backend="hybrid", local_root=tmp_path / "data",
                          s3_access_key="k", s3_secret_key="s"), fake)
    set_storage(hier)
    return hier, fake


def lauf_oben(fake: FakeS3Client, schicht: str, stadt: str, kennung: str,
              *, teile: int = 2) -> str:
    rel = f"{schicht}/city={stadt}/ingest_date=2026-09-05/{kennung}"
    fake.put(f"{rel}/manifest.json", json.dumps({"status": "complete"}).encode())
    for i in range(teile):
        fake.put(f"{rel}/part-{i:04d}.parquet", bytes(1000 + i))
    return rel


def release_oben(fake: FakeS3Client, kennung: str) -> str:
    rel = f"releases/release={kennung}"
    fake.put(f"{rel}/release.json", json.dumps({"release_id": kennung}).encode())
    fake.put(f"{rel}/gold/part-0001.parquet", bytes(5000))
    fake.put("releases/AKTUELL.json", json.dumps({"release_id": kennung}).encode())
    return rel


def register(tmp_path: Path, *paare: tuple[str, str]) -> Path:
    config = tmp_path / "config"
    config.mkdir(exist_ok=True)
    zeilen = ["run_id,quelle,grund,seit"]
    zeilen += [f"{k},city=chicago,{g},2026-09-14" for k, g in paare]
    (config / "referenzstand.csv").write_text("\n".join(zeilen) + "\n",
                                              encoding="utf-8")
    return config


def test_der_satz_nennt_jeden_gepinnten_lauf_und_das_release(tmp_path):
    hier, fake = ablage(tmp_path)
    lauf_oben(fake, "raw", "chicago", "run_A")
    lauf_oben(fake, "bronze", "chicago", "run_A")
    lauf_oben(fake, "raw", "chicago", "run_B")       # nicht gepinnt
    release_oben(fake, "2026-10-17T13-21-03Z")
    config = register(tmp_path, ("run_A", "LN1"))

    eintraege, fehlend = s.satz(hier, config)
    kennungen = sorted(e.kennung for e in eintraege)
    assert kennungen == ["2026-10-17T13-21-03Z", "run_A"], (
        f"erwartet der gepinnte Lauf und das Release, da sind {kennungen}")
    assert not fehlend
    gruende = {e.grund for e in eintraege}
    assert "gepinnt: LN1" in gruende and "aktuelles Release" in gruende


def test_was_sich_nachrechnen_laesst_kommt_nicht_hinein(tmp_path):
    """Silver, Gold und aeltere Releases entstehen neu - 117 Sekunden."""
    hier, fake = ablage(tmp_path)
    lauf_oben(fake, "raw", "chicago", "run_A")
    fake.put("silver/dataset=crime_offense/part-0001.parquet", bytes(9_000))
    fake.put("gold/dataset=fact_offense/part-0001.parquet", bytes(9_000))
    release_oben(fake, "2026-10-17T13-21-03Z")
    fake.put("releases/release=2026-09-01T00-00-00Z/release.json", b"{}")
    config = register(tmp_path, ("run_A", "LN1"))

    eintraege, _ = s.satz(hier, config)
    pfade = " ".join(e.rel for e in eintraege)
    assert "silver/" not in pfade and "gold/dataset" not in pfade
    assert "2026-09-01" not in pfade, "ein aelteres Release gehoert nicht dazu"


def test_ein_gepinnter_lauf_der_oben_fehlt_wird_gemeldet(tmp_path):
    """Das Register zeigt dann ins Leere, und keine Sicherung heilt das."""
    hier, fake = ablage(tmp_path)
    lauf_oben(fake, "raw", "chicago", "run_A")
    release_oben(fake, "2026-10-17T13-21-03Z")
    config = register(tmp_path, ("run_A", "LN1"), ("run_WEG", "LN1"))

    eintraege, fehlend = s.satz(hier, config)
    assert fehlend == ["run_WEG"], f"erwartet run_WEG als fehlend, da ist {fehlend}"
    assert [e.kennung for e in eintraege if e.grund.startswith("gepinnt")] == ["run_A"]


def test_ein_neu_gepinnter_lauf_faellt_sofort_auf(tmp_path):
    """Der Fall, der schleichend passiert: pinnen und das Sichern vergessen."""
    hier, fake = ablage(tmp_path)
    lauf_oben(fake, "raw", "chicago", "run_A")
    lauf_oben(fake, "raw", "chicago", "run_NEU")
    release_oben(fake, "2026-10-17T13-21-03Z")

    eintraege, _ = s.satz(hier, register(tmp_path, ("run_A", "LN1")))
    s.hole(hier, eintraege)
    assert all(e.vollstaendig_lokal for e in s.satz(
        hier, register(tmp_path, ("run_A", "LN1")))[0])

    # Jetzt wird run_NEU gepinnt - der Satz ist damit unvollstaendig.
    eintraege, _ = s.satz(hier, register(tmp_path, ("run_A", "LN1"),
                                         ("run_NEU", "stand-2026-10-18")))
    offen = [e.kennung for e in eintraege if not e.vollstaendig_lokal]
    assert offen == ["run_NEU"], f"erwartet run_NEU als offen, da ist {offen}"


def test_ein_zweiter_lauf_holt_nichts(tmp_path):
    """Die Zusage, die das Kontingent schont.

    Schriebe der Satz jede Nacht neu, legte restic jede Nacht eine weitere
    Fassung desselben Standes ab - genau der Mechanismus, der das
    Backblaze-Kontingent gefuellt hat. Laeufe und Releases sind
    unveraenderlich, also darf ein zweiter Lauf **nichts** anfassen.
    """
    hier, fake = ablage(tmp_path)
    lauf_oben(fake, "raw", "chicago", "run_A")
    release_oben(fake, "2026-10-17T13-21-03Z")
    config = register(tmp_path, ("run_A", "LN1"))

    eintraege, _ = s.satz(hier, config)
    assert s.hole(hier, eintraege), "der erste Lauf muss etwas holen"
    vorher = {p: p.stat().st_mtime_ns
              for p in (tmp_path / "data").rglob("*") if p.is_file()}
    assert vorher, "der erste Lauf muss Dateien hinterlassen"

    fake.anfragen.clear()
    eintraege, _ = s.satz(hier, config)
    assert s.hole(hier, eintraege) == [], "der zweite Lauf holt nichts"

    # **Der Zeiger darf gelesen werden**, er ist 160 Byte und landet nicht auf
    # der Platte; alles andere nicht. Erst formuliert als "kein GET", und das
    # war falsch: Ohne den Zeiger weiss niemand, welches Release gilt.
    daten_gets = [a for a in fake.anfragen
                  if a.startswith("GET ") and release.AKTUELL not in a]
    assert not daten_gets, f"kein Daten-GET erwartet, gestellt: {daten_gets}"

    # Die Zusage in der Form, in der restic sie sieht: **kein Byte neu.**
    nachher = {p: p.stat().st_mtime_ns
               for p in (tmp_path / "data").rglob("*") if p.is_file()}
    assert nachher == vorher, "eine Datei wurde angefasst - restic legte eine neue Fassung ab"


def test_das_manifest_sagt_was_im_archiv_liegt(tmp_path):
    """Wer auspackt, hat dieses Repository nicht zur Hand."""
    hier, fake = ablage(tmp_path)
    lauf_oben(fake, "raw", "chicago", "run_A")
    release_oben(fake, "2026-10-17T13-21-03Z")
    config = register(tmp_path, ("run_A", "LN1"))

    eintraege, fehlend = s.satz(hier, config)
    pfad = s.schreibe_manifest(hier, eintraege, fehlend)
    inhalt = json.loads(pfad.read_text(encoding="utf-8"))
    assert inhalt["objekte"] == sum(e.objekte for e in eintraege)
    assert inhalt["register"] == "referenzstand.csv"
    assert "nachrechnen" in inhalt["grundsatz"]
    kennungen = {e["kennung"] for e in inhalt["eintraege"]}
    assert kennungen == {"run_A", "2026-10-17T13-21-03Z"}
    assert {e["grund"] for e in inhalt["eintraege"]} == {
        "gepinnt: LN1", "aktuelles Release"}


def test_ohne_zeiger_wird_das_gesagt_statt_geraten(tmp_path):
    hier, fake = ablage(tmp_path)
    lauf_oben(fake, "raw", "chicago", "run_A")
    eintraege, fehlend = s.satz(hier, register(tmp_path, ("run_A", "LN1")))
    assert [e.kennung for e in eintraege] == ["run_A"]
    assert any("AKTUELL" in f for f in fehlend), fehlend


def test_ohne_s3_bricht_nichts_ab(tmp_path):
    """``STORAGE_BACKEND=local`` ist die Vorgabe - und dort gibt es kein oben."""
    lokal = Storage(Config(backend="local", local_root=tmp_path / "data"))
    set_storage(lokal)
    assert s.verzeichnisse_oben(lokal) == {}
    eintraege, fehlend = s.satz(lokal, register(tmp_path, ("run_A", "LN1")))
    assert (eintraege, fehlend) == ([], ["run_A"])


@pytest.mark.parametrize("schicht", ["silver", "gold", "serving"])
def test_nur_raw_und_bronze_zaehlen_als_lauf(tmp_path, schicht):
    hier, fake = ablage(tmp_path)
    lauf_oben(fake, schicht, "chicago", "run_A")
    assert "run_A" not in s.verzeichnisse_oben(hier), (
        f"{schicht} ist Rechenergebnis und kein zu sichernder Lauf")


# --------------------------------------------------------------------------
# Das Zielverzeichnis gehoert dem Satz allein
# --------------------------------------------------------------------------


def test_ein_abgeloestes_release_verlaesst_den_satz(tmp_path):
    """Die Zusage, ohne die die Sicherung unbegrenzt waechst.

    Jede Woche wird ein neues Release aktuell. Blieb das vorige liegen, waere
    das nach einem Jahr ein Zuwachs von rund 9 GB - genau die Groesse, an der
    das Backblaze-Kontingent am 18.10.2026 haengen geblieben ist. Holen
    allein genuegt also nicht; der Satz muss auch **abgeben**.
    """
    hier, fake = ablage(tmp_path)
    lauf_oben(fake, "raw", "chicago", "run_A")
    release_oben(fake, "2026-10-10T00-00-00Z")
    config = register(tmp_path, ("run_A", "LN1"))

    eintraege, _ = s.satz(hier, config)
    s.hole(hier, eintraege)
    assert (tmp_path / "data" / "releases" / "release=2026-10-10T00-00-00Z").is_dir()

    # Ein neues Release wird aktuell.
    release_oben(fake, "2026-10-17T13-21-03Z")
    eintraege, _ = s.satz(hier, config)
    s.hole(hier, eintraege)
    weg = s.entferne_fremdes(hier, eintraege)

    assert any("2026-10-10" in w for w in weg), f"das alte muss weg sein, weg: {weg}"
    assert not (tmp_path / "data" / "releases" / "release=2026-10-10T00-00-00Z").exists()
    assert (tmp_path / "data" / "releases" / "release=2026-10-17T13-21-03Z").is_dir()
    assert (tmp_path / "data" / "raw").is_dir(), "der gepinnte Lauf bleibt"


def test_entferne_fremdes_laesst_den_satz_in_ruhe(tmp_path):
    """Zweimal hintereinander darf nichts passieren - sonst sieht restic Arbeit."""
    hier, fake = ablage(tmp_path)
    lauf_oben(fake, "raw", "chicago", "run_A")
    lauf_oben(fake, "bronze", "chicago", "run_A")
    release_oben(fake, "2026-10-17T13-21-03Z")
    config = register(tmp_path, ("run_A", "LN1"))

    eintraege, _ = s.satz(hier, config)
    s.hole(hier, eintraege)
    assert s.entferne_fremdes(hier, eintraege) == []

    vorher = {p: p.stat().st_mtime_ns
              for p in (tmp_path / "data").rglob("*") if p.is_file()}
    assert s.entferne_fremdes(hier, eintraege) == []
    nachher = {p: p.stat().st_mtime_ns
               for p in (tmp_path / "data").rglob("*") if p.is_file()}
    assert nachher == vorher and vorher, "keine Datei darf angefasst werden"


def test_entfernt_wird_nur_unterhalb_des_ziels(tmp_path):
    """Die Grenze, die zaehlt.

    Dieses Modul loescht - und es loescht nach einer Regel, die aus einem
    Register kommt. Griffe es daneben, traefe es Arbeitsdaten oder Schlimmeres.
    Geprueft wird deshalb, dass ein Nachbarverzeichnis unberuehrt bleibt.
    """
    hier, fake = ablage(tmp_path)
    lauf_oben(fake, "raw", "chicago", "run_A")
    release_oben(fake, "2026-10-17T13-21-03Z")
    nachbar = tmp_path / "arbeitsdaten"
    (nachbar / "silver").mkdir(parents=True)
    (nachbar / "silver" / "part.parquet").write_bytes(b"x" * 10)

    eintraege, _ = s.satz(hier, register(tmp_path, ("run_A", "LN1")))
    s.hole(hier, eintraege)
    s.entferne_fremdes(hier, eintraege)

    assert (nachbar / "silver" / "part.parquet").is_file(), \
        "ausserhalb des Ziels darf nichts angefasst werden"


# --------------------------------------------------------------------------
# Die vier Formen einer Kennung (gemessen am 18.10.2026 auf srv01)
# --------------------------------------------------------------------------


def test_detroits_uuid_wird_erkannt(tmp_path):
    """Der Fehler, der zehn Eintraege verschwinden liess.

    Detroits Verzeichnisse heissen ``run_<uuid>``, das Register fuehrt die
    blanke UUID. Die erste Fassung verglich den Verzeichnisnamen stur mit der
    Kennung - und meldete alle acht Detroit-Laeufe des LN1-Stands als *oben
    nicht da*. Hatte der Bericht recht, waere der eingefrorene Stand
    verloren; hatte er unrecht, waere er ungesichert geblieben. Beides
    schlimm, und auffallen musste es auf `srv01`.
    """
    hier, fake = ablage(tmp_path)
    uuid = "1cca323d-5f8f-4b5a-abe9-257253131f9f"
    rel = f"bronze/city=detroit/full/year=2021/run_{uuid}"
    fake.put(f"{rel}/manifest.json", b"{}")
    fake.put(f"{rel}/part-0001.parquet", bytes(2000))
    release_oben(fake, "2026-10-17T13-21-03Z")

    eintraege, fehlend = s.satz(hier, register(tmp_path, (uuid, "LN1")))
    assert not fehlend, f"die UUID muss gefunden werden, fehlend: {fehlend}"
    assert [e.rel for e in eintraege if e.grund.startswith("gepinnt")] == [rel]


def test_ein_gepinntes_release_wird_erkannt(tmp_path):
    """Zwei Releases stehen im Register, und sie sind keine Laeufe.

    ``aufraeumen`` kennt das (*"Eine Release-Kennung steht dort in der Spalte
    run_id"*), meine erste Fassung suchte nur in Raw und Bronze - die beiden
    waeren nie in die Sicherung gekommen.
    """
    hier, fake = ablage(tmp_path)
    alt = "2026-09-21T12-55-05Z"
    fake.put(f"releases/release={alt}/release.json", b"{}")
    fake.put(f"releases/release={alt}/gold/part-0001.parquet", bytes(3000))
    release_oben(fake, "2026-10-17T13-21-03Z")

    eintraege, fehlend = s.satz(hier, register(tmp_path, (alt, "LN1")))
    assert not fehlend, fehlend
    kennungen = sorted(e.kennung for e in eintraege)
    assert kennungen == [alt, "2026-10-17T13-21-03Z"], kennungen


def test_das_aktuelle_release_zaehlt_nur_einmal(tmp_path):
    """Ist es zugleich gepinnt, darf es nicht doppelt im Satz stehen."""
    hier, fake = ablage(tmp_path)
    kennung = "2026-10-17T13-21-03Z"
    release_oben(fake, kennung)
    eintraege, _ = s.satz(hier, register(tmp_path, (kennung, "LN1")))
    assert len(eintraege) == 1, [e.kennung for e in eintraege]
    assert eintraege[0].grund == "gepinnt: LN1", "der Pin ist der staerkere Grund"


@pytest.mark.parametrize("name,kennung", [
    ("run_20260905T174633859259Z", "run_20260905T174633859259Z"),   # Chicago
    ("run_1cca323d-5f8f-4b5a-abe9-257253131f9f",
     "1cca323d-5f8f-4b5a-abe9-257253131f9f"),                       # Detroit
    ("release=2026-09-21T12-55-05Z", "2026-09-21T12-55-05Z"),       # Release
    ("run=abc", "abc"),                                             # vierte Form
])
def test_alle_vier_formen_passen(name, kennung):
    assert s.passt(kennung, name), f"{name} traegt {kennung} nicht"


@pytest.mark.parametrize("name", ["run_abcdef", "release=xyz", "voelligAnders"])
def test_fremde_namen_passen_nicht(name):
    """Sonst nimmt der Satz Fremdes mit, und das waere das umgekehrte Problem."""
    assert not s.passt("abc", name), f"{name} darf 'abc' nicht tragen"
