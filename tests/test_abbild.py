"""Prueft ``Dockerfile`` und ``.dockerignore`` - das Abbild der Strecke.

Ein Abbild laesst sich hier nicht bauen: Der Bau braucht einen Docker-Daemon
und Netz, und beides hat ein Pull Request nicht. Was sich ohne beides pruefen
laesst, ist alles, was im Abbild **falsch sein kann, ohne beim Bauen
aufzufallen** - und das ist die Mehrheit der Faelle:

* ein Ausschluss, der in der ``.dockerignore`` fehlt (``.env`` im Abbild faellt
  nie auf, sie funktioniert ja),
* eine DuckDB-Erweiterung, die der Code laedt und der Bau nicht vorlegt (das
  faellt erst im Lauf ohne Netz auf, und zwar woechentlich um vier Uhr),
* ein ``COPY``, dessen Quelle die ``.dockerignore`` zurueckhaelt,
* ein ``ENTRYPOINT`` statt eines ``CMD``, das jeden zweiten Befehl verschluckt.

Der Bau selbst steht in der Verifikation des Plans, nicht hier.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = PROJECT_ROOT / "Dockerfile"
DOCKERIGNORE = PROJECT_ROOT / ".dockerignore"
QUELLE = PROJECT_ROOT / "src" / "crime"

#: Was FR-2 mindestens verlangt. Jeder Eintrag steht fuer einen eigenen
#: Schaden: Geheimnisse, eine fremde Umgebung, 70 MB Daten, Protokolle und
#: einige hundert MB Versionsgeschichte.
GEFORDERTE_AUSSCHLUESSE = (".env", ".venv/", "data/", "logs/", ".git/")

@pytest.fixture(scope="module")
def dockerfile() -> str:
    if not DOCKERFILE.is_file():
        pytest.fail(f"{DOCKERFILE} fehlt - Welle 3 beginnt damit")
    return DOCKERFILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def muster() -> list[str]:
    """Die Zeilen der ``.dockerignore`` ohne Kommentare und Leerzeilen."""
    if not DOCKERIGNORE.is_file():
        pytest.fail(f"{DOCKERIGNORE} fehlt")
    return [z.strip() for z in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
            if z.strip() and not z.strip().startswith("#")]


# --------------------------------------------------------------------------
# FR-2: was draussen bleibt
# --------------------------------------------------------------------------


@pytest.mark.parametrize("eintrag", GEFORDERTE_AUSSCHLUESSE)
def test_die_fuenf_ausschluesse_stehen_drin(muster, eintrag):
    """Die Liste aus FR-2, Zeile fuer Zeile.

    ``.env`` ist der wichtigste davon und der einzige, dessen Fehlen nichts
    kaputt macht: Ein Abbild mit eingebackenen Schluesseln laeuft bestens -
    und traegt sie in jeder Schicht weiter, auch wenn jemand die Datei
    spaeter loescht.
    """
    erlaubt = {eintrag, eintrag.rstrip("/"), eintrag.rstrip("/") + "/"}
    assert erlaubt & set(muster), (
        f"{eintrag} fehlt in .dockerignore - FR-2 verlangt die fuenf Eintraege "
        f".env, .venv/, data/, logs/ und .git/"
    )


def test_kein_geheimnis_im_dockerfile(dockerfile):
    """Weder eine Datei mit Schluesseln noch ein Schluessel im Klartext.

    Im Abbild liegt kein Geheimnis - es kommt zur Laufzeit herein. Ein
    ``COPY .env`` waere die eine Zeile, die diese Zusage still aufhebt.
    """
    for verboten in ("COPY .env", "COPY ./.env", "CENSUS_API_KEY=",
                     "S3_SECRET_KEY=", "SOCRATA_APP_TOKEN="):
        assert verboten not in dockerfile, f"{verboten} steht im Dockerfile"


def test_die_daten_werden_nicht_hineingebaut(dockerfile):
    """``data/`` ist ein Volume. Ein Abbild mit Bestand darin ist kein Abbild des Codes."""
    kopiert = re.findall(r"^COPY\s+(.+)$", dockerfile, re.M)
    for zeile in kopiert:
        quellen = zeile.split()[:-1]
        assert not any(q.strip("./").startswith("data") for q in quellen), zeile


# --------------------------------------------------------------------------
# Der Bau
# --------------------------------------------------------------------------


def test_die_abhaengigkeiten_kommen_aus_dem_lockfile(dockerfile):
    """Gepinnt, nicht aus den Bereichen in pyproject.toml.

    Beides zusammen gehoert dazu: die Installation **aus** dem Lockfile und
    ``--no-deps`` beim Paket selbst. Ohne das zweite zieht pip aus
    ``duckdb>=1.1,<2`` wieder das Neueste nach, und das Lockfile ist
    ausgehebelt, ohne dass etwas rot wird.
    """
    assert "requirements.lock" in dockerfile
    assert re.search(r"pip install[^\n]*-r requirements\.lock", dockerfile), (
        "das Lockfile wird nicht installiert"
    )
    assert re.search(r"pip install[^\n]*-e \.[^\n]*--no-deps", dockerfile), (
        "'pip install -e . --no-deps' fehlt - ohne --no-deps haengt pip das "
        "Lockfile aus"
    )


def test_der_interpreter_passt_zum_lockfile(dockerfile):
    """Das Lockfile gilt je Interpreter - es sagt selbst, fuer welchen."""
    lock = (PROJECT_ROOT / "requirements.lock").read_text(encoding="utf-8")
    treffer = re.search(r"Exakte Versionen fuer Python (\d+\.\d+)", lock)
    assert treffer, "requirements.lock nennt seine Python-Version nicht mehr"
    assert re.search(rf"^FROM python:{re.escape(treffer.group(1))}\b", dockerfile, re.M), (
        f"requirements.lock ist fuer Python {treffer.group(1)} eingefroren - "
        "das FROM muss dieselbe Nebenversion nennen"
    )


def installierte_erweiterungen() -> set[str]:
    """Jede DuckDB-Erweiterung, die der Code zur Laufzeit zu laden versucht.

    Gemessen, nicht gepflegt: Wer eine vierte Erweiterung einbaut, soll nicht
    daran denken muessen, dass sie ins Abbild gehoert - der Test sagt es ihm.
    """
    gefunden: set[str] = set()
    for datei in QUELLE.rglob("*.py"):
        gefunden.update(re.findall(r'["\']INSTALL (\w+)["\']',
                                   datei.read_text(encoding="utf-8")))
    return gefunden


def test_jede_geladene_erweiterung_liegt_zur_bauzeit_im_abbild(dockerfile):
    """Ohne Netz scheitert ``INSTALL`` hart - und der Lauf hat keines.

    Das ist der Fall, der im Container am ehesten leise falsch wird: Auf dem
    Entwicklungsrechner laedt DuckDB die Erweiterung beim ersten Bedarf nach,
    und niemand merkt, dass es ein Netzzugriff war.
    """
    im_code = installierte_erweiterungen()
    assert im_code, "keine INSTALL-Aufrufe gefunden - die Messung greift nicht"
    assert "duckdb.connect()" in dockerfile, (
        "das Dockerfile installiert keine DuckDB-Erweiterung"
    )
    genannt = set(re.findall(r"'(\w+)'", dockerfile))
    fehlend = sorted(im_code - genannt)
    assert not fehlend, (
        f"{fehlend} wird im Code per INSTALL geladen, liegt aber nicht zur "
        "Bauzeit im Abbild - im Lauf ohne Netz scheitert das hart"
    )


def test_das_zuhause_ist_beschreibbar(dockerfile):
    """DuckDB legt seine Erweiterungen unter ``$HOME`` ab, pip seinen Cache.

    Und zwar fuer **jeden** Benutzer: Der Verbund gibt die uid vor, ein Abbild,
    das nur fuer eine funktioniert, klemmt genau dann.
    """
    assert re.search(r"^ENV HOME=\S+", dockerfile, re.M), "HOME wird nicht gesetzt"
    assert re.search(r'chmod 0777 "\$HOME"', dockerfile), (
        "$HOME ist nicht fuer jeden Benutzer beschreibbar"
    )


# --------------------------------------------------------------------------
# Die Laufzeit-Assets und die Wurzel
# --------------------------------------------------------------------------


def test_die_laufzeit_assets_liegen_im_abbild(dockerfile):
    """``config/`` und ``docs/intern/AENDERUNGEN.md`` (FR-5).

    Beide werden **relativ** aufgeloest. Fehlt ``config/``, baut Gold eine
    leere Dimension und scheitert dabei nicht.
    """
    assert re.search(r"^COPY config ", dockerfile, re.M)
    assert "docs/intern/AENDERUNGEN.md" in dockerfile


def test_die_wurzel_wird_gesetzt_und_heisst_wie_im_code(dockerfile):
    """Sonst raet ``run_all`` wieder - oder bricht im Abbild ab."""
    from manifeste import WURZEL_VARIABLE, WURZELZEICHEN

    treffer = re.search(rf"^ENV {WURZEL_VARIABLE}=(\S+)", dockerfile, re.M)
    assert treffer, f"{WURZEL_VARIABLE} wird im Abbild nicht gesetzt"
    wurzel = treffer.group(1)
    assert re.search(rf"^WORKDIR {re.escape(wurzel)}$", dockerfile, re.M), (
        f"{WURZEL_VARIABLE}={wurzel}, aber das WORKDIR ist ein anderes"
    )
    # Was dort liegen muss, damit projektwurzel die Angabe annimmt.
    for zeichen in WURZELZEICHEN:
        assert re.search(rf"^COPY {re.escape(zeichen)} ", dockerfile, re.M), (
            f"{zeichen} ist ein Kennzeichen der Projektwurzel und wird nicht "
            "ins Abbild kopiert - projektwurzel wiese PROJECT_ROOT ab"
        )


def test_der_commit_kommt_als_argument_herein(dockerfile):
    """``.git/`` bleibt draussen **und** die Herkunft bleibt erhalten."""
    from manifeste import COMMIT_VARIABLE

    assert re.search(rf"^ARG {COMMIT_VARIABLE}=", dockerfile, re.M), (
        f"ohne 'ARG {COMMIT_VARIABLE}' sagt jedes Manifest aus dem Container, "
        "niemand wisse, welcher Code die Zahlen erzeugt hat"
    )
    assert re.search(rf"^ENV {COMMIT_VARIABLE}=", dockerfile, re.M), (
        "das Argument erreicht die Laufzeit nicht"
    )


def test_der_einstiegspunkt_ist_die_strecke(dockerfile):
    """Und zwar als ``CMD``.

    Ein ``ENTRYPOINT`` wuerde jeden anderen Befehl als Argumente an
    ``run_all`` haengen - ``docker run <abbild> python -m storage`` liefe dann
    als ``run_all python -m storage``, und die Probe des Plans
    (``... run_all --trocken``) ebenso.
    """
    assert 'CMD ["python", "-m", "orchestration.run_all"]' in dockerfile
    # Nur als Befehl, nicht als Wort: Der Kommentar daneben erklaert, warum
    # hier kein ENTRYPOINT steht, und soll das duerfen.
    assert not re.search(r"^ENTRYPOINT", dockerfile, re.M)


# --------------------------------------------------------------------------
# Die beiden Dateien gegeneinander
# --------------------------------------------------------------------------


def test_kein_copy_greift_ins_ausgeschlossene(dockerfile, muster):
    """Sonst scheitert der Bau - oder, schlimmer, er scheitert nicht.

    ``docs/`` auszuschliessen waere naheliegend und falsch: Das Dockerfile
    holt ``docs/intern/AENDERUNGEN.md`` daraus. Geprueft wird jede Quelle
    jedes ``COPY`` gegen jede ihrer Elternstufen.
    """
    ausgeschlossen = {z.rstrip("/") for z in muster if not z.startswith("!")}
    for zeile in re.findall(r"^COPY\s+(.+)$", dockerfile, re.M):
        for quelle in zeile.split()[:-1]:
            teile = PurePosixPath(quelle.lstrip("./")).parts   # im Container, also POSIX
            for tiefe in range(1, len(teile) + 1):
                stufe = "/".join(teile[:tiefe])
                assert stufe not in ausgeschlossen, (
                    f"COPY {quelle} - aber '{stufe}' steht in .dockerignore"
                )
