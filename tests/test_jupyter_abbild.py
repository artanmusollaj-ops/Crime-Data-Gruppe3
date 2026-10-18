"""Prueft ``Dockerfile.jupyter``, den Einstieg und die Vorlagen - das Abbild
der Analyse.

Dieselbe Lage wie bei ``tests/test_abbild.py``: Bauen laesst sich hier nichts,
ein Pull Request hat weder Docker-Daemon noch Netz. Geprueft wird deshalb,
was im Abbild **falsch sein kann, ohne beim Bauen aufzufallen**:

* ein Notebook, das mitkommt, obwohl es nicht mitkommen darf
  (``36_hypothesen`` misst Hardware und startet Neubauten - E9),
* eine Wurzel, die nicht der Arbeitsbereich ist: Dann liegen ``config/``,
  ``src/`` und der ganze Bestand im Dateibaum des Browsers,
* ein Arbeitsbereich an der falschen Stelle: Die Notebooks suchen ihre
  Projektwurzel **eine Ebene ueber** dem Arbeitsverzeichnis, und ein
  Arbeitsbereich daneben liesse jedes von ihnen in der ersten Zelle
  abbrechen,
* ein ungepinntes ``jupyterlab``, das die Pins des Lockfiles mitnimmt,
* ein Token oder ein Schluessel im Abbild - der laeuft bestens und ist in
  jeder Schicht lesbar.

**Das Startskript wird ausgefuehrt, nicht gelesen.** Vier Zeilen der
I/O-Matrix des Plans sind Verhalten (leerer Arbeitsbereich, belegter
Arbeitsbereich, bearbeitete Vorlage, fehlender Arbeitsbereich), und ein Test,
der dafuer nur nach Zeichenketten sucht, haelt die Zusage nicht. Gebraucht
wird dafuer nur eine POSIX-Shell; auf Windows ueberspringen sich diese Tests.

Der Bau selbst steht in der Verifikation des Plans, nicht hier.
"""

from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess

import pytest

from tests.test_srv01_compose import lade


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = PROJECT_ROOT / "Dockerfile.jupyter"
GRUNDABBILD = PROJECT_ROOT / "Dockerfile"
DOCKERIGNORE = PROJECT_ROOT / ".dockerignore"
EINSTIEG = PROJECT_ROOT / "docker" / "jupyter-einstieg.sh"
SERVERKONFIG = PROJECT_ROOT / "docker" / "jupyter_server_config.py"
COMPOSE = PROJECT_ROOT / "docker-compose.srv01.yml"
DOKUMENT = PROJECT_ROOT / "docs" / "storage-architektur.md"
LOCKFILE = PROJECT_ROOT / "requirements.lock"

#: Die drei **lesenden** Notebooks. Aus dem Addendum, Befund "Die Notebooks im
#: Container": 35 laeuft ohne alles, 34 und 37 brauchen gebaute Daten. Netz
#: braucht keines von ihnen, und keines schreibt in den Bestand.
VORLAGEN = ("34_gold_sternschema", "35_kontrollen", "37_quellbewegung")

#: Das eine, das ausdruecklich nicht mitkommt (E9). Es misst Hardware und
#: startet Silber-, Gold- und Serving-Neubauten als Unterprozesse.
AUSGESCHLOSSEN = "36_hypothesen"

#: Keine Shell, keine Verhaltenspruefung - auf Windows laeuft die Suite
#: ebenfalls, und ``sh`` gibt es dort nicht.
OHNE_SHELL = pytest.mark.skipif(
    os.name == "nt" or shutil.which("sh") is None,
    reason="der Einstieg ist ein POSIX-Skript; ohne sh laesst er sich nicht ausfuehren",
)


# --------------------------------------------------------------------------
# Die beiden Dateien lesen
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def dockerfile() -> str:
    if not DOCKERFILE.is_file():
        pytest.fail(f"{DOCKERFILE} fehlt - das Abbild der Analyse beginnt damit")
    return DOCKERFILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def einstieg() -> str:
    if not EINSTIEG.is_file():
        pytest.fail(f"{EINSTIEG} fehlt - ohne ihn liegt keine Vorlage im Arbeitsbereich")
    return EINSTIEG.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def serverkonfig() -> str:
    if not SERVERKONFIG.is_file():
        pytest.fail(f"{SERVERKONFIG} fehlt - sie setzt die Wurzel des Servers")
    return SERVERKONFIG.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def jupyter_dienst() -> dict:
    """Der Dienst ``jupyter`` aus der Beschreibung des Serverbetriebs."""
    dienste = lade(COMPOSE.read_text(encoding="utf-8"))["services"]
    assert "jupyter" in dienste, "docker-compose.srv01.yml kennt keinen Jupyter-Dienst"
    return dienste["jupyter"]


