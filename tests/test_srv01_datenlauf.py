"""Haelt den auf ``srv01`` installierten Datenlauf und seinen Zeitplan fest.

Das Skript lag zuerst nur auf dem Server. Dadurch konnte weder die
Voll-/Delta-Verteilung noch der Aufruf aus dem Crontab gegen das Repository
geprueft werden. Besonders wichtig ist der zweite Montag: Ein Volllauf am
ersten Montag kollidiert in Monaten, die an einem Montag beginnen, mit dem
Restic-Vollrestore um 05:00.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "docker" / "srv01-datenlauf.sh"
CRONTAB = PROJECT_ROOT / "deploy" / "cron" / "urbancrime.crontab"


@pytest.mark.parametrize(
    ("day_of_month", "expected"),
    (
        (1, "delta"),
        (7, "delta"),
        (8, "full"),
        (14, "full"),
        (15, "delta"),
        (28, "delta"),
        (29, "skip"),
        (31, "skip"),
    ),
)
def test_der_zweite_montag_ist_der_einzige_volllauf(
        day_of_month, expected, benutzbares_bash):
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; mode_for_day "$2"',
            "--",
            str(SCRIPT),
            str(day_of_month),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == expected


def test_der_crontab_ruft_genau_das_versionierte_skript_auf():
    text = CRONTAB.read_text(encoding="utf-8")
    aktive_zeilen = [
        line for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith(("#", "SHELL=", "PATH="))
    ]
    assert aktive_zeilen == [
        "30 4 * * 1 /usr/bin/flock --wait 21600 "
        "/srv/docker/apps/urbancrime/logs/pipeline.lock "
        "/srv/docker/apps/urbancrime/docker/srv01-datenlauf.sh auto "
        ">> /srv/docker/apps/urbancrime/logs/scheduled-pipeline.log 2>&1"
    ]


def test_das_skript_prueft_den_veroeffentlichten_stand_am_ende():
    """Die Reihenfolge der Abschlussschritte, aus dem Skript gelesen.

    ``build_einstieg`` steht seit dem 12.10.2026 dazwischen und nicht
    irgendwo: Die Seite wird aus dem **eingesetzten** Release gebaut, also
    nach ``holen``, und vor ``pruefe_stand``, damit ein rotes Ergebnis den
    Lauf abbricht, nachdem alles Erzeugte da ist (FR-31).
    """
    text = SCRIPT.read_text(encoding="utf-8")
    schritte = (
        "orchestration.release holen aktuell --einsetzen",
        "serving.load_elasticsearch",
        "serving.build_kibana",
        "serving.build_einstieg",
        "serving.pruefe_stand",
    )
    positionen = [text.index(schritt) for schritt in schritte]
    assert positionen == sorted(positionen)


def test_die_startseite_wird_mit_den_serveradressen_gebaut():
    """Sonst stünden auf der ausgelieferten Seite ``localhost``-Verweise.

    Die Vorgabe des Erzeugers ist ``lokal`` - richtig fuer die Fassung, die im
    Repository liegt, und falsch fuer die, die ein Browser hinter Cloudflare
    Access oeffnet. Der Datenlauf muss die Umschaltung deshalb **nennen**;
    eine vergessene Flagge faellt sonst erst jemandem auf, der auf einen
    Knopf drueckt und in seinem eigenen Rechner landet.
    """
    text = SCRIPT.read_text(encoding="utf-8")
    zeile = next(z for z in text.splitlines() if "serving.build_einstieg" in z)
    assert "--adressen server" in zeile, (
        f"die Seite wird ohne Serveradressen gebaut: {zeile.strip()}"
    )
    assert "--ziel /app/startseite/" in zeile, (
        f"die Seite landet nicht im Datentraeger, den start ausliefert: "
        f"{zeile.strip()}"
    )


def test_der_datentraeger_wird_vor_dem_schreiben_geleert():
    """Docker befuellt einen leeren benannten Datentraeger aus dem Abbild.

    Am 12.10.2026 nachgestellt: Nach dem ersten Start von ``start`` liegen
    nginx' eigene ``index.html`` und ``50x.html`` im Datentraeger - das
    ``:ro`` auf der lesenden Seite verhindert das nicht. Ohne diesen Schritt
    bliebe ``50x.html`` auch nach dem Datenlauf liegen, und nginx liefert aus
    seiner Wurzel alles aus, was darin liegt.
    """
    text = SCRIPT.read_text(encoding="utf-8")
    leeren = text.index("find /app/startseite -mindepth 1 -delete")
    schreiben = text.index("serving.build_einstieg")
    assert leeren < schreiben, (
        "der Datentraeger wird nicht vor dem Schreiben geleert"
    )


# --------------------------------------------------------------------------
# Das Skript ruft elf Module auf, sieben davon mit Flaggen - beide muessen
# es geben
# --------------------------------------------------------------------------

#: Jeder ``python -m <modul> ... --flagge``-Aufruf im Skript, aus dem Text
#: gelesen statt hier gepflegt: Eine Liste von Hand waere die zweite
#: Wahrheit, die genau dann veraltet, wenn das Skript sich aendert.
AUFRUF = re.compile(
    r"python -m (?P<modul>[\w.]+)(?P<rest>(?:\s+\\\s*\n)?(?:[^\n|;]|\\\s*\n)*)"
)


def aufrufe() -> dict[str, set[str]]:
    """Modul -> die langen Flaggen, mit denen das Skript es aufruft."""
    text = SCRIPT.read_text(encoding="utf-8")
    gefunden: dict[str, set[str]] = {}
    for treffer in AUFRUF.finditer(text):
        modul = treffer.group("modul")
        flaggen = set(re.findall(r"--[a-z][a-z-]+", treffer.group("rest")))
        gefunden.setdefault(modul, set()).update(flaggen)
    return gefunden


@pytest.fixture(scope="module")
def skript_aufrufe() -> dict[str, set[str]]:
    gefunden = aufrufe()
    assert gefunden, f"keine 'python -m'-Aufrufe in {SCRIPT.name} gefunden"
    return gefunden


def hilfe(modul: str) -> str:
    """``--help`` des Moduls. Braucht weder Netz noch Schluessel.

    argparse beendet sich vor jeder Arbeit, deshalb laeuft das auch ohne
    ``CENSUS_API_KEY`` und auf einem Rechner ohne Daten.
    """
    lauf = subprocess.run(
        [sys.executable, "-m", modul, "--help"],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
    )
    assert lauf.returncode == 0, (
        f"'python -m {modul} --help' endet mit {lauf.returncode} - das Skript "
        f"auf srv01 ruft dieses Modul montags auf:\n{lauf.stderr[-600:]}"
    )
    return lauf.stdout


def test_jedes_aufgerufene_modul_gibt_es(skript_aufrufe):
    """Eine Umbenennung bricht den Montagslauf, nicht den Testlauf.

    Das ist dieselbe Falle, die ``AGENTS.md`` fuer die Notebooks nennt: Was
    nur woechentlich und unbeaufsichtigt laeuft, faellt erst auf, wenn es
    schon nicht mehr geht. Elf Modulpfade stehen in diesem Skript - seit dem
    12.10.2026 einer mehr, ``serving.build_einstieg`` -, und ohne diesen Test
    haelt sie nichts.
    """
    for modul in sorted(skript_aufrufe):
        hilfe(modul)


def test_jede_flagge_im_skript_gibt_es_auch(skript_aufrufe):
    """Eine Flagge, die es nicht gibt, laesst den Lauf sofort scheitern.

    Gepruefte Form am 12.10.2026: ``--full``, ``--mode``, ``--years``,
    ``--auslieferung``, ``--vintage``, ``--ohne-ingestion``, ``--jahre``,
    ``--einsetzen`` und, seit die Einstiegsseite mitgebaut wird,
    ``--adressen`` und ``--ziel`` - alle vorhanden. Der Test haelt das, damit
    eine Umbenennung in einem ``arguments()`` nicht erst am Montag
    auffaellt.
    """
    fehler: list[str] = []
    for modul, flaggen in sorted(skript_aufrufe.items()):
        if not flaggen:
            continue
        text = hilfe(modul)
        vorhanden = set(re.findall(r"--[a-z][a-z-]+", text))
        for flagge in sorted(flaggen - vorhanden):
            fehler.append(f"{modul} kennt {flagge} nicht")
    assert not fehler, "\n".join(fehler)


# --------------------------------------------------------------------------
# Der Betriebsblick wird auch bei einem Abbruch geschrieben
# --------------------------------------------------------------------------


def test_der_betriebsstand_haengt_an_einem_trap_und_nicht_am_erfolg():
    """Die ganze Idee von FR-30 steht und faellt daran.

    Am 12. und 15.10.2026 ist der Lauf hier gescheitert, und gewusst hat es
    niemand. Ein Zustand, der nur nach einem gruenen Lauf entsteht,
    beschreibt genau den Fall nicht, fuer den man ihn braucht - eine Zeile am
    Ende von ``main`` laeuft bei einem Abbruch gerade nicht.

    **Gepruefte Form statt Verhalten**, und der Grund ist genannt: Das Skript
    ruft ``/usr/bin/docker`` mit absolutem Pfad; ein Verhaltenstest braeuchte
    Docker und liefe damit nicht dort, wo die Suite laeuft. Drei Aussagen
    zusammen machen die Zusage aus dem Text ablesbar.
    """
    text = SCRIPT.read_text(encoding="utf-8")

    # 1. Der trap steht - und im ausfuehrenden Zweig, nicht darueber: Auf der
    #    obersten Ebene feuerte er, wenn ein Test das Skript nur einliest.
    zweig = text.index('if [[ "${BASH_SOURCE[0]}" == "$0" ]]')
    trap = text.find("trap betriebsstand EXIT")
    assert trap > zweig, (
        "kein 'trap betriebsstand EXIT' im ausfuehrenden Zweig - dann "
        "entsteht der Betriebsblick nur, wenn der Lauf durchlaeuft")

    # 2. Das Modul wird genau einmal **gerufen**. Gezaehlt werden Zeilen
    #    ohne Kommentarzeichen: Die Begruendung darueber nennt den Modulnamen
    #    auch, und die erste Fassung dieses Tests zaehlte sie mit.
    aufrufe = [z for z in text.splitlines()
               if "serving.betriebsstand" in z and not z.lstrip().startswith("#")]
    assert len(aufrufe) == 1, (
        f"{len(aufrufe)} Aufrufe - dann ist nicht mehr zu sehen, welcher "
        f"zaehlt: {aufrufe}")

    # 3. Und nicht aus ``main`` heraus: Von dort waere er wieder an den
    #    Erfolg gebunden, und der trap daneben wuerde ihn doppelt schreiben.
    # Der Ausschnitt endet an der schliessenden Klammer von ``main`` und
    # nicht am naechsten Funktionskopf: Zwischen beiden steht die
    # Begruendung, und die nennt den Namen. Die erste Fassung las sie mit und
    # meldete richtigen Code als Fehler.
    anfang = text.index("main() {")
    ende = anfang + text[anfang:].index("\n}\n")
    assert "betriebsstand" not in text[anfang:ende], (
        "betriebsstand wird aus main gerufen - dann haengt er wieder am "
        "Erfolg des Laufs")


def test_ein_fehler_im_betriebsstand_faellt_den_lauf_nicht():
    """Der Bericht ueber einen Lauf ist nicht der Lauf.

    Ohne ``|| true`` macht ein Fehler beim Schreiben der Metrikdatei aus
    einem gruenen Lauf nachtraeglich einen roten - und das Gegenteil von
    Betriebssicherheit.
    """
    text = SCRIPT.read_text(encoding="utf-8")
    block = text[text.index("betriebsstand() {"):]
    block = block[:block.index("\n}")]
    assert "|| true" in block, "dem Aufruf fehlt '|| true'"


# --------------------------------------------------------------------------
# Der Sicherungssatz (18.10.2026)
# --------------------------------------------------------------------------


def test_der_sicherungssatz_wird_nach_dem_release_geholt():
    """Reihenfolge ist hier Inhalt.

    Der Satz soll das Release tragen, das **jetzt** gilt. Stuende der Aufruf
    vor ``release holen aktuell``, sicherte er eine Woche lang das vorige -
    und niemand saehe es, denn vorhanden waere ja etwas.
    """
    skript = SCRIPT.read_text(encoding="utf-8")
    satz = skript.index("orchestration.sicherungssatz")
    release = skript.index("orchestration.release holen aktuell")
    ende = skript.index("run completed for")
    assert release < satz < ende, (
        f"der Sicherungssatz steht nicht zwischen dem Release und dem Ende "
        f"(Release {release}, Satz {satz}, Ende {ende})")


def test_ein_unvollstaendiger_satz_macht_den_lauf_nicht_rot():
    """Zwei Dinge, die auseinandergehalten gehoeren.

    Ein fehlender gepinnter Lauf ist ein Problem der **naechsten Sicherung**,
    nicht des gerade gelaufenen Datenlaufs. Waere er ein Abbruch, kaeme
    `set -Eeuo pipefail` zum Zug und ein gruener Lauf stuende am Ende rot da -
    und beim naechsten Mal schaltet jemand den Satz ab, nicht den Fehler.
    Gemeldet wird er trotzdem: mit Exitcode 1 aus dem Modul, einer Warnung
    hier und in `sicherungssatz.json`.
    """
    skript = SCRIPT.read_text(encoding="utf-8")
    zeile = next(z for z in skript.splitlines()
                 if "orchestration.sicherungssatz" in z and not z.strip().startswith("#"))
    block = skript[skript.index(zeile):skript.index(zeile) + 240]
    assert "||" in block, (
        f"der Aufruf faengt seinen Fehlschlag nicht ab: {block[:120]!r}")
    assert "WARNUNG" in block or "warn" in block.lower(), \
        "er faengt ihn ab, ohne etwas zu sagen - das ist schlimmer"


def test_der_satz_wird_geholt_und_nicht_nur_gezeigt():
    """Ohne ``--holen`` zeigt das Modul nur - dann liegt nichts im Volume."""
    skript = SCRIPT.read_text(encoding="utf-8")
    zeile = next(z for z in skript.splitlines()
                 if "orchestration.sicherungssatz" in z and not z.strip().startswith("#"))
    assert "--holen" in zeile, f"ohne --holen passiert nichts: {zeile.strip()!r}"
