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
         relativ: str = "", stadt: str = "detroit") -> Lauf:
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
    return Lauf(Path(f"/gibt-es-nicht/{run_id}"), manifest,
                relativ or f"bronze/city={stadt}/run_{run_id}")


def schnappschuss(wurzel: Path, run_id: str, zeilen: list[dict], *,
                  wann: str, modus: str = "FULL") -> None:
    """Ein Bronze-Lauf, wie ihn die Detroit-Ingestion ablegt.

    ``attributes`` ist ein Struct - genau wie in der echten Datei, denn an
    dessen Feldern entscheidet sich der ganze Vergleich.
    """
    import duckdb

    verzeichnis = wurzel / "bronze" / "city=detroit" / f"run_{run_id}"
    verzeichnis.mkdir(parents=True, exist_ok=True)

    felder = ["incident_entry_id", "offense_description", "state_offense_code",
              "case_status", "updated_at", "ESRI_OID"]
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
    }), encoding="utf-8")


def zeile(ident: str, **rest) -> dict:
    grund = {"incident_entry_id": ident, "offense_description": "ASSAULT",
             "state_offense_code": "1300", "case_status": "OPEN",
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


def test_die_datierung_wird_bei_jedem_bau_neu_gerechnet(tmp_path):
    """Sie ist eine Annotation, keine Tatsache des Paares.

    Das ist der Unterschied zu den uebrigen Spalten: Was einmal
    herausgezogen wurde, bleibt stehen - aber die Datierung darf besser
    werden, sobald ein Delta dazukommt. Ohne diese Eigenschaft waeren die
    bereits gezogenen Paare fuer immer undatiert, und Vertrag 2 haette nur
    fuer kuenftige Paare einen Wert.
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
