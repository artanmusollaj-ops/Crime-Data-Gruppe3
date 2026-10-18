"""Die Alarmregeln reden ueber Messwerte, die es wirklich gibt.

**Warum es diese Datei braucht.** Eine Prometheus-Regel auf einen Namen, den
``serving.betriebsstand`` nicht ausgibt, feuert nie - und sieht dabei aus wie
Vorsorge. Das ist schlimmer als keine Regel: Niemand sucht nach einem Alarm,
den es gar nicht geben kann. Prometheus selbst sagt dazu nichts; ``promtool``
prueft die Syntax, nicht ob der Name existiert.

**Gemessen statt gelesen.** Die Namen und Marken kommen aus einem echten
Lauf des Moduls gegen ein Protokoll, nicht aus einer Liste hier. Stuende sie
hier, waere sie die, die veraltet.

Was diese Datei **nicht** prueft: ob ein Alarm im Ernstfall ankommt. Das
haengt an einem Mailkanal im Monitoring-Stapel, also ausserhalb dieses
Repositories (`docs/storage-architektur.md`, "Der Betriebsblick").
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")   # Sammelzeit: in pyproject deklariert


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGELVERZEICHNIS = PROJECT_ROOT / "docker" / "prometheus-regeln"
REGELN = REGELVERZEICHNIS / "urbancrime.yaml"
ABLAGEDOKUMENT = PROJECT_ROOT / "docs" / "storage-architektur.md"

#: Was Prometheus selbst mitbringt und kein Modul von uns ausgibt.
EIGENE_VON_PROMETHEUS = frozenset({"up"})

#: Funktionen und Schluesselwoerter von PromQL, die in einem Ausdruck wie ein
#: Metrikname aussehen.
PROMQL = frozenset({"absent", "rate", "increase", "sum", "avg", "max", "min",
                    "count", "by", "without", "on", "ignoring", "and", "or",
                    "unless", "time", "changes", "delta", "offset"})


def test_die_regeldatei_liegt_da_wo_der_glob_sie_findet():
    """Zwei Fallen auf einmal, und beide sind lautlos.

    **Die Endung.** Prometheus liest Regeln auf `srv01` ueber
    ``rule_files: .../*.yaml``. Eine Datei mit ``.yml`` liegt richtig und
    wird nie gelesen - kein Fehler, keine Regel, nichts.

    **Das Verzeichnis.** Eingehaengt wird der *Ordner*, nicht die Datei: Ein
    Datei-Bind-Mount haengt am Inode, und ``git pull`` ersetzt eine Datei,
    statt sie zu aendern. Der Container saehe danach fuer immer die alte
    Fassung.

    Dieser Test steht **vor** allen anderen, weil die Fixture darunter sich
    ueberspringt, wenn der Pfad nicht stimmt - und ein uebersprungener
    Waechter sieht wie ein gruener aus. Beim Umzug der Datei am 18.10.2026
    waren genau so acht Pruefungen auf einmal stumm.
    """
    assert REGELVERZEICHNIS.is_dir(), (
        f"{REGELVERZEICHNIS} ist kein Verzeichnis - eingehaengt wird der "
        f"Ordner, nicht die Datei")
    gefunden = sorted(d.name for d in REGELVERZEICHNIS.glob("*.yaml"))
    assert gefunden, (
        f"keine *.yaml in {REGELVERZEICHNIS} - mit '.yml' liest Prometheus "
        f"sie nicht, und zwar ohne Fehlermeldung. Liegt da: "
        f"{sorted(d.name for d in REGELVERZEICHNIS.iterdir())}")
    assert REGELN.name in gefunden, f"{REGELN.name} fehlt, da liegt {gefunden}"


def test_das_ablagedokument_nennt_genau_dieses_verzeichnis():
    """Der Einhaengeblock steht im Dokument, der Ordner liegt hier.

    Geht der Ordner um und das Dokument nicht mit, haengt jemand auf
    `srv01` ein Verzeichnis ein, das es nicht gibt - und Prometheus startet
    trotzdem, nur ohne unsere Regeln.
    """
    if not ABLAGEDOKUMENT.is_file():
        pytest.skip("docs/storage-architektur.md fehlt")
    relativ = REGELVERZEICHNIS.relative_to(PROJECT_ROOT).as_posix()
    doku = ABLAGEDOKUMENT.read_text(encoding="utf-8")
    assert relativ in doku, (
        f"das Ablagedokument nennt '{relativ}' nicht - der Block zum "
        f"Einsetzen zeigt dann auf ein anderes Verzeichnis")


@pytest.fixture(scope="module")
def regeln() -> list[dict]:
    if not REGELN.is_file():
        pytest.skip(f"{REGELN} fehlt")
    daten = yaml.safe_load(REGELN.read_text(encoding="utf-8"))
    return [regel for gruppe in daten["groups"] for regel in gruppe["rules"]]


@pytest.fixture(scope="module")
def gemessen(tmp_path_factory) -> dict[str, set[str]]:
    """Metrik -> Marken, aus einem echten Lauf von ``betriebsstand``.

    Gegen ein Protokoll aus dem Test, nicht gegen ``data/``: So ist das
    Ergebnis in einem frischen Klon dasselbe wie hier.
    """
    from serving import betriebsstand

    # Die Schluesselnamen sind die des echten Protokolls, nicht geraten:
    # ``finished_at_utc``, ``source_freshness``, ``output_rows``,
    # ``release_id``. Die erste Fassung erfand ``finished_at`` und ``rows``,
    # und dann fehlten drei Messwerte - der Waechter meldete sie als
    # "gibt niemand aus", und recht hatte er.
    protokoll = {
        "status": "failed",
        "started_at_utc": "2026-10-18T04:30:00Z",
        "finished_at_utc": "2026-10-18T04:41:00Z",
        "stages": [{"name": "crime_offense", "gruppe": "silver",
                    "exit": 1, "sekunden": 12.5}],
        "source_freshness": {"chicago": "2026-10-17T00:00:00Z"},
        "output_rows": {"silver/crime_offense": 1886254},
        "release": {"release_id": "2026-10-18T04-41-00Z", "files": 28,
                    "bytes": 123, "published": False},
    }
    wurzel = tmp_path_factory.mktemp("stand")
    (wurzel / "data").mkdir()
    (wurzel / "data" / "pipeline_run.json").write_text(
        json.dumps(protokoll), encoding="utf-8")

    import storage

    text = betriebsstand.metriken(
        betriebsstand.protokoll_lesen(storage.for_root(wurzel / "data")))
    gefunden: dict[str, set[str]] = {}
    for zeile in text.splitlines():
        treffer = re.match(r"^([a-z_]+)(\{([^}]*)\})? ", zeile)
        if not treffer:
            continue
        marken = set(re.findall(r"(\w+)=", treffer.group(3) or ""))
        gefunden.setdefault(treffer.group(1), set()).update(marken)
    return gefunden


def namen_im_ausdruck(ausdruck: str) -> set[str]:
    """Die Metriknamen eines PromQL-Ausdrucks, ohne Funktionen und Zahlen."""
    roh = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", ausdruck))
    # Markennamen innerhalb von {...} gehoeren nicht dazu.
    for block in re.findall(r"\{([^}]*)\}", ausdruck):
        roh -= set(re.findall(r"(\w+)=", block))
        roh -= set(re.findall(r'"([^"]*)"', block))
    return roh - PROMQL


def test_die_datei_ist_lesbar_und_nicht_leer(regeln):
    """Sonst prueft alles darunter nichts und bleibt gruen."""
    assert len(regeln) >= 5, f"nur {len(regeln)} Regeln - zu wenige fuer FR-17"


def test_jede_regel_zeigt_auf_einen_messwert_den_es_gibt(regeln, gemessen):
    """Der Kern. Ein Tippfehler im Namen ist eine Regel, die nie feuert."""
    bekannt = set(gemessen) | EIGENE_VON_PROMETHEUS
    fehler = []
    for regel in regeln:
        for name in sorted(namen_im_ausdruck(regel["expr"])):
            if name not in bekannt:
                fehler.append(f"{regel['alert']}: '{name}' gibt niemand aus")
    assert not fehler, "\n".join(fehler) + (
        f"\n\nausgegeben werden: {sorted(bekannt)}")


def test_jede_marke_in_einer_meldung_gibt_es_auch(regeln, gemessen):
    """``{{ $labels.x }}`` auf eine Marke, die fehlt, wird leer gedruckt.

    Eine Mail mit *„Stufe  mit Exitcode 1"* ist schlimmer als eine ohne die
    Stufe: Sie sieht aus, als waere der Wert leer, nicht als waere er falsch
    abgefragt.
    """
    fehler = []
    for regel in regeln:
        marken_der_regel = set()
        for name in namen_im_ausdruck(regel["expr"]):
            marken_der_regel |= gemessen.get(name, set())
        text = " ".join(str(w) for w in regel.get("annotations", {}).values())
        for benutzt in re.findall(r"\$labels\.(\w+)", text):
            if benutzt not in marken_der_regel:
                fehler.append(
                    f"{regel['alert']}: $labels.{benutzt} - der Messwert "
                    f"traegt nur {sorted(marken_der_regel) or 'keine Marken'}")
    assert not fehler, "\n".join(fehler)


def test_jede_regel_sagt_was_los_ist_und_wie_dringend(regeln):
    """Eine Mail ohne Betreff und ohne Grund ist eine Mail, die man wegklickt."""
    fehler = []
    for regel in regeln:
        if regel.get("labels", {}).get("severity") not in ("critical", "warning"):
            fehler.append(f"{regel['alert']}: keine brauchbare severity")
        for pflicht in ("summary", "description"):
            if len(str(regel.get("annotations", {}).get(pflicht, ""))) < 20:
                fehler.append(f"{regel['alert']}: {pflicht} fehlt oder ist leer")
    assert not fehler, "\n".join(fehler)


def test_jede_regel_wartet_eine_weile(regeln):
    """``for`` fehlt heisst: feuert beim ersten Messpunkt.

    Die Metrikdatei wird waehrend eines Laufs neu geschrieben, und ein
    Dienst startet mal neu. Ohne Wartezeit kommt die erste Mail fuer einen
    Zustand, den beim naechsten Messpunkt niemand mehr sieht.
    """
    ohne = [r["alert"] for r in regeln if not r.get("for")]
    assert not ohne, f"ohne 'for': {ohne}"


def test_der_fall_lauf_gar_nicht_gelaufen_ist_abgedeckt(regeln):
    """Der teure Fall, und der Grund fuer den ganzen Weg ueber Prometheus.

    Am 12. und 15.10.2026 ist der Lauf **ausgefallen**. Ein Programm, das
    selbst meldet, haette geschwiegen - es lief nicht. Abgedeckt sein muss
    deshalb beides: ein Lauf, der scheitert, **und** ein Lauf, der fehlt.
    """
    ausdruecke = " ".join(r["expr"] for r in regeln)
    assert "urbancrime_lauf_erfolgreich" in ausdruecke, \
        "keine Regel auf einen gescheiterten Lauf"
    assert "urbancrime_lauf_alter_sekunden" in ausdruecke, \
        "keine Regel auf einen ausgefallenen Lauf (Alter des Standes)"
    assert "urbancrime_lauf_bekannt" in ausdruecke, \
        "keine Regel auf ein fehlendes Protokoll"


def test_das_schweigen_selbst_wird_gemeldet(regeln):
    """Ohne diese Regel ist der ganze Satz wertlos.

    Faellt der Dienst aus, der die Datei ausliefert, liefern alle Regeln
    oben *keine Daten* - und keine Daten feuern in Prometheus nicht. Das
    Schweigen sieht dann aus wie Ruhe.
    """
    ausdruecke = " ".join(r["expr"] for r in regeln)
    assert re.search(r'up\{job="[^"]+"\}', ausdruecke), \
        "keine Regel auf 'up' - ein ausgefallener Scrape bliebe stumm"
    assert "absent(" in ausdruecke, \
        "keine Regel auf absent() - eine leere Metrikdatei bliebe stumm"


def test_der_jobname_der_regel_steht_so_im_ablagedokument(regeln):
    """``up{job="..."}`` haengt am Namen des Scrapes - und der steht woanders.

    Der Scrape wird im Monitoring-Stapel eingetragen, also ausserhalb dieses
    Repositories; das Ablagedokument nennt den Block zum Einsetzen. Heisst
    der Job dort anders, ist genau die Regel stumm, die das Schweigen aller
    anderen melden soll - und zwar ohne Fehlermeldung.
    """
    if not ABLAGEDOKUMENT.is_file():
        pytest.skip("docs/storage-architektur.md fehlt")
    aus_regel = {m for r in regeln
                 for m in re.findall(r'up\{job="([^"]+)"\}', r["expr"])}
    assert aus_regel, "keine Regel nennt einen Jobnamen"
    doku = ABLAGEDOKUMENT.read_text(encoding="utf-8")
    fehlen = [name for name in aus_regel
              if not re.search(rf"job_name:\s*{re.escape(name)}\b", doku)]
    assert not fehlen, (
        f"die Regel fragt job={fehlen}, das Ablagedokument nennt keinen "
        f"solchen 'job_name:' - der Scrape-Block dort gehoert mitgezogen")
