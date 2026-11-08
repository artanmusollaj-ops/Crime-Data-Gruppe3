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
Word-Dokument; geschrieben wird es aus [`ln2_konzept.md`](ln2_konzept.md).
Gemeint ist seit dem 5.10.2026 das Word-Dokument zu **LN2**: Das von LN1 ist
abgegeben und wird nicht mehr angefasst, während die Datei hier weiterläuft —
sie beschreibt seit PR #132 die Jahrgänge 2021–2026 und heisst deshalb
`ln2_konzept.md`. Der letzte Stand, der den Jahrgang 2024 beschrieb, liegt
unter *Archiv*.
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
| [`ln2_konzept.md`](ln2_konzept.md) | Konzept, Methode, Befunde — **die Hauptquelle des LN2-Word-Dokuments** |
| [`architektur-ist-und-ziel.md`](architektur-ist-und-ziel.md) | Ist- und Ziel-Architektur, Teil A und Teil B |
| [`architektur-einseiter.html`](architektur-einseiter.html) | dieselbe Architektur auf **einer A4-Seite**, zum Ausdrucken |
| [`architektur.md`](architektur.md) | der Aufbau in zwei erzeugten Bildern, dazu ein Lesepfad |
| [`sternschema-und-wuerfel.md`](sternschema-und-wuerfel.md) · [`.html`](sternschema-und-wuerfel.html) | warum Gold ein Stern ist und kein Würfel — die begründete Entwurfsentscheidung |
| [`zaehlperspektiven.md`](zaehlperspektiven.md) | vier Arten zu zählen, und was sich nicht addiert |
| [`eine-zahl.md`](eine-zahl.md) | eine Zahl über sieben Schichten zurückverfolgt |
| [`storage-architektur.md`](storage-architektur.md) | die Ablage im Aufbau: Modi, Zusagen, API, Fehlerbilder — LN1 verlangt die Storage-Evaluation ausdrücklich; Abschnitt 16 beschreibt, wie die Strecke auf `srv01` liegt, mit den gemessenen Speichergrenzen und den sieben Diensten |
| [`feldkatalog.md`](feldkatalog.md) | was jede Spalte bedeutet, 192 Spalten in 15 Tabellen — und **erzeugt** (siehe unten) |
| [`ausblick.md`](ausblick.md) | was nach LN1 käme, mit Messwerten und Reihenfolge |
| [`nachweise/`](nachweise/README.md) | die Notebooks 31, 33–37 **ausgeführt**, als HTML mit allen Ausgaben, je Lauf mit Commit, Umgebung und Datenstand — der Beleg, den die Beurteilung von LN1 vermisste (siehe unten) |

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
| [`intern/fr-stand.md`](intern/fr-stand.md) | der Stand je Anforderung des PRD — mit Beleg je Zeile; `tests/test_fr_stand.py` hält sie gegen das PRD |
| [`intern/offene-punkte.md`](intern/offene-punkte.md) | was liegen geblieben ist, an einer Stelle — Entscheidungen, Handgriffe auf dem Server, Code; je Punkt ein Verantwortlicher und ein Beleg. Die Anforderungen stehen in `fr-stand.md` |
| [`datenhistorie.md`](intern/datenhistorie.md) | was beim Aufräumen verlorenginge — Entscheidungspapier |
| [`dritte-stadt.md`](intern/dritte-stadt.md) | was eine dritte Stadt bräuchte: welche der zehn grössten US-Städte in Frage kommen, was an der Ingestion vorbereitet ist (`config/quellen.toml`) und was Schicht für Schicht noch fehlt — keine Stadt geplant |
| [`platzbedarf.md`](intern/platzbedarf.md) | was die Strecke an Platz braucht, gemessen und auf 2021–2026 hochgerechnet — **erzeugt** (siehe unten) |
| [`DETROIT_PIPELINE_ANLEITUNG.md`](intern/DETROIT_PIPELINE_ANLEITUNG.md) | Detroit-Pipeline Schritt für Schritt (Windows) |
| [`ENGINEERING_KONSOLE.md`](intern/ENGINEERING_KONSOLE.md) | die Engineering-Konsole: Funktionen, Impact-Bericht, lokale Einrichtung, Betrieb auf `srv01`, Umstellung auf den verwalteten Betrieb, Fehlerdiagnose — als PDF unter [`intern/handbuch/`](intern/handbuch/ENGINEERING_KONSOLE.pdf) (erzeugt, siehe unten) |
| [`notebook-analysesitzungen.md`](intern/notebook-analysesitzungen.md) | E-5: Datenherkunft, Voraussetzungen, Analysesitzung und gemeinsame Sperre; Job-Volumes und Vorbereitung für den Roll-out |
| [`e5-pruefnachweis.md`](intern/e5-pruefnachweis.md) | dauerhafte Zusammenfassung der lokalen Windows-/Docker-Abnahme am 31.10.2026 und der verbleibenden Server-Abnahme |
| [`console-settings.example.json`](console-settings.example.json) | Einstellungen der Konsole für 2021–2026 — vor dem ersten `init` als `config/platform_admin_settings.json`; ohne sie gilt nur 2024 |