@pytest.fixture(scope="module")
def muster() -> list[str]:
    """Die Zeilen der ``.dockerignore`` ohne Kommentare und Leerzeilen."""
    return [z.strip() for z in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
            if z.strip() and not z.strip().startswith("#")]


def kopien(dockerfile: str) -> list[tuple[list[str], str]]:
    """Jedes ``COPY`` als (Quellen, Ziel) - Fortsetzungszeilen zusammengefasst.

    Die drei Notebooks stehen in **einem** ``COPY`` ueber vier Zeilen; ein
    Leser, der Zeile fuer Zeile liest, saehe davon nur die erste.
    """
    ganze = dockerfile.replace("\\\n", " ")
    gefunden = []
    for zeile in re.findall(r"^COPY\s+(.+)$", ganze, re.M):
        teile = [t for t in zeile.split() if not t.startswith("--")]
        gefunden.append((teile[:-1], teile[-1]))
    return gefunden


def arbeitsbereich(dockerfile: str) -> str:
    """Der Pfad, den das Abbild anlegt und fuer jeden beschreibbar macht."""
    treffer = re.search(r"mkdir -p (\S+) && chmod 0777 \1", dockerfile)
    assert treffer, (
        "Dockerfile.jupyter legt keinen fuer jeden Benutzer beschreibbaren "
        "Arbeitsbereich an (erwartet: mkdir -p <pfad> && chmod 0777 <pfad>)"
    )
    return treffer.group(1)


def vorlagenort(dockerfile: str) -> str:
    """Das Verzeichnis, in das die Notebooks als Vorlagen kopiert werden."""
    ziele = {ziel for quellen, ziel in kopien(dockerfile)
             if any("notebooks/" in q for q in quellen)}
    assert len(ziele) == 1, f"die Vorlagen landen nicht an genau einem Ort: {ziele}"
    return ziele.pop().rstrip("/")


# --------------------------------------------------------------------------
# Die Grundlage: das Strecken-Abbild, nicht eine zweite Abhaengigkeitsliste
# --------------------------------------------------------------------------


def test_das_abbild_setzt_auf_dem_strecken_abbild_auf(dockerfile):
    """Und zwar ueber ein ``ARG``, das vor dem ``FROM`` steht.

    Ohne das Argument liesse sich dieselbe Datei nicht fuer den lokalen Bau
    und fuer die per Digest gepinnte Adresse aus der Registry benutzen - und
    genau diesen Weg nimmt das Abbild (gebaut auf dem Entwicklungsrechner,
    dann geschoben).
    """
    arg = re.search(r"^ARG BASIS=(\S+)", dockerfile, re.M)
    assert arg, "kein 'ARG BASIS=' - die Grundlage waere fest verdrahtet"
    frm = re.search(r"^FROM \$\{BASIS\}", dockerfile, re.M)
    assert frm, "das FROM benutzt das Argument BASIS nicht"
    assert arg.start() < frm.start(), (
        "ARG BASIS steht nach dem FROM - dort gilt es nicht mehr fuer die "
        "Wahl des Grundabbilds"
    )


def test_die_grundlage_ist_das_abbild_der_strecke(dockerfile, jupyter_dienst):
    """Die Vorgabe muss das Abbild sein, das der Verbund als Strecke laufen laesst.

    Sonst zeigt das Analyse-Abbild Zahlen, die eine andere Strecke erzeugt hat
    - und der Unterschied faellt nirgends auf.
    """
    vorgabe = re.search(r"^ARG BASIS=(\S+)", dockerfile, re.M).group(1)
    dienste = lade(COMPOSE.read_text(encoding="utf-8"))["services"]
    treffer = re.fullmatch(r"\$\{PIPELINE_IMAGE:-(\S+)\}", dienste["pipeline"]["image"])
    assert treffer, f"unerwartete Abbildangabe der Strecke: {dienste['pipeline']['image']}"
    assert vorgabe == treffer.group(1), (
        f"Dockerfile.jupyter setzt auf {vorgabe} auf, der Verbund laesst "
        f"{treffer.group(1)} als Strecke laufen"
    )


def test_jupyterlab_ist_gepinnt(dockerfile):
    """Eine Fassung je Abbild - nicht "was am Bautag gerade neu ist"."""
    assert re.search(r'"jupyterlab==\$\{JUPYTERLAB\}"', dockerfile), (
        "jupyterlab wird nicht ueber ein Argument installiert"
    )
    arg = re.search(r"^ARG JUPYTERLAB=(\S+)", dockerfile, re.M)
    assert arg, "kein 'ARG JUPYTERLAB=' - die Fassung waere nicht benennbar"
    assert re.fullmatch(r"\d+\.\d+\.\d+", arg.group(1)), (
        f"jupyterlab=={arg.group(1)} ist keine exakte Fassung - gepinnt heisst "
        "eine Zahl, kein Bereich"
    )
    for lose in (">=", "~=", "<", "*"):
        assert f"jupyterlab{lose}" not in dockerfile, (
            f"jupyterlab{lose}... - ein Bereich statt eines Pins"
        )


