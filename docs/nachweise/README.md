# Nachweise — ausgeführte Notebooks

Erzeugt von `tools/build_nachweise.py` — nie von Hand ändern.

Die Notebooks unter `notebooks/` liegen ohne Ausgaben im Repository. Hier
liegen sie **ausgeführt**: je Lauf ein Ordner mit einer HTML-Datei je
Notebook, lesbar ohne Python und ohne Daten, und `nachweis.json` mit
Commit, Umgebung, Laufzeit und Datenstand. `tests/test_nachweise.py` hält
den jüngsten Nachweis gegen die Notebooks: Ändert sich der Code eines
Notebooks, ist der Nachweis veraltet und der Test rot.

Ein Nachweis ist kein Erzeugnis: Laufzeiten wiederholen sich nie byteweise.
Er belegt, dass dieser Code an diesem Tag auf diesem Datenstand gelaufen
ist und dies ausgegeben hat.

| Lauf | Commit | Datenstand (Silver) | Release passt | Notebooks |
| --- | --- | --- | --- | --- |
| 2026-11-07_7dd8f89 | `7dd8f89` | `cac64863d0b9` | nein (letztes: `2026-10-17T08-38-50Z`) | [31](2026-11-07_7dd8f89/31_storage_evaluation.html), [33](2026-11-07_7dd8f89/33_serving_evaluation.html), [34](2026-11-07_7dd8f89/34_gold_sternschema.html), [35](2026-11-07_7dd8f89/35_kontrollen.html), [36](2026-11-07_7dd8f89/36_hypothesen.html), [37](2026-11-07_7dd8f89/37_quellbewegung.html) |
