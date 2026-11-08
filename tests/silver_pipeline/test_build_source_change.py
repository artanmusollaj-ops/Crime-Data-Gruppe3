"""Die Aenderungstabelle - geprueft an Schnappschuessen, die der Test selbst baut.

Ein Werkzeug, das Aenderungen finden soll, muss vor allem **nicht** finden,
was keine ist. Der groessere Teil dieser Pruefungen fuehrt deshalb Paare vor,
zwischen denen sich etwas bewegt hat, das nicht zaehlt - eine ArcGIS-Zeilen-
nummer, ein angehaengtes Leerzeichen - und sieht nach, dass die Tabelle leer
bleibt.

Eine Pruefung fasst den gebauten Bestand an und rechnet die Zahlen aus
``docs/intern/datenhistorie.md`` nach; sie traegt ``referenzstand``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from manifeste import Lauf
from silver_pipeline import PARQUET_FILE, TransformError
from silver_pipeline import build_source_change as bsc

DETROIT = bsc.QUELLEN[0]


# --------------------------------------------------------------------------
# Werkzeug
# --------------------------------------------------------------------------


#: Wie die beiden Staedte denselben Sachverhalt schreiben. Chicagos
#: Ingestion nennt den Schluessel ``mode`` und den Vollabzug
#: ``full_snapshot``, Detroits ``extraction_mode`` und ``FULL``; beim
#: Startzeitpunkt steht ``started_at_utc`` gegen ``started_at``. Beides
#: nebeneinander hier, damit der Test nicht nur eine Stadt beweist.
VOKABULAR = {
    "detroit": ("extraction_mode", "FULL", "DELTA", "started_at"),
    "chicago": ("mode", "full_snapshot", "delta", "started_at_utc"),
}


def lauf(run_id: str, *, voll: bool = True, wann: str = "",
         relativ: str = "", stadt: str = "detroit",
         jahrgang: int | None = None) -> Lauf:
    """Ein Lauf als **echter** ``manifeste.Lauf``, nicht als Doppel.

    Vorher stand hier eine eigene Klasse mit drei Attributen. Sie kannte nur
    Detroits Vokabular und waere gruen geblieben, als ``schnappschuesse`` auf
    den gemeinsamen Manifestleser umgestellt wurde - ein Doppel prueft, was
    man ihm beigebracht hat. Mit dem echten Typ kann es nicht auseinander
    laufen.
    """
    feld, ja, nein, zeitfeld = VOKABULAR[stadt]
    manifest: dict[str, object] = {"run_id": run_id, feld: ja if voll else nein}
    if wann:
        manifest[zeitfeld] = wann
    if jahrgang is not None:
        # Chicago nennt ihn ``event_year``, Detroit ``year`` - ``Lauf.jahrgang``
        # kennt beide, und dieser Helfer soll dieselbe Asymmetrie treffen.
        manifest["event_year" if stadt == "chicago" else "year"] = jahrgang
    return Lauf(Path(f"/gibt-es-nicht/{run_id}"), manifest,
                relativ or f"bronze/city={stadt}/run_{run_id}")


def schnappschuss(wurzel: Path, run_id: str, zeilen: list[dict], *,
                  wann: str, modus: str = "FULL", jahrgang: int | None = None) -> None:
    """Ein Bronze-Lauf, wie ihn die Detroit-Ingestion ablegt.

    ``attributes`` ist ein Struct - genau wie in der echten Datei, denn an
    dessen Feldern entscheidet sich der ganze Vergleich.
    """
    import duckdb

    verzeichnis = wurzel / "bronze" / "city=detroit" / f"run_{run_id}"
    verzeichnis.mkdir(parents=True, exist_ok=True)

    felder = ["incident_entry_id", "offense_description", "state_offense_code",
              "offense_category", "case_status", "updated_at", "ESRI_OID"]
    werte = [
        "SELECT {"
        + ", ".join(f"{f!r}: {str(z.get(f, ''))!r}" for f in felder)
        + "} AS attributes"
        for z in zeilen
    ]
    con = duckdb.connect()
    con.execute(f"COPY ({' UNION ALL '.join(werte)}) "
                f"TO '{verzeichnis / PARQUET_FILE}' (FORMAT PARQUET)")
    con.close()

    (verzeichnis / "manifest.json").write_text(json.dumps({
        "status": "SUCCESS", "extraction_mode": modus, "started_at": wann,
        "row_count": len(zeilen), "pipeline_run_id": run_id,
        **({"year": jahrgang} if jahrgang is not None else {}),
    }), encoding="utf-8")


def zeile(ident: str, **rest) -> dict:
    grund = {"incident_entry_id": ident, "offense_description": "ASSAULT",
             "state_offense_code": "1300", "offense_category": "ASSAULT",
             "case_status": "OPEN",
             "updated_at": "1000", "ESRI_OID": "1"}
    return {**grund, **rest}


def baue_in(wurzel: Path) -> dict:
    return bsc.baue(wurzel)


def gelesen(wurzel: Path) -> list[dict]:
    import duckdb

    datei = bsc.tabellenverzeichnis(wurzel) / PARQUET_FILE
    con = duckdb.connect()
    try:
        spalten = ", ".join(bsc.SPALTEN)
        return [dict(zip(bsc.SPALTEN, r)) for r in con.execute(
            f"SELECT {spalten} FROM read_parquet('{datei}')").fetchall()]
    finally:
        con.close()


# --------------------------------------------------------------------------
# Welche Laeufe ueberhaupt vergleichbar sind
# --------------------------------------------------------------------------


@pytest.mark.parametrize("stadt", sorted(VOKABULAR))
def test_nur_vollschnappschuesse_werden_verglichen(stadt):
    """Ein Delta enthaelt nur die bewegten Zeilen.

    *Was fehlt* liesse sich daraus nicht von *was sich nicht geaendert hat*
    unterscheiden - jede Zeile ausserhalb des Deltas saehe verschwunden aus.

    Geprueft wird fuer **beide** Staedte: Bis zum 3.10.2026 las dieses Modul
    nur ``extraction_mode`` und haette Chicagos Vollabzuege auch dann nicht
    gefunden, wenn zwei dagelegen haetten.
    """
    laeufe = [lauf("a", voll=True, wann="2026-09-11T12:00:00", stadt=stadt),
              lauf("b", voll=False, wann="2026-09-12T12:00:00", stadt=stadt),
              lauf("c", voll=True, wann="2026-09-13T12:00:00", stadt=stadt)]
    assert [s.run_id for s in bsc.schnappschuesse(laeufe)] == ["a", "c"]


def test_sortiert_wird_nach_der_zeit_nicht_nach_dem_namen():
    """Detroits Laufverzeichnisse heissen nach einer UUID - die sagt nichts."""
    laeufe = [lauf("zzz", wann="2026-09-11T12:00:00"),
              lauf("aaa", wann="2026-09-12T12:00:00")]
    assert [s.run_id for s in bsc.schnappschuesse(laeufe)] == ["zzz", "aaa"]


def test_ein_manifest_ohne_zeitstempel_bricht_ab():
    with pytest.raises(TransformError, match="ohne ihn"):
        bsc.schnappschuesse([lauf("a", wann="")])


def test_paare_sind_aufeinanderfolgend_nicht_jedes_gegen_jedes():
    """Sonst stuende jede Bewegung mehrfach in der Tabelle."""
    alle = [bsc.Schnappschuss(c, c, f"2026-09-1{i}") for i, c in enumerate("abcd")]
    assert [(a.run_id, b.run_id) for a, b in bsc.paare(alle)] == [
        ("a", "b"), ("b", "c"), ("c", "d")]


def test_ein_einzelner_schnappschuss_ergibt_kein_paar():
    assert bsc.paare([bsc.Schnappschuss("a", "a", "x")]) == []


def test_zwei_jahrgaenge_werden_nicht_gegeneinander_verglichen():
    """Der groessere der beiden Fehler vom 17.10.2026.

    Bis dahin bildete ``paare`` **eine** Kette je Stadt, nach Zeit geordnet.
    Seit beide Staedte am 4.10.2026 anfingen, je Jahrgang zu laden, sind
    aufeinanderfolgende Abzuege verschiedene Jahrgaenge - und der Vergleich
    meldete jede Zeile des einen als ``verschwunden`` und jede des anderen als
    ``neu``. **1,64 Mio. erfundene "verschwunden"** standen so in der Tabelle,
    die der Gegenstand der Arbeit ist.

    Dieser Test prueft nicht, dass Paare entstehen, sondern **welche**: Ein
    Paar ueber zwei Jahrgaenge darf nicht dabei sein.
    """
    alle = [
        bsc.Schnappschuss("a24", "a24", "2026-09-05", "2024"),
        bsc.Schnappschuss("b24", "b24", "2026-10-03", "2024"),
        bsc.Schnappschuss("c21", "c21", "2026-10-04", "2021"),
        bsc.Schnappschuss("d21", "d21", "2026-10-05", "2021"),
    ]
    gebildet = [(a.run_id, b.run_id) for a, b in bsc.paare(alle)]
    assert gebildet == [("c21", "d21"), ("a24", "b24")], (
        f"erwartet sind zwei Ketten, eine je Jahrgang - gebildet wurde "
        f"{gebildet}")
    gemischt = [(a, b) for a, b in bsc.paare(alle) if a.jahrgang != b.jahrgang]
    assert not gemischt, (
        f"ueber Jahrgaenge hinweg verglichen: "
        f"{[(a.run_id, b.run_id) for a, b in gemischt]} - dann ist jede Zeile "
        f"des einen Jahrgangs 'verschwunden' und jede des anderen 'neu'")


def test_ein_einzelner_abzug_je_jahrgang_ergibt_kein_paar():
    """Der Stand nach dem Mehrjahresbau vom 4.10.2026: fuenf Jahrgaenge mit je
    einem Abzug, und nichts zu vergleichen. Vorher waren daraus funf Paare
    geworden - alle falsch."""
    alle = [bsc.Schnappschuss(f"r{j}", f"r{j}", f"2026-10-0{i}", str(j))
            for i, j in enumerate((2021, 2022, 2023, 2025, 2026), start=4)]
    assert bsc.paare(alle) == []


def test_der_jahrgang_kommt_aus_dem_manifest():
    """Beide Vokabulare - sonst traegt eine Stadt ihn nicht."""
    for stadt in ("chicago", "detroit"):
        abzug, = bsc.schnappschuesse(
            [lauf("r1", wann="2026-10-03", stadt=stadt, jahrgang=2024)])
        assert abzug.jahrgang == "2024", f"{stadt}: Jahrgang nicht gelesen"


def test_jahrgangslose_abzuege_bilden_ihre_eigene_kette():
    """Bestaende aus der Zeit vor der Jahrgangstrennung bleiben vergleichbar."""
    alle = [bsc.Schnappschuss("a", "a", "2026-09-01"),
            bsc.Schnappschuss("b", "b", "2026-09-02")]
    assert [(a.run_id, b.run_id) for a, b in bsc.paare(alle)] == [("a", "b")]


# --------------------------------------------------------------------------
# Was als Aenderung zaehlt
# --------------------------------------------------------------------------


def test_eine_inhaltliche_aenderung_wird_aufgezeichnet(tmp_path):
    schnappschuss(tmp_path, "a", [zeile("1")], wann="2026-09-11T12:00:00")
    schnappschuss(tmp_path, "b", [zeile("1", case_status="CLOSED")],
                  wann="2026-09-12T12:00:00")
    baue_in(tmp_path)
    zeilen = [z for z in gelesen(tmp_path) if z["feld"] == "case_status"]
    assert len(zeilen) == 1
    assert (zeilen[0]["wert_alt"], zeilen[0]["wert_neu"]) == ("OPEN", "CLOSED")
    assert zeilen[0]["art"] == "geaendert"


def test_eine_bewegte_zeilennummer_allein_ist_keine_aenderung(tmp_path):
    """``ESRI_OID`` bewegte sich bei 88'677 von 88'685 Zeilen.

    Wer es mitvergleicht, erzeugt ein Protokoll, in dem die hundert echten
    Aenderungen nicht zu finden sind - Faktor 870 Rauschen.
    """
    schnappschuss(tmp_path, "a", [zeile("1", ESRI_OID="1")],
                  wann="2026-09-11T12:00:00")
    schnappschuss(tmp_path, "b", [zeile("1", ESRI_OID="99999")],
                  wann="2026-09-12T12:00:00")
    baue_in(tmp_path)
    assert [z["art"] for z in gelesen(tmp_path)] == ["unveraendert"]


def test_ein_angehaengtes_leerzeichen_ist_keine_aenderung(tmp_path):
    """150 von 160 Beschreibungsaenderungen waren reine Leerzeichen."""
    schnappschuss(tmp_path, "a", [zeile("1", offense_description="ARSON")],
                  wann="2026-09-11T12:00:00")
    schnappschuss(tmp_path, "b", [zeile("1", offense_description="ARSON   ")],
                  wann="2026-09-12T12:00:00")
    baue_in(tmp_path)
    assert [z["art"] for z in gelesen(tmp_path)] == ["unveraendert"]


def test_nur_ein_stempel_bewegt_heisst_beruehrt(tmp_path):
    """Die Quelle hat die Zeile angefasst, ohne dass sich fachlich etwas
    aenderte - das ist eine eigene Beobachtung, kein Rauschen."""
    schnappschuss(tmp_path, "a", [zeile("1", updated_at="1000")],
                  wann="2026-09-11T12:00:00")
    schnappschuss(tmp_path, "b", [zeile("1", updated_at="2000")],
                  wann="2026-09-12T12:00:00")
    baue_in(tmp_path)
    zeilen = gelesen(tmp_path)
    assert {z["art"] for z in zeilen} == {"beruehrt"}
    assert {z["feld"] for z in zeilen} == {"updated_at"}


def test_stempel_neben_einer_inhaltsaenderung_macht_sie_nicht_zur_beruehrung(tmp_path):
    schnappschuss(tmp_path, "a", [zeile("1")], wann="2026-09-11T12:00:00")
    schnappschuss(tmp_path, "b",
                  [zeile("1", updated_at="2000", case_status="CLOSED")],
                  wann="2026-09-12T12:00:00")
    baue_in(tmp_path)
    zeilen = gelesen(tmp_path)
    assert {z["art"] for z in zeilen} == {"geaendert"}
    # Der Stempel wird trotzdem aufgezeichnet - er gehoert zur Beobachtung.
    assert {z["feld"] for z in zeilen} == {"updated_at", "case_status"}


def test_eine_neue_zeile_heisst_neu(tmp_path):
    schnappschuss(tmp_path, "a", [zeile("1")], wann="2026-09-11T12:00:00")
    schnappschuss(tmp_path, "b", [zeile("1"), zeile("2")],
                  wann="2026-09-12T12:00:00")
    baue_in(tmp_path)
    zeilen = [z for z in gelesen(tmp_path) if z["art"] == "neu"]
    assert [z["offense_id"] for z in zeilen] == ["2"]


def test_eine_fehlende_zeile_heisst_verschwunden(tmp_path):
    schnappschuss(tmp_path, "a", [zeile("1"), zeile("2")],
                  wann="2026-09-11T12:00:00")
    schnappschuss(tmp_path, "b", [zeile("1")], wann="2026-09-12T12:00:00")
    baue_in(tmp_path)
    zeilen = [z for z in gelesen(tmp_path) if z["art"] == "verschwunden"]
    assert [z["offense_id"] for z in zeilen] == ["2"]


def test_ein_paar_ohne_aenderung_wird_trotzdem_festgehalten(tmp_path):
    """Sonst waere *nichts gefunden* nicht von *noch nicht verglichen* zu
    unterscheiden - und beide Laeufe blieben nach Regel 2a fuer immer
    gesperrt. Genau das ist beim ersten Lauf passiert."""
    schnappschuss(tmp_path, "a", [zeile("1")], wann="2026-09-11T12:00:00")
    schnappschuss(tmp_path, "b", [zeile("1")], wann="2026-09-12T12:00:00")
    baue_in(tmp_path)
    zeilen = gelesen(tmp_path)
    assert [z["art"] for z in zeilen] == ["unveraendert"]
    assert zeilen[0]["offense_id"] is None
    assert bsc.ungezogene_laeufe(tmp_path) == set()


# --------------------------------------------------------------------------
# Append-only
# --------------------------------------------------------------------------


def test_ein_zweiter_lauf_zieht_nichts_doppelt(tmp_path):
    schnappschuss(tmp_path, "a", [zeile("1")], wann="2026-09-11T12:00:00")
    schnappschuss(tmp_path, "b", [zeile("1", case_status="CLOSED")],
                  wann="2026-09-12T12:00:00")
    erst = baue_in(tmp_path)
    zweit = baue_in(tmp_path)
    assert zweit["paare"] == 0 and zweit["uebersprungen"] == 1
    assert zweit["row_count"] == erst["row_count"]


def test_ein_neues_paar_kommt_dazu_ohne_das_alte_anzutasten(tmp_path):
    schnappschuss(tmp_path, "a", [zeile("1")], wann="2026-09-11T12:00:00")
    schnappschuss(tmp_path, "b", [zeile("1", case_status="CLOSED")],
                  wann="2026-09-12T12:00:00")
    erst = baue_in(tmp_path)
    schnappschuss(tmp_path, "c", [zeile("1", case_status="REOPENED")],
                  wann="2026-09-13T12:00:00")
    zweit = baue_in(tmp_path)
    assert zweit["paare"] == 1
    assert zweit["row_count"] > erst["row_count"]
    paare = {(z["vorher_run_id"], z["run_id"]) for z in gelesen(tmp_path)}
    assert paare == {("a", "b"), ("b", "c")}


def test_der_bestand_bleibt_auch_wenn_die_laeufe_weg_sind(tmp_path):
    """Der Grund, warum diese Tabelle nicht neu gebaut wird wie die uebrigen.

    Ihr Rohstoff verschwindet: Ist ein Lauf aufgeraeumt, laesst sich sein
    Vergleich nicht wiederherstellen.
    """
    import shutil

    schnappschuss(tmp_path, "a", [zeile("1")], wann="2026-09-11T12:00:00")
    schnappschuss(tmp_path, "b", [zeile("1", case_status="CLOSED")],
                  wann="2026-09-12T12:00:00")
    erst = baue_in(tmp_path)
    shutil.rmtree(tmp_path / "bronze" / "city=detroit" / "run_a")
    zweit = baue_in(tmp_path)
    assert zweit["row_count"] == erst["row_count"], "der Bestand ging verloren"


# --------------------------------------------------------------------------
# Der Zusammenhang: Deliktsart und Bestand (Vertrag 4)
# --------------------------------------------------------------------------


def test_eine_verschwundene_zeile_nennt_ihre_deliktsart(tmp_path):
    """Sonst traegt sie nur ihren Schluessel - und ihr Inhalt steht in keinem
    spaeteren Stand mehr. *Was* verschwindet, liesse sich nie mehr sagen."""
    schnappschuss(tmp_path, "a", [zeile("1"), zeile("2", state_offense_code="2900",
                                                     offense_category="ARSON")],
                  wann="2026-09-11T12:00:00")
    schnappschuss(tmp_path, "b", [zeile("1")], wann="2026-09-12T12:00:00")
    baue_in(tmp_path)
    [weg] = [z for z in gelesen(tmp_path) if z["art"] == "verschwunden"]
    assert (weg["quellcode"], weg["quellkategorie"]) == ("2900", "ARSON")


def test_eine_neue_zeile_nennt_die_deliktsart_aus_dem_juengeren_stand(tmp_path):
    schnappschuss(tmp_path, "a", [zeile("1")], wann="2026-09-11T12:00:00")
    schnappschuss(tmp_path, "b", [zeile("1"), zeile("2", state_offense_code="2400",
                                                     offense_category="STOLEN VEHICLE")],
                  wann="2026-09-12T12:00:00")
    baue_in(tmp_path)
    [neu] = [z for z in gelesen(tmp_path) if z["art"] == "neu"]
    assert (neu["quellcode"], neu["quellkategorie"]) == ("2400", "STOLEN VEHICLE")


def test_eine_geaenderte_zeile_nennt_die_deliktsart_von_vorher(tmp_path):
    """Aendert sich die Deliktsart selbst, gilt der Stand, der sich geaendert hat."""
    schnappschuss(tmp_path, "a", [zeile("1")], wann="2026-09-11T12:00:00")
    schnappschuss(tmp_path, "b", [zeile("1", state_offense_code="1200",
                                         offense_category="ROBBERY")],
                  wann="2026-09-12T12:00:00")
    baue_in(tmp_path)
    zeilen = [z for z in gelesen(tmp_path) if z["art"] == "geaendert"]
    assert {(z["quellcode"], z["quellkategorie"]) for z in zeilen} == {("1300", "ASSAULT")}


def test_jede_zeile_des_paares_nennt_den_bestand(tmp_path):
    """Der Nenner jeder Rate - auch in der Markierungszeile eines ruhigen Paares."""
    schnappschuss(tmp_path, "a", [zeile("1"), zeile("2"), zeile("3")],
                  wann="2026-09-11T12:00:00")
    schnappschuss(tmp_path, "b", [zeile("1"), zeile("2")], wann="2026-09-12T12:00:00")
    schnappschuss(tmp_path, "c", [zeile("1"), zeile("2")], wann="2026-09-13T12:00:00")
    baue_in(tmp_path)
    je_paar = {(z["vorher_run_id"], z["run_id"], z["bestand_vorher"], z["bestand_nachher"])
               for z in gelesen(tmp_path)}
    assert je_paar == {("a", "b", 3, 2), ("b", "c", 2, 2)}


def test_jedes_paar_nennt_seinen_jahrgang(tmp_path):
    """Aus dem Manifest des Laufs - damit sich die Bewegung je Tatjahr filtern laesst."""
    schnappschuss(tmp_path, "a", [zeile("1"), zeile("2")], wann="2026-09-11T12:00:00",
                  jahrgang=2023)
    schnappschuss(tmp_path, "b", [zeile("1")], wann="2026-09-12T12:00:00", jahrgang=2023)
    schnappschuss(tmp_path, "c", [zeile("1")], wann="2026-09-13T12:00:00")
    schnappschuss(tmp_path, "d", [zeile("1", case_status="X")], wann="2026-09-14T12:00:00")
    baue_in(tmp_path)
    assert {(z["vorher_run_id"], z["jahrgang"]) for z in gelesen(tmp_path)} == {
        ("a", 2023), ("c", None)}


def test_ein_fehlender_jahrgang_wird_nachgetragen_ohne_den_bestand_zu_verlieren(tmp_path):
    """Eine Fassung ohne die Spalte: Der Bestand klebt, der Jahrgang kommt aus dem Manifest."""
    import duckdb

    schnappschuss(tmp_path, "a", [zeile("1"), zeile("2")], wann="2026-09-11T12:00:00",
                  jahrgang=2022)
    schnappschuss(tmp_path, "b", [zeile("1")], wann="2026-09-12T12:00:00", jahrgang=2022)
    baue_in(tmp_path)
    datei = bsc.tabellenverzeichnis(tmp_path) / PARQUET_FILE
    con = duckdb.connect()
    spalten = ", ".join(s for s in bsc.SPALTEN if s != "jahrgang")
    con.execute(f"COPY (SELECT {spalten} FROM read_parquet('{datei}')) "
                f"TO '{datei}.alt' (FORMAT PARQUET)")
    con.close()
    Path(f"{datei}.alt").replace(datei)
    manifest = bsc.tabellenverzeichnis(tmp_path) / "manifest.json"
    m = json.loads(manifest.read_text(encoding="utf-8"))
    m["schema"].pop("jahrgang")
    manifest.write_text(json.dumps(m), encoding="utf-8")
    # Die Daten des aelteren Schnappschusses sind weg, sein Manifest nicht:
    # Der Bestand liesse sich nicht neu zaehlen, der Jahrgang schon lesen.
    (tmp_path / "bronze" / "city=detroit" / "run_a" / PARQUET_FILE).unlink()
    baue_in(tmp_path)
    paar = {(z["vorher_run_id"], z["bestand_vorher"], z["jahrgang"]) for z in gelesen(tmp_path)}
    assert paar == {("a", 2, 2022)}


def test_der_zusammenhang_klebt_wenn_die_laeufe_weg_sind(tmp_path):
    """Wie die Datierung: einmal bestimmt, bleibt er stehen."""
    import shutil

    schnappschuss(tmp_path, "a", [zeile("1"), zeile("2", offense_category="ARSON")],
                  wann="2026-09-11T12:00:00")
    schnappschuss(tmp_path, "b", [zeile("1")], wann="2026-09-12T12:00:00")
    baue_in(tmp_path)
    shutil.rmtree(tmp_path / "bronze" / "city=detroit" / "run_a")
    schnappschuss(tmp_path, "c", [zeile("1", case_status="CLOSED")],
                  wann="2026-09-13T12:00:00")
    baue_in(tmp_path)
    zeilen = gelesen(tmp_path)
    [weg] = [z for z in zeilen if z["art"] == "verschwunden"]
    assert weg["quellkategorie"] == "ARSON"
    assert {(z["vorher_run_id"], z["bestand_vorher"]) for z in zeilen} == {("a", 2), ("b", 1)}


def test_ein_bestand_aus_vertrag_3_bekommt_den_zusammenhang_nachgetragen(tmp_path):
    """Die Paare, die vor dem 8.11.2026 gezogen wurden, haben ihn nicht.

    Solange ihre Schnappschuesse da sind, wird er nachgetragen; das Paar
    selbst wird dabei nicht neu gezogen.
    """
    import duckdb

    schnappschuss(tmp_path, "a", [zeile("1"), zeile("2", offense_category="ARSON")],
                  wann="2026-09-11T12:00:00")
    schnappschuss(tmp_path, "b", [zeile("1")], wann="2026-09-12T12:00:00")
    baue_in(tmp_path)
    # Die Datei so ablegen, wie Vertrag 3 sie schrieb: ohne die vier Spalten.
    datei = bsc.tabellenverzeichnis(tmp_path) / PARQUET_FILE
    con = duckdb.connect()
    spalten = ", ".join(bsc.SPALTEN_ROH + bsc.SPALTEN_DATIERUNG)
    con.execute(f"COPY (SELECT {spalten} FROM read_parquet('{datei}')) "
                f"TO '{datei}.alt' (FORMAT PARQUET)")
    con.close()
    Path(f"{datei}.alt").replace(datei)
    manifest = bsc.tabellenverzeichnis(tmp_path) / "manifest.json"
    m = json.loads(manifest.read_text(encoding="utf-8"))
    m["contract_version"] = 3
    m["schema"] = {k: v for k, v in m["schema"].items() if k not in bsc.SPALTEN_KONTEXT}
    manifest.write_text(json.dumps(m), encoding="utf-8")

    bericht = baue_in(tmp_path)
    assert bericht["paare"] == 0, "das Paar wurde neu gezogen statt ergaenzt"
    assert bericht["kontext"] == {"paare": 1, "zeilen": 1, "nicht_bestimmbar": 0}
    [weg] = [z for z in gelesen(tmp_path) if z["art"] == "verschwunden"]
    assert (weg["quellkategorie"], weg["bestand_vorher"]) == ("ARSON", 2)


def test_ohne_schnappschuss_bleibt_der_zusammenhang_leer(tmp_path):
    """Nicht bestimmbar heisst leer - nicht geraten und kein Abbruch."""
    con = bsc.connect()
    con.execute("CREATE TABLE roh AS SELECT 'detroit' AS city, '1' AS offense_id, "
                "'x' AS vorher_run_id, 'y' AS run_id, 'verschwunden' AS art")
    con.execute("CREATE TABLE zeilen_kontext (city VARCHAR, offense_id VARCHAR, "
                "vorher_run_id VARCHAR, run_id VARCHAR, quellcode VARCHAR, "
                "quellkategorie VARCHAR)")
    con.execute("CREATE TABLE paar_kontext (city VARCHAR, vorher_run_id VARCHAR, "
                "run_id VARCHAR, bestand_vorher BIGINT, bestand_nachher BIGINT, "
                "jahrgang INTEGER)")
    from storage import for_root
    bericht = bsc.ergaenze_kontext(con, for_root(tmp_path), {})
    assert bericht == {"paare": 0, "zeilen": 0, "nicht_bestimmbar": 1}
    assert con.execute("SELECT count(*) FROM zeilen_kontext").fetchone()[0] == 0


# --------------------------------------------------------------------------
# Die Auskunft fuer das Aufraeumen
# --------------------------------------------------------------------------


def test_ohne_tabelle_bleibt_jeder_schnappschuss_gesperrt(tmp_path):
    schnappschuss(tmp_path, "a", [zeile("1")], wann="2026-09-11T12:00:00")
    schnappschuss(tmp_path, "b", [zeile("1")], wann="2026-09-12T12:00:00")
    assert bsc.ungezogene_laeufe(tmp_path) == {"a", "b"}


def test_nach_dem_ziehen_ist_keiner_mehr_gesperrt(tmp_path):
    schnappschuss(tmp_path, "a", [zeile("1")], wann="2026-09-11T12:00:00")
    schnappschuss(tmp_path, "b", [zeile("1", case_status="CLOSED")],
                  wann="2026-09-12T12:00:00")
    baue_in(tmp_path)
    assert bsc.ungezogene_laeufe(tmp_path) == set()


# --------------------------------------------------------------------------
# Die erzeugte Abfrage
# --------------------------------------------------------------------------


def test_ein_rauschfeld_steht_in_keinem_zweig():
    sql = bsc.vergleich_sql("a.parquet", "b.parquet",
                            ["incident_entry_id", "case_status", "ESRI_OID"],
                            DETROIT)
    assert "'case_status'" in sql
    assert "ESRI_OID" not in sql


def test_ein_fehlendes_schluesselfeld_bricht_ab():
    with pytest.raises(TransformError, match="Schluesselfeld"):
        bsc.vergleich_sql("a", "b", ["case_status"], DETROIT)


def test_eine_leere_stempelliste_erzeugt_gueltiges_sql():
    assert bsc._liste(frozenset()) == "''"
    assert bsc._liste(frozenset({"b", "a"})) == "'a', 'b'"


# --------------------------------------------------------------------------
# Gegen den gebauten Bestand
# --------------------------------------------------------------------------


@pytest.mark.referenzstand
def test_die_zahlen_des_papiers_werden_reproduziert():
    """``docs/intern/datenhistorie.md`` Abschnitt 1, Paar 11.9./12.9.

    Das Papier hat die Zahlen von Hand gemessen; dieses Modul misst sie noch
    einmal. Weichen sie ab, ist eines von beidem falsch.
    """
    duckdb = pytest.importorskip("duckdb")
    datei = Path("data/silver/dataset=source_change") / PARQUET_FILE
    if not datei.is_file():
        pytest.skip("Aenderungstabelle nicht gebaut")

    con = duckdb.connect()
    try:
        arten = dict(con.execute(f"""
            SELECT art, count(DISTINCT offense_id) FROM read_parquet('{datei}')
            WHERE vorher_run_id LIKE '1cca323d%' GROUP BY 1""").fetchall())
        felder = dict(con.execute(f"""
            SELECT feld, count(*) FROM read_parquet('{datei}')
            WHERE vorher_run_id LIKE '1cca323d%' AND feld IS NOT NULL
            GROUP BY 1""").fetchall())
    finally:
        con.close()
    if not arten:
        pytest.skip("das Paar vom 11./12.9. liegt nicht mehr vor")

    assert arten.get("geaendert") == 102, "Papier: 102 mit echter Inhaltsaenderung"
    assert arten.get("beruehrt") == 147, "Papier: 147 nur updated_at bewegt"
    for feld, erwartet in (("updated_at", 249), ("updated_in_ibr_at", 121),
                           ("case_status", 89), ("state_offense_code", 14),
                           ("offense_category", 1)):
        assert felder.get(feld) == erwartet, f"Papier nennt {erwartet} fuer {feld}"
    # 160 Aenderungen minus 150 reine Leerzeichen.
    assert felder.get("offense_description") == 10
    assert "ESRI_OID" not in felder, "88'677 Zeilen Rauschen"


# --------------------------------------------------------------------------
# Die Datierung aus den Deltas (Vertrag 2)
# --------------------------------------------------------------------------
#
# Gefunden wird eine Aenderung weiter nur zwischen zwei Vollabzuegen - aus
# einem Delta liesse sich *verschwunden* nicht von *ruhig* unterscheiden. Die
# Deltas tragen eine andere Aufgabe: Sie sagen, **wann** innerhalb des
# Fensters die Aenderung zuerst zu sehen war. Bei Monatsabstand macht das aus
# "irgendwann in dreissig Tagen" wenige Tage.


def nur_mit_schluessel(wurzel):
    """Die Zeilen, die datiert werden koennen - die Markierungszeile nicht."""
    return [z for z in gelesen(wurzel) if z["offense_id"] is not None]


def test_eine_aenderung_wird_auf_das_erste_delta_datiert(tmp_path):
    """Das erste, nicht das naechstgelegene: Es ist die obere Schranke."""
    schnappschuss(tmp_path, "f1", [zeile("1")], wann="2026-09-01T12:00:00")
    schnappschuss(tmp_path, "d1", [zeile("1", case_status="CLOSED")],
                  wann="2026-09-05T12:00:00", modus="DELTA")
    schnappschuss(tmp_path, "d2", [zeile("1", case_status="CLOSED")],
                  wann="2026-09-10T12:00:00", modus="DELTA")
    schnappschuss(tmp_path, "f2", [zeile("1", case_status="CLOSED")],
                  wann="2026-09-30T12:00:00")
    baue_in(tmp_path)
    zeilen = nur_mit_schluessel(tmp_path)
    assert zeilen, "keine datierbare Zeile gebaut"
    for z in zeilen:
        assert z["datierung"] == "delta"
        assert z["zuerst_gesehen_in"] == "d1", "nicht das erste Delta"
        assert str(z["zuerst_gesehen_am"]).startswith("2026-09-05")


def test_ein_delta_das_den_schluessel_nicht_traegt_ergibt_kein_delta(tmp_path):
    """Die Quelle hat die Aenderung nicht angemeldet - oder sie kam spaeter.

    Beides laesst sich von hier aus nicht trennen, und deshalb heisst der
    Zustand ``kein_delta`` und nicht *"nicht angemeldet"*.
    """
    schnappschuss(tmp_path, "f1", [zeile("1"), zeile("2")],
                  wann="2026-09-01T12:00:00")
    schnappschuss(tmp_path, "d1", [zeile("2")],
                  wann="2026-09-05T12:00:00", modus="DELTA")
    schnappschuss(tmp_path, "f2", [zeile("1", case_status="CLOSED"), zeile("2")],
                  wann="2026-09-30T12:00:00")
    baue_in(tmp_path)
    betroffen = [z for z in nur_mit_schluessel(tmp_path) if z["offense_id"] == "1"]
    assert betroffen, "die Aenderung an Zeile 1 fehlt"
    for z in betroffen:
        assert z["datierung"] == "kein_delta"
        assert z["zuerst_gesehen_in"] is None


def test_ohne_delta_im_fenster_ist_nichts_datierbar(tmp_path):
    """Keine Leerstelle: Eine Luecke im Vorrat ist kein Befund."""
    schnappschuss(tmp_path, "f1", [zeile("1")], wann="2026-09-01T12:00:00")
    schnappschuss(tmp_path, "f2", [zeile("1", case_status="CLOSED")],
                  wann="2026-09-30T12:00:00")
    baue_in(tmp_path)
    for z in nur_mit_schluessel(tmp_path):
        assert z["datierung"] == "nicht_datierbar"


def test_ein_delta_ausserhalb_des_fensters_zaehlt_nicht(tmp_path):
    """Sonst datierte ein spaeteres Delta eine frueher gefundene Aenderung."""
    schnappschuss(tmp_path, "f1", [zeile("1")], wann="2026-09-01T12:00:00")
    schnappschuss(tmp_path, "f2", [zeile("1", case_status="CLOSED")],
                  wann="2026-09-10T12:00:00")
    schnappschuss(tmp_path, "d1", [zeile("1", case_status="CLOSED")],
                  wann="2026-09-20T12:00:00", modus="DELTA")
    baue_in(tmp_path)
    for z in nur_mit_schluessel(tmp_path):
        assert z["datierung"] == "nicht_datierbar", (
            "ein Delta nach dem Fenster wurde mitgezaehlt")


def test_die_markierungszeile_bleibt_undatiert(tmp_path):
    """Sie traegt keinen Schluessel - es gibt nichts zu datieren."""
    schnappschuss(tmp_path, "f1", [zeile("1")], wann="2026-09-01T12:00:00")
    schnappschuss(tmp_path, "f2", [zeile("1")], wann="2026-09-30T12:00:00")
    baue_in(tmp_path)
    zeilen = gelesen(tmp_path)
    assert [z["art"] for z in zeilen] == ["unveraendert"]
    assert zeilen[0]["datierung"] is None
    assert zeilen[0]["zuerst_gesehen_in"] is None


def test_die_datierung_wird_nachgerechnet_wenn_sie_besser_wird(tmp_path):
    """Nach oben offen: Ein Delta, das dazukommt, datiert nachtraeglich.

    Ohne diese Eigenschaft waeren die bereits gezogenen Paare fuer immer
    undatiert, und der Vertrag haette nur fuer kuenftige Paare einen Wert.
    """
    schnappschuss(tmp_path, "f1", [zeile("1")], wann="2026-09-01T12:00:00")
    schnappschuss(tmp_path, "f2", [zeile("1", case_status="CLOSED")],
                  wann="2026-09-30T12:00:00")
    erst = baue_in(tmp_path)
    assert {z["datierung"] for z in nur_mit_schluessel(tmp_path)} == {"nicht_datierbar"}

    schnappschuss(tmp_path, "d1", [zeile("1", case_status="CLOSED")],
                  wann="2026-09-05T12:00:00", modus="DELTA")
    zweit = baue_in(tmp_path)
    assert zweit["paare"] == 0, "es kam kein neues Paar dazu"
    assert zweit["row_count"] == erst["row_count"], "die Tatsachen bewegten sich"
    for z in nur_mit_schluessel(tmp_path):
        assert z["datierung"] == "delta", "die Datierung wurde nicht nachgerechnet"
        assert z["zuerst_gesehen_in"] == "d1"


def test_die_datierung_verblasst_nicht_wenn_die_deltas_weg_sind(tmp_path):
    """Der Grund, warum die Datierung klebt - und warum Aufraeumen geht.

    Der erste Entwurf rechnete bei jedem Bau frisch. Loeschte man die Deltas,
    wurde aus ``delta`` wieder ``nicht_datierbar``: Die Aenderungszeile blieb,
    ihre Datierung war weg. Das ist genau das, wogegen diese Tabelle gebaut
    ist - den Unterschied herausziehen, **bevor** der Rohstoff entbehrlich
    wird. Aufraeumen ist ein Ziel, nicht ein Unfall; eine Spalte, die daran
    zerbricht, verhindert es.
    """
    import shutil

    schnappschuss(tmp_path, "f1", [zeile("1")], wann="2026-09-01T12:00:00")
    schnappschuss(tmp_path, "d1", [zeile("1", case_status="CLOSED")],
                  wann="2026-09-05T12:00:00", modus="DELTA")
    schnappschuss(tmp_path, "f2", [zeile("1", case_status="CLOSED")],
                  wann="2026-09-30T12:00:00")
    erst = baue_in(tmp_path)
    vorher = [(z["datierung"], z["zuerst_gesehen_in"], z["zuerst_gesehen_am"])
              for z in nur_mit_schluessel(tmp_path)]
    assert vorher and all(d == "delta" for d, _, _ in vorher)

    shutil.rmtree(tmp_path / "bronze" / "city=detroit" / "run_d1")
    zweit = baue_in(tmp_path)

    assert zweit["row_count"] == erst["row_count"], "der Bestand ging verloren"
    nachher = [(z["datierung"], z["zuerst_gesehen_in"], z["zuerst_gesehen_am"])
               for z in nur_mit_schluessel(tmp_path)]
    assert nachher == vorher, (
        "die Datierung ist mit dem Delta verschwunden - sie soll kleben")


def test_eine_bessere_datierung_verdraengt_eine_schlechtere(tmp_path):
    """Die Rangfolge, an einem Fall: nicht_datierbar -> delta, nie zurueck."""
    schnappschuss(tmp_path, "f1", [zeile("1"), zeile("2")],
                  wann="2026-09-01T12:00:00")
    schnappschuss(tmp_path, "d1", [zeile("2")],
                  wann="2026-09-05T12:00:00", modus="DELTA")
    schnappschuss(tmp_path, "f2",
                  [zeile("1", case_status="CLOSED"), zeile("2", case_status="CLOSED")],
                  wann="2026-09-30T12:00:00")
    baue_in(tmp_path)
    erst = {z["offense_id"]: z["datierung"] for z in nur_mit_schluessel(tmp_path)}
    assert erst["1"] == "kein_delta", "Zeile 1 stand in keinem Delta"
    assert erst["2"] == "delta"

    # Ein Delta, das nun auch Zeile 1 traegt - die schlechtere Auskunft weicht.
    schnappschuss(tmp_path, "d2", [zeile("1"), zeile("2")],
                  wann="2026-09-20T12:00:00", modus="DELTA")
    baue_in(tmp_path)
    zweit = {z["offense_id"]: z["datierung"] for z in nur_mit_schluessel(tmp_path)}
    assert zweit["1"] == "delta", "die bessere Datierung kam nicht durch"
    assert zweit["2"] == "delta"
    bleibt = {z["offense_id"]: z["zuerst_gesehen_in"]
              for z in nur_mit_schluessel(tmp_path)}
    assert bleibt["2"] == "d1", "das erste Delta wurde durch ein spaeteres ersetzt"


def test_die_tabelle_wird_auch_hinaufgebracht(tmp_path, monkeypatch):
    """Jeder andere Silver-Bau ruft ``publish_table`` - dieser tat es nicht.

    Bis zum 17.10.2026 schrieb ``baue`` die Tabelle nur lokal. Im ``s3``-Modus
    erreichte sie SeaweedFS damit nie: Oben lag der Stand vom 3.10.2026,
    eingefroren, waehrend jeder Lauf unten eine neue Fassung baute und wieder
    verlor. Gesehen wurde es erst, als das Aufraeumen nach dem Release die
    lokale Kopie entfernte - 21,4 Mio. Zeilen gebaut, nie publiziert, dann
    geloescht.

    Geprueft wird, **dass** publiziert wird, nicht wohin: Ein echtes S3
    braeuchte Netz, und der Fehler lag nicht im Hochladen, sondern im
    fehlenden Aufruf.
    """
    gesehen = []

    class Spion:
        def __init__(self, echt):
            self._echt = echt

        def publish_table(self, ziel, **kw):
            gesehen.append(str(ziel))
            return []

        def __getattr__(self, name):
            return getattr(self._echt, name)

    echt = bsc.for_root
    monkeypatch.setattr(bsc, "for_root", lambda wurzel: Spion(echt(wurzel)))

    schnappschuss(tmp_path, "a", [zeile("1")], wann="2026-09-11T12:00:00")
    schnappschuss(tmp_path, "b", [zeile("1", offense_description="X")],
                  wann="2026-09-12T12:00:00")
    bsc.baue(tmp_path)

    assert gesehen, (
        "publish_table wurde nicht gerufen - im s3-Modus bleibt die Tabelle "
        "unten und der Stand oben friert ein")
    assert any("source_change" in z for z in gesehen), \
        f"publiziert wurde etwas anderes: {gesehen}"


# --------------------------------------------------------------------------
# Das Bestehende kommt dazu, auch wenn es nur oben liegt
# --------------------------------------------------------------------------


def test_das_bestehende_bleibt_ueber_laeufe_hinweg_stehen(tmp_path):
    """Die Zusage, auf der das ganze Aufraeumen ruht - funktional geprueft.

    ``bereits_gezogen`` sagt: *"Ist ein Lauf aufgeraeumt, laesst sich sein
    Vergleich nicht wiederherstellen - was einmal herausgezogen wurde, bleibt
    deshalb stehen."*
    """
    schnappschuss(tmp_path, "a", [zeile("1")], wann="2026-09-11T12:00:00")
    schnappschuss(tmp_path, "b", [zeile("1", offense_description="X")],
                  wann="2026-09-12T12:00:00")
    assert bsc.baue(tmp_path)["paare"] == 1

    schnappschuss(tmp_path, "c", [zeile("1", offense_description="Y")],
                  wann="2026-09-13T12:00:00")
    zweiter = bsc.baue(tmp_path)

    assert zweiter["paare"] == 1, "nur das neue Paar ist zu ziehen"
    assert zweiter["uebersprungen"] == 1, "das alte gilt als schon gezogen"
    paare = {(z["vorher_run_id"], z["run_id"]) for z in gelesen(tmp_path)}
    assert len(paare) == 2, (
        f"nach dem zweiten Lauf stehen {len(paare)} Paare in der Tabelle - "
        f"das Bestehende ist weggefallen")


def test_das_bestehende_wird_dort_gelesen_wo_die_ablage_es_nennt(tmp_path,
                                                                 monkeypatch):
    """Die andere Haelfte, und die, die im ``s3``-Modus brach.

    Bis zum 17.10.2026 suchte der Bau das Bestehende ueber ``alt.is_file()`` -
    also lokal. Im ``s3``-Modus ist die Arbeitskopie nach dem Publizieren
    entfernt, die Antwort war immer "es gibt nichts", und jeder Lauf schrieb
    nur, was er selbst gezogen hatte. **29 Paare und 39'650 Zeilen wurden zu
    7 Paaren und 23'078**; die Vergleiche, deren Schnappschuesse der
    Aufraeumlauf danach entfernte, sind endgueltig weg.

    **Ein echter Ferntest ginge nicht** - DuckDB liest die Parquet-Datei
    selbst, und ``FakeS3Client`` ist ein dict, das DuckDB nicht bedienen kann.
    Pruefbar ist dafuer der Unterschied, der im ``s3``-Modus zaehlt: Die
    abgelegte Datei liegt **nicht** am lokalen Tabellenpfad, sondern dort, wo
    die Ablage sie nennt. Wer das Dateisystem fragt, findet nichts; wer die
    Ablage fragt, findet sie. Ein erster Entwurf dieses Tests sah nur zu, ob
    ``exists`` gerufen wird - das tut ``bereits_gezogen`` auch, und die
    Mutationsprobe blieb gruen.
    """
    from storage import Storage

    schnappschuss(tmp_path, "a", [zeile("1")], wann="2026-09-11T12:00:00")
    schnappschuss(tmp_path, "b", [zeile("1", offense_description="X")],
                  wann="2026-09-12T12:00:00")
    assert bsc.baue(tmp_path)["paare"] == 1

    # Die abgelegte Tabelle woanders hin - lokal liegt dann nichts mehr,
    # genau wie nach ``publish_table`` im ``s3``-Modus.
    tabelle = bsc.tabellenverzeichnis(tmp_path)
    woanders = tmp_path / "woanders"
    woanders.mkdir()
    (tabelle / PARQUET_FILE).rename(woanders / PARQUET_FILE)
    (tabelle / "manifest.json").rename(woanders / "manifest.json")

    rel_tabelle = f"silver/dataset={bsc.TABLE}"
    echt_exists, echt_pfad = Storage.exists, Storage.resolve_read_path

    def exists(self, *teile):
        if teile and str(teile[0]).endswith(f"dataset={bsc.TABLE}"):
            return (woanders / str(teile[-1])).is_file()
        return echt_exists(self, *teile)

    def pfad(self, *teile):
        if teile and str(teile[0]).endswith(f"dataset={bsc.TABLE}"):
            return str(woanders / str(teile[-1]))
        return echt_pfad(self, *teile)

    monkeypatch.setattr(Storage, "exists", exists)
    monkeypatch.setattr(Storage, "resolve_read_path", pfad)
    monkeypatch.setattr(Storage, "tabellen_manifest",
                        lambda self, ziel: json.loads(
                            (woanders / "manifest.json").read_text(encoding="utf-8")))

    schnappschuss(tmp_path, "c", [zeile("1", offense_description="Y")],
                  wann="2026-09-13T12:00:00")
    zweiter = bsc.baue(tmp_path)

    assert zweiter["uebersprungen"] == 1, (
        "das alte Paar wurde nicht erkannt - die Ablage wird nicht gefragt")
    paare = {(z["vorher_run_id"], z["run_id"]) for z in gelesen(tmp_path)}
    assert len(paare) == 2, (
        f"nach dem zweiten Lauf stehen {len(paare)} Paare in der Tabelle. Das "
        f"Bestehende lag nicht am lokalen Pfad, sondern dort, wo die Ablage "
        f"es nennt - wer das Dateisystem fragt, verliert es. (rel war "
        f"{rel_tabelle})")