def test_das_lockfile_bleibt_die_eine_wahrheit(dockerfile):
    """``-c requirements.lock``: Der Server darf keinen Pin verschieben.

    Ohne die Nebenbedingung zieht pip beim Aufloesen der Server-Pakete
    jinja2, tornado, traitlets, nbconvert oder nbformat mit - und das
    Analyse-Abbild rechnete mit anderen Paketen als die Strecke, deren Zahlen
    es zeigt. Eine **zweite** Abhaengigkeitsliste waere die andere, schlechtere
    Antwort: zwei Wahrheiten.
    """
    installationen = re.findall(r"pip install[^\n]*(?:\\\n[^\n]*)*", dockerfile)
    assert installationen, "Dockerfile.jupyter installiert nichts"
    for zeile in installationen:
        assert re.search(r"(-c|--constraint) \S*requirements\.lock", zeile), (
            f"Installation ohne Nebenbedingung aus requirements.lock: {zeile!r}"
        )
    quellen = [q for quellen, _ in kopien(dockerfile) for q in quellen]
    weitere = [q for q in quellen
               if (q.endswith((".txt", ".lock")) and PurePosixPath(q).name != "requirements.lock")]
    assert not weitere, f"eine zweite Abhaengigkeitsliste im Abbild: {weitere}"


def test_der_server_fehlt_im_lockfile_und_deshalb_dieses_abbild(dockerfile):
    """Die Begruendung des ganzen Abbilds, nachgemessen.

    Das Strecken-Abbild traegt ``ipykernel`` und ``nbconvert`` - aber keinen
    Server. Stuende ``jupyterlab`` eines Tages im Lockfile, waere diese Datei
    kein zweites Abbild mehr wert, und dieser Test sagt es.
    """
    lock = LOCKFILE.read_text(encoding="utf-8").lower()
    assert "\nipykernel==" in lock, "ipykernel fehlt im Lockfile - dann stimmt die Lage nicht"
    for paket in ("jupyterlab==", "jupyter_server==", "jupyter-server=="):
        assert paket not in lock, (
            f"{paket} steht im Lockfile - dann bringt das Strecken-Abbild den "
            "Server schon mit, und dieses Abbild braucht ihn nicht nachzulegen"
        )


# --------------------------------------------------------------------------
# Die Vorlagen - und das eine, das nicht mitkommt
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", VORLAGEN)
def test_jede_lesende_vorlage_kommt_mit(dockerfile, name):
    """Die drei aus dem Addendum, einzeln - und sie muessen es wirklich geben."""
    quellen = [q for quellen, _ in kopien(dockerfile) for q in quellen]
    erwartet = f"notebooks/{name}.ipynb"
    assert erwartet in quellen, f"{erwartet} wird nicht ins Abbild kopiert"
    assert (PROJECT_ROOT / erwartet).is_file(), (
        f"{erwartet} steht im Dockerfile, liegt aber nicht im Repository - "
        "der Bau braeche ab"
    )


def test_hypothesen_kommt_nicht_mit(dockerfile):
    """E9: Es misst Hardware und startet Neubauten als Unterprozesse.

    Auf einer geteilten, auslagernden Maschine misst es das Rauschen der
    Nachbarn, und 768 MiB sprengt es dabei. Der Ausschluss ist eine
    Entscheidung und kein Versehen - deshalb muss das Notebook im Repository
    liegen **und** im Abbild fehlen.
    """
    assert (PROJECT_ROOT / "notebooks" / f"{AUSGESCHLOSSEN}.ipynb").is_file(), (
        f"{AUSGESCHLOSSEN} gibt es nicht mehr - dann gehoert dieser Test weg "
        "und nicht sein Gegenstand"
    )
    quellen = [q for quellen, _ in kopien(dockerfile) for q in quellen]
    assert not [q for q in quellen if AUSGESCHLOSSEN in q], (
        f"{AUSGESCHLOSSEN} wird ins Abbild kopiert - E9 verlangt das Gegenteil"
    )
    assert AUSGESCHLOSSEN in dockerfile, (
        f"{AUSGESCHLOSSEN} wird nirgends erwaehnt - ein stiller Ausschluss "
        "sieht in drei Wochen wie ein vergessener aus"
    )


