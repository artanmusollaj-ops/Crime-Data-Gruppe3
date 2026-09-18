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
import re
import subprocess
import sys
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


def test_assault_und_battery_bleiben_getrennt(zeilen):
    """Illinois trennt Drohung und Beruehrung - NIBRS auch.

    Eine erste Fassung warf beides auf 13B. Aufgefallen ist es in Artans
    Review vom 11.9.; belegt hat es die ILCS-Tabelle der Illinois State
    Police, die 720-5/12-1 *Assault* auf 13C fuehrt und 720-5/12-3 *Battery*
    auf 13B. Das sind die einzigen beiden Zeilen der 13er-Familie, deren
    Wortlaut zu Chicagos Katalog passt.

    Die Verwechslung ist teuer: Sie betraf 15'120 Faelle, 28 Prozent von
    Chicagos einfacher Koerperverletzung, und verschob das Verhaeltnis zu
    Detroit von 2,45 auf 3,40.
    """
    nach_code = {z["iucr"]: z for z in zeilen}
    assert nach_code["0460"]["ibr_code"] == "13B", "BATTERY / SIMPLE ist der Angriff"
    assert nach_code["0560"]["ibr_code"] == "13C", "ASSAULT / SIMPLE ist die Drohung"


def test_bedrohung_ohne_beleg_bleibt_ermessen(zeilen):
    """0545 und 0554 folgen derselben Logik, aber ohne Quelle.

    Chicago fuehrt beide unter ASSAULT, was fuer 13C spraeche. Die
    ILCS-Tabelle kennt zu diesen Kuerzeln aber keine Zeile. Ohne Beleg wird
    nicht umgebucht - aber die Frage muss in der Tabelle stehen.
    """
    for code in ("0545", "0554"):
        zeile = next(z for z in zeilen if z["iucr"] == code)
        assert zeile["match"] == "nibrs_ermessen", f"{code} ist keine belegte Zuordnung"
        assert "ISP" in zeile["note"] or "ILCS" in zeile["note"], (
            f"{code}: die Notiz muss sagen, woran der Beleg fehlt"
        )


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


# --------------------------------------------------------------------------
# Gegenprobe durch die Landespolizei
# --------------------------------------------------------------------------

# Original: isp.illinois.gov/CrimeReporting/NIBRS, "NIBRS Code Table".
ISP_TABELLE = PROJECT_ROOT / "docs" / "quellen" / "isp_nibrs_code_table_2026.xlsx"

# Woerter, die in fast jeder Deliktbeschreibung stehen und deshalb nichts ueber
# Uebereinstimmung aussagen.
FUELLWOERTER = {"other", "than", "with", "from", "over", "under", "and", "the",
                "for", "not", "only"}

# Ab hier gilt der Wortlaut als deckend. Darunter ist es eine Namensaehnlichkeit
# ohne Aussage - 0810 "THEFT / OVER $500" und "Retail Theft - Alters Label"
# teilen sich das Wort "theft" und meinen Verschiedenes.
DECKUNG = 0.6

# Wo wir der Landespolizei widersprechen - und warum. Jede neue Abweichung
# laesst den Test fallen und muss hier begruendet werden, oder die Zuordnung
# ist falsch. Genau diese Liste hat gefehlt, als 0560 auf 13B lag.
ABWEICHUNGEN = {
    # Statut-Artefakte: die ISP-Zeile ist ein anderes Delikt. Die ISP-Tabelle
    # ist nach ILCS-Statut geschluesselt und vergibt je Statut ein eigenes
    # I-UCR-Kuerzel; Chicagos Katalog benutzt dieselben Kuerzel anders.
    "0810": ("23H", "26A", "ISP-Zeile ist Retail Theft mit manipuliertem "
                           "Preisschild, Chicago meint Diebstahl ueber 500 Dollar"),
    "0820": ("23H", "23C", "ISP-Zeile ist Retail Theft durch Verbergen von Ware"),
    "1505": ("40B", "40A", "ISP-Zeile ist das Grunddelikt Prostitution; "
                           "Chicagos Call Operation ist die Foerderung"),
    # Sachliche Abweichungen: die NIBRS-Definition ist eindeutiger als die
    # Wahl der ISP.
    "1030": ("520", "90Z", "Die Definition von 520 nennt explosives und "
                           "incendiary devices ausdruecklich"),
    "1145": ("280", "26E", "280 ist woertlich das Verkaufen von Sachen in "
                           "Kenntnis der Herkunft; beim Hehlen wird der Kaeufer "
                           "nicht getaeuscht"),
    "1147": ("280", "26E", "wie 1145: elektronisches Hehlen ist das Verkaufen "
                           "gestohlener Sachen, nicht die Taeuschung des Kaeufers"),
    "3920": ("90Z", "210", "210 Extortion verlangt eine Drohung, die "
                           "Amtsmissbrauch nicht zwingend hat"),
    "4750": ("90Z", "90F", "90F setzt ein Familienmitglied voraus, der "
                           "Offenbarende ist keines"),
}


