"""Baut config/iucr_nibrs_mapping.csv aus Chicagos IUCR-Liste neu auf.

Warum dieses Skript existiert
-----------------------------
Die erste Fassung des Crosswalks entstand aus einem Join ueber den I-UCR-Code
auf eine Codetabelle der Illinois State Police. Der Join traegt nicht: jene
Tabelle ist nach ILCS-Statut geschluesselt und vergibt je Statut ein eigenes
vierstelliges Kuerzel, waehrend Chicagos IUCR-Katalog dieselben Kuerzel fuer
etwas anderes benutzt. Bei 86 von 240 gemeinsamen Codes beschrieb das Statut
ein voellig anderes Delikt als Chicagos Eintrag - und von dort stammte der
NIBRS-Code. Sichtbar wurde das an Zeilen wie 1140 "DECEPTIVE PRACTICE /
EMBEZZLEMENT", das auf 250 Counterfeiting/Forgery zeigte statt auf 270
Embezzlement.

Die Zuordnung entsteht deshalb hier neu: aus Chicagos eigener Beschreibung des
Delikts gegen die Deliktdefinitionen der NIBRS Technical Specification 2025
(docs/nibrs_technical_specification_2025.pdf, Anhang A; als Tabelle in
config/nibrs_offense_codes_2025.csv). Kein Code ist geraten und keiner stammt
aus einer Positionsentsprechung - jede Zeile unten ist eine gelesene
Entscheidung.

Grundsaetze
-----------
* **Versuch zaehlt wie die Tat.** NIBRS fuehrt keine eigenen Versuchscodes;
  ATTEMPT-Zeilen bekommen den Code der vollendeten Tat.
* **Waffe oder schwere Verletzung trennt 13A von 13B.** Chicagos Zusatz
  "HANDS, FISTS, FEET, NO / MINOR INJURY" ist Simple Assault, auch wenn
  Illinois die Tat "aggravated" nennt, weil das Opfer geschuetzt ist.
* **90Z ist der ehrliche Auffangwert**, nicht der bequeme. Er steht dort, wo
  NIBRS das Delikt nicht kennt - Registrierungspflichten, Bewaehrungsverstoesse,
  Illinois-Eigenheiten. Diese Zeilen sind mit ``nibrs_auffang`` gekennzeichnet
  und in einer Auswertung sichtbar, statt in einer Deliktgruppe unterzugehen.
* **Bundesdelikte scheiden aus.** Anhang A markiert Codes, die nur Bundes- und
  Stammesbehoerden melden. 26H Money Laundering ist so einer - Chicago kann ihn
  nicht melden, deshalb geht 4800 nach 90Z und nicht nach 26H.

Aufruf::

    python tools/build_iucr_nibrs_mapping.py

Das Skript laedt Chicagos amtliche IUCR-Liste vom Datenportal, prueft die
beschreibenden Spalten gegen die bestehende Datei und schreibt sie neu. Ohne
Netz benutzt es die vorhandene Datei als Basis - die beschreibenden Spalten
stammen ohnehin von dort und wurden gegen das Portal verifiziert.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ZIEL = PROJECT_ROOT / "config" / "iucr_nibrs_mapping.csv"
CODELISTE = PROJECT_ROOT / "config" / "nibrs_offense_codes_2025.csv"
PORTAL = "https://data.cityofchicago.org/resource/c7ck-438e.json?$limit=1000"

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


# ---------------------------------------------------------------------------
# Die Zuordnung, nach Chicagos Deliktgruppen geordnet
# ---------------------------------------------------------------------------

ZUORDNUNG: dict[str, str] = {}


def _gruppe(codes: str, nibrs: str) -> None:
    """Traegt alle Codes einer Zeile auf denselben NIBRS-Code ein."""
    for code in codes.split():
        if code in ZUORDNUNG:
            raise SystemExit(f"{code} doppelt zugeordnet")
        ZUORDNUNG[code] = nibrs


# --- Toetungsdelikte -------------------------------------------------------
_gruppe("0110 0130", "09A")          # Mord ersten und zweiten Grades
_gruppe("0141 0142", "09B")          # fahrlaessige Toetung, reckless homicide

# --- Sexualdelikte mit Penetration ----------------------------------------
# NIBRS trennt 11A/11B/11C nach Tathandlung; Chicago erfasst diese
# Unterscheidung nicht, sondern nur Waffe und Versuch. 11A ist damit der
# einzige belegbare Code fuer die ganze Gruppe.
_gruppe("0261 0262 0263 0264 0265 0266 0271 0272 0273 0274 0275 0281 0291", "11A")
_gruppe("1753 1754", "11A")          # Sexual Assault of Child by Family Member
_gruppe("1577 1599", "36B")          # Opfer 13-16, Taeter aelter: Statutory Rape
_gruppe("1573", "36B")               # ISP bezieht es auf 720-5/11-1.50(b):
                                     # Taeter unter 17, Opfer 9-17
_gruppe("1580", "36A")               # Sexual Relations in Family
_gruppe("1751 1752", "36A")          # Criminal Sexual Abuse by Family Member

# --- Sexualdelikte ohne Penetration ---------------------------------------
_gruppe("1562 1563 1590 5004 5005", "11D")   # Criminal Sexual Abuse: Kontakt

# --- Raub ------------------------------------------------------------------
_gruppe("0312 0313 031A 031B 0320 0325 0326 0330 0331 0334 0337 033A 033B 0340", "120")

# --- Koerperverletzung: Waffe oder schwere Verletzung ----------------------
_gruppe("041A 041B 0420 0430 0450 0451 0452 0453 0461 0462 0479 0480 0481 0482 "
        "0483 0485 0487 0488 0489 0495 0496 0497 0498 0499", "13A")
_gruppe("051A 051B 0520 0530 0550 0551 0552 0553 0555 0556 0557 0558", "13A")
_gruppe("0490 0491 0492 0493 0510", "13A")   # Ritual Mutilation mit Waffe
_gruppe("1564", "13A")               # Criminal Transmission of HIV: schwere
                                     # Gesundheitsschaedigung, deshalb 13A

# --- Koerperverletzung: ohne Waffe, keine oder leichte Verletzung ---------
_gruppe("0440 0454 0460 0475 0484 0486", "13B")
_gruppe("0545 0554", "13B")   # siehe ERMESSEN: koennte 13C sein
_gruppe("0494", "13B")               # Ritual Mutilation, Haende, leichte Verletzung
_gruppe("1750", "13B")               # Child Abuse, nicht sexuell

# --- Bedrohung -------------------------------------------------------------
_gruppe("3960 3961 3966 3975 3980", "13C")
# Illinois trennt Assault von Battery: Assault ist die Drohung ohne Beruehrung
# (720 ILCS 5/12-1), Battery die Beruehrung (5/12-3). NIBRS trennt genauso -
# 13C Intimidation ist die Drohung, 13B Simple Assault der Angriff. Die
# ILCS-Tabelle der Illinois State Police bestaetigt beides ausdruecklich:
# 720-5/12-1 Assault -> 13C, 720-5/12-3 Battery -> 13B. Das sind die einzigen
# beiden Zeilen der 13er-Familie, deren Wortlaut wirklich zu Chicagos Katalog
# passt; bei allen uebrigen greift der Statut-Versatz aus Kapitel 8.5.
_gruppe("0560", "13C")               # ASSAULT / SIMPLE
_gruppe("0580 0581 0583", "13C")     # Stalking: NIBRS kennt keinen eigenen Code
_gruppe("2850 2851", "13C")          # Bomb Threat, Arson Threat
_gruppe("2820", "13C")               # Telephone Threat
_gruppe("3970", "210")               # Extortion

# --- Freiheitsberaubung ----------------------------------------------------
_gruppe("1790 1792 4210 4220 4230 4240", "100")
_gruppe("4255", "90F")               # Unlawful Visitation Interference

# --- Menschenhandel --------------------------------------------------------
_gruppe("1050", "64A")
_gruppe("1055", "64B")

# --- Prostitution ----------------------------------------------------------
_gruppe("1506 1507 1511 1549", "40A")                      # Ausuebung
_gruppe("1505 1510 1512 1513 1515 1520 1530", "40B")             # Foerderung
# Illinois hat Juvenile Pimping und Keeping a Place of Juvenile Prostitution
# 2013 in 720-5/11-14.4 zusammengefasst. Die ISP fuehrt dieses Statut auf 64A -
# das Foerdern einer minderjaehrigen Prostituierten ist Menschenhandel. Das
# Patronisieren dagegen bleibt 40C (ISP zu 11-18.1(a)).
_gruppe("1531 1521", "64A")
_gruppe("1504 1525 1526", "40C")                           # Freier

# --- Einbruch, Diebstahl, Fahrzeugdiebstahl -------------------------------
_gruppe("0610 0620 0630 0650", "220")
_gruppe("3400", "220")               # Looting: Betreten und Wegnahme im Katastrophenfall
_gruppe("0870", "23A")
_gruppe("0880", "23B")
_gruppe("0830 0860", "23C")
_gruppe("0890", "23D")
_gruppe("0895", "23E")
_gruppe("0710 0760", "23F")          # auch Burglary from Motor Vehicle: NIBRS zaehlt
                                     # das Eindringen in ein Fahrzeug als Diebstahl
_gruppe("0810 0820 0850 0865 1205 1220 1260", "23H")
_gruppe("0910 0915 0917 0918 0920 0925 0927 0928 0930 0935 0937 0938", "240")
_gruppe("1206", "240")               # Theft by Lessee, Motor Vehicle

# --- Brandstiftung ---------------------------------------------------------
_gruppe("1010 1020 1025 1090", "200")

# --- Sachbeschaedigung -----------------------------------------------------
_gruppe("1265 1305 1310 1320 1340 1345 1370 1375", "290")
_gruppe("2896 502T", "290")          # Tire Deflation Device, Tamper with Motor Vehicle

# --- Hausfriedensbruch -----------------------------------------------------
_gruppe("1330 1335 1350 1360 1365", "90J")

# --- Faelschung und Betrug -------------------------------------------------
_gruppe("1120 1121 1122 1160 502P", "250")
_gruppe("1110 1130 1135 1195 1197 1210 1242 1245", "26A")
_gruppe("1150 1151 1152", "26B")
_gruppe("1170 1185", "26C")   # 1185: das Statut ist "False Representation as
                              # Person Authorized to Enforce the Law" (ISP)
_gruppe("1101 1102 1187 1192", "26D")
_gruppe("1199", "26E")
_gruppe("0840 0841 0842 0843 1153 1154 1155 1156", "26F")
_gruppe("1240 1241", "26G")
_gruppe("1140", "270")
_gruppe("1200 1145 1147", "280")

# --- Betaeubungsmittel -----------------------------------------------------
_gruppe("1811 1812 1821 1822 1840 1850 1860 "
        "2010 2011 2012 2013 2014 2015 2016 2017 2018 2019 "
        "2020 2021 2022 2023 2024 2025 2026 2027 2028 2029 "
        "2030 2031 2032 2033 2034 2040 2050 2060 2070 2080 2090 "
        "2092 2093 2094 2095 1900", "35A")
_gruppe("2110 2111 2120 2160 2170", "35B")

# --- Sittlichkeitsdelikte, Pornografie ------------------------------------
_gruppe("1518 1535 1540 1541 1542", "370")
_gruppe("1519 1537 1582 1726 1581", "370")

# --- Gluecksspiel ----------------------------------------------------------
_gruppe("1651 1661", "39A")          # Teilnahme am Spiel
_gruppe("1610 1611 1620 1621 1622 1623 1624 1625 1626 1627 "
        "1630 1631 1632 1650 1680 1681 "
        "1690 1691 1692 1693 1694 1695 1696 1697", "39B")
_gruppe("1670", "39C")               # Game / Amusement Device
_gruppe("1633 1683 1684", "39D")     # Sports Tampering, Bestechung im Wettkampf

# --- Sexualstraftaeterregister --------------------------------------------
_gruppe("4650 4651 4652", "360")

# --- Bestechung ------------------------------------------------------------
_gruppe("3910", "510")
_gruppe("4810", "510")               # Compounding a Crime: Geld dafuer nehmen,
                                     # eine Tat nicht anzuzeigen (ISP)

# --- Waffendelikte ---------------------------------------------------------
_gruppe("141A 141B 141C 142A 142B 1435 143A 143B 143C 1440 1450 1460 "
        "1475 1476 1477 2900", "520")
_gruppe("1478 1479 1480", "520")     # Concealed Carry License Violation
_gruppe("1030 1035", "520")          # Besitz Spreng-/Brandvorrichtung
_gruppe("3200 4860 5007 5008", "520")   # 4740 Body Armor ist keine Waffe

# --- Tierquaelerei ---------------------------------------------------------
_gruppe("1682 501A", "720")

# --- Alkoholrecht ----------------------------------------------------------
_gruppe("2210 2220 2230 2240 2250 2251", "90G")

# --- Stoerung der oeffentlichen Ordnung -----------------------------------
# 720 ILCS 5/26-1 fasst unter Disorderly Conduct ausdruecklich auch den
# Falschalarm, die falsche Polizeimeldung und das Spaehen in eine Wohnung.
# NIBRS 90C ist entsprechend weit gefasst: Verhalten, das den oeffentlichen
# Frieden stoert oder das Sittlichkeitsempfinden verletzt.
_gruppe("0470 2840 2860 2870 2890 3100 3300", "90C")
_gruppe("1536 1570", "90C")          # Public Indecency
_gruppe("2825 2826 2830", "90C")     # Belaestigung per Telefon und elektronisch
_gruppe("1574", "90C")               # Fornication, ISP ist spezifischer

# --- Brandstiftung, Auffangzeile ------------------------------------------
_gruppe("5003", "200")               # Other Arson / Explosive Incident

# --- Ohne NIBRS-Entsprechung: Auffang 90Z ---------------------------------
_gruppe("1544 1565 1566 1572 1576 1578 1585", "90Z")
_gruppe("1710 1715 1720 1725 1755 1775 1780 1791", "90Z")
_gruppe("0584", "90Z")               # Verstoss gegen Kontaktverbot, nicht das Stalking
_gruppe("1230 1235 1255 1261 1262 1263", "90Z")
_gruppe("2091", "90Z")               # Forfeit Property
_gruppe("1640", "90Z")               # Register Federal Gambling Stamp
_gruppe("2895 3000", "90Z")
_gruppe("3710 3720 3730 3731 3740 3750 3751 3760 3770 3800 3920", "90Z")
_gruppe("3610 4310 4386 4387 4388 4389 4410 4420 4510 4625 "
        "4750 4800", "90Z")
_gruppe("4740", "90Z")               # Koerperschutz, keine Waffe (ISP)
_gruppe("5000 5001 5002 5009 500E 500N 5011 5013 501H 502R", "90Z")
_gruppe("5110 5111 5112 5120 5121 5122 5130 5131 5132", "90Z")


# ---------------------------------------------------------------------------
# Zeilen ohne Zuordnung: kein Delikt
# ---------------------------------------------------------------------------

NICHT_ZUGEORDNET = {
    "1481": "Entzug der Waffentragerlaubnis ist eine Verwaltungsmassnahme, "
            "kein Delikt; Chicago fuehrt die Zeile selbst als NON-CRIMINAL",
    "9901": "Sammelkennzeichen fuer haeusliche Gewalt, kein eigenes Delikt; "
            "index_code D, seit Jahren inaktiv",
}


# ---------------------------------------------------------------------------
# Ermessensentscheidungen - zwei Codes waren vertretbar
# ---------------------------------------------------------------------------

ERMESSEN = {
    "0475": "Battery of an Unborn Child ohne Waffenangabe; als einfache "
            "Koerperverletzung gewertet",
    "0760": "Chicago fuehrt es als Burglary, NIBRS zaehlt das Eindringen in ein "
            "Fahrzeug jedoch als 23F Theft From Motor Vehicle",
    "1206": "Nichtrueckgabe eines Mietfahrzeugs; NIBRS fuehrt das als "
            "Fahrzeugdiebstahl, nicht als Betrug",
    "1210": "Theft of Labor / Services als Erschleichen von Leistungen unter "
            "26A gefuehrt, nicht als Diebstahl",
    "1242": "Computer Fraud unter 26A gefuehrt, weil der Betrug die Tat ist; "
            "26G deckt den unbefugten Zugriff (1240, 1241)",
    "1581": "Non-Consensual Dissemination of Private Sexual Images als "
            "Verbreitung von Bildmaterial unter 370",
    "1750": "Child Abuse ohne Angabe von Waffe oder Verletzungsgrad; als "
            "einfache Koerperverletzung gewertet",
    "1753": "Sexual Assault of Child by Family Member: NIBRS setzt die "
            "Gewaltform vor die Verwandtschaft, deshalb 11A statt 36A",
    "1754": "wie 1753",
    "2090": "Alter / Forge Prescription unter 35A gefuehrt, weil das "
            "Betaeubungsmittel die Tat traegt, nicht die Faelschung",
    "2896": "Tire Deflation Device Deployment als Sachbeschaedigung gewertet",
    "3400": "Looting nach Illinois ist Betreten und Wegnahme im "
            "Katastrophenfall, damit 220",
    "4800": "Money Laundering: NIBRS fuehrt 26H, markiert ihn aber als nur von "
            "Bundes- und Stammesbehoerden meldbar; fuer Chicago bleibt 90Z",
    "2900": "Air Rifle wird von Chicago als Waffe gefuehrt, deshalb 520",
    # Artans Review vom 11.9. hat 0560 als falsch nachgewiesen (jetzt 13C).
    # Diese beiden folgen derselben Logik - Chicago fuehrt sie unter ASSAULT,
    # also als Drohung -, aber die ILCS-Tabelle kennt keine Zeile dazu. Ohne
    # Beleg wird nicht umgebucht, sondern benannt.
    "0545": "Chicago fuehrt es unter ASSAULT, was in Illinois die Drohung ohne "
            "Beruehrung meint; das spraeche fuer 13C. Die ILCS-Tabelle der ISP "
            "fuehrt keine Zeile zu diesem Kuerzel, deshalb bleibt es bei 13B",
    "0554": "wie 0545: Chicago fuehrt es unter ASSAULT, die ILCS-Tabelle der "
            "ISP kennt aber keine Zeile zu diesem Kuerzel",
    # Offene Frage, bewusst nicht stillschweigend entschieden: nach der
    # Bundesdefinition des Menschenhandels gilt ein Opfer unter 18 Jahren auch
    # ohne Noetigung als Fall von 64A. Die Technical Specification ist eine
    # reine Datenspezifikation und enthaelt keine Deliktdefinitionen, kann die
    # Frage also nicht belegen. Bis dahin folgt die Zuordnung Chicagos eigener
    # Einstufung: index_code N, also kein Indexdelikt.
    "1521": "Keeping Place of Juvenile Prostitution: 64A folgt aus 720-5/11-14.4, "
            "in dem Illinois das Delikt 2013 aufgehen liess. Die ISP fuehrt "
            "dieses Statut auf 64A, kennt zu diesem Kuerzel aber keine Zeile - "
            "die Zuordnung ist Schlussfolgerung, nicht Beleg",
    "1573": "ISP bezieht 720-5/11-1.50(b) auf Taeter unter 17 und Opfer 9 bis 17, "
            "also Statutory Rape. Chicagos Beschreibung nennt kein Alter, aber "
            "(b) ist die einzige Penetrationsvariante ohne Gewalt",
}


def lade_basis() -> list[dict[str, str]]:
    """Chicagos IUCR-Liste, bevorzugt vom Portal, sonst aus der Datei."""
    try:
        with urllib.request.urlopen(PORTAL, timeout=30) as antwort:
            roh = json.load(antwort)
        print(f"Portal: {len(roh)} Zeilen")
        return [
            {
                "iucr": r["iucr"].strip(),
                "primary_description": r["primary_description"].strip(),
                "secondary_description": r["secondary_description"].strip(),
                "index_code": r.get("index_code", "").strip(),
                "active": "true" if r["active"] in (True, "true") else "false",
            }
            for r in roh
        ]
    except (urllib.error.URLError, TimeoutError, OSError) as fehler:
        print(f"Portal nicht erreichbar ({fehler}); benutze {ZIEL.name}")
        with ZIEL.open(encoding="utf-8") as datei:
            return [
                {s: z[s] for s in
                 ("iucr", "primary_description", "secondary_description",
                  "index_code", "active")}
                for z in csv.DictReader(datei)
            ]


def arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Das Ziel laesst sich umlenken.

    Gebraucht wird das von ``tests/config/test_iucr_nibrs_mapping.py``: Der
    Test laesst das Werkzeug in ein temporaeres Verzeichnis schreiben und
    vergleicht mit der versionierten Datei. Ohne die Umlenkung muesste er die
    echte Konfiguration ueberschreiben und danach wiederherstellen - und bei
    einem Abbruch bliebe sie veraendert liegen.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ZIEL,
        help=f"Zieldatei (Vorgabe: {ZIEL.relative_to(PROJECT_ROOT)})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ziel = arguments(argv).output
    with CODELISTE.open(encoding="utf-8") as datei:
        amtlich = {z["nibrs_code"]: z for z in csv.DictReader(datei)}

    basis = sorted(lade_basis(), key=lambda z: z["iucr"])
    bekannt = {z["iucr"] for z in basis}

    fehlt = bekannt - set(ZUORDNUNG) - set(NICHT_ZUGEORDNET)
    ueber = (set(ZUORDNUNG) | set(NICHT_ZUGEORDNET)) - bekannt
    if fehlt or ueber:
        print(f"FEHLER: ohne Zuordnung {sorted(fehlt)}", file=sys.stderr)
        print(f"        unbekannter IUCR-Code {sorted(ueber)}", file=sys.stderr)
        return 1

    unbekannte_codes = {c for c in ZUORDNUNG.values() if c not in amtlich}
    if unbekannte_codes:
        print(f"FEHLER: kein NIBRS-Code der Fassung 2025: "
              f"{sorted(unbekannte_codes)}", file=sys.stderr)
        return 1

    zeilen = []
    for z in basis:
        iucr = z["iucr"]
        if iucr in NICHT_ZUGEORDNET:
            zeilen.append({**z, "ibr_code": "", "ibr_category": "", "match": "",
                           "mapped": "false", "note": NICHT_ZUGEORDNET[iucr]})
            continue
        code = ZUORDNUNG[iucr]
        if code == "90Z":
            herkunft = "nibrs_auffang"
        elif iucr in ERMESSEN:
            herkunft = "nibrs_ermessen"
        else:
            herkunft = "nibrs_definition"
        zeilen.append({
            **z,
            "ibr_code": code,
            "ibr_category": amtlich[code]["nibrs_description"].upper(),
            "match": herkunft,
            "mapped": "true",
            "note": ERMESSEN.get(iucr, ""),
        })

    ziel.parent.mkdir(parents=True, exist_ok=True)
    with ziel.open("w", newline="", encoding="utf-8") as datei:
        schreiber = csv.DictWriter(datei, fieldnames=SPALTEN)
        schreiber.writeheader()
        schreiber.writerows(zeilen)

    verteilung: dict[str, int] = {}
    for z in zeilen:
        verteilung[z["match"] or "(nicht zugeordnet)"] = \
            verteilung.get(z["match"] or "(nicht zugeordnet)", 0) + 1
    print(f"{ziel}: {len(zeilen)} Zeilen")
    for k, n in sorted(verteilung.items()):
        print(f"  {k:<22}{n:>4}")
    print(f"  verschiedene NIBRS-Codes: "
          f"{len({z['ibr_code'] for z in zeilen if z['ibr_code']})}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
