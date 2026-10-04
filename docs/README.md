# Welches Dokument für wen

Dieser Ordner hat drei Leserkreise, und bis zum 18.9.2026 sah man ihnen das
nicht an. Diese Seite ist die Einteilung — nicht als Erinnerung, sondern
aufgeschrieben und von `tests/test_dokumentwegweiser.py` dagegengehalten: Ein
neues Dokument in `docs/`, das hier nicht steht, lässt den Test fallen.

Wer nur eines lesen will, liest das [README im Projekt-Root](../README.md).
Hier steht, was es sonst noch gibt.

---

## Abgabe — was in das Word-Dokument fliesst

**Die Abgabe liegt nicht in diesem Ordner.** Sie entsteht als eigenes
Word-Dokument; geschrieben wird es aus [`ln1_konzept.md`](ln1_konzept.md).
Die Dokumente hier sind seine **Quelle**: Ihr Inhalt wandert hinein. Das
Word-Dokument verweist **nicht** auf sie zurück — es steht für sich, und wer es
liest, soll nicht ins Repository springen müssen (Entscheid vom 19.9.2026).
Geschrieben sind sie trotzdem alle für jemanden, der das Projekt nicht kennt:
Was sich nicht ohne uns lesen lässt, lässt sich auch nicht übertragen.

> **Die Fassung hier ist die belastbarere.** Jede Zahl in diesen Dokumenten
> wird von der Testsuite gegen die gebauten Daten gehalten. Im Word-Dokument
> gilt das nicht mehr — dort ist eine Zahl so aktuell wie der Tag, an dem sie
> kopiert wurde. Deshalb spät übertragen, und danach
> `python -m pytest -m referenzstand` laufen lassen.

| Dokument | Was darin steht |
| --- | --- |
| [`ln1_konzept.md`](ln1_konzept.md) | Konzept, Methode, Befunde — **die Hauptquelle des Word-Dokuments** |
| [`architektur-ist-und-ziel.md`](architektur-ist-und-ziel.md) | Ist- und Ziel-Architektur, Teil A und Teil B |
| [`architektur-einseiter.html`](architektur-einseiter.html) | dieselbe Architektur auf **einer A4-Seite**, zum Ausdrucken |
| [`architektur.md`](architektur.md) | der Aufbau in zwei erzeugten Bildern, dazu ein Lesepfad |
| [`sternschema-und-wuerfel.md`](sternschema-und-wuerfel.md) · [`.html`](sternschema-und-wuerfel.html) | warum Gold ein Stern ist und kein Würfel — die begründete Entwurfsentscheidung |
| [`zaehlperspektiven.md`](zaehlperspektiven.md) | vier Arten zu zählen, und was sich nicht addiert |
| [`eine-zahl.md`](eine-zahl.md) | eine Zahl über sieben Schichten zurückverfolgt |
| [`storage-architektur.md`](storage-architektur.md) | die Ablage im Aufbau: Modi, Zusagen, API, Fehlerbilder — LN1 verlangt die Storage-Evaluation ausdrücklich |
| [`feldkatalog.md`](feldkatalog.md) | was jede Spalte bedeutet, 174 Spalten in 13 Tabellen — und **erzeugt** (siehe unten) |
| [`ausblick.md`](ausblick.md) | was nach LN1 käme, mit Messwerten und Reihenfolge |

## Intern — was wir beim Arbeiten brauchen

Sie liegen seit dem 19.9.2026 in [`intern/`](intern/), damit dieser Ordner nur
noch enthält, was in die Abgabe einfliesst.

Diese Dokumente setzen voraus, dass man am Projekt arbeitet. Sie gehören
**nicht** in die Abgabe; einige widersprächen ihr sogar dem Ton nach, weil sie
offene Fragen und Lücken benennen. Das Konzept führt sie in 11.5 unter genau
diesem Vorbehalt.

Wird das Repository mit abgegeben, liegen sie zwar bei — das lässt sich nicht
trennen und soll es auch nicht. Was sich steuern lässt, ist, **worauf das
Word-Dokument verweist**: auf keines davon.

