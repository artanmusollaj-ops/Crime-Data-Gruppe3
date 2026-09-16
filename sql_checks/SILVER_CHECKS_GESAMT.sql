-- KOMFORTDATEI: Setup + Checks 01-04. Keine Reprocessing-Snapshots.

-- DATEI: 00_setup.sql
-- EINMAL PRO VERBINDUNG AUSFUEHREN. Pfade relativ zum Projektverzeichnis.
-- Nur TEMP-Objekte: keine Aenderung an Silver, Gold oder dauerhaften Tabellen.
-- Fuer SQL-Editoren: alle Anweisungen dieses Setups in derselben Verbindung ausfuehren.
SET TimeZone = 'UTC';

-- Ausschliessliche Obergrenzen, jeweils lokale Stadtzeit.
-- Beispiel Juni: 2024-06-01 bis 2024-07-01.
-- Beispiel 09.11.: 2024-11-09 bis 2024-11-10.
-- completed_before_local: Mitternacht NACH dem letzten freigegebenen Tat-Tag.
-- Bei Referenztag 31.12.2024 also 01.01.2025, nicht 31.12.2024 00:00.
CREATE OR REPLACE TEMP TABLE audit_parameters AS
SELECT DATE '2024-01-01' AS scope_start,
       DATE '2025-01-01' AS scope_end_exclusive,
       DATE '2025-01-01' AS completed_before_local,
       FALSE AS exclude_unfounded;
-- FALSE ermoeglicht Vergleich mit bisherigem counts-Vertrag.
-- TRUE ist eine bewusst andere Kennzahl; Chicago hat unfounded=NULL, nicht FALSE.

SELECT CASE WHEN scope_start < scope_end_exclusive
 AND scope_end_exclusive <= completed_before_local
 THEN 'OK: gueltiges Analysefenster'
 ELSE error('Ungueltige Parameter: Beginn < Ende <= completed_before_local erforderlich')
 END AS parameter_check FROM audit_parameters;

-- Nur EIN aktueller Silver-Stand, kein Glob ueber historische Releases.
-- Alternative bei bestehender Serving-View: FROM crime_offense
CREATE OR REPLACE TEMP VIEW audit_silver AS
SELECT city, offense_id, event_id, occurred_at_utc, occurred_at_local,
       occurred_date_local, source_offense_code, source_offense_description,
       nibrs_code, nibrs_description, nibrs_group, crime_against,
       nibrs_match, nibrs_mapped, mapping_status, latitude, longitude,
       tract_geoid, located, arrest, unfounded, offense_group_id,
       counts, counts_reason, counts_case
FROM read_parquet(
 './data/silver/dataset=crime_offense/part-0001.parquet',
 hive_partitioning = false
);
-- Projektion funktioniert auch mit dem im ZIP enthaltenen aelteren Schema.
-- Neue DST-Flags sind hier absichtlich nicht vorausgesetzt.

CREATE OR REPLACE TEMP TABLE audit_ref_map AS
SELECT 'chicago' AS city, iucr AS source_code, ibr_code AS target_code,
       match AS rule_origin, mapped
FROM read_csv('./config/iucr_nibrs_mapping.csv', header=true, all_varchar=true)
UNION ALL
SELECT 'detroit', micr_code, nibrs_code, match, mapped
FROM read_csv('./config/micr_nibrs_mapping.csv', header=true, all_varchar=true);

CREATE OR REPLACE TEMP TABLE audit_categories AS
SELECT nibrs_code, nibrs_category
FROM read_csv('./config/nibrs_offense_categories_2025.csv',header=true,all_varchar=true);

-- Referenzen muessen eindeutig sein, bevor sie Fakten anreichern.
SELECT CASE WHEN
 (SELECT count(*) FROM (SELECT city,source_code FROM audit_ref_map
 GROUP BY 1,2 HAVING count(*)>1 OR source_code IS NULL))=0
 AND (SELECT count(*) FROM (SELECT nibrs_code FROM audit_categories
 GROUP BY 1 HAVING count(*)>1 OR nibrs_code IS NULL))=0
 THEN 'OK: eindeutige Mapping- und Kategorieschluessel'
 ELSE error('Referenzschluessel doppelt oder NULL; Join wuerde Zahlen verfaelschen') END
 AS reference_key_check;

CREATE OR REPLACE TEMP VIEW audit_scoped AS
SELECT s.* FROM audit_silver s CROSS JOIN audit_parameters p
WHERE s.occurred_at_local >= CAST(p.scope_start AS TIMESTAMP)
  AND s.occurred_at_local < CAST(p.scope_end_exclusive AS TIMESTAMP);