@pytest.mark.parametrize("name", VORLAGEN)
def test_jede_vorlage_ist_im_baukontext_freigestellt(muster, name):
    """``.dockerignore`` haelt ``notebooks/`` draussen - fuer das Strecken-Abbild
    richtig, fuer dieses falsch.

    Fehlt die Freistellung, scheitert der Bau mit "file not found" an einer
    Datei, die es offensichtlich gibt. Geprueft wird die Form, die Docker
    versteht: die Datei einzeln, mit ``!``.
    """
    assert "notebooks/" in muster or "notebooks" in muster, (
        "notebooks/ steht nicht mehr in .dockerignore - dann gehoeren die drei "
        "Freistellungen weg, sonst taeuschen sie eine Regel vor"
    )
    assert f"!notebooks/{name}.ipynb" in muster, (
        f"notebooks/{name}.ipynb ist nicht freigestellt - der Bau des "
        "Analyse-Abbilds braeche an dieser Datei ab"
    )


def test_keine_freistellung_holt_mehr_als_die_drei(muster):
    """Eine Ausnahme fuer den ganzen Ordner waere bequem und falsch.

    Dann lage ``36_hypothesen`` im Baukontext, und zwischen "liegt im
    Kontext" und "liegt im Abbild" steht nur noch eine Zeile, die jemand
    aendert.
    """
    freigestellt = sorted(z for z in muster if z.startswith("!notebooks"))
    assert freigestellt == sorted(f"!notebooks/{n}.ipynb" for n in VORLAGEN), (
        f"freigestellt sind {freigestellt} - erwartet sind genau die drei "
        "lesenden Notebooks"
    )


def test_die_vorlagen_liegen_neben_dem_arbeitsbereich_und_sind_nur_lesbar(dockerfile):
    """Vorlage heisst: Die Fassung im Abbild bleibt die ausgelieferte.

    Und sie liegt **nicht** im Arbeitsbereich: Der ist ein Datentraeger und
    ueberdeckte beim Start alles, was das Abbild dort liegen hat.
    """
    ort = vorlagenort(dockerfile)
    assert ort != arbeitsbereich(dockerfile), (
        "die Vorlagen liegen im Arbeitsbereich - der eingehaengte Datentraeger "
        "verdeckt sie beim ersten Start"
    )
    assert re.search(rf"chmod -R a=rX {re.escape(ort)}\b", dockerfile), (
        f"{ort} wird nicht schreibgeschuetzt - wer eine Vorlage bearbeitet, "
        "aenderte dann die ausgelieferte Fassung"
    )


# --------------------------------------------------------------------------
# Die Wurzel ist der Arbeitsbereich - an drei Stellen dieselbe
# --------------------------------------------------------------------------


def test_die_wurzel_des_servers_ist_der_arbeitsbereich(dockerfile, serverkonfig):
    """Nicht ``/app``: Dort liegen ``config/``, ``src/`` und der ganze Bestand.

    Die Zusage steht in der Konfiguration des Abbilds und nicht nur im
    Startbefehl - ein ueberschriebenes ``command`` (der Verbund tut genau
    das) darf sie nicht aufheben.
    """
    treffer = re.search(r'c\.ServerApp\.root_dir\s*=\s*"([^"]+)"', serverkonfig)
    assert treffer, "die Konfiguration setzt ServerApp.root_dir nicht"
    assert treffer.group(1) == arbeitsbereich(dockerfile), (
        f"die Wurzel ist {treffer.group(1)}, der Arbeitsbereich "
        f"{arbeitsbereich(dockerfile)}"
    )
    assert re.search(r"^COPY docker/jupyter_server_config\.py \S*etc/jupyter/",
                     dockerfile, re.M), (
        "die Konfiguration wird nicht in ein Jupyter-Konfigurationsverzeichnis "
        "kopiert - dann liest der Server sie nie"
    )


def test_der_verbund_haengt_den_arbeitsbereich_genau_dorthin(dockerfile, jupyter_dienst):
    """Drei Stellen nennen denselben Pfad; zwei davon reichen nicht.

    Der Datentraeger, der Startbefehl und das Abbild muessen sich einig sein -
    sonst startet der Server in einem leeren Verzeichnis, das niemandem
    gehoert, und die Vorlagen liegen daneben.
    """
    bereich = arbeitsbereich(dockerfile)
    eingehaengt = [v for v in jupyter_dienst["volumes"]
                   if v.rsplit(":", 1)[-1].rstrip("/") == bereich
                   or v.endswith(f":{bereich}")]
    assert eingehaengt, (
        f"kein Datentraeger auf {bereich} - der Arbeitsbereich waere nach dem "
        f"Neustart leer. Eingehaengt ist: {jupyter_dienst['volumes']}"
    )
    assert not eingehaengt[0].endswith(":ro"), (
        f"{eingehaengt[0]} ist schreibgeschuetzt - dann laesst sich kein "
        "Notebook speichern"
    )
    befehl = jupyter_dienst.get("command", "")
    treffer = re.search(r"--ServerApp\.root_dir=([^\"',\s]+)", befehl)
    assert treffer, f"der Startbefehl nennt die Wurzel nicht: {befehl!r}"
    assert treffer.group(1) == bereich, (
        f"der Startbefehl setzt die Wurzel auf {treffer.group(1)}, der "
        f"Arbeitsbereich ist {bereich}"
    )


