"""Formpruefung des Abbildbaus.

Ohne pyyaml und ohne Netz - geprueft wird der Text. Dieser Workflow ersetzt
Handarbeit, die zweimal schiefgehen konnte: die vergessene Plattformangabe
(sichtbar erst auf ``srv01`` als ``exec format error``, also nach Bau,
Schieben und Holen) und der von Hand uebertragene Digest. Beides faellt
hier auf, wenn es wieder aus dem Workflow verschwindet.

Zwei Dinge werden **abgelesen statt getippt**: die Namen der beiden
Abbildvariablen kommen aus ``.env.example``, die Namen der beiden Abbilder
aus ``docs/storage-architektur.md``. Stuende eine der Aussagen hier als
Literal, waere sie die, die veraltet, sobald das Dokument sich dreht - genau
der Fall, der am 11.10.2026 acht Aussagen auf einmal ueberholt hat.
"""

from __future__ import annotations

import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "abbilder.yml"
ENV_BEISPIEL = PROJECT_ROOT / ".env.example"
ABLAGE_DOKUMENT = PROJECT_ROOT / "docs" / "storage-architektur.md"


def text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def ausloeserblock() -> str:
    """Der ``on:``-Block allein.

    Nicht die ganze Datei durchsuchen: ``push: true`` steht in beiden
    Bau-Schritten, und ein Test, der das fuer einen Ausloeser haelt, ist rot
    ohne Grund. Geschnitten wird bis zur naechsten Zeile ohne Einzug.
    """
    zeilen = text().splitlines()
    anfang = next(i for i, z in enumerate(zeilen) if z.rstrip() == "on:")
    block = []
    for zeile in zeilen[anfang + 1:]:
        if zeile and not zeile[0].isspace():
            break
        block.append(zeile)
    return "\n".join(block)


def abbildvariablen() -> set[str]:
    """Die Variablen, die ein Abbild pinnen - gelesen aus ``.env.example``."""
    beispiel = ENV_BEISPIEL.read_text(encoding="utf-8")
    return set(re.findall(r"^([A-Z_]*IMAGE)=", beispiel, re.MULTILINE))


def abbildnamen() -> set[str]:
    """Die Abbilder unter ``ghcr.io/datenwerft`` - gelesen aus dem Dokument."""
    doku = ABLAGE_DOKUMENT.read_text(encoding="utf-8")
    return set(re.findall(r"ghcr\.io/datenwerft/([a-z0-9-]+)", doku))


def test_der_workflow_liegt_im_repository():
    assert WORKFLOW.exists()


def test_er_laeuft_nur_von_hand():
    """Das Repository ist privat, Minuten werden verrechnet.

    Am 1.10.2026 war das Budget nach acht Laeufen weg (Begruendung in
    tests.yml). Ein Abbildbau ist nur noetig, wenn der Stapel wirklich
    umgestellt wird - ein Anstoss auf jedem Push waere teuer und nutzlos.
    """
    block = ausloeserblock()
    ausloeser = set(re.findall(r"^  (\w+):", block, re.MULTILINE))
    assert ausloeser == {"workflow_dispatch"}, \
        f"Ausloeser sind {sorted(ausloeser)} - erwartet ist allein workflow_dispatch"


def test_beide_abbilder_werden_gebaut():
    """So viele Abbilder, wie das Dokument unter dem Namensraum nennt."""
    t = text()
    fehlen = [name for name in abbildnamen()
              if f"ghcr.io/datenwerft/{name}" not in t]
    assert not fehlen, f"nicht gebaut, aber im Dokument genannt: {fehlen}"


def test_beide_baue_sind_auf_linux_amd64_festgelegt():
    """Der Grund, warum es diesen Workflow gibt.

    Der Entwicklungsrechner ist arm64, ``srv01`` ist x86-64. Ohne
    Plattformangabe laesst sich das Abbild schieben und scheitert erst dort
    beim Start.
    """
    t = text()
    baue = t.count("uses: docker/build-push-action")
    plattformen = t.count("platforms: linux/amd64")
    assert baue >= 2, f"nur {baue} Bau/Baeue - erwartet sind zwei"
    assert plattformen == baue, \
        f"{baue} Baeue, aber {plattformen} Plattformangaben"


def test_er_prueft_das_token_vorab():
    t = text()
    pruefung = t.index("GHCR_TOKEN fehlt")
    anmeldung = t.index("docker/login-action")
    assert pruefung < anmeldung, "das Token gehoert vor die Anmeldung geprueft"


def test_er_schiebt_mit_dem_token_und_nicht_mit_github_token():
    """``GITHUB_TOKEN`` darf nur Pakete des Repository-Eigentuemers schreiben.

    Der Namensraum haengt am persoenlichen Konto, das Repository an
    ``artanmusollaj-ops``. Mit dem eingebauten Token landeten die Abbilder
    unter einem Namen, auf den weder die ``.env`` auf ``srv01`` noch die
    Dokumente zeigen.
    """
    t = text()
    assert "secrets.GHCR_TOKEN" in t
    anmeldung = t.index("docker/login-action")
    abschnitt = t[anmeldung:anmeldung + 400]
    assert "secrets.GITHUB_TOKEN" not in abschnitt, \
        "mit GITHUB_TOKEN ginge es in den falschen Namensraum"


def test_das_analyse_abbild_setzt_auf_dem_digest_auf_nicht_auf_der_marke():
    """Eine Marke laesst sich zwischen den beiden Schritten umhaengen."""
    t = text()
    assert re.search(r"BASIS=\$\{\{ env\.BASIS_NAME \}\}@\$\{\{ steps\.basis\.outputs\.digest \}\}", t), \
        "BASIS muss per Digest kommen, nicht per Marke"


