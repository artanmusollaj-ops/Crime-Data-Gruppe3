# Herkunft der amtlichen Unterlagen

Diese sieben Dateien sind die **Belege**, aus denen die Referenztabellen in
`config/` reproduziert werden. Ohne sie wäre jeder Crosswalk eine Behauptung:
`tests/config/` baut die CSV-Dateien aus ihnen neu und vergleicht byteweise.

Bis zum 19.09.2026 lagen sie ohne Herkunftsnachweis hier — sieben Binärdateien,
bei denen niemand mehr sagen konnte, woher sie stammen. Diese Datei schliesst
das. `tests/test_quellenverzeichnis.py` hält sie vollständig: Jede Datei im
Ordner braucht hier eine Zeile mit Adresse, Prüfsumme und Grösse, und jede Zeile
braucht ihre Datei.

**Spalte „belegt":** `Prüfsumme` heisst, dass die Datei am 19.09.2026 unter der
angegebenen Adresse heruntergeladen wurde und **byteidentisch** mit der hier
liegenden war. `Adresse` heisst, dass die Adresse belegt ist, der Server aber
automatisierte Abrufe mit HTTP 403 beantwortet — nachprüfbar nur im Browser.

---

## FBI — der nationale Standard

### `nibrs_technical_specification_2025.pdf`

| | |
| --- | --- |
| Titel | *2025.0 NIBRS Technical Specification* |
| Herausgeber | FBI, Criminal Justice Information Services Division |
| Fassung | 2025.0, Dokumentdatum 13.06.2025 (PDF erstellt 13.06.2025) |
| Umfang | 238 Seiten |
| Adresse | <https://le.fbi.gov/file-repository/2025-0-nibrs-technical-specification-062625.pdf> |
| Direktabruf | `…/2025-0-nibrs-technical-specification-062625.pdf/@@download/file` |
| Grösse | 2'405'888 Bytes |
| SHA-256 | `1f96eaa8c2005e007963560685f57ef18d91979ef53d5224a9d81c6457d69eb0` |
| belegt | **Prüfsumme** |
| Wofür | Anhang A liefert die 81 amtlichen Codes → `config/nibrs_offense_codes_2025.csv` |

### `nibrs-user-manual-2025-0-062625.pdf`

| | |
| --- | --- |
| Titel | *NIBRS User Manual 2025.0* |
| Herausgeber | FBI, Criminal Justice Information Services Division |
| Fassung | 2025.0, Dokumentdatum 23.06.2025 |
| Umfang | 192 Seiten |
| Adresse | <https://le.fbi.gov/file-repository/nibrs-user-manual-2025-0-062625.pdf> |
| Direktabruf | `…/nibrs-user-manual-2025-0-062625.pdf/@@download/file` |
| Grösse | 3'223'021 Bytes |
| SHA-256 | `06e8c400000c1ed559ed8dcce2ca8367d4c82c893c8341850bacdef83e5bf73a` |
| belegt | **Prüfsumme** |
| Wofür | 28 Group-A- und 10 Group-B-Kategorien → `config/nibrs_offense_categories_2025.csv`, gelesen von `tools/build_nibrs_categories.py`. Dazu die Deliktdefinitionen und das Änderungsprotokoll |

Der Dateiname ist der des FBI und wurde bewusst nicht vereinheitlicht — `062625`
ist das Veröffentlichungsdatum und macht die Fassung am Namen erkennbar.

### `NIBRS_Offense_Codes.pdf`

| | |
| --- | --- |
| Titel | *NIBRS Offense Codes* |
| Herausgeber | FBI, Uniform Crime Reporting Program |
| Fassung | **2011** — überholt |
| Umfang | 5 Seiten |
| Adresse | <https://ucr.fbi.gov/nibrs/2011/resources/nibrs-offense-codes/view> |
| Direktabruf | <https://ucr.fbi.gov/nibrs/2011/resources/nibrs-offense-codes/at_download/file> |
| Grösse | 427'555 Bytes |
| SHA-256 | `e7c794a573a113b5a29b5d392ebb56fe574135e35af1611f1579087cac5f67ab` |
| belegt | **Prüfsumme** |
| Wofür | Der einzige Beleg für die vier zurückgezogenen Codes `90A`, `90E`, `90H`, `90I` |

**Warum ein überholtes Dokument bleibt.** Es führt 22 statt 28 Kategorien und 46
statt 71 Group-A-Delikte, und `11A` heisst dort noch *Forcible Rape*. Kein
aktuelles FBI-Dokument führt die vier zurückgezogenen Codes noch — zwei davon
stehen in den Falldaten 2024. Es wegzuwerfen hiesse, die Herkunft dieser Fälle
wegzuwerfen.

---

## Illinois — die Gegenprobe zu Chicago

### `isp_nibrs_code_table_2026.xlsx`

| | |
| --- | --- |
| Titel | *NIBRS Code Table 2026* |
| Herausgeber | Illinois State Police |
| Adresse | <https://isp.illinois.gov/StaticFiles/docs/CrimeReporting/nibrs/NIBRS%20Code%20Table%202026.xlsx> |
| Übersichtsseite | <https://isp.illinois.gov/CrimeReporting/NIBRS> |
| Grösse | 143'217 Bytes |
| SHA-256 | `679ef97fb95b8b170373f7edf4a14fdb1b4c60b5e0c3b3bfb5f10a0b2cb7cc18` |
| belegt | **Prüfsumme** |
| Wofür | Die Gegenprobe aus Notebook 32, Abschnitt 4.1: ILCS-Statut → IBR-Code |