CREATE OR REPLACE TEMP VIEW audit_enriched AS
SELECT s.*,c.nibrs_category AS audit_category,
       (NOT p.exclude_unfounded OR NOT coalesce(s.unfounded,false)) AS audit_eligible
FROM audit_scoped s CROSS JOIN audit_parameters p
LEFT JOIN audit_categories c USING(nibrs_code);
-- NULL-Status wird hier nicht als UNFOUNDED ausgeschlossen. Das ist kein
-- Beweis fuer bestaetigte Taten; Statusverfuegbarkeit separat beachten.


-- DATEI: 01_schluessel_zaehlregeln.sql
-- Voraussetzung: 00_setup.sql, gleiche Verbindung.
-- S01 PROFIL: alle aktuellen Zeilen; keine Aussage zu Quellvollstaendigkeit.
SELECT city,count(*) AS silver_zeilen,count(DISTINCT offense_id) AS offense_ids,
 count(DISTINCT event_id) AS reports,count(*) FILTER(WHERE counts) AS counts_zeilen,
 count(*) FILTER(WHERE counts_case) AS counts_case_zeilen
FROM audit_silver GROUP BY 1 ORDER BY 1;

-- S02 FEHLER: Erwartung 0 Zeilen. IDs immer zusammen mit Stadt beurteilen.
SELECT city,offense_id,count(*) AS anzahl
FROM audit_silver GROUP BY 1,2
HAVING city IS NULL OR city NOT IN ('chicago','detroit')
 OR offense_id IS NULL OR trim(offense_id)='' OR count(*)<>1;

-- S03 FEHLER fuer Reportanalysen: Erwartung 0 Zeilen.
SELECT city,offense_id,event_id FROM audit_silver
WHERE event_id IS NULL OR trim(event_id)='';

-- S04 FEHLER: Auswahlfelder duerfen nicht unbekannt sein.
SELECT city,offense_id,counts,counts_case FROM audit_silver
WHERE counts IS NULL OR counts_case IS NULL OR (counts_case AND NOT counts);

-- S05 VERTRAGSCHECK: je bestehender Deliktgruppe genau eine counts-Zeile.
-- Beweist nicht, dass die fachliche Gruppierung korrekt gewaehlt wurde!
SELECT city,offense_group_id,count(*) AS zeilen,
 count(*) FILTER(WHERE counts) AS ausgewaehlt,
 count(DISTINCT event_id) AS reports
FROM audit_silver GROUP BY 1,2
HAVING offense_group_id IS NULL OR trim(offense_group_id)=''
 OR ausgewaehlt<>1 OR reports>1;

-- S06 VERTRAGSCHECK: eine counts_case-Zeile je Report mit counts-Zeile.
-- Auf GESAMTEM Stand pruefen, nicht auf einem abgeschnittenen Tagesfenster.
SELECT city,coalesce(nullif(trim(event_id),''),offense_id) AS fall,
 count(*) FILTER(WHERE counts) AS z,
 count(*) FILTER(WHERE counts_case) AS hauptzeilen
FROM audit_silver GROUP BY 1,2
HAVING (z>0 AND hauptzeilen<>1) OR (z=0 AND hauptzeilen<>0);

-- S07 REVIEW: gruppierte Zeilen haben verschiedene Zielcodes.
-- Kein automatischer Dubletten- oder Mappingfehler; Auswahl fachlich begruenden.
SELECT city,offense_group_id,count(*) AS zeilen,
 list(DISTINCT nibrs_code ORDER BY nibrs_code) AS zielcodes,
 count(*) FILTER(WHERE counts) AS ausgewaehlt
FROM audit_scoped GROUP BY 1,2 HAVING count(DISTINCT nibrs_code)>1
ORDER BY zeilen DESC,city,offense_group_id;

-- S08 REVIEW: globaler Ranggewinner ist UNFOUNDED, andere counts-Zeile nicht.
SELECT city,event_id FROM audit_silver GROUP BY 1,2
HAVING count(*) FILTER(WHERE counts_case AND coalesce(unfounded,false))>0
 AND count(*) FILTER(WHERE counts AND NOT coalesce(unfounded,false))>0;

