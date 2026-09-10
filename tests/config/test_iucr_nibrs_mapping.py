"""Tests fuer die IUCR-NIBRS-Zuordnung Chicagos.

Die Tabelle wird von tools/build_iucr_nibrs_mapping.py erzeugt. Geprueft wird
hier nicht das Skript, sondern das Ergebnis: dass die beschreibenden Spalten
unveraendert Chicagos Katalog wiedergeben, dass jeder Zielcode in der
NIBRS-Codeliste steht, und dass die Zuordnung dort, wo sie nicht eindeutig ist,
das auch sagt.

Der Anlass fuer diese Tests ist ein konkreter Fehler: die erste Fassung der
Tabelle entstand aus einem Join ueber den I-UCR-Code auf eine Codetabelle der
Illinois State Police, die nach ILCS-Statut geschluesselt ist. Der Join lieferte
gueltige NIBRS-Codes fuer das falsche Delikt - 1140 "EMBEZZLEMENT" zeigte auf
250 Counterfeiting/Forgery. Ein Test auf blosse Gueltigkeit haette das nicht
gefunden. Die Stichproben unten pruefen deshalb den Inhalt, nicht die Form.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAPPING = PROJECT_ROOT / "config" / "iucr_nibrs_mapping.csv"
CODELISTE = PROJECT_ROOT / "config" / "nibrs_offense_codes_2025.csv"

SPALTEN = [
    "iucr",
    "primary_description",
    "secondary_description",
    "index_code",
    "active",
    "ibr_code",
    "ibr_category",
    "match",
    "mapped",
    "note",
]

# nibrs_definition : Chicagos Beschreibung hat eine klare NIBRS-Entsprechung
# nibrs_ermessen   : zwei Codes waren vertretbar, die Notiz sagt welcher warum
# nibrs_auffang    : NIBRS kennt das Delikt nicht, deshalb 90Z
HERKUNFT = {"nibrs_definition", "nibrs_ermessen", "nibrs_auffang", ""}

# Chicagos IUCR-Katalog, Stand der Uebernahme vom Datenportal.
ANZAHL_ZEILEN = 434


@pytest.fixture(scope="module")
def zeilen() -> list[dict[str, str]]:
    with MAPPING.open(encoding="utf-8") as datei:
        return list(csv.DictReader(datei))


@pytest.fixture(scope="module")
def amtlich() -> dict[str, dict[str, str]]:
    with CODELISTE.open(encoding="utf-8") as datei:
        return {z["nibrs_code"]: z for z in csv.DictReader(datei)}


# --------------------------------------------------------------------------
# Form
# --------------------------------------------------------------------------


def test_spalten_wie_vereinbart(zeilen):
    assert list(zeilen[0]) == SPALTEN


def test_alle_zeilen_des_katalogs(zeilen):
    assert len(zeilen) == ANZAHL_ZEILEN


def test_iucr_ist_eindeutig(zeilen):
    alle = [z["iucr"] for z in zeilen]
    doppelt = {c for c in alle if alle.count(c) > 1}
    assert not doppelt, f"mehrfach vorhanden: {sorted(doppelt)}"


def test_iucr_ist_vierstellig(zeilen):
    """Fuehrende Nullen sind bedeutungstragend - 0110 ist Mord."""
    falsch = [z["iucr"] for z in zeilen if len(z["iucr"]) != 4]
    assert not falsch, f"nicht vierstellig: {falsch}"


def test_herkunft_stammt_aus_fester_menge(zeilen):
    unbekannt = {z["match"] for z in zeilen} - HERKUNFT
    assert not unbekannt, f"unbekannte Herkunft: {unbekannt}"


def test_mapped_ist_ein_wahrheitswert(zeilen):
    falsch = {z["mapped"] for z in zeilen} - {"true", "false"}
    assert not falsch, falsch


# --------------------------------------------------------------------------
# Zielcodes
# --------------------------------------------------------------------------


def test_jeder_zielcode_ist_gueltig(zeilen, amtlich):
    unbekannt = sorted({z["ibr_code"] for z in zeilen if z["ibr_code"]} - set(amtlich))
    assert not unbekannt, f"kein NIBRS-Code der Fassung 2025: {unbekannt}"


def test_kein_zielcode_ist_bundesdelikt(zeilen, amtlich):
    """Anhang A markiert Codes, die nur Bundesbehoerden melden duerfen.

    Chicago kann sie nicht vergeben; stuende einer hier, waere die Zeile aus
    einer Codeliste uebernommen statt aus der Deliktbeschreibung abgeleitet.
    """
    bund = sorted({z["ibr_code"] for z in zeilen
                   if z["ibr_code"] and amtlich[z["ibr_code"]]["federal_only"] == "true"})
    assert not bund, f"nur von Bundesbehoerden meldbar: {bund}"


def test_kategorie_passt_zum_code(zeilen, amtlich):
    """Die Klartextspalte darf nicht von der Codeliste abweichen."""
    falsch = [
        (z["iucr"], z["ibr_code"], z["ibr_category"])
        for z in zeilen if z["ibr_code"]
        and z["ibr_category"] != amtlich[z["ibr_code"]]["nibrs_description"].upper()
    ]
    assert not falsch, f"Kategorie passt nicht zum Code: {falsch[:5]}"


def test_zugeordnete_zeilen_sind_vollstaendig(zeilen):
    unvollstaendig = [z["iucr"] for z in zeilen
                      if z["mapped"] == "true"
                      and not (z["ibr_code"] and z["ibr_category"] and z["match"])]
    assert not unvollstaendig, f"als zugeordnet markiert, aber unvollstaendig: {unvollstaendig}"


def test_nicht_zugeordnete_zeilen_behaupten_nichts(zeilen):
    erfunden = [z["iucr"] for z in zeilen
                if z["mapped"] == "false" and (z["ibr_code"] or z["ibr_category"])]
    assert not erfunden, f"ohne Zuordnung, aber mit NIBRS-Angabe: {erfunden}"


def test_nicht_zugeordnete_zeilen_nennen_den_grund(zeilen):
    ohne = [z["iucr"] for z in zeilen
            if z["mapped"] == "false" and not z["note"].strip()]
    assert not ohne, f"ohne Zuordnung und ohne Begruendung: {ohne}"


def test_ermessenszeilen_nennen_den_grund(zeilen):
    """Eine Ermessensentscheidung ohne Begruendung ist eine Behauptung."""
    ohne = [z["iucr"] for z in zeilen
            if z["match"] == "nibrs_ermessen" and not z["note"].strip()]
    assert not ohne, f"Ermessen ohne Notiz: {ohne}"


def test_auffang_ist_immer_90z(zeilen):
    falsch = [(z["iucr"], z["ibr_code"]) for z in zeilen
              if z["match"] == "nibrs_auffang" and z["ibr_code"] != "90Z"]
    assert not falsch, f"als Auffang markiert, aber nicht 90Z: {falsch}"


def test_auffang_bleibt_die_ausnahme(zeilen):
    """90Z ist ehrlich, aber wertlos fuer den Vergleich - es darf nicht kippen."""
    auffang = sum(1 for z in zeilen if z["ibr_code"] == "90Z")
    anteil = auffang / len(zeilen)
    assert anteil < 0.25, f"{anteil:.1%} der Zeilen landen im Auffang 90Z"


# --------------------------------------------------------------------------
# Inhalt - die Stichproben, die der alte Join nicht bestanden haette
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "iucr,erwartet,warum",
    [
        # Diese sechs waren in der Fassung aus dem ISP-Join nachweislich falsch.
        ("1140", "270", "EMBEZZLEMENT ist Unterschlagung, nicht Faelschung"),
        ("1265", "290", "LIBRARY VANDALISM ist Sachbeschaedigung"),
        ("1153", "26F", "FINANCIAL IDENTITY THEFT ist Identitaetsdiebstahl"),
        ("0451", "13A", "AGGRAVATED POLICE OFFICER - OTHER FIREARM ist kein Drogendelikt"),
        ("0263", "11A", "AGGRAVATED - KNIFE ist kein Inzest"),
        ("0264", "11A", "AGGRAVATED - OTHER DANGEROUS WEAPON ist keine Unzucht mit Minderjaehrigen"),
        # Die Grundachsen der Zuordnung.
        ("0110", "09A", "First Degree Murder"),
        ("0141", "09B", "Involuntary Manslaughter"),
        ("031A", "120", "Armed Robbery - Handgun"),
        ("0440", "13B", "Haende und leichte Verletzung bleibt Simple Assault"),
        ("0479", "13A", "Haende, aber schwere Verletzung, wird Aggravated"),
        ("0610", "220", "Burglary Forcible Entry"),
        ("0760", "23F", "Eindringen in ein Fahrzeug zaehlt NIBRS als Diebstahl"),
        ("0910", "240", "Motor Vehicle Theft"),
        ("1020", "200", "Arson by Fire"),
        ("2022", "35A", "Possess Cocaine"),
        ("2170", "35B", "Possession of Drug Equipment"),
        ("1525", "40C", "Patronizing a Prostitute ist die Freierseite"),
        ("1530", "40B", "Pimping ist Foerderung"),
        ("1506", "40A", "Solicit on Public Way ist die Ausuebung"),
        ("4650", "360", "Sex Offender - Fail to Register"),
    ],
)
def test_stichproben(zeilen, iucr, erwartet, warum):
    zeile = next(z for z in zeilen if z["iucr"] == iucr)
    assert zeile["ibr_code"] == erwartet, warum


def test_prostitution_ist_kein_sexualdelikt(zeilen):
    """Die Fassung aus dem ISP-Join hatte 1512 auf 11A Rape stehen.

    Prostitutionsdelikte gehoeren in den 40er-Namensraum - oder, wo
    Menschenhandel im Spiel ist, auf 64A. Ein Vergewaltigungscode ist dort
    immer ein Fehler und verzerrt jede Auswertung der Gewaltdelikte.
    """
    falsch = [(z["iucr"], z["ibr_code"]) for z in zeilen
              if z["primary_description"] == "PROSTITUTION"
              and not (z["ibr_code"].startswith("40") or z["ibr_code"] == "64A")]
    assert not falsch, f"Prostitution ausserhalb des 40er-Namensraums: {falsch}"


def test_gewaltdelikte_liegen_im_person_namensraum(zeilen, amtlich):
    """Raub, Toetung und Sexualdelikte muessen NIBRS-Delikte gegen Personen
    oder Eigentum sein - nie Society-Delikte wie Drogen oder Gluecksspiel."""
    betroffen = {"HOMICIDE", "CRIMINAL SEXUAL ASSAULT", "ROBBERY", "ASSAULT", "BATTERY"}
    falsch = [
        (z["iucr"], z["primary_description"], z["ibr_code"])
        for z in zeilen
        if z["primary_description"] in betroffen and z["ibr_code"]
        and amtlich[z["ibr_code"]]["crime_against"] not in {"Person", "Property", "Not a Crime"}
    ]
    assert not falsch, f"Gewaltdelikt auf einem Society-Code: {falsch}"


def test_jede_deliktgruppe_ist_zugeordnet(zeilen):
    """Keine Gruppe darf vollstaendig im Auffang landen."""
    gruppen: dict[str, set[str]] = {}
    for z in zeilen:
        gruppen.setdefault(z["primary_description"], set()).add(z["ibr_code"])
    nur_auffang = sorted(
        name for name, codes in gruppen.items()
        if codes <= {"90Z", ""} and name not in {"NON-CRIMINAL", "DOMESTIC VIOLENCE"}
    )
    assert not nur_auffang, f"Gruppe komplett im Auffang: {nur_auffang}"
