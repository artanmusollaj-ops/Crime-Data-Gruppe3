"""Die Reihenfolge, in der die Schichten entstehen - und ihr Gesamtmanifest.

Bis hierher konnte jede Stufe fuer sich laufen, und jede wusste, wo ihre
Eingaben liegen. Was fehlte, war zweierlei:

**Die Reihenfolge.** ``build_crime_offense`` braucht ``silver/tract``,
``build_gold`` braucht alle vier Silver-Tabellen, und die Census-Ingestion
braucht zwei Aufrufe - einen fuer ``tract``, einen fuer ``place``. Wer das
nicht weiss, baut ein Gold ohne Stadtzuordnung, und **es scheitert dabei
nicht**: Die Rate hat dann einfach keinen Nenner.

**Die Herkunft an einer Stelle.** Jede Schicht nennt ihre direkte Quelle, aber
keine sagt, auf welchen *Bronze-Laeufen* eine Gold-Zahl ruht. Bei Quellen, die
sich staendig bewegen - Chicago und Detroit aendern Eintraege noch Jahre nach
der Tat -, ist das die Frage, die zaehlt: **Auf welchem Stand beruht diese
Zahl?**

**Was der Controller bewusst nicht tut.**

*Keine Prozesssperre.* Zwei gleichzeitige Laeufe koennen nichts zerstoeren:
Ingestion-Laeufe sind unveraenderlich und additiv, Silver und Gold werden ueber
``.part`` geschrieben und atomar umbenannt. Schlimmstenfalls gewinnt der
zweite - und der schreibt denselben Stand.

*Keine Wiederaufnahme.* Jede Stufe ist idempotent und die ganze Strecke laeuft
in Minuten. "Nochmal starten" loest dasselbe Problem billiger als ein
Zustandsautomat, den niemand testet.

*Keine Parallelitaet.* Fuenf Quellen seriell zu laden dauert wenige Minuten und
haengt fast nur am Netz. Nebenlaeufigkeit waere Aufwand ohne Gegenwert.
"""

from __future__ import annotations

ORCHESTRATION_LAYER = "orchestration"

# Wo das Gesamtmanifest liegt. Neben den Daten und nicht in einer Schicht - es
# beschreibt den Lauf, nicht eine Tabelle.
LAUF_MANIFEST = "pipeline_run.json"

# Beide Vokabulare gelten. Acht Module schreiben ``complete``, Detroits
# Ingestion ``SUCCESS``. Das zu vereinheitlichen wuerde jedes bereits
# geschriebene Manifest ungueltig machen; der Controller nimmt deshalb beide
# und nennt sie hier einmal, statt die Kenntnis zu verstreuen.
FERTIG = {"complete", "success"}