def test_der_arbeitsbereich_liegt_eine_ebene_unter_der_projektwurzel(dockerfile):
    """Gemessen an den Notebooks, nicht behauptet.

    Alle drei Vorlagen suchen ihre Projektwurzel beim Arbeitsverzeichnis und
    **eine** Ebene darueber, erkannt an ``config/``. Ein Arbeitsbereich
    daneben (``/arbeit``) liesse jedes von ihnen in der ersten Zelle mit
    "Projektwurzel nicht gefunden" abbrechen - und zwar erst im Browser, nach
    dem Bau, nach dem Schieben, auf dem Server.
    """
    wurzel = re.search(r"^ENV PROJECT_ROOT=(\S+)",
                       GRUNDABBILD.read_text(encoding="utf-8"), re.M)
    assert wurzel, "das Grundabbild setzt PROJECT_ROOT nicht mehr"
    bereich = arbeitsbereich(dockerfile)
    # **PurePosixPath, nicht Path**: Das sind Pfade *im Container*, und der
    # ist Linux. ``Path`` ist auf Windows ``WindowsPath``, dort wird aus
    # ``/app/arbeit`` die Eltern ``\app`` - genau daran fiel dieser Test am
    # 17.10.2026 auf dem Windows-Laeufer um, obwohl das Dockerfile richtig
    # ist. Die Konvention des Containers gehoert nicht an die des Laeufers.
    assert str(PurePosixPath(bereich).parent) == wurzel.group(1), (
        f"{bereich} liegt nicht unmittelbar unter {wurzel.group(1)} - die "
        "Wurzelprobe der Notebooks greift dann nicht"
    )
    for name in VORLAGEN:
        quelle = json.loads(
            (PROJECT_ROOT / "notebooks" / f"{name}.ipynb").read_text(encoding="utf-8"))
        text = "\n".join("".join(z["source"]) for z in quelle["cells"]
                         if z["cell_type"] == "code")
        assert "Path.cwd()" in text, f"{name}: keine Wurzelprobe am Arbeitsverzeichnis"
        assert text.count("PROJECT_ROOT = PROJECT_ROOT.parent") == 1, (
            f"{name} probiert nicht genau eine Ebene nach oben - dann passt "
            "der Arbeitsbereich eine Ebene unter der Wurzel nicht mehr"
        )


def test_die_gesundheitspruefung_braucht_kein_token(jupyter_dienst):
    """``/api/status`` ist die naheliegende Probe und die falsche.

    Am 6.10.2026 im gebauten Abbild gemessen (jupyter-server 2.21.1):
    ``/api/status`` antwortet **ohne Token mit 403**, ``/login`` mit 200. Mit
    der naheliegenden Probe waere der Dienst dauerhaft "unhealthy", obwohl er
    laeuft - und das Token mitzugeben hiesse, die Gesundheit des Dienstes an
    einen Eintrag in der ``.env`` des Stapels zu haengen.
    """
    probe = (jupyter_dienst.get("healthcheck") or {}).get("test", "")
    assert probe, "der Jupyter-Dienst hat keine Gesundheitspruefung"
    assert "/api/" not in probe, (
        f"die Gesundheitspruefung fragt einen angemeldeten Endpunkt: {probe} - "
        "ohne Token antwortet er mit 403, und der Dienst gilt als krank"
    )
    assert "/login" in probe, (
        f"unerwartete Gesundheitspruefung: {probe} - gemessen antwortet "
        "/login unangemeldet mit 200"
    )


def test_der_arbeitsbereich_liegt_nicht_im_schreibgeschuetzten_bestand(
        dockerfile, jupyter_dienst):
    """``data/`` ist ``:ro`` eingehaengt - ein Arbeitsbereich darunter waere keiner."""
    bereich = PurePosixPath(arbeitsbereich(dockerfile))   # im Container, also POSIX
    for einhang in jupyter_dienst["volumes"]:
        if not einhang.endswith(":ro"):
            continue
        ziel = PurePosixPath(einhang.split(":")[1])
        assert not (bereich == ziel or ziel in bereich.parents), (
            f"der Arbeitsbereich {bereich} liegt unter dem schreibgeschuetzten "
            f"{ziel} - dort liesse sich kein Notebook speichern"
        )


# --------------------------------------------------------------------------
# Jeder Benutzer, kein Geheimnis
# --------------------------------------------------------------------------


