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
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAPPING = PROJECT_ROOT / "config" / "micr_nibrs_mapping.csv"
# Original: michigan.gov/.../micr-assets/2009/diappf.pdf, hier sprechend
# benannt. Liegt im Repository, weil michigan.gov automatisierte Abrufe
# mit HTTP 403 beantwortet.
QUELLEN = {
    "micr_manual_1110_2024": PROJECT_ROOT / "docs" / "micr_manual_1110_2024.pdf",
    # Dieselbe Quelle, anderer Abschnitt: die Arrest-Charge-Liste statt der
    # File-Class-Liste. Die Herkunft bleibt getrennt, weil die Zuordnung eine
    # Stufe mehr durchlaeuft - Arrest Charge, File Class, dann NIBRS.
    "micr_arrest_charge_1110_2024": PROJECT_ROOT / "docs" / "micr_manual_1110_2024.pdf",
    "appendix_f_2009": PROJECT_ROOT / "docs" / "micr_appendix_f_2009.pdf",
}

# Eine Herkunft, deren Beleg kein Dokument ist, sondern die Quelle selbst: Zu
# drei Codes widerspricht Detroits Verwendung dem Handbuch, und Detroit liefert
# die Aufloesung in zwei eigenen Feldern mit. Belegt wird das nicht durch ein
# PDF, sondern durch eine Rechnung - und die muss auffindbar sein.
AUS_DEN_DATEN = {
    "detroit_charge_file_class": PROJECT_ROOT / "notebooks" / "11_detroit_source.ipynb",
}

