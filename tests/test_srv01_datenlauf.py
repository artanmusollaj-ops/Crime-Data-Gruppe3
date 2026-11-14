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

    Seit dem 1.11.2026 (C-9) ohne ``load_elasticsearch`` und
    ``build_kibana``: Auf srv01 steht das Dashboard an ihrer Stelle, und das
    liest den Eimer selbst. Es muss laufen, bevor ``pruefe_stand`` es fragt.
    """
    text = SCRIPT.read_text(encoding="utf-8")
    schritte = (
        "compose up -d --wait dashboard",
        "orchestration.release holen aktuell --einsetzen",
        "serving.build_einstieg",
        "serving.pruefe_stand",
    )
    positionen = [text.index(schritt) for schritt in schritte]
    assert positionen == sorted(positionen)
    for weg in ("serving.load_elasticsearch", "serving.build_kibana",
                "elasticsearch kibana"):
        assert weg not in text, f"der Serverlauf ruft noch {weg!r}"


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
# Das Skript ruft Module auf, die meisten mit Flaggen - beide muessen es
# geben
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
    schon nicht mehr geht. Die Modulpfade stehen nur in diesem Skript - seit
    dem 12.10.2026 mit ``serving.build_einstieg``, seit dem 1.11.2026 ohne
    die beiden Elastic-Schritte -, und ohne diesen Test haelt sie nichts.
    Gezaehlt wird hier bewusst nicht: Hier stand "elf", als es fuenfzehn
    waren.
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


def test_die_drift_wird_nach_dem_release_gemessen():
    """FR-30 nennt sie, und sie braucht den fertigen Stand.

    ``orchestration.drift`` haelt die dokumentierten Zahlen gegen das
    **Gebaute**. Vor dem Release gemessen, waere es der Stand von letzter
    Woche - und die Zahl sagte dann etwas ueber nichts.
    """
    skript = SCRIPT.read_text(encoding="utf-8")
    drift = skript.index("orchestration.drift")
    release = skript.index("orchestration.release holen aktuell")
    ende = skript.index("run completed for")
    assert release < drift < ende, (
        f"die Drift steht nicht zwischen dem Release und dem Ende "
        f"(Release {release}, Drift {drift}, Ende {ende})")


def test_die_drift_faellt_den_lauf_nicht():
    """Sonst ist der Lauf jede Woche rot, und dann schaut niemand mehr hin.

    Die Quellen bewegen sich woechentlich; eine Drift ueber der Toleranz ist
    eine Aufgabe fuer die Dokumente und kein Vorfall im Betrieb. Genau das
    sagt ``orchestration.drift`` in seinem eigenen Docstring: *ein Alarm,
    der immer klingelt, ist keiner.*
    """
    skript = SCRIPT.read_text(encoding="utf-8")
    zeile = next(z for z in skript.splitlines()
                 if "orchestration.drift" in z and not z.strip().startswith("#"))
    block = skript[skript.index(zeile):skript.index(zeile) + 220]
    assert "--nur-melden" in zeile, (
        f"ohne --nur-melden faellt der Lauf an der Drift: {zeile.strip()!r}")
    assert "||" in block, "und der Aufruf faengt seinen Fehlschlag nicht ab"


def test_die_drift_wird_dorthin_geschrieben_wo_der_blick_sie_liest():
    """Zwei Module, ein Ort - und der Ort steht in beiden."""
    from serving.betriebsstand import DRIFT

    skript = SCRIPT.read_text(encoding="utf-8")
    zeile = next(z for z in skript.splitlines()
                 if "orchestration.drift" in z and not z.strip().startswith("#"))
    assert f"--json /app/data/{DRIFT}" in zeile, (
        f"der Bericht muss als {DRIFT} neben dem Laufprotokoll liegen, "
        f"dort liest ihn serving.betriebsstand: {zeile.strip()!r}")


# --------------------------------------------------------------------------
# Eine gescheiterte Quelle wird nachgefasst (12.11.2026)
# --------------------------------------------------------------------------


def laden_mit(tmp_path: Path, fehlversuche: dict[str, int], *schritte: str):
    """``laden`` mit falschem ``pipeline`` und ``sleep``; Spur und Exitcode zurueck.

    Jeder Schritt scheitert so oft, wie ``fehlversuche`` fuer sein Modul sagt.
    """
    spur = tmp_path / "spur.txt"
    pausen = tmp_path / "pausen.txt"
    zaehler = tmp_path / "zaehler"
    zaehler.mkdir()
    # Kein ``declare -A``: Das bash 3.2 auf macOS kennt es nicht.
    grenzen = " ".join(f"{m}) echo {n};;" for m, n in fehlversuche.items())
    programm = f"""
        source "$1"
        grenze() {{ case "$1" in {grenzen} *) echo 0;; esac; }}
        pipeline() {{
            local modul="$3" n=0
            [[ -f "{zaehler.as_posix()}/$modul" ]] && n=$(cat "{zaehler.as_posix()}/$modul")
            n=$((n + 1)); echo "$n" > "{zaehler.as_posix()}/$modul"
            echo "$*" >> "{spur.as_posix()}"
            (( n > $(grenze "$modul") ))
        }}
        sleep() {{ echo "$1" >> "{pausen.as_posix()}"; }}
        laden "${{@:2}}"
    """
    lauf = subprocess.run(["bash", "-c", programm, "--", SCRIPT.as_posix(), *schritte],
                          capture_output=True, text=True)
    lesen = lambda p: p.read_text().split("\n")[:-1] if p.exists() else []  # noqa: E731
    return lauf, lesen(spur), lesen(pausen)


def test_eine_gescheiterte_quelle_haelt_die_anderen_nicht_auf(tmp_path, benutzbares_bash):
    lauf, spur, pausen = laden_mit(
        tmp_path, {"chicago": 1},
        "python -m chicago --year 2021 --full", "python -m detroit --mode full")
    assert lauf.returncode == 0, lauf.stderr
    assert spur == ["python -m chicago --year 2021 --full", "python -m detroit --mode full",
                    "python -m chicago --year 2021 --full"]
    assert pausen == ["1800"]


def test_nach_dem_letzten_versuch_endet_laden_mit_eins(tmp_path, benutzbares_bash):
    lauf, spur, pausen = laden_mit(
        tmp_path, {"chicago": 9}, "python -m chicago --year 2021", "python -m detroit")
    assert lauf.returncode == 1
    assert spur.count("python -m chicago --year 2021") == 3
    assert spur.count("python -m detroit") == 1
    assert pausen == ["1800", "3600"]
    assert "python -m chicago --year 2021" in lauf.stderr


def test_ohne_fehler_wird_nicht_gewartet(tmp_path, benutzbares_bash):
    lauf, spur, pausen = laden_mit(tmp_path, {}, "python -m detroit")
    assert lauf.returncode == 0 and spur == ["python -m detroit"] and pausen == []


def test_der_volllauf_laedt_ueber_laden_und_leitet_danach_ab():
    """Kein Quellaufruf mehr ausserhalb von ``laden`` - sonst bricht er wieder alles ab."""
    text = SCRIPT.read_text(encoding="utf-8")
    voll = text[text.index("    full)"):text.index("    delta)")]
    assert not re.search(r"^\s*pipeline python -m \w+_pipeline", voll, re.M)
    assert voll.index('laden "${schritte[@]}"') < voll.index("orchestration.run_all")
    for modul in ("chicago_pipeline.download_chicago", "detroit_pipeline.extract_detroit",
                  "census_pipeline.download_tiger", "census_pipeline.download_acs",
                  "weather_pipeline.download_noaa"):
        assert f'schritte+=("python -m {modul}' in voll, modul


def test_skript_und_controller_fassen_gleich_nach():
    import run_all as ra
    text = SCRIPT.read_text(encoding="utf-8")
    sekunden = re.search(r"^NACHFASSEN_SEKUNDEN=\(([\d ]+)\)", text, re.M).group(1).split()
    assert [int(s) for s in sekunden] == [int(m * 60) for m in ra.NACHFASSEN_MINUTEN]


def test_beginn_und_ende_tragen_einen_zeitstempel():
    """FR-16: Wie lange ein Montagslauf dauert, sagt das Protokoll selbst.

    Bis zum 14.11.2026 trugen die Markerzeilen keine Zeit, und die letzten
    Schritte (Drift, Sicherungssatz) auch nicht - die Dauer liess sich nur
    bis zur letzten Python-Logzeile messen. Gemessen wurde damals 4,7 bis
    5,1 Minuten je Delta-Lauf; das wahre Ende lag etwas spaeter.
    """
    text = SCRIPT.read_text(encoding="utf-8")
    zeit = '$(date +%Y-%m-%dT%H:%M:%S%z)'
    assert f'echo "Urban Crime: ${{mode}} run started at {zeit}"' in text
    assert f'echo "Urban Crime: ${{mode}} run completed for ${{YEAR_RANGE}} at {zeit}"' in text
    # Der Beginn steht vor der Vorpruefung: Auch ein Lauf, der dort scheitert,
    # hat dann eine Startzeit.
    assert text.index("run started at") < text.index("orchestration.vorpruefung")
    # Und das Ende auch bei einem Abbruch: im EXIT-trap, mit Exitcode.
    trap = text[text.index("betriebsstand() {"):text.index("betriebsstand() {") + 400]
    assert f'run ended with exit ${{rc}} at {zeit}' in trap


@pytest.mark.parametrize(("tag", "erwartet"), [
    ("01", "--nachfassen"), ("1", "--nachfassen"), ("02", ""), ("08", ""), ("15", ""), ("31", ""),
])
def test_am_monatsersten_wird_nicht_nachgefasst(tag, erwartet, benutzbares_bash):
    """FR-16: Am Ersten beginnt um 05:00 der Restore-Test. Ein Delta-Lauf, der
    eine Quelle nach 30 und 60 Minuten nachfasst, liefe bis nach 06:00.
    ``--nachfassen`` ohne Werte schaltet das Nachfassen in run_all ab."""
    result = subprocess.run(
        ["bash", "-c", 'source "$1"; delta_nachfassen "$2"', "--", str(SCRIPT), tag],
        check=True, capture_output=True, text=True,
    )
    assert result.stdout.strip() == erwartet
    text = SCRIPT.read_text(encoding="utf-8")
    delta = text[text.index("    delta)"):text.index("    *)")]
    assert '$(delta_nachfassen "$(date +%d)")' in delta


def test_ohne_werte_schaltet_nachfassen_ab(monkeypatch):
    """Die Zusage, auf der der Monatserste ruht: Der echte Parser von
    ``run_all`` liest ``--nachfassen`` ohne Werte als leere Liste - und
    ``main`` reicht sie als ``nachfassen=tuple(...)`` an ``lauf`` durch, dessen
    Schleife ``(0, *nachfassen)`` dann genau eine Runde faehrt."""
    from orchestration import run_all as ra
    monkeypatch.setattr(sys, "argv", ["run_all", "--jahre", "2024", "--nachfassen"])
    assert ra.arguments().nachfassen == []
    monkeypatch.setattr(sys, "argv", ["run_all", "--jahre", "2024"])
    assert tuple(ra.arguments().nachfassen) == ra.NACHFASSEN_MINUTEN


def test_der_naechste_montag_am_ersten_steht_richtig_in_den_dokumenten():
    """Dieselbe Aussage steht in drei Dokumenten (AGENTS.md: der Waechter
    muss alle erfassen). Gerechnet ab dem Tag der Messung, 14.11.2026."""
    from datetime import date, timedelta
    tag = date(2026, 11, 15)
    while not (tag.day == 1 and tag.weekday() == 0):
        tag += timedelta(days=1)
    text = f"{tag.day}.{tag.month}.{tag.year}"
    assert text == "1.2.2027"
    for doc in ("docs/intern/fr-stand.md", "docs/intern/AENDERUNGEN.md",
                "docs/storage-architektur.md"):
        assert text in (PROJECT_ROOT / doc).read_text(encoding="utf-8"), doc
