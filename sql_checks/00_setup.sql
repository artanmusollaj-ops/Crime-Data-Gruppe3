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