SPALTEN = [
    "micr_code",
    "micr_code_type",
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
HERKUNFT = set(QUELLEN) | set(AUS_DEN_DATEN) | {""}

# MICR fuehrt zwei Codelisten. Welche eine Zeile meint, muss dastehen - sonst
# ist der vierstellige Code doppeldeutig.
CODE_ARTEN = {"file_class", "arrest_charge", ""}

# Drei Codes, deren Zuordnung nicht aus dem Handbuch stammt, sondern aus
# Detroits eigenen Feldern - das Handbuch sagt zu ihnen etwas anderes.
# Hergeleitet und nachgerechnet in notebooks/11_detroit_source.ipynb, 7.1.
AUS_DETROITS_FELDERN = {
    "3072": ("30002", "23C"),
    "5421": ("54001", "90Z"),
    "5422": ("54001", "90Z"),
}


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
    """Appendix F fuehrt fuenfstellig NN00M, Detroit vierstellig NN0M.

    Gilt nur fuer Zeilen, deren Code selbst eine File Class ist. Bei einem
    Arrest Charge nennt ``micr_file_class`` die uebergeordnete Klasse, und die
    hat mit dem Code nichts zu tun: 3071 haengt unter 30001.
    """
    falsch = [
        (z["micr_code"], z["micr_file_class"])
        for z in zeilen
        if z["micr_code_type"] == "file_class" and z["micr_file_class"]
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


def test_jede_genutzte_herkunft_hat_einen_beleg(zeilen):
    """Jede Herkunft zeigt auf etwas Nachlesbares - ein PDF oder eine Rechnung."""
    genutzt = {z["match"] for z in zeilen if z["match"]}
    ohne_beleg = genutzt - set(QUELLEN) - set(AUS_DEN_DATEN)
    assert not ohne_beleg, f"Herkunft ohne hinterlegten Beleg: {ohne_beleg}"


def test_der_beleg_aus_den_daten_liegt_wirklich_da(zeilen):
    """Ein Verweis auf eine Rechnung ist nur so viel wert wie die Rechnung.

    Waere das Notebook geloescht oder umbenannt, stuenden drei Zeilen des
    Crosswalks ohne nachvollziehbaren Grund da - und niemand wuesste es.
    """
    genutzt = {z["match"] for z in zeilen if z["match"]}
    for herkunft, beleg in AUS_DEN_DATEN.items():
        if herkunft in genutzt:
            assert beleg.exists(), f"{herkunft} verweist auf {beleg}, das fehlt"


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
# Die zweite Codeliste: Arrest Charges
# --------------------------------------------------------------------------


def test_code_art_stammt_aus_fester_menge(zeilen):
    unbekannt = {z["micr_code_type"] for z in zeilen} - CODE_ARTEN
    assert not unbekannt, f"unbekannte Code-Art: {unbekannt}"


def test_jede_zugeordnete_zeile_sagt_welche_liste_sie_meint(zeilen):
    """Ohne diese Angabe ist ein vierstelliger Code nicht aufloesbar.

    54 Kuerzel koennen beides sein: 0901 ist die gekuerzte File Class 09001
    und zugleich der Arrest Charge "Family, Gun".
    """
    ohne = [z["micr_code"] for z in zeilen
            if z["mapped"] == "true" and not z["micr_code_type"]]
    assert not ohne, f"zugeordnet, aber ohne Code-Art: {ohne}"


def test_arrest_charge_nennt_seine_file_class(zeilen):
    """Die Zuordnung laeuft ueber die File Class - die muss nachlesbar sein."""
    ohne = [z["micr_code"] for z in zeilen
            if z["micr_code_type"] == "arrest_charge" and z["mapped"] == "true"
            and not z["micr_file_class"]]
    assert not ohne, f"Arrest Charge ohne File Class: {ohne}"


def test_arrest_charge_erbt_den_code_seiner_file_class(zeilen):
    """Der NIBRS-Code kommt von der File Class, nicht aus eigener Deutung.

    Genau das ist der Unterschied zu einer erfundenen Zuordnung: Jede dieser
    Zeilen laesst sich in der Tabelle selbst nachrechnen.
    """
    nach_klasse = {z["micr_file_class"]: z for z in zeilen
                   if z["micr_code_type"] == "file_class" and z["micr_file_class"]}
    abweichend = []
    for z in zeilen:
        if z["micr_code_type"] != "arrest_charge" or z["mapped"] != "true":
            continue
        quelle = nach_klasse.get(z["micr_file_class"])
        assert quelle is not None, f"{z['micr_code']}: File Class fehlt in der Tabelle"
        if (z["nibrs_code"], z["nibrs_group"]) != (quelle["nibrs_code"],
                                                   quelle["nibrs_group"]):
            abweichend.append((z["micr_code"], z["nibrs_code"], quelle["nibrs_code"]))
    assert not abweichend, f"weicht von der File Class ab: {abweichend}"


def test_arrest_charge_zeilen_nennen_ihre_herkunft(zeilen):
    falsch = [z["micr_code"] for z in zeilen
              if z["micr_code_type"] == "arrest_charge" and z["mapped"] == "true"
              and z["match"] not in {"micr_arrest_charge_1110_2024",
                                     "detroit_charge_file_class"}]
    assert not falsch, f"Arrest Charge mit falscher Herkunft: {falsch}"


@pytest.mark.parametrize("code", sorted(AUS_DETROITS_FELDERN))
def test_zuordnung_gegen_das_handbuch_ist_kenntlich(zeilen, code):
    """Diese drei Zeilen folgen nicht dem Handbuch. Das muss man ihnen ansehen.

    Sie standen lange unzugeordnet, weil Detroits Beschreibung dem Handbuch
    widerspricht - und beim Chicago-Crosswalk hat die Versuchung, so etwas zu
    raten, 106 falsche Zeilen gekostet. Geraten wird auch jetzt nicht: Die
    File Class kommt aus Detroits eigenem Feld ``arrest_charge``, der Name aus
    ``charge_description``. Wer die Zeile spaeter liest, muss beides in der
    Herkunft und der Notiz wiederfinden.
    """
    file_class, nibrs = AUS_DETROITS_FELDERN[code]
    zeile = next(z for z in zeilen if z["micr_code"] == code)
    assert zeile["mapped"] == "true"
    assert zeile["micr_file_class"] == file_class
    assert zeile["nibrs_code"] == nibrs
    assert zeile["match"] == "detroit_charge_file_class", (
        f"{code}: die Herkunft muss sagen, dass nicht das Handbuch die Quelle ist"
    )
    assert "Handbuch" in zeile["note"], f"{code}: die Notiz muss den Widerspruch nennen"
    assert "charge_description" in zeile["note"], (
        f"{code}: die Notiz muss den Beleg nennen, nicht nur den Widerspruch"
    )


def test_nur_diese_drei_weichen_vom_handbuch_ab(zeilen):
    """Gegenprobe - sonst waechst die Ausnahme unbemerkt."""
    abweichend = {z["micr_code"] for z in zeilen
                  if z["match"] == "detroit_charge_file_class"}
    assert abweichend == set(AUS_DETROITS_FELDERN), (
        f"neu gegen das Handbuch: {sorted(abweichend - set(AUS_DETROITS_FELDERN))}, "
        f"nicht mehr dabei: {sorted(set(AUS_DETROITS_FELDERN) - abweichend)}"
    )


def test_die_tabelle_hat_keine_luecke_mehr(zeilen):
    """Seit den drei Codes ist jede Zeile zugeordnet.

    Bleibt der Test gruen, ohne dass jemand ihn anfasst, ist das die Zusage;
    faellt er, ist eine neue Zeile dazugekommen, die niemand geprueft hat.
    """
    offen = {z["micr_code"] for z in zeilen if z["mapped"] != "true"}
    assert not offen, f"unzugeordnet: {sorted(offen)}"


# --------------------------------------------------------------------------
# Abdeckung der echten Daten, wenn vorhanden
# --------------------------------------------------------------------------


def detroit_codes() -> dict[str, int] | None:
    """Die MICR-Codes des juengsten Detroit-Bronze-Laufs, oder None.

    Detroit schreibt seit dem 11.9. Parquet in Laufverzeichnissen. Der frueher
    gelesene NDJSON-Bestand ist geloescht: Sein Jahresfenster war in UTC
    gezogen statt in Detroiter Ortszeit, er enthielt also Faelle aus 2023.
    """
    wurzel = PROJECT_ROOT / "data" / "bronze" / "detroit"
    treffer = sorted(
        p for p in wurzel.glob("**/run_*/part-0001.parquet")
        if not any(teil.startswith(".") for teil in p.parts)
    ) if wurzel.exists() else []
    if not treffer:
        return None
    duckdb = pytest.importorskip("duckdb")
    con = duckdb.connect()
    try:
        return {
            code: anzahl
            for code, anzahl in con.execute(f"""
                SELECT attributes.state_offense_code, count(*)
                FROM read_parquet({[str(p) for p in treffer]!r})
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
    # Seit 3072, 5421 und 5422 ueber Detroits eigene Felder angeschlossen sind,
    # deckt die Tabelle jeden Code ab, der 2024 vorkommt. Die Schwelle steht
    # trotzdem knapp darunter und nicht bei 100 %: Ein neuer Code in einem
    # spaeteren Jahrgang soll den Test nicht sofort fallen lassen, sondern der
    # Test oben, der die Luecke beim Namen nennt.
    assert anteil > 0.999, f"nur {anteil:.1%} der Faelle zugeordnet"


def test_seen_in_detroit_stimmt_mit_den_daten(zeilen):
    daten = detroit_codes()
    if daten is None:
        pytest.skip("kein Detroit-Bronze-Lauf vorhanden")
    behauptet = {z["micr_code"] for z in zeilen if z["seen_in_detroit_2024"] == "true"}
    assert behauptet == set(daten), (
        f"nur in der Tabelle: {sorted(behauptet - set(daten))}, "
        f"nur in den Daten: {sorted(set(daten) - behauptet)}"
    )


# --------------------------------------------------------------------------
# Reproduzierbarkeit
# --------------------------------------------------------------------------
#
# Das Konzept sagt zu, die Crosswalks seien reproduzierbar abgeleitet. Bis
# hierher pruefen alle Tests nur die fertige Datei - jemand koennte sie von
# Hand aendern, und alles bliebe gruen. Der Test unten laesst das Werkzeug den
# Anschluss noch einmal herstellen und vergleicht byteweise.

WERKZEUG = PROJECT_ROOT / "tools" / "extend_micr_arrest_charges.py"
MANUAL = PROJECT_ROOT / "docs" / "micr_manual_1110_2024.pdf"

# Die Herkunftswerte, fuer die dieses Werkzeug zustaendig ist. Zeilen mit einer
# anderen Herkunft stammen aus den Handbuechern und sind seine Eingabe.
ERZEUGT = {"micr_arrest_charge_1110_2024", "detroit_charge_file_class"}

# Die Spalten, die es fuellt. Genau sie werden fuer die Probe geleert.
GEFUELLT = ("micr_code_type", "micr_file_class", "nibrs_group", "nibrs_code",
            "nibrs_description", "hierarchy", "match", "note")


def test_das_werkzeug_stellt_den_anschluss_wieder_her(tmp_path, zeilen):
    """Die Probe aufs Exempel: aus dem Stand davor entsteht der Stand danach.

    Ein normaler Lauf taete nichts - das Werkzeug fuellt nur Zeilen, die noch
    nicht zugeordnet sind, und inzwischen sind es alle. Geprueft wird deshalb
    gegen eine Fassung, in der genau die 23 Zeilen geleert sind, die es selbst
    angeschlossen hat.
    """
    if not MANUAL.exists():
        pytest.skip(f"{MANUAL} fehlt")

    davor = tmp_path / "davor.csv"
    danach = tmp_path / "danach.csv"
    geleert = 0
    with davor.open("w", newline="", encoding="utf-8") as datei:
        schreiber = csv.DictWriter(datei, fieldnames=list(zeilen[0]))
        schreiber.writeheader()
        for zeile in zeilen:
            kopie = dict(zeile)
            if kopie["match"] in ERZEUGT:
                for spalte in GEFUELLT:
                    kopie[spalte] = ""
                kopie["mapped"] = "false"
                geleert += 1
            schreiber.writerow(kopie)

    assert geleert == 23, f"erwartet 23 erzeugte Zeilen, gefunden {geleert}"

    fertig = subprocess.run(
        [sys.executable, str(WERKZEUG),
         "--mapping", str(davor), "--output", str(danach)],
        capture_output=True, text=True, cwd=PROJECT_ROOT,
    )
    assert fertig.returncode == 0, fertig.stderr

    assert danach.read_text(encoding="utf-8") == MAPPING.read_text(encoding="utf-8"), (
        "Das Werkzeug baut den Anschluss nicht mehr so auf, wie er in "
        "config/micr_nibrs_mapping.csv steht - die Datei ist dann von Hand "
        "geaendert worden oder das Werkzeug hat sich geaendert"
    )


def test_ein_lauf_auf_dem_fertigen_stand_aendert_nichts(tmp_path):
    """Zweimal laufen darf nicht zweimal etwas tun."""
    if not MANUAL.exists():
        pytest.skip(f"{MANUAL} fehlt")
    ziel = tmp_path / "kopie.csv"
    ziel.write_text(MAPPING.read_text(encoding="utf-8"), encoding="utf-8")
    fertig = subprocess.run(
        [sys.executable, str(WERKZEUG), "--mapping", str(ziel)],
        capture_output=True, text=True, cwd=PROJECT_ROOT,
    )
    assert fertig.returncode == 0, fertig.stderr
    assert ziel.read_text(encoding="utf-8") == MAPPING.read_text(encoding="utf-8")