def test_die_gegenprobe_holt_zurueck_und_prueft_die_plattform():
    """Bauen allein beweist nichts ueber das, was in der Registry liegt."""
    t = text()
    assert "docker pull" in t, "ohne Zurueckholen ist der Digest unbelegt"
    assert 'docker image inspect --format=\'{{.Os}}/{{.Architecture}}\'' in t, \
        "die Gegenprobe, die das Ablagedokument verlangt, fehlt"
    probe = t.index("Gegenprobe")
    assert "exit 1" in t[probe:], "die Gegenprobe muss den Lauf rot machen koennen"


def test_die_herkunft_im_abbild_wird_gegen_den_gebauten_commit_gehalten():
    """``GIT_COMMIT`` ist das einzige, was ein Container ueber seinen Stand sagt."""
    t = text()
    assert "GIT_COMMIT=${{ github.sha }}" in t, "der Commit muss als Argument hinein"
    herkunft = t.index("Herkunft des Abbilds pruefen")
    assert "github.sha" in t[herkunft:], "und danach dagegen gehalten werden"


def test_das_abbild_wird_gegen_den_git_baum_gehalten():
    """Derselbe Abgleich, den ein Impact-Job vor dem Bau macht.

    Am 3.11.2026 scheiterte der erste Impact auf srv01 mit "Builddatei
    fehlt: requirements.txt" - das Abbild trug die Datei nie, und kein Bau
    hatte es bemerkt.
    """
    workflow = text()
    assert 'git ls-tree -r "${{ github.sha }}"' in workflow
    assert "python -m platform_admin.release_flow /app" in workflow


def test_die_zusammenfassung_nennt_genau_die_variablen_der_env():
    """Beide Variablen aus ``.env.example``, keine erfundene dazu."""
    t = text()
    erwartet = abbildvariablen()
    assert erwartet, ".env.example nennt keine Abbildvariable - Test waere wertlos"
    zusammenfassung = t[t.index("Die zwei Zeilen fuer die .env"):]
    fehlen = [name for name in erwartet if f"{name}=" not in zusammenfassung]
    assert not fehlen, f"nicht in der Zusammenfassung: {fehlen}"
    genannt = set(re.findall(r"^\s*echo \"([A-Z_]*IMAGE)=", zusammenfassung, re.MULTILINE))
    assert genannt == erwartet, f"Zusammenfassung nennt {genannt}, .env.example {erwartet}"


def test_er_schreibt_nicht_auf_srv01():
    """Die bewusste Grenze: der Digest wird von Hand getragen.

    Ein Workflow mit Schreibzugriff auf den Server waere ein zweiter Weg
    hinein. Faellt dieser Test, ist das eine Entscheidung und kein Versehen -
    dann gehoert sie dokumentiert.
    """
    t = text()
    for verraeter in ("ssh", "scp", "known_hosts", "appleboy/ssh-action"):
        assert verraeter not in t, f"{verraeter} deutet auf einen Zugriff auf srv01"


def test_zwei_baeue_laufen_nicht_gleichzeitig():
    """Beide wuerden dieselbe Marke umhaengen."""
    t = text()
    assert "concurrency:" in t
    nebenlauf = t.index("concurrency:")
    assert "cancel-in-progress: false" in t[nebenlauf:nebenlauf + 300], \
        "ein halb geschobenes Abbild ist schlimmer als ein Warten"


def test_der_workflow_setzt_die_marke_die_srv01_nachschlaegt():
    """Ohne sie findet das Einsetz-Skript den neuen Stand nicht.

    ``docker/srv01-abbild-einsetzen.sh`` schlaegt den Digest ueber eine
    mitwandernde Marke nach, statt das Baudatum zu kennen. Faellt sie hier
    weg, scheitert das Skript dort mit *„manifest unknown"* - und zwar auf
    dem Server, nicht hier.

    **Gepinnt wird sie nie.** Das Skript schreibt den gelesenen Digest in
    die ``.env``; die Marke dient nur dem Nachschlagen. Deshalb prueft
    dieser Test zusaetzlich, dass sie in der Beschreibung der Abbildvariablen
    **nicht** vorkommt.
    """
    t = text()
    marke = re.search(r"WANDERNDE_MARKE:\s*(\S+)", t)
    assert marke, "der Workflow nennt keine wandernde Marke"
    wert = marke.group(1)

    # Beide Abbilder tragen sie - gezaehlt, nicht geraten.
    assert t.count("${{ env.WANDERNDE_MARKE }}") >= len(abbildnamen()), (
        f"nicht jedes Abbild bekommt die Marke ':{wert}'")

    beispiel = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    assert f":{wert}" not in beispiel, (
        f"'.env.example' nennt die wandernde Marke ':{wert}' - gepinnt wird "
        f"der Digest, eine Marke laesst sich umhaengen")


def test_die_zusammenfassung_nennt_den_einen_befehl_fuer_srv01():
    """Sonst schreibt jemand die Digests wieder von Hand ab.

    Fuenf Handgriffe waren es vorher; der dritte - die ``.env`` aendern - ist
    der, bei dem ein Zeichen verlorengeht. Die Zusammenfassung des Laufs ist
    die Stelle, an der jemand steht, wenn er sie braeuchte.
    """
    t = text()
    zusammenfassung = t[t.index("Die zwei Zeilen fuer die .env"):]
    assert "srv01-abbild-einsetzen.sh" in zusammenfassung, (
        "die Job-Zusammenfassung nennt den Befehl nicht, der das Abschreiben "
        "erspart")
