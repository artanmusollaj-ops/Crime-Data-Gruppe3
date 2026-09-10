"""Tests fuer die MICR-NIBRS-Zuordnung.

Die Tabelle ist keine Ableitung aus Code, sondern gepflegte Referenz. Geprueft
wird deshalb ihre Form und ihre Herkunft, nicht ein Algorithmus: dass jede Zeile
eindeutig ist, dass zugeordnete Zeilen einen NIBRS-Code tragen und nicht
zugeordnete keinen, und dass die Herkunft jeder Zeile aus einer festen Menge
stammt.

Die Pruefungen gegen die echten Detroit-Daten ueberspringen sich selbst, wenn
kein Bronze-Lauf vorliegt - ``data/`` ist nicht versioniert.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAPPING = PROJECT_ROOT / "config" / "micr_nibrs_mapping.csv"
# Original: michigan.gov/.../micr-assets/2009/diappf.pdf, hier sprechend
# benannt. Liegt im Repository, weil michigan.gov automatisierte Abrufe
# mit HTTP 403 beantwortet.
QUELLEN = {
    "micr_manual_1110_2024": PROJECT_ROOT / "docs" / "micr_manual_1110_2024.pdf",
    "appendix_f_2009": PROJECT_ROOT / "docs" / "micr_appendix_f_2009.pdf",
}

SPALTEN = [
    "micr_code",
    "micr_file_class",
    "micr_description",
    "nibrs_group",
    "nibrs_code",
    "nibrs_description",
    "hierarchy",
    "match",
    "mapped",
    "seen_in_detroit_2024",
    "note",
]

# Jede Zeile muss sagen, woher sie kommt. Ein leerer Wert heisst: keine
# Zuordnung, und dann muss auch kein NIBRS-Code dastehen.
HERKUNFT = {"micr_manual_1110_2024", "appendix_f_2009", ""}


@pytest.fixture(scope="module")
def zeilen() -> list[dict[str, str]]:
    with MAPPING.open(encoding="utf-8") as datei:
        return list(csv.DictReader(datei))


# --------------------------------------------------------------------------
# Form
# --------------------------------------------------------------------------


def test_tabelle_existiert():
    assert MAPPING.exists(), f"{MAPPING} fehlt"


def test_spalten_wie_vereinbart(zeilen):
    assert list(zeilen[0]) == SPALTEN


def test_micr_code_ist_eindeutig(zeilen):
    codes = [z["micr_code"] for z in zeilen]
    doppelt = {c for c in codes if codes.count(c) > 1}
    assert not doppelt, f"mehrfach vorhanden: {sorted(doppelt)}"


def test_micr_code_ist_vierstellig(zeilen):
    falsch = [z["micr_code"] for z in zeilen
              if not (len(z["micr_code"]) == 4 and z["micr_code"].isdigit())]
    assert not falsch, f"kein vierstelliger Code: {falsch}"


def test_file_class_passt_zum_micr_code(zeilen):
    """Appendix F fuehrt fuenfstellig NN00M, Detroit vierstellig NN0M."""
    falsch = [
        (z["micr_code"], z["micr_file_class"])
        for z in zeilen
        if z["micr_file_class"]
        and z["micr_file_class"][:2] + z["micr_file_class"][3:5] != z["micr_code"]
    ]
    assert not falsch, f"Code und File Class passen nicht: {falsch}"


# --------------------------------------------------------------------------
# Herkunft
# --------------------------------------------------------------------------


def test_herkunft_stammt_aus_fester_menge(zeilen):
    """Wie beim IUCR-Mapping haelt eine Spalte fest, woher die Zeile kommt."""
    unbekannt = {z["match"] for z in zeilen} - HERKUNFT
    assert not unbekannt, f"unbekannte Herkunft: {unbekannt}"


@pytest.mark.parametrize("herkunft", sorted(QUELLEN))
def test_quelldokument_liegt_im_repository(herkunft):
    """Die Herkunft muss nachlesbar sein, nicht nur behauptet.

    michigan.gov beantwortet automatisierte Abrufe mit HTTP 403; deshalb liegen
    die Dokumente im Repository statt nur als Verweis.
    """
    pfad = QUELLEN[herkunft]
    assert pfad.exists(), f"{pfad} fehlt - ohne Quelle ist die Tabelle unbelegt"
    assert pfad.stat().st_size > 10_000


def test_jede_genutzte_herkunft_hat_ein_dokument(zeilen):
    genutzt = {z["match"] for z in zeilen if z["match"]}
    ohne_beleg = genutzt - set(QUELLEN)
    assert not ohne_beleg, f"Herkunft ohne hinterlegtes Dokument: {ohne_beleg}"


def test_zugeordnete_zeilen_sind_vollstaendig(zeilen):
    unvollstaendig = [
        z["micr_code"] for z in zeilen
        if z["mapped"] == "true"
        and not (z["nibrs_code"] and z["nibrs_description"]
                 and z["nibrs_group"] in {"A", "B"} and z["match"])
    ]
    assert not unvollstaendig, f"als zugeordnet markiert, aber unvollstaendig: {unvollstaendig}"


def test_nicht_zugeordnete_zeilen_behaupten_nichts(zeilen):
    """Wichtiger als die Zuordnung: dass eine fehlende nicht erfunden wird."""
    erfunden = [
        z["micr_code"] for z in zeilen
        if z["mapped"] == "false"
        and (z["nibrs_code"] or z["nibrs_description"] or z["nibrs_group"])
    ]
    assert not erfunden, f"ohne Zuordnung, aber mit NIBRS-Angabe: {erfunden}"


def test_nicht_zugeordnete_zeilen_nennen_den_grund(zeilen):
    ohne_grund = [z["micr_code"] for z in zeilen
                  if z["mapped"] == "false" and not z["note"].strip()]
    assert not ohne_grund, f"ohne Zuordnung und ohne Begruendung: {ohne_grund}"


def test_mapped_ist_ein_wahrheitswert(zeilen):
    falsch = {z["mapped"] for z in zeilen} - {"true", "false"}
    assert not falsch, falsch


# --------------------------------------------------------------------------
# Inhalt, stichprobenweise gegen Appendix F
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code,file_class,nibrs_code,nibrs_description",
    [
        ("0901", "09001", "09A", "Murder and Non-Negligent Manslaughter"),
        ("0904", "09004", "09C", "Justifiable Homicide"),
        # Bezeichnungen nach der Fassung 2024: aus "Forcible Rape" wurde
        # "Rape", aus "Forcible Fondling" wurde "Fondling".
        ("1101", "11001", "11A", "Rape"),
        ("1107", "11007", "11D", "Fondling"),
        ("1200", "12000", "120", "Robbery"),
        ("1301", "13001", "13B", "Simple Assault"),
        ("1302", "13002", "13A", "Aggravated Assault"),
        ("1303", "13003", "13C", "Intimidation"),
        ("2000", "20000", "200", "Arson"),
    ],
)
def test_stichproben_gegen_appendix_f(zeilen, code, file_class, nibrs_code,
                                      nibrs_description):
    """Handverlesene Zeilen, direkt aus der PDF abgelesen."""
    zeile = next(z for z in zeilen if z["micr_code"] == code)
    assert zeile["micr_file_class"] == file_class
    assert zeile["nibrs_code"] == nibrs_code
    assert zeile["nibrs_description"] == nibrs_description


def test_gruppe_b_liegt_im_90er_namensraum(zeilen):
    """NIBRS fuehrt die Group-B-Delikte als 90A bis 90J, plus 90Z als Rest.

    Eine erste Fassung dieses Tests forderte 90Z fuer alle Group-B-Zeilen. Das
    war falsch: Appendix F vergibt fuer die zehn benannten Group-B-Delikte
    eigene Codes und nutzt 90Z nur als Sammelposten.
    """
    gruppe_b = [z for z in zeilen if z["nibrs_group"] == "B"]
    assert gruppe_b, "keine Group-B-Zeilen gefunden"
    abweichend = [z["micr_code"] for z in gruppe_b
                  if not z["nibrs_code"].startswith("90")]
    assert not abweichend, f"Group B ausserhalb des 90er-Namensraums: {abweichend}"


def test_gruppe_a_liegt_ausserhalb_des_90er_namensraums(zeilen):
    """Die Gegenprobe - sonst wuerde der Test oben auch alles durchlassen."""
    gruppe_a = [z for z in zeilen if z["nibrs_group"] == "A"]
    assert gruppe_a, "keine Group-A-Zeilen gefunden"
    abweichend = [z["micr_code"] for z in gruppe_a
                  if z["nibrs_code"].startswith("90")]
    assert not abweichend, f"Group A im 90er-Namensraum: {abweichend}"


# --------------------------------------------------------------------------
# Abdeckung der echten Daten, wenn vorhanden
# --------------------------------------------------------------------------


def detroit_codes() -> dict[str, int] | None:
    """Die MICR-Codes des juengsten Detroit-Bronze-Laufs, oder None."""
    treffer = sorted((PROJECT_ROOT / "data" / "bronze" / "detroit").glob("*.ndjson")) \
        if (PROJECT_ROOT / "data" / "bronze" / "detroit").exists() else []
    if not treffer:
        return None
    duckdb = pytest.importorskip("duckdb")
    con = duckdb.connect()
    try:
        return {
            code: anzahl
            for code, anzahl in con.execute(f"""
                SELECT attributes.state_offense_code, count(*)
                FROM read_json_auto('{treffer[-1]}')
                WHERE attributes.state_offense_code IS NOT NULL
                GROUP BY 1
            """).fetchall()
        }
    finally:
        con.close()


def test_jeder_code_der_daten_steht_in_der_tabelle(zeilen):
    """Ein unbekannter Code darf nicht stillschweigend durchfallen."""
    daten = detroit_codes()
    if daten is None:
        pytest.skip("kein Detroit-Bronze-Lauf vorhanden")
    bekannt = {z["micr_code"] for z in zeilen}
    fehlend = sorted(set(daten) - bekannt)
    assert not fehlend, f"in den Daten, aber nicht in der Tabelle: {fehlend}"


def test_abdeckung_der_faelle_ist_ausgewiesen(zeilen):
    """Die Tabelle deckt nicht alles ab - die Luecke muss messbar bleiben."""
    daten = detroit_codes()
    if daten is None:
        pytest.skip("kein Detroit-Bronze-Lauf vorhanden")
    zugeordnet = {z["micr_code"] for z in zeilen if z["mapped"] == "true"}
    gesamt = sum(daten.values())
    gedeckt = sum(n for code, n in daten.items() if code in zugeordnet)
    anteil = gedeckt / gesamt
    # Die Fassung von 2009 kennt spaetere Ergaenzungen nicht; ein Einbrechen
    # dieser Quote waere aber ein Zeichen, dass etwas anderes kaputt ist.
    assert anteil > 0.90, f"nur {anteil:.1%} der Faelle zugeordnet"


def test_seen_in_detroit_stimmt_mit_den_daten(zeilen):
    daten = detroit_codes()
    if daten is None:
        pytest.skip("kein Detroit-Bronze-Lauf vorhanden")
    behauptet = {z["micr_code"] for z in zeilen if z["seen_in_detroit_2024"] == "true"}
    assert behauptet == set(daten), (
        f"nur in der Tabelle: {sorted(behauptet - set(daten))}, "
        f"nur in den Daten: {sorted(set(daten) - behauptet)}"
    )