-- S09 REVIEW: reine Textvarianten innerhalb derselben Stadt/Report/Quellcode.
-- Nicht ohne fachlichen Nachweis zusammenfuehren.
SELECT city,event_id,source_offense_code,
 upper(regexp_replace(trim(source_offense_description),'\s+',' ','g')) AS normtext,
 list(DISTINCT source_offense_description ORDER BY source_offense_description) AS varianten
FROM audit_scoped GROUP BY 1,2,3,4
HAVING count(DISTINCT source_offense_description)>1;


-- DATEI: 02_mapping.sql
-- Voraussetzung: 00_setup.sql. Profile gelten fuer den konfigurierten Zeitraum.
-- M01 PROFIL: unterschiedliche Qualitaetsstufen sind NICHT automatisch Fehler.
SELECT city,mapping_status,count(*) AS offenses,count(DISTINCT event_id) AS reports,
 round(100.0*count(*)/sum(count(*)) OVER(PARTITION BY city),2) AS anteil_prozent
FROM audit_scoped GROUP BY 1,2 ORDER BY 1,2;

-- M02 FEHLER: inkonsistente technische Mappingfelder. Erwartung 0 Zeilen.
SELECT city,offense_id,nibrs_code,nibrs_mapped,mapping_status
FROM audit_scoped
WHERE mapping_status IS NULL
 OR mapping_status NOT IN ('exact','ambiguous','fallback_90Z','unmapped')
 OR nibrs_mapped IS DISTINCT FROM (nibrs_code IS NOT NULL)
 OR ((mapping_status='unmapped') IS DISTINCT FROM (nibrs_code IS NULL))
 OR ((mapping_status='fallback_90Z') IS DISTINCT FROM (nibrs_code='90Z'))
    AND nibrs_code IS NOT NULL;

-- M03 REVIEW/FEHLER: aktueller Silver-Code gegen aktuell geladene Referenz.
-- Differenz kann auch bedeuten: Mapping geaendert, Silver noch nicht neu gebaut.
SELECT s.city,s.offense_id,s.source_offense_code,s.nibrs_code AS silver_code,
 CASE WHEN lower(m.mapped)='true' THEN m.target_code END AS erwarteter_code,
 s.nibrs_match,m.rule_origin
FROM audit_scoped s LEFT JOIN audit_ref_map m
 ON s.city=m.city AND trim(s.source_offense_code)=m.source_code
WHERE s.nibrs_code IS DISTINCT FROM
      CASE WHEN lower(m.mapped)='true' THEN m.target_code END
 OR (lower(m.mapped)='true' AND s.nibrs_match IS DISTINCT FROM m.rule_origin);

-- M04 REVIEW: Code fehlt in Referenz oder hat keine aktivierte Zuordnung.
SELECT s.city,s.source_offense_code,s.source_offense_description,
 count(*) AS offenses,count(DISTINCT s.event_id) AS reports
FROM audit_scoped s LEFT JOIN audit_ref_map m
 ON s.city=m.city AND trim(s.source_offense_code)=m.source_code
WHERE m.source_code IS NULL OR lower(coalesce(m.mapped,''))<>'true'
GROUP BY 1,2,3 ORDER BY offenses DESC;

-- M05 FEHLER: Zielcode hat keine Kategorie. Erwartung 0 Zeilen.
SELECT city,nibrs_code,count(*) AS offenses
FROM audit_enriched WHERE nibrs_code IS NOT NULL AND audit_category IS NULL
GROUP BY 1,2;

-- M06 PROFIL fuer Review: non_exact ist ein Kandidat, KEINE offene Reviewquote.
-- Silver enthaelt aktuell keinen verbindlichen review_required-Status.
SELECT city,occurred_date_local,
 coalesce(audit_category,'__UNMAPPED__') AS kategorie,
 count(*) AS offenses,
 count(*) FILTER(WHERE mapping_status<>'exact' OR mapping_status IS NULL) AS nicht_exakt,
 count(DISTINCT event_id) FILTER(WHERE mapping_status<>'exact' OR mapping_status IS NULL) AS betroffene_reports,
 round(100.0*nicht_exakt/count(*),2) AS nicht_exakt_prozent
FROM audit_enriched WHERE audit_eligible GROUP BY 1,2,3
ORDER BY nicht_exakt_prozent DESC,city,occurred_date_local,kategorie;

-- M07 REVIEW: eine Code-/Beschreibungs-Kombination hat mehrere Ziele.
SELECT city,source_offense_code,source_offense_description,
 list(DISTINCT nibrs_code ORDER BY nibrs_code) AS zielcodes,count(*) AS offenses