**Kein Crosswalk.** Die Tabelle ist nach ILCS-Statut geschlüsselt, nicht nach
Chicagos IUCR. Ein Join über das vierstellige Kürzel liefert ein formgültiges und
falsches Ergebnis — daran ist die erste Fassung von `iucr_nibrs_mapping.csv`
gescheitert. Als Gegenprobe trägt sie nur mit semantischem Tor davor.

### `illinois_nibrs_iepd_2023.xlsx`

| | |
| --- | --- |
| Titel der Quelle | **`2025 nibrs_CodesTables.xlsx`** |
| Herausgeber | Illinois State Police |
| Adresse | <https://isp.illinois.gov/StaticFiles/docs/CrimeReporting/nibrs/2025%20nibrs_CodesTables.xlsx> |
| Übersichtsseite | <https://isp.illinois.gov/CrimeReporting/NIBRS> |
| Grösse | 237'697 Bytes |
| SHA-256 | `d03940f7823bed7a6ace87c0cc8cc10cca9292b9c9bd6748bf1fd4fdc880e87e` |
| belegt | **Prüfsumme** |
| Wofür | Blatt `OffenseCode`: Illinois' eigene Abschrift der FBI-Codeliste, der Abgleich aus Notebook 32, Abschnitt 3.4 |

> **Der lokale Dateiname führt in die Irre.** Er heisst
> `illinois_nibrs_iepd_2023.xlsx`, die Arbeitsmappe der ISP heisst aber
> `2025 nibrs_CodesTables.xlsx`. Die `2023` im lokalen Namen bezieht sich auf das
> **Blatt `OffenseILUCRCode`**, das die Fassung 2023.0 führt — nicht auf die
> Arbeitsmappe. Gebraucht wird das Blatt `OffenseCode`. Der Name bleibt, weil
> `tests/config/test_nibrs_offense_codes.py` ihn führt; wer die Datei neu holt,
> holt `2025 nibrs_CodesTables.xlsx`.

---

## Michigan — Detroits Codelisten

Beide Dokumente liegen als Datei im Repository statt nur als Verweis, weil
`michigan.gov` automatisierte Abrufe ausnahmslos mit **HTTP 403** beantwortet.
Die Adressen sind belegt, die Prüfsummen lassen sich von hier aus nicht
nachziehen — nur im Browser.

### `micr_manual_1110_2024.pdf`

| | |
| --- | --- |
| Titel | *Michigan Incident Crime Reporting Manual* |
| Herausgeber | Michigan State Police, Criminal Justice Information Center |
| Fassung | **1110**, PDF erstellt 03.12.2024 |
| Umfang | 134 Seiten |
| Adresse | `https://www.michigan.gov/msp/-/media/Project/Websites/msp/micr-assets/MICR-Manual_1110.pdf` |
| Übersichtsseite | <https://www.michigan.gov/msp/divisions/cjic/micr> |
| Grösse | 2'642'691 Bytes |
| SHA-256 | `c23087da21adc3813967f8b1e863c06d3055dd2155a884aaa026650cbc12b663` |
| belegt | **Adresse** (HTTP 403 für automatisierte Abrufe) |
| Wofür | Offense File Classes **und** Arrest Charges → `config/micr_nibrs_mapping.csv` |

**Inzwischen überholt.** Die MSP führt dieselbe Reihe weiter als `MICR-Manual_1122`
(Juli 2025) und `MICR-Manual_1130`. Unsere Fassung 1110 bleibt, weil
`config/micr_nibrs_mapping.csv` gegen sie gebaut ist; ein Wechsel ist ein eigener
Schritt mit eigenem Abgleich.

### `micr_appendix_f_2009.pdf`

| | |
| --- | --- |
| Titel | *MICR Appendix F — Offense File Class Mapping Chart* |
| Herausgeber | Michigan State Police |
| Fassung | **2009** — überholt; PDF erstellt 05.03.2010 |
| Umfang | 3 Seiten |
| Adresse | `https://www.michigan.gov/-/media/Project/Websites/msp/micr-assets/2009/diappf.pdf` |
| Grösse | 110'757 Bytes |
| SHA-256 | `e27c5d325b2270a40020f9e1d0b84a1789be747d0fdcd60fcd22000fbbd281ea` |
| belegt | **Adresse** (HTTP 403 für automatisierte Abrufe) |
| Wofür | Die erste Quelle für Michigans File Classes. Belegt zusätzlich, dass `90A` und `90I` **nur** in der Fassung 2009 stehen und im Manual 1110 nicht mehr — dieselbe Streichung, die das FBI unabhängig vornahm |

Der interne PDF-Titel lautet `Microsoft Word - Di- appf.doc` und deckt sich mit
dem Dateinamen `diappf.pdf` an der Quelle.

---

## Was hier **nicht** liegt

Der IUCR-Katalog des Chicago Data Portal (`c7ck-438e`) ist bewusst keine Datei
hier: `tools/build_iucr_nibrs_mapping.py` lädt ihn bei jedem Lauf frisch und
gleicht ihn gegen `config/iucr_nibrs_mapping.csv` ab. Eine eingefrorene Kopie
wäre eine zweite Wahrheit.

Adresse: <https://data.cityofchicago.org/Public-Safety/Chicago-Police-Department-Illinois-Uniform-Crime-R/c7ck-438e>

## Stand der Prüfung

Alle Adressen und Prüfsummen wurden am **19.09.2026** erhoben. Die fünf mit
`belegt = Prüfsumme` wurden an diesem Tag heruntergeladen und byteweise mit den
hier liegenden Dateien verglichen; sie stimmten überein.