@pytest.fixture(scope="module")
def isp_zeilen() -> dict[str, tuple[str, str]]:
    """I-UCR-Kuerzel -> (Wortlaut des Statuts, IBR-Code) aus der ISP-Tabelle."""
    openpyxl = pytest.importorskip("openpyxl")
    if not ISP_TABELLE.exists():
        pytest.skip(f"{ISP_TABELLE} fehlt")
    blatt = openpyxl.load_workbook(ISP_TABELLE, read_only=True, data_only=True)
    blatt = blatt[blatt.sheetnames[0]]
    return {
        str(iucr).strip(): (str(literal or ""), str(ibr).strip())
        for _ilcs, literal, iucr, ibr, _kat
        in blatt.iter_rows(min_row=4, values_only=True)
        if iucr and ibr
    }


def _begriffe(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", text.lower())} - FUELLWOERTER


def vergleichbare_zeilen(zeilen, isp_zeilen):
    """Die Zeilen, bei denen die ISP wirklich dasselbe Delikt meint.

    Ohne dieses Tor ist der Vergleich wertlos: Die ISP-Tabelle ist nach Statut
    geschluesselt, und bei 86 von 240 gemeinsamen Kuerzeln beschreibt sie ein
    voellig anderes Delikt (Konzept 8.5). Verglichen wird deshalb nur, wo sich
    die Beschreibungen decken.
    """
    for z in zeilen:
        if not z["ibr_code"] or z["iucr"] not in isp_zeilen:
            continue
        literal, ibr = isp_zeilen[z["iucr"]]
        unser = _begriffe(f"{z['primary_description']} {z['secondary_description']}")
        ihrer = _begriffe(literal)
        if not unser or not ihrer:
            continue
        if len(unser & ihrer) / min(len(unser), len(ihrer)) >= DECKUNG:
            yield z, literal, ibr


def test_die_gegenprobe_deckt_genug_zeilen_ab(zeilen, isp_zeilen):
    """Ohne Mindestueberdeckung liefe der Test unten leer durch."""
    anzahl = sum(1 for _ in vergleichbare_zeilen(zeilen, isp_zeilen))
    assert anzahl > 90, f"nur {anzahl} Zeilen vergleichbar"


def test_abweichungen_von_der_landespolizei_sind_begruendet(zeilen, isp_zeilen):
    """Die Pruefung, die 0560 gefunden haette.

    Die ILCS-Tabelle der Illinois State Police ist die einzige **unabhaengige**
    Beurteilung unserer Zuordnung: Alle anderen Tests vergleichen sie mit
    Chicagos eigener Beschreibung, und nach diesem Massstab sah
    ``ASSAULT / SIMPLE -> 13B`` richtig aus. Erst die Landespolizei sagt, dass
    Assault in Illinois die Drohung ohne Beruehrung meint.

    Der Test verlangt nicht Uebereinstimmung - dafuer ist die Tabelle zu sehr
    nach Statut geschluesselt. Er verlangt, dass die Menge der Abweichungen
    genau der dokumentierten entspricht. Eine neue faellt auf und muss
    begruendet werden.
    """
    gefunden = {
        z["iucr"]: (z["ibr_code"], ibr)
        for z, _literal, ibr in vergleichbare_zeilen(zeilen, isp_zeilen)
        if ibr != z["ibr_code"]
    }
    erwartet = {k: (v[0], v[1]) for k, v in ABWEICHUNGEN.items()}
    assert gefunden == erwartet, (
        f"neu abweichend: { {k: v for k, v in gefunden.items() if k not in erwartet} }, "
        f"nicht mehr abweichend: { {k: v for k, v in erwartet.items() if k not in gefunden} }"
    )


def test_jede_abweichung_traegt_eine_begruendung():
    ohne = [k for k, v in ABWEICHUNGEN.items() if len(v[2].strip()) < 20]
    assert not ohne, f"Abweichung ohne Begruendung: {ohne}"


def test_wo_die_landespolizei_zustimmt_stimmt_auch_0560(zeilen, isp_zeilen):
    """Die beiden Zeilen, an denen sich der Fehler entschied.

    Illinois trennt Assault (Drohung, 720-5/12-1) von Battery (Beruehrung,
    5/12-3). Beide haben eine ISP-Zeile mit deckendem Wortlaut - und nur bei
    diesen beiden traegt der Join in der ganzen 13er-Familie.
    """
    treffer = {z["iucr"]: (z["ibr_code"], ibr)
               for z, _l, ibr in vergleichbare_zeilen(zeilen, isp_zeilen)}
    assert treffer.get("0460") == ("13B", "13B"), "BATTERY / SIMPLE ist der Angriff"
    assert treffer.get("0560") == ("13C", "13C"), "ASSAULT / SIMPLE ist die Drohung"


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


# --------------------------------------------------------------------------
# Reproduzierbarkeit
# --------------------------------------------------------------------------


WERKZEUG = PROJECT_ROOT / "tools" / "build_iucr_nibrs_mapping.py"


def test_das_werkzeug_erzeugt_genau_diese_datei(tmp_path):
    """Die Zusage aus dem Konzept, gepruft statt behauptet.

    ``config/iucr_nibrs_mapping.csv`` ist nicht gepflegt, sondern erzeugt: aus
    Chicagos IUCR-Katalog und den Zuordnungsregeln im Werkzeug. Solange das
    niemand nachrechnet, koennte jemand die Datei von Hand aendern und alle
    uebrigen Tests blieben gruen - sie pruefen die Datei, nicht ihre Herkunft.

    Gelaufen wird mit ``--offline``: Der Katalog kommt aus der versionierten
    Datei, nicht vom Portal. Geprueft werden damit die **Zuordnungsregeln** -
    ob Chicagos Katalog sich bewegt hat, ist eine andere Frage, und Notebook 32
    stellt sie live. Ohne den Schalter kostete dieser Test zwanzig Sekunden und
    haenge an einer Netzverbindung.
    """
    ziel = tmp_path / "erzeugt.csv"
    fertig = subprocess.run(
        [sys.executable, str(WERKZEUG), "--output", str(ziel), "--offline"],
        capture_output=True, text=True, cwd=PROJECT_ROOT,
    )
    assert fertig.returncode == 0, fertig.stderr
    assert ziel.exists(), "das Werkzeug hat nichts geschrieben"

    erzeugt = ziel.read_text(encoding="utf-8")
    versioniert = MAPPING.read_text(encoding="utf-8")
    if erzeugt != versioniert:
        erz = erzeugt.splitlines()
        ver = versioniert.splitlines()
        abweichend = [
            (a, b) for a, b in zip(erz, ver) if a != b
        ][:3]
        raise AssertionError(
            f"Das Werkzeug erzeugt eine andere Datei "
            f"({len(erz)} gegen {len(ver)} Zeilen). "
            f"Entweder wurde die Datei von Hand geaendert, oder Chicagos "
            f"Katalog hat sich bewegt und das Werkzeug muss neu laufen. "
            f"Erste Unterschiede: {abweichend}"
        )


def test_zweimal_laufen_liefert_dasselbe(tmp_path):
    """Ohne das waere der Vergleich oben nur ein Zufall."""
    erste = tmp_path / "eins.csv"
    zweite = tmp_path / "zwei.csv"
    for ziel in (erste, zweite):
        fertig = subprocess.run(
            [sys.executable, str(WERKZEUG), "--output", str(ziel), "--offline"],
            capture_output=True, text=True, cwd=PROJECT_ROOT,
        )
        assert fertig.returncode == 0, fertig.stderr
    assert erste.read_text(encoding="utf-8") == zweite.read_text(encoding="utf-8")
