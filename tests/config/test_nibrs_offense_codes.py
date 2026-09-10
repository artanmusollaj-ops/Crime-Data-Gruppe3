"""Tests fuer die amtliche NIBRS-Codeliste und die beiden Crosswalks.

``config/nibrs_offense_codes_2025.csv`` ist der gemeinsame Nenner des
Staedtevergleichs: Detroit kommt ueber MICR dorthin, Chicago ueber I-UCR. Solange
niemand prueft, ob die Zielcodes ueberhaupt existieren, kann ein Tippfehler oder
ein zurueckgezogener Code unbemerkt durch beide Crosswalks laufen.

Geprueft wird deshalb dreierlei: die Form der Codeliste, ihre Herkunft aus dem
hinterlegten Dokument, und dass jeder Zielcode der beiden Crosswalks in dieser
Liste steht - oder die Zeile ausdruecklich sagt, warum nicht.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CODELISTE = PROJECT_ROOT / "config" / "nibrs_offense_codes_2025.csv"
MICR_MAPPING = PROJECT_ROOT / "config" / "micr_nibrs_mapping.csv"
IUCR_MAPPING = PROJECT_ROOT / "config" / "iucr_nibrs_mapping.csv"

# Original: le.fbi.gov, "2025.0 NIBRS Technical Specification", Anhang A.
# Liegt wie die MICR-Dokumente im Repository, damit die Herkunft nachlesbar
# bleibt und nicht von einer erreichbaren Webseite abhaengt.
SPEZIFIKATION = PROJECT_ROOT / "docs" / "nibrs_technical_specification_2025.pdf"
# Original: isp.illinois.gov/CrimeReporting/NIBRS, "NIBRS Code Table".
ISP_TABELLE = PROJECT_ROOT / "docs" / "isp_nibrs_code_table_2026.xlsx"

SPALTEN = [
    "nibrs_code",
    "nibrs_description",
    "nibrs_group",
    "crime_against",
    "federal_only",
    "source",
]

QUELLE = "nibrs_technical_specification_2025"
GEGEN = {"Person", "Property", "Society", "Not a Crime", "Person, Property, or Society"}

# Anhang A.2 fuehrt zehn Group-B-Delikte; alles andere ist Group A.
GRUPPE_B = {"90B", "90C", "90D", "90F", "90G", "90J", "90K", "90L", "90M", "90Z"}

# Codes, die frueher galten und in der Fassung 2025 fehlen. Die MICR-Quellen
# von 2009 und 2024 kennen sie noch, deshalb stehen sie im Crosswalk - aber
# jede solche Zeile muss den Grund nennen.
ZURUECKGEZOGEN = {"90A", "90E", "90H", "90I"}


@pytest.fixture(scope="module")
def codeliste() -> list[dict[str, str]]:
    with CODELISTE.open(encoding="utf-8") as datei:
        return list(csv.DictReader(datei))


@pytest.fixture(scope="module")
def codes(codeliste) -> set[str]:
    return {z["nibrs_code"] for z in codeliste}


def _zeilen(pfad: Path) -> list[dict[str, str]]:
    with pfad.open(encoding="utf-8") as datei:
        return list(csv.DictReader(datei))


# --------------------------------------------------------------------------
# Form der Codeliste
# --------------------------------------------------------------------------


def test_codeliste_existiert():
    assert CODELISTE.exists(), f"{CODELISTE} fehlt"


def test_spalten_wie_vereinbart(codeliste):
    assert list(codeliste[0]) == SPALTEN


def test_code_ist_eindeutig(codeliste):
    alle = [z["nibrs_code"] for z in codeliste]
    doppelt = {c for c in alle if alle.count(c) > 1}
    assert not doppelt, f"mehrfach vorhanden: {sorted(doppelt)}"


def test_code_hat_die_nibrs_form(codeliste):
    """Dreistellig numerisch oder zwei Ziffern plus Buchstabe, nichts sonst."""
    falsch = [
        z["nibrs_code"] for z in codeliste
        if not (
            (len(z["nibrs_code"]) == 3 and z["nibrs_code"].isdigit())
            or (len(z["nibrs_code"]) == 3
                and z["nibrs_code"][:2].isdigit()
                and z["nibrs_code"][2].isupper())
        )
    ]
    assert not falsch, f"keine NIBRS-Codeform: {falsch}"


def test_jede_zeile_hat_eine_bezeichnung(codeliste):
    ohne = [z["nibrs_code"] for z in codeliste if not z["nibrs_description"].strip()]
    assert not ohne, f"ohne Bezeichnung: {ohne}"


def test_bezeichnung_traegt_keine_fussnote(codeliste):
    """Der Stern im PDF markiert die Bundesmeldung - er gehoert in die eigene
    Spalte, nicht in den Text."""
    mit_stern = [z["nibrs_code"] for z in codeliste if "*" in z["nibrs_description"]]
    assert not mit_stern, f"Stern in der Bezeichnung: {mit_stern}"


def test_gruppe_passt_zum_namensraum(codeliste):
    """Group B liegt im 90er-Namensraum, Group A ausserhalb - beide Richtungen."""
    falsch = [
        (z["nibrs_code"], z["nibrs_group"]) for z in codeliste
        if z["nibrs_group"] != ("B" if z["nibrs_code"] in GRUPPE_B else "A")
    ]
    assert not falsch, f"Gruppe passt nicht zum Code: {falsch}"


def test_group_b_ist_vollstaendig(codeliste):
    gefunden = {z["nibrs_code"] for z in codeliste if z["nibrs_group"] == "B"}
    assert gefunden == GRUPPE_B, (
        f"fehlt: {sorted(GRUPPE_B - gefunden)}, zuviel: {sorted(gefunden - GRUPPE_B)}"
    )


def test_crime_against_stammt_aus_fester_menge(codeliste):
    unbekannt = {z["crime_against"] for z in codeliste} - GEGEN
    assert not unbekannt, f"unbekannter Wert: {unbekannt}"


def test_federal_only_ist_ein_wahrheitswert(codeliste):
    falsch = {z["federal_only"] for z in codeliste} - {"true", "false"}
    assert not falsch, falsch


def test_herkunft_ist_einheitlich(codeliste):
    fremd = {z["source"] for z in codeliste} - {QUELLE}
    assert not fremd, f"fremde Herkunft: {fremd}"


# --------------------------------------------------------------------------
# Herkunft und Inhalt, gegen die Spezifikation
# --------------------------------------------------------------------------


def test_quelldokument_liegt_im_repository():
    assert SPEZIFIKATION.exists(), (
        f"{SPEZIFIKATION} fehlt - ohne Quelle ist die Codeliste unbelegt"
    )
    assert SPEZIFIKATION.stat().st_size > 100_000


@pytest.mark.parametrize(
    "code,bezeichnung,gruppe,gegen",
    [
        # Handverlesen aus Anhang A. Absichtlich auch die Faelle, bei denen die
        # Fassung 2025 von der aelteren Benennung abweicht.
        ("09A", "Murder and Nonnegligent Manslaughter", "A", "Person"),
        ("09C", "Justifiable Homicide", "A", "Not a Crime"),
        # Aus "Forcible Fondling" wurde "Criminal Sexual Contact".
        ("11D", "Criminal Sexual Contact", "A", "Person"),
        ("120", "Robbery", "A", "Property"),
        ("13A", "Aggravated Assault", "A", "Person"),
        ("200", "Arson", "A", "Property"),
        ("23G", "Theft of Motor Vehicle Parts or Accessories", "A", "Property"),
        ("26A", "False Pretenses/Swindle/Confidence Game", "A", "Property"),
        ("290", "Destruction/Damage/Vandalism of Property", "A", "Property"),
        ("90Z", "All Other Offenses", "B", "Person, Property, or Society"),
    ],
)
def test_stichproben_gegen_anhang_a(codeliste, code, bezeichnung, gruppe, gegen):
    zeile = next(z for z in codeliste if z["nibrs_code"] == code)
    assert zeile["nibrs_description"] == bezeichnung
    assert zeile["nibrs_group"] == gruppe
    assert zeile["crime_against"] == gegen


def test_bundesdelikte_sind_als_solche_erkennbar(codeliste):
    """Anhang A markiert Delikte, die nur Bundes- und Stammesbehoerden melden.

    Fuer den Staedtevergleich sind sie unerheblich - aber sie muessen
    unterscheidbar bleiben, damit niemand ihr Fehlen fuer einen Datenverlust
    haelt.
    """
    bund = {z["nibrs_code"] for z in codeliste if z["federal_only"] == "true"}
    assert {"101", "103", "30A", "49A", "58A", "90K"} <= bund
    # Gegenprobe: die grossen Alltagsdelikte duerfen nicht darunter fallen.
    assert not bund & {"09A", "120", "13A", "220", "240", "35A", "90Z"}


# --------------------------------------------------------------------------
# Die beiden Crosswalks zeigen auf existierende Codes
# --------------------------------------------------------------------------


def test_chicago_zeigt_nur_auf_gueltige_codes(codes):
    """Chicago geht ueber I-UCR nach NIBRS - ohne Ausnahmen."""
    zeilen = _zeilen(IUCR_MAPPING)
    unbekannt = sorted({z["ibr_code"] for z in zeilen if z["ibr_code"]} - codes)
    assert not unbekannt, f"IBR-Code ausserhalb der Spezifikation 2025: {unbekannt}"


def test_detroit_zeigt_nur_auf_gueltige_oder_erklaerte_codes(codes):
    """Detroit geht ueber MICR nach NIBRS.

    Die MICR-Quellen von 2009 und 2024 kennen vier Codes, die das FBI inzwischen
    zurueckgezogen hat. Die duerfen stehen bleiben - die Zeile muss es aber
    sagen, sonst wird aus einem veralteten Code stillschweigend ein gueltiger.
    """
    zeilen = _zeilen(MICR_MAPPING)
    unbekannt = sorted({z["nibrs_code"] for z in zeilen if z["nibrs_code"]} - codes)
    assert set(unbekannt) <= ZURUECKGEZOGEN, (
        f"NIBRS-Code weder gueltig noch als zurueckgezogen bekannt: "
        f"{sorted(set(unbekannt) - ZURUECKGEZOGEN)}"
    )


def test_zurueckgezogene_codes_nennen_den_grund(codes):
    betroffen = [z for z in _zeilen(MICR_MAPPING) if z["nibrs_code"] in ZURUECKGEZOGEN]
    assert betroffen, "keine Zeile mit zurueckgezogenem Code gefunden"
    stumm = [z["micr_code"] for z in betroffen
             if "zurueckgezogen" not in z["note"].lower()]
    assert not stumm, f"zurueckgezogener Code ohne Begruendung: {stumm}"


def test_zurueckgezogene_codes_sind_wirklich_zurueckgezogen(codes):
    """Gegenprobe: sonst haelt der Test oben auch dann, wenn die Liste waechst."""
    versehentlich = sorted(ZURUECKGEZOGEN & codes)
    assert not versehentlich, (
        f"als zurueckgezogen gefuehrt, steht aber in der Spezifikation: {versehentlich}"
    )


# --------------------------------------------------------------------------
# Chicago gegen die Codetabelle der Illinois State Police
# --------------------------------------------------------------------------

# Die ISP-Tabelle ist nach ILCS-Statut geschluesselt, nicht nach Chicagos
# IUCR-Katalog. Wo dasselbe I-UCR-Kuerzel bei der ISP an einem anderen Statut
# haengt als in Chicagos Katalog, weichen die Zielcodes berechtigt ab.
ISP_ABWEICHUNGEN = {
    # ISP: "Retail Theft - Alters/Transfers/Removes Label" (720-5/16-25(a)),
    # Chicago: "THEFT / OVER $500".
    "0810": ("23H", "26A"),
    # ISP: "Retail Theft - Permissive Inference" (720-5/16-25(c)),
    # Chicago: "THEFT / $500 AND UNDER".
    "0820": ("23H", "23C"),
    # ISP: "Unlawful Possession of Firearm Projectiles" (720-5/24-2.1) als
    # Sammelposten, Chicago fuehrt es als Waffendelikt.
    "1475": ("520", "90Z"),
}


@pytest.fixture(scope="module")
def isp_tabelle() -> dict[str, str]:
    openpyxl = pytest.importorskip("openpyxl")
    if not ISP_TABELLE.exists():
        pytest.skip(f"{ISP_TABELLE} fehlt")
    mappe = openpyxl.load_workbook(ISP_TABELLE, read_only=True, data_only=True)
    blatt = mappe[mappe.sheetnames[0]]
    # Zeile 1 und 2 sind Titel, Zeile 3 ist die Kopfzeile.
    return {
        str(iucr).strip(): str(ibr).strip()
        for _ilcs, _literal, iucr, ibr, _kategorie
        in blatt.iter_rows(min_row=4, values_only=True)
        if iucr and ibr
    }


def test_isp_tabelle_ist_lesbar(isp_tabelle):
    assert len(isp_tabelle) > 2_000, f"nur {len(isp_tabelle)} Zeilen gelesen"


def test_chicago_deckt_sich_mit_der_isp_tabelle(isp_tabelle):
    """Unabhaengige Gegenprobe zu config/iucr_nibrs_mapping.csv.

    Der Crosswalk entstand aus der IUCR-Liste der Stadt; die ISP-Tabelle ist
    eine zweite, davon getrennte Quelle. Wo beide denselben I-UCR-Code kennen,
    muessen sie denselben NIBRS-Code nennen - ausser in den drei oben
    begruendeten Faellen.
    """
    abweichend = {}
    for zeile in _zeilen(IUCR_MAPPING):
        iucr, unser = zeile["iucr"], zeile["ibr_code"]
        if not unser or iucr not in isp_tabelle:
            continue
        if unser != isp_tabelle[iucr]:
            abweichend[iucr] = (unser, isp_tabelle[iucr])
    assert abweichend == ISP_ABWEICHUNGEN, (
        f"neu abweichend: { {k: v for k, v in abweichend.items() if k not in ISP_ABWEICHUNGEN} }, "
        f"nicht mehr abweichend: { {k: v for k, v in ISP_ABWEICHUNGEN.items() if k not in abweichend} }"
    )


def test_die_gegenprobe_deckt_genug_zeilen_ab(isp_tabelle):
    """Ohne Mindestueberdeckung koennte der Test oben leer durchlaufen."""
    gemeinsam = sum(1 for z in _zeilen(IUCR_MAPPING)
                    if z["ibr_code"] and z["iucr"] in isp_tabelle)
    assert gemeinsam > 200, f"nur {gemeinsam} Zeilen gegengeprueft"