def test_arbeitsbereich_und_zuhause_sind_fuer_jeden_benutzer_beschreibbar(dockerfile):
    """Der Verbund gibt die uid vor (``docker run --user ...``).

    Ein Abbild, das nur fuer eine uid funktioniert, klemmt genau dann. Das
    Zuhause kommt aus dem Grundabbild - deshalb hier beides: dass dieses
    Abbild den Arbeitsbereich oeffnet und dass es die Zusage des Grundabbilds
    nicht mit einem eigenen ``USER`` aushebelt.
    """
    assert arbeitsbereich(dockerfile)  # wirft, wenn das chmod 0777 fehlt
    assert not re.search(r"^USER ", dockerfile, re.M), (
        "ein USER im Abbild - dann entscheidet nicht mehr der Verbund, wer "
        "laeuft, und $HOME und der Arbeitsbereich passen zu genau einer uid"
    )
    assert re.search(r'chmod 0777 "\$HOME"', GRUNDABBILD.read_text(encoding="utf-8")), (
        "das Grundabbild macht $HOME nicht mehr fuer jeden beschreibbar - "
        "JupyterLab legt dort seine Laufzeitdateien ab"
    )


def test_kein_geheimnis_im_abbild(dockerfile, einstieg, serverkonfig):
    """Weder ein Schluessel noch ein Token - auch nicht als Vorgabe.

    Ein Token im Abbild laeuft bestens und ist in jeder Schicht lesbar, auch
    nach einem spaeteren Loeschen. Es kommt als ``JUPYTER_TOKEN`` aus der
    Umgebung; der eigentliche Zugang liegt davor (Cloudflare Access ueber
    ``urbancrime-*``).
    """
    verboten = ("COPY .env", "COPY ./.env", "CENSUS_API_KEY=", "S3_SECRET_KEY=",
                "S3_ACCESS_KEY=", "SOCRATA_APP_TOKEN=", "JUPYTER_TOKEN=",
                "ServerApp.token", "NotebookApp.token", "ServerApp.password",
                "--ServerApp.token")
    for text, woher in ((dockerfile, "Dockerfile.jupyter"),
                        (einstieg, "docker/jupyter-einstieg.sh"),
                        (serverkonfig, "docker/jupyter_server_config.py")):
        for eintrag in verboten:
            assert eintrag not in text, f"{eintrag} steht in {woher}"


# --------------------------------------------------------------------------
# Der Einstieg: gelesen und ausgefuehrt
# --------------------------------------------------------------------------


def test_der_einstieg_verschluckt_keinen_zweiten_befehl(dockerfile, einstieg):
    """Die Lektion des Grundabbilds, hier mit ``ENTRYPOINT``.

    Das Grundabbild hat bewusst keines: Ein ``ENTRYPOINT`` haengt jeden
    anderen Befehl als Argumente an. Hier braucht es eines - der Dienst
    bringt sein ``command`` mit, und die Vorlagen sollen trotzdem liegen -,
    und deshalb muss das Skript mit ``exec "$@"`` enden. Sonst antwortete
    ``docker run <abbild> jupyter lab --version`` nicht mehr.
    """
    assert re.search(r'^ENTRYPOINT \["[^"]*jupyter-einstieg"\]', dockerfile, re.M), (
        "der Einstieg ist nicht das ENTRYPOINT - dann legt ein eigenes "
        "command des Dienstes keine Vorlage mehr hin"
    )
    assert re.search(r'^CMD \["jupyter", "lab"', dockerfile, re.M), (
        "ohne CMD startet 'docker run <abbild>' keinen Server"
    )
    assert einstieg.rstrip().endswith('exec "$@"'), (
        'der Einstieg endet nicht mit exec "$@" - er verschluckte jeden '
        "zweiten Befehl"
    )
    assert re.search(r"chmod 0755 \S*jupyter-einstieg", dockerfile), (
        "das Ausfuehrbit wird im Abbild nicht gesetzt - ein Klon auf Windows "
        "traegt es nicht, und der Dienst startete mit 'permission denied'"
    )


def vorgabe(einstieg: str, variable: str) -> str:
    treffer = re.search(rf'^{variable}="\$\{{\w+:-([^}}]+)\}}"', einstieg, re.M)
    assert treffer, f"{variable} hat keine Vorgabe im Einstieg"
    return treffer.group(1)


def test_die_vorgaben_des_einstiegs_sind_die_pfade_des_abbilds(dockerfile, einstieg):
    """Sonst pruefen die Laeufe unten etwas, das im Abbild nicht gilt."""
    assert vorgabe(einstieg, "ARBEIT") == arbeitsbereich(dockerfile)
    assert vorgabe(einstieg, "VORLAGEN") == vorlagenort(dockerfile)


