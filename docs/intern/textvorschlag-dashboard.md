# Textvorschlag: das Dashboard im Konzept

Für Artan. Stand 25.11.2026. Ein **Vorschlag**, kein Beleg. In
[`ln2_konzept.md`](../ln2_konzept.md) steht das Dashboard seit dem 25.11.2026
als Fakt: in 5.1, in der Konsumententabelle von 5.2 und in 11.1. Was dort
fehlt, ist eine Beschreibung: was es zeigt, und warum es so gebaut ist. Das ist
neue Argumentation und gehört deshalb dir. Der Vorschlag unten ist der Stoff
dafür. Die Quelle jeder Aussage ist der Modulkopf unter
`src/crime/serving/dashboard/`.

**Wo es hinpasst.** In 5.2, als eigener Abschnitt nach „Wer konsumiert“, zum
Beispiel „Was gebaut ist: das Dashboard“. Die Vorlage sind deine Entwürfe
unter `docs/bilder/dashboard_*.png`.

## Die acht Bretter

| Brett | Frage auf der Seite | Was es zeigt |
| --- | --- | --- |
| Überblick | Kriminalität im Überblick | Fälle und Taten je Stadt, die Rate je 1'000 Einwohner, die Veränderung zum Vorjahr |
| Zeitverlauf | Zeitliche Muster erkennen | Monate gegen dieselben Monate des Vorjahrs, Wochentag und Stunde in Ortszeit, ob sich beide Städte unabhängig von ihrer Grösse gleich entwickeln, Tageslicht und Dunkelheit |
| Geografie | Räumliche Verteilung | eine Karte je Stadt, nach Tract, Polizeibezirk oder Stadtteil, jede Fläche nach einer Kennzahl gefärbt, dazu die Flächen mit den höchsten Werten |
| Deliktstruktur | Welche Delikte verändern sich? | welche Kategorien eine Stadt tragen und welche sich gegen das Vorjahr verändern |
| Datenqualität | Sind die Daten analysebereit? | Zuordnung und Verortung im gewählten Ausschnitt, gegen dieselben Schwellen wie das Publish-Gate |
| Soziales Umfeld | Fallrate und Armut | die Fallrate je Tract neben Armutsquote und Medianeinkommen, in festen Bändern und als Karte mit neun Farben |
| Wetter | Hängen die Fallzahlen am Wetter? | Fälle je Tag gegen das Wetter, roh und am Mittel des eigenen Monats gemessen |
| Quellbewegung | Was ändern und löschen die Quellen? | welche Felder sich nachträglich ändern, wie oft, welche Einträge verschwinden, aus `serving/source_movement` |

## Was für jedes Brett gilt

- **Es liest das aktive Release**, nicht die Arbeitsschicht
  (`releases/AKTUELL.json`, seit dem 1.11.2026). Ein Release ist
  unveränderlich. Das Dashboard lädt nach, sobald `AKTUELL.json` auf ein
  anderes zeigt.
- **Fälle vorn, Taten auf Wunsch.** Das ist der Entscheid E-2 der Dokumente:
  Chicago erfasst je Fall ein Delikt, Detroit jedes. Ein Vergleich auf der
  Tatebene misst diesen Erfassungsunterschied mit.
- **Je 1'000 Einwohner, nicht je 100'000.** Die Entwürfe rechnen je 100'000.
  Die Dokumente, Kibana und die Hypothesen rechnen je 1'000, und eine zweite
  Einheit wäre eine zweite Wahrheit.
- **Die Rate ist die der Dokumente.** Gezählt werden nur Taten in Tracts, die
  der Stadt zugeordnet sind, geteilt durch deren Einwohner. Der Nenner ist das
  ACS-Vintage der Tat. Das ist dieselbe Regel wie in
  `gold_pipeline.raten_je_stadt`.
- **Ein Zeitraum ist ein Tagesbereich** (seit dem 24.11.2026). Die Achse folgt
  der Spanne: bis 92 Tage je Tag, bis zwei Jahre je Woche, darüber je Monat.
  Eine Rate gilt je Jahr. Ein Vergleich mit dem Vorjahr ist nur für einen
  Zeitraum bis zu einem Jahr möglich.

## Warum ein eigenes Dashboard statt Kibana

Das steht schon in [`textvorschlag-fr-58.md`](textvorschlag-fr-58.md), Punkt 5,
mit Beleg und Grenze. Für das Konzept genügt ein Verweis darauf, damit es an
einer Stelle steht.

## Grenze

Die Bretter beantworten die Fragen der Entwürfe. Eine Hypothese stützt sich
nicht auf sie: Gerechnet werden die Hypothesen in Notebook 36, nicht im
Dashboard.