| Dokument | Was darin steht |
| --- | --- |
| [`projektabsprache.md`](intern/projektabsprache.md) | Absprachen und Entscheide im Team |
| [`leistungsnachweise.md`](intern/leistungsnachweise.md) | Anforderungen, Stand, Lücken — ist *über* den LN, nicht Teil davon |
| [`AENDERUNGEN.md`](intern/AENDERUNGEN.md) | das Projektgedächtnis: was sich wann geändert hat und warum |
| [`datenhistorie.md`](intern/datenhistorie.md) | was beim Aufräumen verlorenginge — Entscheidungspapier |
| [`platzbedarf.md`](intern/platzbedarf.md) | was die Strecke an Platz braucht, gemessen und auf 2021–2026 hochgerechnet — **erzeugt** (siehe unten) |
| [`DETROIT_PIPELINE_ANLEITUNG.md`](intern/DETROIT_PIPELINE_ANLEITUNG.md) | Detroit-Pipeline Schritt für Schritt (Windows) |

## Erzeugt — nie von Hand ändern

Eine Handänderung hier ist beim nächsten Lauf weg. Wer den Inhalt ändern will,
ändert den Code darüber; die Wächter halten beides zusammen.

| Was | Erzeugt von |
| --- | --- |
| [`feldkatalog.md`](feldkatalog.md) | `tools/build_feldkatalog.py`, aus den Manifesten |
| [`intern/platzbedarf.md`](intern/platzbedarf.md) | `tools/build_platzbedarf.py`, aus der gemessenen Belegung je Schicht — und die Quelle der Grössentabelle in `architektur-ist-und-ziel.md` und im Einseiter |
| [`referenz/`](referenz/index.html) | `tools/build_referenz.py` (pdoc), eine Seite je Modul |
| [`einstieg.html`](einstieg.html) | `tools/build_einstieg.py`, aus dem aktuellen Release — **wo ein Analyst anfängt** |
| `bilder/architektur-pakete.svg`, `bilder/architektur-datenfluss.svg`, `bilder/architektur-kontext.svg` | `tools/build_architekturbilder.py`, aus dem Importgraphen |
| `bilder/dashboard-*.png` | `tools/build_dashboardbilder.py`, fotografiert die laufenden Kibana-Dashboards |

Die übrigen Dateien in [`bilder/`](bilder/) sind von Hand gezeichnet
(`granularitaet.svg`, `stern.svg`, `wuerfel.svg`) beziehungsweise für Folien
gesetzt (`Data_Pipeline_fuer_Folie.png`, `Endarchitektur_LN2.png`).

## Quellen — die amtlichen Unterlagen

[`quellen/`](quellen/) hält die sieben Dokumente, aus denen die Crosswalks in
`config/` **reproduziert** werden: NIBRS-Spezifikation und -Handbuch, Michigans
MICR-Handbücher, Illinois' Codetabellen. Sie liegen im Repository, weil ein
Crosswalk ohne seine Quelle eine Behauptung wäre — `tests/config/` baut die CSVs
daraus neu und vergleicht byteweise.

Zusammen 8,8 MB. Bis zum 18.9.2026 lagen sie zwischen der Prosa.

**Woher jedes Dokument stammt**, steht in
[`quellen/README.md`](quellen/README.md): Adresse, Herausgeber, Fassung, Grösse
und SHA-256 je Datei. Fünf der sieben sind dort per Prüfsumme gegen die Quelle
belegt — am 19.9.2026 heruntergeladen und byteweise verglichen; die beiden
Michigan-Dokumente nur per Adresse, weil `michigan.gov` automatisierte Abrufe
mit HTTP 403 beantwortet. `tests/test_quellenverzeichnis.py` hält die Liste
vollständig: eine Unterlage ohne Eintrag lässt die Suite fallen.

## Archiv — überholt, aber nicht gelöscht

[`archiv/`](archiv/) hält Dokumente, deren Inhalt anderswo aufgegangen ist.
Gelöscht werden sie nicht: Ein Eintrag in `AENDERUNGEN.md` verweist darauf, und
ein toter Verweis wäre schlimmer als eine überholte Datei.

| Dokument | Aufgegangen in |
| --- | --- |
| [`archiv/2026-09-09-detroit-zeitzonenvertrag.md`](archiv/2026-09-09-detroit-zeitzonenvertrag.md) | dem Code (`detroit_arcgis.build_local_date_window`) und `AENDERUNGEN.md` |

---

## Was hier bewusst **nicht** steht

* **Berichte und Abgleiche** liegen in [`reports/`](../reports/) — sie sind
  datiert und werden nicht nachgeführt.
* **Notebooks** liegen in [`notebooks/`](../notebooks/). Sie sind der
  Rechenweg, nicht die Dokumentation; jede Zahl darin rechnet sich selbst nach.
* **Die Testsuite** ist die ausführbare Dokumentation. Was ein Dokument
  behauptet und eine Zahl betrifft, steht in `tests/` noch einmal als Wächter.