def lauf(tmp_path: Path, *befehl: str, arbeit: Path | None = None,
         vorlagen: Path | None = None) -> subprocess.CompletedProcess:
    """Fuehrt den Einstieg mit eigenen Pfaden aus - ohne Docker."""
    umgebung = dict(os.environ)
    umgebung["JUPYTER_VORLAGEN"] = str(vorlagen if vorlagen else tmp_path / "vorlagen")
    umgebung["JUPYTER_ARBEIT"] = str(arbeit if arbeit else tmp_path / "arbeit")
    return subprocess.run(["sh", str(EINSTIEG), *befehl],
                          capture_output=True, text=True, env=umgebung)


@pytest.fixture
def gelegt(tmp_path: Path) -> tuple[Path, Path]:
    """Ein Vorlagenverzeichnis mit den drei Namen und ein leerer Arbeitsbereich.

    Die Vorlagen sind hier **nur lesbar**, wie im Abbild - sonst entgeht
    diesem Test genau der Fehler, den das ``chmod u+w`` im Einstieg behebt.
    """
    vorlagen = tmp_path / "vorlagen"
    vorlagen.mkdir()
    for name in VORLAGEN:
        datei = vorlagen / f"{name}.ipynb"
        datei.write_text("{}", encoding="utf-8")
        datei.chmod(0o444)
    arbeit = tmp_path / "arbeit"
    arbeit.mkdir()
    return vorlagen, arbeit


@OHNE_SHELL
def test_ein_leerer_arbeitsbereich_bekommt_die_vorlagen(tmp_path, gelegt):
    """Zeile 2 der Matrix: Erster Start, Arbeitsbereich leer."""
    vorlagen, arbeit = gelegt
    fertig = lauf(tmp_path, "sh", "-c", "echo gelaufen",
                  arbeit=arbeit, vorlagen=vorlagen)
    assert fertig.returncode == 0, fertig.stderr
    assert sorted(p.name for p in arbeit.iterdir()) == \
        sorted(f"{n}.ipynb" for n in VORLAGEN)
    assert fertig.stdout.strip() == "gelaufen", (
        "der uebergebene Befehl lief nicht oder bekam stdout nicht allein - "
        "die Meldungen des Einstiegs gehoeren nach stderr"
    )


@OHNE_SHELL
def test_die_kopie_laesst_sich_speichern(tmp_path, gelegt):
    """``cp`` uebernimmt die Rechte der Vorlage, und die ist nur lesbar.

    Ohne das ``chmod u+w`` im Einstieg liegt die Kopie da und liesse sich
    nicht speichern - ein Fehler, der erst mitten in einer Analyse auffaellt.
    """
    vorlagen, arbeit = gelegt
    assert lauf(tmp_path, "true", arbeit=arbeit, vorlagen=vorlagen).returncode == 0
    for name in VORLAGEN:
        kopie = arbeit / f"{name}.ipynb"
        assert kopie.stat().st_mode & 0o200, f"{kopie.name} ist nicht beschreibbar"
        kopie.write_text('{"meine": "Fassung"}', encoding="utf-8")


@OHNE_SHELL
def test_ein_belegter_arbeitsbereich_bleibt_unberuehrt(tmp_path, gelegt):
    """Zeile 3 der Matrix: Zweiter Start - **nichts** wird ueberschrieben."""
    vorlagen, arbeit = gelegt
    (arbeit / "meine_analyse.ipynb").write_text("eigen", encoding="utf-8")
    fertig = lauf(tmp_path, "true", arbeit=arbeit, vorlagen=vorlagen)
    assert fertig.returncode == 0, fertig.stderr
    assert [p.name for p in arbeit.iterdir()] == ["meine_analyse.ipynb"], (
        "in einen belegten Arbeitsbereich wurde trotzdem gelegt"
    )
    assert (arbeit / "meine_analyse.ipynb").read_text(encoding="utf-8") == "eigen"


@OHNE_SHELL
def test_eine_bearbeitete_vorlage_wird_nicht_zurueckgesetzt(tmp_path, gelegt):
    """Zeile 5 der Matrix: Nur seine Kopie aendert sich, die im Abbild nicht."""
    vorlagen, arbeit = gelegt
    assert lauf(tmp_path, "true", arbeit=arbeit, vorlagen=vorlagen).returncode == 0
    bearbeitet = arbeit / f"{VORLAGEN[0]}.ipynb"
    bearbeitet.write_text('{"meine": "Fassung"}', encoding="utf-8")
    assert lauf(tmp_path, "true", arbeit=arbeit, vorlagen=vorlagen).returncode == 0
    assert bearbeitet.read_text(encoding="utf-8") == '{"meine": "Fassung"}', (
        "der zweite Start hat die bearbeitete Kopie ueberschrieben"
    )
    assert (vorlagen / f"{VORLAGEN[0]}.ipynb").read_text(encoding="utf-8") == "{}", (
        "die Vorlage selbst wurde geaendert"
    )