FROM audit_scoped GROUP BY 1,2,3 HAVING count(DISTINCT nibrs_code)>1;

-- M08 PROFIL: alle Kombinationen zur manuellen fachlichen Pruefung.
-- Silver besitzt keine vollstaendige offense_category/charge_description mehr.
SELECT city,source_offense_code,source_offense_description,nibrs_code,mapping_status,
 count(*) AS offenses,count(DISTINCT event_id) AS reports,
 count(*) FILTER(WHERE counts) AS ausgewaehlte_zeilen
FROM audit_scoped GROUP BY 1,2,3,4,5 ORDER BY city,offenses DESC;

-- M09 FEHLER: Mappingstatus entspricht nicht der hinterlegten Herkunftsregel.
-- Konsistenzcheck, keine unabhaengige fachliche Begutachtung der Referenz.
WITH expected AS (
 SELECT *,CASE WHEN nibrs_code IS NULL THEN 'unmapped'
 WHEN nibrs_code='90Z' THEN 'fallback_90Z'
 WHEN nibrs_match IN ('nibrs_definition','micr_manual_1110_2024',
                     'micr_arrest_charge_1110_2024','appendix_f_2009') THEN 'exact'
 WHEN nibrs_match IN ('nibrs_ermessen','detroit_charge_file_class') THEN 'ambiguous'
 WHEN nibrs_match='nibrs_auffang' THEN 'fallback_90Z'
 ELSE '__UNKNOWN_RULE_ORIGIN__' END AS expected_status
 FROM audit_scoped
)
SELECT city,offense_id,nibrs_code,nibrs_match,mapping_status,expected_status
FROM expected WHERE mapping_status IS DISTINCT FROM expected_status;


-- DATEI: 03_zeitfenster.sql
-- Voraussetzung 00_setup.sql. Strukturelle Zeitchecks laufen auf GANZ Silver.
-- Z01 FEHLER: NULL oder abweichendes abgeleitetes lokales Tatdatum.
SELECT city,offense_id,occurred_at_local,occurred_at_utc,occurred_date_local
FROM audit_silver
WHERE occurred_at_local IS NULL OR occurred_at_utc IS NULL
 OR occurred_date_local IS DISTINCT FROM CAST(occurred_at_local AS DATE);

-- Z02 ERWARTETER GESAMTSCOPE: nur Fehler, falls die ganze Datei ausschliesslich
-- den Parameter-Zeitraum enthalten SOLL. Bei Mehrjahresdaten ggf. legitime Treffer.
SELECT s.city,count(*) AS ausserhalb_analysescope
FROM audit_silver s CROSS JOIN audit_parameters p
WHERE s.occurred_at_local<CAST(p.scope_start AS TIMESTAMP)
 OR s.occurred_at_local>=CAST(p.scope_end_exclusive AS TIMESTAMP) GROUP BY 1;

-- Z03 STICHTAG: nicht zum abgeschlossenen Stand passende Zeilen.
-- Fuer Stichtag D ist D+1 00:00 exklusiv. Lokale Zeit jeder Stadt!
SELECT s.city,s.offense_id,s.occurred_at_local,p.completed_before_local
FROM audit_silver s CROSS JOIN audit_parameters p
WHERE s.occurred_at_local>=CAST(p.completed_before_local AS TIMESTAMP);

-- Z04 PROFIL: lokales und UTC-Maximum getrennt; NULL wird explizit gezaehlt.
SELECT city,min(occurred_at_local) AS min_lokal,max(occurred_at_local) AS max_lokal,
 min(occurred_at_utc) AS min_utc,max(occurred_at_utc) AS max_utc,
 count(*) FILTER(WHERE occurred_at_local IS NULL) AS ohne_tatzeit
FROM audit_silver GROUP BY 1 ORDER BY 1;

-- Z05 FEHLER/REVIEW: UTC passt nicht zur gespeicherten Ortszeit.
-- Chicago: nicht existierende Quell-Ortszeit kann ebenfalls Ursache sein.
-- Mehrdeutige Chicago-Ortszeit ist damit NICHT eindeutig aufgeloest.
SELECT city,offense_id,occurred_at_utc,occurred_at_local
FROM audit_silver
WHERE city IN ('chicago','detroit') AND occurred_at_utc IS NOT NULL
 AND occurred_at_local IS DISTINCT FROM timezone(
 CASE city WHEN 'chicago' THEN 'America/Chicago' ELSE 'America/Detroit' END,
 occurred_at_utc AT TIME ZONE 'UTC');

