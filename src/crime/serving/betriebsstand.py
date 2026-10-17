"""Der Betriebsblick als Text, den eine Maschine liest.

    python -m serving.betriebsstand                      # nach /app/startseite/metrics
    python -m serving.betriebsstand --ziel /tmp/metrics   # woandershin
    python -m serving.betriebsstand --zeigen              # nur ausgeben

**Warum es das braucht (FR-30, und FR-17 zur Haelfte).** Am 17.10.2026 war zu
sehen, was fehlt: Der woechentliche Lauf auf ``srv01`` ist am 12. und am
15.10. gescheitert, und gewusst hat es niemand - bis jemand von Hand ein Log
geschickt hat. Danach meldete ``serving.pruefe_stand`` wochenlang eine
fehlende Tabelle, und niemand hat den Bericht gelesen. **Der Betrieb hatte
keine Stimme.**

Gemessen wird dafuer **nichts Neues**: ``data/pipeline_run.json`` traegt schon
Status, Dauer, jede Stufe mit ihrem Exitcode, die Quellenfrische, die
Zeilenzahlen und das Release. Es fehlte nicht die Messung, sondern die
Sichtbarkeit. Dieses Modul rendert, was dasteht, im Textformat von Prometheus.

**Was ein fehlender Lauf heissen muss.** Liegt kein Protokoll, ist die Antwort
nicht "alles in Ordnung" und auch nicht "nichts" - sondern ``lauf_bekannt 0``.
Eine Datei, die bei einem fehlenden Lauf schweigt, sieht aus wie eine, die
Erfolg meldet; das ist die teuerste Art, falsch zu sein. Mit der Null kann
``absent()`` auf der anderen Seite alarmieren, und ein Mensch sieht es auch.

**Wo die Grenze dieses Moduls liegt - und sie ist am 17.10.2026 gemessen.**
Es schreibt eine Datei. Dass jemand sie liest, ist Infrastruktur und liegt
**nicht in diesem Repository**:

* Prometheus wird auf ``srv01`` aus
  ``/srv/docker/infrastructure/monitoring/prometheus/prometheus.yaml``
  konfiguriert - geteilt mit paperless, n8n, docmost - und scrapet heute nur
  sich selbst.
* Prometheus liegt im Netz ``monitoring``, der Dienst ``start`` dieses
  Vorhabens in ``proxy``. Ein Scrape braucht eine Netzzeile; der
  Pipeline-Container erreicht ``alertmanager:9093`` nachweislich nicht.
* Alertmanager laeuft, traegt aber die **Beispielvorgabe**
  (``webhook_configs: http://127.0.0.1:5001/``) - dort hoert nichts. Es gibt
  auf ``srv01`` kein ``MAILTO``, kein ``sendmail`` und keinen laufenden MTA,
  und der Crontab leitet ohnehin alles in ein Log und unterdrueckt damit die
  Cron-Mail.

Deshalb erfuellt dieses Modul **FR-30 zur Haelfte und FR-17 nicht**: Ein
Meldekanal laesst sich nicht erfinden, und welcher es sein soll, ist eine
Entscheidung ueber fremde Dienste. Was hier steht, ist der Teil, der ohne
diese Entscheidung richtig ist - und ab dem Tag, an dem eine Scrape-Zeile
dazukommt, ist der Betriebsblick da.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from storage import for_root

#: Das Protokoll, das ``orchestration.run_all`` am Ende schreibt.
PROTOKOLL = "pipeline_run.json"

#: Wohin im Abbild geschrieben wird. Derselbe Datentraeger, den der Dienst
#: ``start`` schreibgeschuetzt ausliefert (FR-31) - der eine Ort, an dem
#: dieses Vorhaben schon etwas veroeffentlicht.
VORGABE_ZIEL = Path("/app/startseite/metrics")

#: Vorsilbe aller Messwerte. Ein Name ohne sie waere im Prometheus eines
#: geteilten Servers nicht zuzuordnen.
VORSILBE = "urbancrime"


def _zeit(wert: Any) -> float | None:
    """ISO-8601 in Unixsekunden - oder ``None``, wenn es keine Zeit ist."""
    if not wert:
        return None
    try:
        text = str(wert).replace("Z", "+00:00")
        zeitpunkt = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    if zeitpunkt.tzinfo is None:
        zeitpunkt = zeitpunkt.replace(tzinfo=timezone.utc)
    return zeitpunkt.timestamp()


def _zeile(metrik: str, wert: float | int, **marken: str) -> str:
    """Eine Messzeile. Marken werden gesetzt, nicht formatiert geraten.

    Der erste Parameter heisst ``metrik`` und nicht ``name``: Eine der Marken
    heisst ``name`` (die Stufe), und ``_zeile("stufe_exit", 0, name="gold")``
    traf damit zweimal dasselbe Argument.
    """
    if marken:
        inhalt = ",".join(f'{k}="{_entwerte(v)}"'
                          for k, v in sorted(marken.items()))
        return f"{VORSILBE}_{metrik}{{{inhalt}}} {wert}"
    return f"{VORSILBE}_{metrik} {wert}"


def _entwerte(wert: object) -> str:
    """Rueckwaertsschraegstrich und Anfuehrungszeichen maskieren.

    Das Textformat von Prometheus verlangt es, und ein Markenwert kommt hier
    aus den Daten - ein Tabellenname, ein Quellpfad. Ein Anfuehrungszeichen
    darin zerriss die Zeile.
    """
    return str(wert).replace("\\", "\\\\").replace('"', '\\"')


def protokoll_lesen(ablage: Any) -> dict[str, Any] | None:
    """Das Laufprotokoll - oder ``None``, wenn keines liegt.

    Nimmt die **Ablage** und keine Wurzel. Das ist nicht Geschmack: Ein
    ``--data-root`` ohne Vorgabe ist ``None``, und jede Verwendung muss durch
    ``for_root`` gehen, bevor sie weiterreist
    (``tests/storage/test_pipelines_hybrid.py``). Mit der Ablage im Argument
    kann die Frage hier gar nicht mehr auftreten.

    """
    datei = ablage.local_path(PROTOKOLL)
    # Lokal mit Absicht: ``pipeline_run.json`` ist das Protokoll des letzten
    # Laufs auf *dieser* Maschine, keine Schichttabelle. Es wird nie
    # publiziert - oben gibt es keinen Lauf, dessen Protokoll das waere.
    if not datei.is_file():
        return None
    try:
        return json.loads(datei.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def metriken(protokoll: dict[str, Any] | None,
             jetzt: float | None = None) -> str:
    """Der Betriebsblick im Textformat von Prometheus.

    Die Reihenfolge ist fest und die Hilfetexte stehen dabei: Eine
    Metrikdatei ist eine Schnittstelle, und eine Schnittstelle, deren Felder
    sich je Lauf anders ordnen, ist keine.
    """
    jetzt = jetzt if jetzt is not None else datetime.now(timezone.utc).timestamp()
    aus: list[str] = [
        "# HELP " + VORSILBE + "_lauf_bekannt Ob ein Laufprotokoll vorliegt.",
        "# TYPE " + VORSILBE + "_lauf_bekannt gauge",
    ]
    if protokoll is None:
        # **Die Null ist die Aussage.** Schweigen saehe aus wie Erfolg.
        aus.append(_zeile("lauf_bekannt", 0))
        return "\n".join(aus) + "\n"
    aus.append(_zeile("lauf_bekannt", 1))

    gruen = str(protokoll.get("status", "")).lower() == "complete"
    aus += [
        "# HELP " + VORSILBE + "_lauf_erfolgreich 1 wenn der letzte Lauf gruen war.",
        "# TYPE " + VORSILBE + "_lauf_erfolgreich gauge",
        _zeile("lauf_erfolgreich", 1 if gruen else 0),
    ]

    ende = _zeit(protokoll.get("finished_at_utc"))
    beginn = _zeit(protokoll.get("started_at_utc"))
    if ende is not None:
        aus += [
            "# HELP " + VORSILBE + "_lauf_ende_sekunden Unixzeit des Laufendes.",
            "# TYPE " + VORSILBE + "_lauf_ende_sekunden gauge",
            _zeile("lauf_ende_sekunden", round(ende, 3)),
            "# HELP " + VORSILBE + "_lauf_alter_sekunden Wie alt der Stand ist.",
            "# TYPE " + VORSILBE + "_lauf_alter_sekunden gauge",
            _zeile("lauf_alter_sekunden", round(jetzt - ende, 3)),
        ]
    if beginn is not None and ende is not None:
        aus += [
            "# HELP " + VORSILBE + "_lauf_dauer_sekunden Dauer des letzten Laufs.",
            "# TYPE " + VORSILBE + "_lauf_dauer_sekunden gauge",
            _zeile("lauf_dauer_sekunden", round(ende - beginn, 3)),
        ]

    stufen = protokoll.get("stages") or []
    if stufen:
        aus += [
            "# HELP " + VORSILBE + "_stufe_exit Exitcode je Stufe; 0 ist gruen.",
            "# TYPE " + VORSILBE + "_stufe_exit gauge",
        ]
        aus += [
            _zeile("stufe_exit", int(s.get("exit", -1)),
                   gruppe=str(s.get("gruppe", "")), name=str(s.get("name", "")))
            for s in stufen
        ]
        aus += [
            "# HELP " + VORSILBE + "_stufe_sekunden Dauer je Stufe.",
            "# TYPE " + VORSILBE + "_stufe_sekunden gauge",
        ]
        aus += [
            _zeile("stufe_sekunden", float(s.get("sekunden", 0)),
                   gruppe=str(s.get("gruppe", "")), name=str(s.get("name", "")))
            for s in stufen
        ]

    frische = protokoll.get("source_freshness") or {}
    if frische:
        aus += [
            "# HELP " + VORSILBE + "_quelle_alter_sekunden Alter des juengsten Laufs je Quelle.",
            "# TYPE " + VORSILBE + "_quelle_alter_sekunden gauge",
        ]
        for quelle in sorted(frische):
            wann = _zeit(frische[quelle])
            if wann is not None:
                aus.append(_zeile("quelle_alter_sekunden", round(jetzt - wann, 3),
                                  quelle=quelle))

    zeilen = protokoll.get("output_rows") or {}
    if zeilen:
        aus += [
            "# HELP " + VORSILBE + "_tabelle_zeilen Zeilen je gebauter Tabelle.",
            "# TYPE " + VORSILBE + "_tabelle_zeilen gauge",
        ]
        aus += [_zeile("tabelle_zeilen", int(zeilen[t]), tabelle=t)
                for t in sorted(zeilen)]

    freigabe = protokoll.get("release") or {}
    if freigabe.get("release_id"):
        aus += [
            "# HELP " + VORSILBE + "_release_dateien Dateien im letzten Release.",
            "# TYPE " + VORSILBE + "_release_dateien gauge",
            _zeile("release_dateien", int(freigabe.get("files") or 0)),
            "# HELP " + VORSILBE + "_release_bytes Groesse des letzten Releases.",
            "# TYPE " + VORSILBE + "_release_bytes gauge",
            _zeile("release_bytes", int(freigabe.get("bytes") or 0)),
            "# HELP " + VORSILBE + "_release_publiziert 1 wenn es hochgebracht wurde.",
            "# TYPE " + VORSILBE + "_release_publiziert gauge",
            _zeile("release_publiziert", 1 if freigabe.get("published") else 0),
        ]
    else:
        # Auch das ist eine Aussage: Die Strecke lief, ein Release entstand
        # nicht. Am 17.10.2026 dreimal der Fall - zweimal am Kontingent des
        # Buckets, einmal an einem Serverfehler beim Upload.
        aus += [
            "# HELP " + VORSILBE + "_release_dateien Dateien im letzten Release.",
            "# TYPE " + VORSILBE + "_release_dateien gauge",
            _zeile("release_dateien", 0),
        ]

    return "\n".join(aus) + "\n"


def kommandozeile() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m serving.betriebsstand", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ziel", type=Path, default=VORGABE_ZIEL,
                   help=f"wohin geschrieben wird (Vorgabe: {VORGABE_ZIEL})")
    p.add_argument("--data-root", type=Path, default=None,
                   help="Wurzel der Schichten (Vorgabe: LOCAL_DATA_ROOT)")
    p.add_argument("--zeigen", action="store_true",
                   help="nur ausgeben, nichts schreiben")
    return p


def main(argv: list[str] | None = None) -> int:
    args = kommandozeile().parse_args(argv)
    protokoll = protokoll_lesen(for_root(args.data_root))
    text = metriken(protokoll)
    if args.zeigen:
        print(text, end="")
        return 0
    args.ziel.parent.mkdir(parents=True, exist_ok=True)
    args.ziel.write_text(text, encoding="utf-8")
    zahl = len([z for z in text.splitlines() if not z.startswith("#")])
    print(f"{args.ziel}: {zahl} Messwerte"
          + ("" if protokoll else " - kein Laufprotokoll, lauf_bekannt 0"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
