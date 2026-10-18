"""Das Brett zeigt Messwerte, die es wirklich gibt.

**Warum es das braucht.** FR-30 verlangt den Betriebsblick *in Grafana*:
ob die Strecke laeuft, wie alt jede Quelle ist, wo die Drift steht, wie voll
die Platte ist. Ein Brett ist dabei die unangenehmste Sorte Artefakt: Ein
Panel mit einem falschen Metriknamen zeigt eine **leere Flaeche**, und eine
leere Flaeche liest sich wie "null" oder wie "gerade nichts passiert" - nicht
wie ein Fehler. Grafana sagt dazu nichts, und niemand merkt es, bis jemand
die Zahl braucht.

Geprueft wird deshalb dasselbe wie bei den Alarmregeln
(``tests/test_alarmregeln.py``), und auf demselben Weg: Die Namen kommen aus
einem **echten Lauf** von ``serving.betriebsstand``, nicht aus einer Liste
hier. Stuende sie hier, waere sie die, die veraltet.

Was dieser Waechter **nicht** prueft: ob das Brett schoen ist oder ob die
Schwellen richtig gewaehlt sind. Das erste ist Geschmack, das zweite eine
Aussage ueber den Betrieb - beides kann kein Test.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BRETT = PROJECT_ROOT / "docker" / "grafana-brett" / "urbancrime.json"
ABLAGEDOKUMENT = PROJECT_ROOT / "docs" / "storage-architektur.md"

#: Was andere liefern und wir nicht. ``up`` kommt von Prometheus selbst, die
#: Dateisystemwerte von node-exporter - FR-30 nennt die Plattenfuellung
#: ausdruecklich, und ein eigener Exporter dafuer waere ein neuer Dienst.
FREMDE = frozenset({"up", "node_filesystem_avail_bytes",
                    "node_filesystem_size_bytes"})

#: PromQL-Funktionen und Schluesselwoerter, die wie ein Name aussehen.
PROMQL = frozenset({"rate", "increase", "sum", "avg", "max", "min", "count",
                    "by", "without", "on", "ignoring", "and", "or", "unless",
                    "absent", "time", "changes", "delta", "offset"})


@pytest.fixture(scope="module")
def brett() -> dict:
    if not BRETT.is_file():
        pytest.skip(f"{BRETT} fehlt")
    return json.loads(BRETT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def panels(brett) -> list[dict]:
    """Alle Panels, auch die in eingeklappten Reihen."""
    gefunden = []
    for p in brett.get("panels", []):
        gefunden.append(p)
        gefunden.extend(p.get("panels", []))
    return gefunden


@pytest.fixture(scope="module")
def ausgegeben(tmp_path_factory) -> set[str]:
    """Die Messwertnamen aus einem echten Lauf des Moduls."""
    import storage
    from serving import betriebsstand

    protokoll = {
        "status": "complete",
        "started_at_utc": "2026-10-18T04:30:00Z",
        "finished_at_utc": "2026-10-18T04:41:00Z",
        "stages": [{"name": "crime_offense", "gruppe": "silver",
                    "exit": 0, "sekunden": 117.0}],
        "source_freshness": {"chicago": "2026-10-17T00:00:00Z"},
        "output_rows": {"silver/crime_offense": 1886254},
        "release": {"release_id": "2026-10-18T04-41-00Z", "files": 28,
                    "bytes": 182069322, "published": True},
    }
    drift = {"within_tolerance": True, "measures": {
        "gold/fact_offense": {"documented": 1, "measured": 1, "drift": 0,
                              "drift_percent": 0.0, "exceeded": False}}}
    wurzel = tmp_path_factory.mktemp("brett")
    text = betriebsstand.metriken(protokoll, drift=drift)
    assert text, "das Modul gab nichts aus"
    _ = storage.for_root(wurzel)   # dieselbe Ablage wie im Betrieb
    return {m.group(1) for m in re.finditer(r"^([a-z_]+)(\{|\s)", text, re.M)}


def namen(expr: str) -> set[str]:
    """Die Metriknamen eines Ausdrucks - Klammerbloecke ganz heraus."""
    ohne_marken = re.sub(r"\{[^}]*\}", " ", expr)
    roh = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", ohne_marken))
    return roh - PROMQL


def ausdruecke(panels: list[dict]) -> list[tuple[str, str]]:
    return [(p.get("title", "(ohne Titel)"), z["expr"])
            for p in panels for z in p.get("targets", []) if z.get("expr")]


def test_das_brett_hat_panels_mit_ausdruecken(panels):
    """Sonst prueft alles darunter nichts und bleibt gruen."""
    gefunden = ausdruecke(panels)
    assert len(gefunden) >= 10, (
        f"nur {len(gefunden)} Ausdruecke - dann ist der Leser kaputt oder "
        f"das Brett leer")


def test_jeder_ausdruck_zeigt_auf_einen_messwert_den_es_gibt(panels, ausgegeben):
    """Der Kern. Ein Tippfehler zeigt eine leere Flaeche, keinen Fehler."""
    bekannt = ausgegeben | FREMDE
    fehler = [f"{titel}: {name!r} gibt niemand aus"
              for titel, expr in ausdruecke(panels)
              for name in sorted(namen(expr)) if name not in bekannt]
    assert not fehler, "\n".join(fehler) + f"\n\nausgegeben: {sorted(bekannt)}"


def test_jedes_panel_nennt_die_datenquelle_ausdruecklich(panels):
    """Die Vorgabe reicht nicht.

    Auf `srv01` gibt es zwei Datenquellen (Prometheus und Loki). Ein Panel
    ohne Angabe nimmt die voreingestellte - und zeigt nach der naechsten
    Umstellung leere Flaechen statt eines Fehlers.
    """
    fehler = []
    for p in panels:
        if p.get("type") == "row":
            continue
        quelle = p.get("datasource") or {}
        if quelle.get("uid") != "prometheus":
            fehler.append(f"{p.get('title')}: datasource={quelle}")
    assert not fehler, "\n".join(fehler)


def test_die_vier_dinge_aus_fr30_kommen_vor(panels):
    """FR-30 nennt sie ausdruecklich, also werden sie einzeln geprueft.

    *„ob die Strecke laeuft, wie alt jede Quelle ist, wo die Drift steht,
    wie voll die Platte ist."* Ein Brett, das drei davon zeigt, erfuellt die
    Anforderung nicht - und das faellt beim Ansehen nicht auf, weil die
    vierte Flaeche einfach fehlt statt leer zu sein.
    """
    alle = " ".join(expr for _, expr in ausdruecke(panels))
    fehlen = [was for was, nadel in (
        ("ob die Strecke laeuft", "urbancrime_lauf_erfolgreich"),
        ("wie alt jede Quelle ist", "urbancrime_quelle_alter_sekunden"),
        ("wo die Drift steht", "urbancrime_drift"),
        ("wie voll die Platte ist", "node_filesystem"),
    ) if nadel not in alle]
    assert not fehlen, f"FR-30 verlangt auch: {fehlen}"


def test_das_brett_traegt_eine_feste_kennung_und_ist_nicht_bearbeitbar(brett):
    """Beides haengt an der Provisionierung.

    Die Kennung macht aus zwei Einspielungen dasselbe Brett statt zweier.
    Und ``allowUiUpdates: false`` im Stapel heisst: Was jemand in der
    Oberflaeche aendert, ist beim naechsten Einlesen weg - ein Brett, das
    sich als bearbeitbar ausgibt, ladet dazu ein.
    """
    assert brett.get("uid"), "ohne uid entsteht bei jeder Einspielung ein neues Brett"
    assert brett.get("editable") is False, (
        "editable muss false sein - der Stapel liest das Brett alle 30 "
        "Sekunden neu und wirft Aenderungen weg")
    assert brett.get("title"), "ohne Titel findet es niemand"


def test_das_ablagedokument_nennt_dieses_verzeichnis():
    """Eingehaengt wird im fremden Monitoring-Stapel.

    Dieselbe Trennung wie bei den Alarmregeln: Hier liegt das Brett, dort
    steht der Block zum Einsetzen. Geht das Verzeichnis um und das Dokument
    nicht mit, haengt jemand eines ein, das es nicht gibt - und Grafana
    startet trotzdem, nur ohne das Brett.
    """
    if not ABLAGEDOKUMENT.is_file():
        pytest.skip("docs/storage-architektur.md fehlt")
    relativ = BRETT.parent.relative_to(PROJECT_ROOT).as_posix()
    assert relativ in ABLAGEDOKUMENT.read_text(encoding="utf-8"), (
        f"das Ablagedokument nennt '{relativ}' nicht")