-- Z06 REVIEW: ein Report betrifft mehrere lokale Tage.
SELECT city,event_id,count(DISTINCT occurred_date_local) AS tage,
 min(occurred_date_local) AS erster_tag,max(occurred_date_local) AS letzter_tag
FROM audit_scoped WHERE nullif(trim(event_id),'') IS NOT NULL
GROUP BY 1,2 HAVING tage>1 ORDER BY 1,2;

-- Z07 ABDECKUNG: erwartete Stadt-Tage ohne sichtbare Zeile.
-- Treffer bedeuten LEER/UNBEKANNT, keine bewiesenen Null Faelle!
WITH tage AS (
 SELECT CAST(t AS DATE) AS tatdatum FROM audit_parameters p,
 unnest(generate_series(p.scope_start,p.scope_end_exclusive-INTERVAL 1 DAY,INTERVAL 1 DAY)) d(t)
), staedte AS (SELECT * FROM (VALUES ('chicago'),('detroit')) v(city))
SELECT c.city,t.tatdatum,count(s.offense_id) AS offenses
FROM staedte c CROSS JOIN tage t LEFT JOIN audit_scoped s
 ON s.city=c.city AND s.occurred_date_local=t.tatdatum
GROUP BY 1,2 HAVING offenses=0 ORDER BY 1,2;

-- Z08 ANSCHAULICH: echte UTC-Grenzen und Tageslaenge pro lokalem Tat-Tag.
-- 23/25 Stunden bei Sommerzeitwechseln sind korrekt, kein Vollstaendigkeitsfehler.
WITH tage AS (
 SELECT CAST(t AS DATE) AS tatdatum FROM audit_parameters p,
 unnest(generate_series(p.scope_start,p.scope_end_exclusive-INTERVAL 1 DAY,INTERVAL 1 DAY)) d(t)
), staedte AS (SELECT * FROM (VALUES ('chicago','America/Chicago'),('detroit','America/Detroit')) v(city,zone))
SELECT city,tatdatum,timezone(zone,CAST(tatdatum AS TIMESTAMP)) AS start_utc,
 timezone(zone,CAST(tatdatum+1 AS TIMESTAMP)) AS ende_utc_exklusiv,
 epoch(ende_utc_exklusiv-start_utc)/3600 AS stunden
FROM staedte CROSS JOIN tage ORDER BY city,tatdatum;


-- DATEI: 04_aggregate.sql
-- Voraussetzung 00_setup.sql. Vergleichskennzahlen aus SILVER, kein Gold noetig.
-- Alle Kennzahlen respektieren den lokalen Zeitraum und exclude_unfounded.
-- A01 PROFIL: vier Perspektiven, nicht als dieselbe Kennzahl beschriften.
SELECT city,coalesce(audit_category,'__UNMAPPED__') AS kategorie,
 count(*) AS aktuelle_offense_zeilen,
 count(*) FILTER(WHERE counts) AS ausgewaehlte_deliktzeilen,
 count(DISTINCT event_id) AS reports_alle_offenses,
 count(DISTINCT event_id) FILTER(WHERE counts) AS reports_ausgewaehlte_offenses,
 count(*) FILTER(WHERE counts_case) AS hauptdelikt_zeilen
FROM audit_enriched WHERE audit_eligible GROUP BY 1,2 ORDER BY 1,2;

-- A02 DIREKTE Aggregate: Tag, ISO-Wochenbeginn (Montag), Kalendermonat.
-- report_count wird JEWEILS aus Einzelzeilen berechnet, nicht aus Tageszahlen.
-- Randwochen/-monate enthalten nur den konfigurierten Teilzeitraum!
WITH periods AS (
 SELECT 'TAG' AS ebene,occurred_date_local AS periode,* FROM audit_enriched
 UNION ALL
 SELECT 'WOCHE',CAST(date_trunc('week',occurred_date_local) AS DATE),* FROM audit_enriched
 UNION ALL
 SELECT 'MONAT',CAST(date_trunc('month',occurred_date_local) AS DATE),* FROM audit_enriched
)
SELECT ebene,periode,city,coalesce(audit_category,'__UNMAPPED__') AS kategorie,
 count(*) FILTER(WHERE counts) AS deliktzeilen,
 count(DISTINCT event_id) FILTER(WHERE counts) AS reports,
 count(*) FILTER(WHERE counts_case) AS hauptdelikt_zeilen
FROM periods WHERE audit_eligible GROUP BY 1,2,3,4 ORDER BY 1,2,3,4;

