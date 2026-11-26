# Textvorschlag: die Mehrheitsregel nach der Neumessung

Für Artan. Stand 26.11.2026. Ein **Vorschlag**, kein Beleg. Zwei Stellen in
[`ln2_konzept.md`](../ln2_konzept.md) beruhen auf einer Messung, die vor
Gold-Vertrag 10 lag. Notebook 34 hat sie am 26.11.2026 wiederholt, am
Zwischenstand vom selben Tag (Release `2026-11-26T05-27-08Z`). Die Zahlen in
der Tabelle von 5.2 sind schon nachgezogen. Die beiden Absätze unten gehören
dir, weil sie eine Aussage treffen.

## Was sich geändert hat

Bis zum 21.11.2026 rechnete die Mehrheitsregel über die **ganze** Fläche eines
Tracts. Am Chicagoer Seeufer reicht ein Tract in den Michigansee, die
Stadtgrenze aus TIGER endet am Ufer. Über die ganze Fläche gerechnet kam so ein
Tract nie über die Hälfte, auch wenn sein ganzes Land in der Stadt lag.
Gold-Vertrag 10 rechnet über die **Landfläche**. Seither zählen elf Tracts mehr
zu Chicago.

| Jahrgang 2024, Chicago | vor Vertrag 10 | seit Vertrag 10 |
| --- | ---: | ---: |
| Tracts der Stadt | 782 | 793 |
| Einwohner (Mehrheitsregel) | 2'661'953 | 2'713'800 |
| Einwohner (Flächengewichtung) | 2'651'921 | 2'714'927 |
| Abstand zum Zensus 2020 (2'746'388) | −3,1 % | −1,2 % |
| Fälle in der Stadt, aber in einem fremden Tract | 5'249 | 441 |
| Rate auf der Tatebene, ohne und mit diesen Fällen | 94,5 / 95,6 | 94,5 / 94,5 |

Detroit ändert sich nicht: 0,07 % unter dem Zensus, 12 Grenzfälle, Rate 134,2.

Quelle: Notebook 34, Abschnitte 3 bis 3.2, und
`gold_pipeline.build_gold.dim_tract_query`.

## Stelle 1 · Konzept 5.2, der Absatz unter der Regeltabelle

Heute steht dort, der grössere Abstand bei Chicago sei „der Unterschied
zwischen einer ACS-Schätzung und einer Zählung, nicht ein Fehler der Regel“.
Das war bis Vertrag 10 nur zum Teil richtig: Rund 52'000 der damals 84'000
Einwohner Abstand waren die Seeufer-Tracts. Vorschlag:

> Gewählt ist die **Mehrheitsregel**: Ein Tract gehört zu der Stadt, die mehr
> als die Hälfte seiner **Landfläche** bedeckt. Sie gibt jedem Tract genau eine
> Stadt — die Voraussetzung dafür, dass sich Fälle ohne Doppelzählung summieren
> lassen — und liegt praktisch gleichauf mit der Flächengewichtung. Detroit
> trifft sie auf **0,07 %** genau, Chicago auf **1,2 %**; dieser Rest ist der
> Unterschied zwischen einer ACS-Schätzung und einer Zählung.
>
> **Landfläche, nicht Gesamtfläche.** Bis zum 21.11.2026 zählte die ganze
> Fläche eines Tracts. Am Seeufer reicht ein Tract in den Michigansee, die
> Stadtgrenze endet am Ufer, und so fielen elf Tracts aus Chicago heraus; die
> Stadt lag 3,1 % unter der Zählung. Ein Fehler der Regel, kein Merkmal der
> Daten, und er fiel erst beim Vergleich mit dem Zensus auf.

## Stelle 2 · Konzept 9, der Punkt „Die Mehrheitsregel schliesst Grenzfälle aus“

Heute steht dort, die Regel untertreibe Chicagos Rate um gut einen Punkt
(94,5 statt 95,6). Das gilt seit Vertrag 10 nicht mehr. Vorschlag:

> - **Die Mehrheitsregel hat einen Rand.** 441 Chicagoer Delikte liegen
>   innerhalb der Stadtgrenze, aber in einem Tract, der mehrheitlich zur
>   Nachbargemeinde gehört; in Detroit sind es 12. Diese Randtracts sind
>   deliktdichter als der Stadtschnitt, rund 180 je 1'000 gegen 94,5, aber zu
>   klein, um die Rate zu bewegen: Mit ihnen und ihren anteiligen Einwohnern
>   bleibt Chicago bei 94,5. Bis Gold-Vertrag 10 waren es 5'249 Fälle und gut
>   ein Punkt Unterschied. Gemessen in Notebook 34, Abschnitt 3.2.

Ob der Punkt in Kapitel 9 bleiben soll, ist deine Entscheidung. Als Grenze
trägt er kaum noch. Als Beleg dafür, dass die Regel gemessen und korrigiert
wurde, trägt er dagegen.