## Erzeugt — nie von Hand ändern

Eine Handänderung hier ist beim nächsten Lauf weg. Wer den Inhalt ändern will,
ändert den Code darüber; die Wächter halten beides zusammen.

| Was | Erzeugt von |
| --- | --- |
| [`feldkatalog.md`](feldkatalog.md) | `tools/build_feldkatalog.py`, aus den Manifesten |
| [`forschungsfragen.md`](forschungsfragen.md) | `tools/build_forschungsfragen.py`, aus dem abgegebenen LN1-PDF (Kapitel 3 und 11) — **der massgebliche Wortlaut** der sechs Fragen und Hypothesen; Kapitel 3 von `ln2_konzept.md` und Notebook 36 werden dagegen gehalten. Das PDF liegt bewusst nicht im Repository, der Reproduktionswächter überspringt ohne es |
| [`intern/platzbedarf.md`](intern/platzbedarf.md) | `tools/build_platzbedarf.py`, aus der gemessenen Belegung je Schicht — und die Quelle der Grössentabelle in `architektur-ist-und-ziel.md` und im Einseiter |
| [`referenz/`](referenz/index.html) | `tools/build_referenz.py` (pdoc), eine Seite je Modul |
| [`einstieg.html`](einstieg.html) | `python -m serving.build_einstieg`, aus dem aktuellen Release — **wo ein Analyst anfängt**. Dieselbe Seite liefert auf `srv01` der Dienst `urbancrime-start` aus, mit Serveradressen statt `localhost` (`--adressen server`); sie liegt dort in einem Datenträger und nicht in diesem Ordner |
| `bilder/architektur-pakete.svg`, `bilder/architektur-datenfluss.svg`, `bilder/architektur-kontext.svg` | `tools/build_architekturbilder.py`, aus dem Importgraphen |
| `bilder/dashboard-*.png` | `tools/build_dashboardbilder.py`, fotografiert die laufenden Kibana-Dashboards |
| [`nachweise/README.md`](nachweise/README.md) | `tools/build_nachweise.py`, aus den abgelegten `nachweis.json`. Die Nachweise selbst erzeugt dasselbe Werkzeug, sie sind aber **kein Erzeugnis**: Laufzeiten wiederholen sich nicht byteweise, also kein Reproduktionswächter. Stattdessen hält `tests/test_nachweise.py` den Code-Abdruck je Notebook gegen das Notebook — ändert sich der Code, ist der Nachweis veraltet und der Test rot |
| [`intern/handbuch/ENGINEERING_KONSOLE.pdf`](intern/handbuch/ENGINEERING_KONSOLE.pdf) | `tools/build_konsole_pdf.py`, aus `intern/ENGINEERING_KONSOLE.md`; der Titel trägt den Hash des Markdowns, und `tests/test_konsole_handbuch.py` vergleicht ihn |

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

Eine Ausnahme steht darunter: Die LN1-Fassung des Konzepts ist nicht
aufgegangen, sie ist **abgelöst**. Sie liegt vollständig im Archiv, weil sie die
Quelle einer abgegebenen Arbeit ist und ihr Studienzeitraum — der Jahrgang
2024 — in der lebenden Fassung nicht mehr vorkommt.

| Dokument | Aufgegangen in |
| --- | --- |
| [`archiv/2026-09-09-detroit-zeitzonenvertrag.md`](archiv/2026-09-09-detroit-zeitzonenvertrag.md) | dem Code (`detroit_arcgis.build_local_date_window`) und `AENDERUNGEN.md` |
| [`archiv/2026-10-04-ln1-konzept-jahrgang-2024.md`](archiv/2026-10-04-ln1-konzept-jahrgang-2024.md) | nichts — **abgelöst** von `ln2_konzept.md`; der letzte Stand (`9160ff1`), der den Jahrgang 2024 beschrieb, vollständig |

---

## Was hier bewusst **nicht** steht

* **Berichte und Abgleiche** liegen in [`reports/`](../reports/) — sie sind
  datiert und werden nicht nachgeführt.
* **Notebooks** liegen in [`notebooks/`](../notebooks/). Sie sind der
  Rechenweg, nicht die Dokumentation; jede Zahl darin rechnet sich selbst nach.
* **Die Testsuite** ist die ausführbare Dokumentation. Was ein Dokument
  behauptet und eine Zahl betrifft, steht in `tests/` noch einmal als Wächter.