-- A03 REVIEW: Summe von Tages-Reports versus direkte Wochen-/Monats-Reports.
-- Abweichungen zeigen Nicht-Additivitaet von DISTINCT, keinen Beweis fuer Dubletten.
WITH daily AS (
 SELECT city,occurred_date_local AS d,coalesce(audit_category,'__UNMAPPED__') AS category,
 count(DISTINCT event_id) AS n FROM audit_enriched
 WHERE counts AND audit_eligible GROUP BY 1,2,3
), summed AS (
 SELECT 'MONAT' AS ebene,city,CAST(date_trunc('month',d) AS DATE) AS periode,category,sum(n) AS summe_tage
 FROM daily GROUP BY 1,2,3,4
 UNION ALL
 SELECT 'WOCHE',city,CAST(date_trunc('week',d) AS DATE),category,sum(n)
 FROM daily GROUP BY 1,2,3,4
), direct AS (
 SELECT 'MONAT' AS ebene,city,CAST(date_trunc('month',occurred_date_local) AS DATE) AS periode,
 coalesce(audit_category,'__UNMAPPED__') AS category,count(DISTINCT event_id) AS direkt
 FROM audit_enriched WHERE counts AND audit_eligible GROUP BY 1,2,3,4
 UNION ALL
 SELECT 'WOCHE',city,CAST(date_trunc('week',occurred_date_local) AS DATE),
 coalesce(audit_category,'__UNMAPPED__'),count(DISTINCT event_id)
 FROM audit_enriched WHERE counts AND audit_eligible GROUP BY 1,2,3,4
)
SELECT *,summe_tage-direkt AS differenz FROM summed JOIN direct USING(ebene,city,periode,category)
WHERE summe_tage<>direkt ORDER BY 1,2,3,4;

-- A04 REVIEW: bereits VOR Gold ausgeschlossene Report-/Kategorie-Kombinationen.
-- Fachliche Auswahlwirkung, nicht automatisch verlorene Straftaten.
WITH alle AS (
 SELECT DISTINCT city,event_id,coalesce(audit_category,'__UNMAPPED__') AS category
 FROM audit_enriched WHERE audit_eligible
), zaehlend AS (
 SELECT DISTINCT city,event_id,coalesce(audit_category,'__UNMAPPED__') AS category
 FROM audit_enriched WHERE audit_eligible AND counts
)
SELECT city,category,count(*) AS report_kategorien_ohne_counts
FROM (SELECT * FROM alle EXCEPT SELECT * FROM zaehlend)
GROUP BY 1,2 ORDER BY 3 DESC,1,2;

-- A05 FOKUS-KATEGORIEN: explizite Beispieldefinition, fachlich freizugeben.
-- ASSAULT=13A/13B/13C, VEHICLE_THEFT=240, ARSON=200.
-- Kein Treffer ergibt keine Gruppe, nicht automatisch einen freigegebenen Nullwert.
WITH x AS (
 SELECT *,CASE WHEN nibrs_code IN ('13A','13B','13C') THEN 'ASSAULT'
 WHEN nibrs_code='240' THEN 'VEHICLE_THEFT'
 WHEN nibrs_code='200' THEN 'ARSON' END AS vergleichskategorie
 FROM audit_enriched WHERE audit_eligible
)
SELECT city,vergleichskategorie,count(*) FILTER(WHERE counts) AS deliktzeilen,
 count(DISTINCT event_id) FILTER(WHERE counts) AS reports,
 count(*) FILTER(WHERE counts_case) AS hauptdelikt_zeilen
FROM x WHERE vergleichskategorie IS NOT NULL GROUP BY 1,2 ORDER BY 1,2;

-- A06 FEHLER: dasselbe counts-Aggregat auf zwei unabhaengigen Wegen.
-- Erwartung 0 Zeilen. Prueft Zeilenaggregation, KEINE Monats-Report-Additivitaet.
WITH daily AS (
 SELECT city,occurred_date_local, count(*) AS n
 FROM audit_enriched WHERE counts AND audit_eligible GROUP BY 1,2
), a AS (SELECT city,sum(n) AS aus_tagen FROM daily GROUP BY 1),
b AS (SELECT city,count(*) AS direkt FROM audit_enriched WHERE counts AND audit_eligible GROUP BY 1)
SELECT coalesce(a.city,b.city) AS city,aus_tagen,direkt FROM a FULL OUTER JOIN b USING(city)
WHERE aus_tagen IS DISTINCT FROM direkt;