@OHNE_SHELL
def test_ein_fehlender_arbeitsbereich_haelt_den_start_nicht_auf(tmp_path, gelegt):
    """``docker run <abbild> jupyter lab --version`` haengt keinen Datentraeger ein.

    Der Befehl soll trotzdem antworten - und der Einstieg sagen, warum keine
    Vorlage liegt.
    """
    vorlagen, _ = gelegt
    fertig = lauf(tmp_path, "sh", "-c", "echo da",
                  arbeit=tmp_path / "gibt-es-nicht", vorlagen=vorlagen)
    assert fertig.returncode == 0, fertig.stderr
    assert fertig.stdout.strip() == "da"
    assert "gibt-es-nicht" in fertig.stderr


@OHNE_SHELL
def test_ohne_befehl_bricht_der_einstieg_ab(tmp_path, gelegt):
    """Sonst endete der Container still mit 0 und sahe wie ein Erfolg aus."""
    vorlagen, arbeit = gelegt
    fertig = lauf(tmp_path, arbeit=arbeit, vorlagen=vorlagen)
    assert fertig.returncode != 0, "ohne Befehl endet der Einstieg erfolgreich"


@OHNE_SHELL
def test_ein_unbeschreibbarer_arbeitsbereich_haelt_den_start_nicht_auf(tmp_path, gelegt):
    """Wessen uid nicht schreiben darf, entscheidet der Verbund.

    Der Server soll starten und den Grund zeigen, statt im Neustartkreis zu
    haengen.
    """
    vorlagen, arbeit = gelegt
    arbeit.chmod(0o500)
    try:
        fertig = lauf(tmp_path, "sh", "-c", "echo trotzdem",
                      arbeit=arbeit, vorlagen=vorlagen)
    finally:
        arbeit.chmod(0o700)
    if os.geteuid() == 0:
        pytest.skip("als root schreibt auch ein 0500-Verzeichnis")
    assert fertig.returncode == 0, fertig.stderr
    assert fertig.stdout.strip() == "trotzdem"
    assert "konnte keine Vorlage" in fertig.stderr


# --------------------------------------------------------------------------
# Das Dokument
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def abschnitt_16() -> str:
    doku = DOKUMENT.read_text(encoding="utf-8")
    return doku[doku.index("## 16 ·"):]


def test_abschnitt_16_beschreibt_das_zweite_abbild(abschnitt_16):
    """Ein Abbild, das niemand bauen kann, ist keines.

    Verlangt sind der Name der Datei, der Bau **mit** dem Argument fuer das
    Grundabbild und der Schiebebefehl - ohne ihn endet die Beschreibung an
    dem Punkt, an dem der Server anfaengt.
    """
    for erwartet in ("Dockerfile.jupyter", "--build-arg BASIS", "docker push"):
        assert erwartet in abschnitt_16, (
            f"Abschnitt 16 nennt {erwartet!r} nicht"
        )
    assert "Das zweite ist noch nicht gebaut" not in abschnitt_16, (
        "Abschnitt 16 sagt weiter, das Analyse-Abbild sei nicht gebaut - "
        "Dockerfile.jupyter liegt daneben"
    )


def test_abschnitt_16_nennt_die_gepinnte_fassung(abschnitt_16, dockerfile):
    """Eine Fassung in einem Dokument veraltet, sobald sie im Abbild steigt.

    Deshalb steht sie an beiden Stellen und wird hier gegeneinander gehalten -
    dieselbe Regel wie bei jeder anderen Zahl der Abgabe.
    """
    gepinnt = re.search(r"^ARG JUPYTERLAB=(\S+)", dockerfile, re.M).group(1)
    assert f"jupyterlab=={gepinnt}" in abschnitt_16, (
        f"Abschnitt 16 nennt nicht jupyterlab=={gepinnt} - das Abbild legt "
        "genau diese Fassung dazu"
    )


def test_abschnitt_16_nennt_die_vorlagen_und_das_ausgeschlossene(abschnitt_16):
    """Dieselbe Liste wie im Abbild - sonst veraltet die unbewachte Seite.

    Gemessen gegen ``VORLAGEN``: Wer eine vierte mitnimmt, muss es hier
    hinschreiben.
    """
    for name in VORLAGEN:
        assert name in abschnitt_16, f"Abschnitt 16 nennt die Vorlage {name} nicht"
    assert AUSGESCHLOSSEN in abschnitt_16, (
        f"Abschnitt 16 sagt nicht, dass {AUSGESCHLOSSEN} nicht mitkommt - und "
        "das ist die Entscheidung, nach der jemand fragt"
    )
