-- OPTIONAL: 05 vorher, ETL separat, dann 00_setup erneut mit denselben Zeitparametern,
-- dann dieses Skript. 05 NICHT erneut ausfuehren. Gleiche DuckDB-Verbindung beibehalten.
-- Neue/veraenderte Eingaben duerfen Unterschiede erzeugen. Gleiche Eingaben +
-- gleiche Regeln muessen 0 Inhalts-/Aggregatabweichungen ergeben.
CREATE OR REPLACE TEMP TABLE audit_after AS SELECT * FROM audit_silver;

-- R01 VORAUSSETZUNG: eindeutige vorhandene Schluessel, sonst ist Zeilenjoin mehrdeutig.
SELECT CASE WHEN (SELECT count(*) FROM (
 SELECT 'vorher' AS stand,city,offense_id FROM audit_before GROUP BY 1,2,3
 HAVING city IS NULL OR offense_id IS NULL OR trim(offense_id)='' OR count(*)>1
 UNION ALL
 SELECT 'nachher',city,offense_id FROM audit_after GROUP BY 1,2,3
 HAVING city IS NULL OR offense_id IS NULL OR trim(offense_id)='' OR count(*)>1
))=0 THEN 'OK: vergleichbare Zeilenschluessel'
 ELSE error('Vorher/Nachher hat ungueltige oder doppelte Schluessel; erst S02 klaeren') END AS schluessel_check;

-- R02 Kontext: geaenderte Parameter und Mappingreferenzen erklaeren Unterschiede.
SELECT 'parameter' AS objekt,count(*) AS unterschiedliche_zeilen FROM (
 (SELECT * FROM audit_parameters_before EXCEPT ALL SELECT * FROM audit_parameters)
 UNION ALL (SELECT * FROM audit_parameters EXCEPT ALL SELECT * FROM audit_parameters_before))
UNION ALL
SELECT 'mapping',count(*) FROM (
 (SELECT * FROM audit_ref_map_before EXCEPT ALL SELECT * FROM audit_ref_map)
 UNION ALL (SELECT * FROM audit_ref_map EXCEPT ALL SELECT * FROM audit_ref_map_before))
UNION ALL
SELECT 'kategorien',count(*) FROM (
 (SELECT * FROM audit_categories_before EXCEPT ALL SELECT * FROM audit_categories)
 UNION ALL (SELECT * FROM audit_categories EXCEPT ALL SELECT * FROM audit_categories_before));

-- R03 Inhaltsabgleich beider Richtungen; geaenderte Zeile erscheint auf beiden Seiten.
-- Unter identischen Eingaben/Regeln jeweils 0; keine Byte-/Dateiidentitaet verlangt.
SELECT 'nur_vorher' AS richtung,count(*) AS zeilen FROM (
 SELECT * FROM audit_before EXCEPT ALL SELECT * FROM audit_after)
UNION ALL
SELECT 'nur_nachher',count(*) FROM (
 SELECT * FROM audit_after EXCEPT ALL SELECT * FROM audit_before);

-- R04 Alte UND neue Zuordnung sichtbar machen, damit Rekalkulation beide trifft.
CREATE OR REPLACE TEMP VIEW audit_delta AS
SELECT coalesce(b.city,a.city) AS city,coalesce(b.offense_id,a.offense_id) AS offense_id,
 CASE WHEN b.offense_id IS NULL THEN 'NEU'
      WHEN a.offense_id IS NULL THEN 'NICHT_MEHR_IM_SILVER'
      ELSE 'GEAENDERT' END AS aenderung,
 b.event_id AS report_alt,a.event_id AS report_neu,
 b.occurred_date_local AS tatdatum_alt,a.occurred_date_local AS tatdatum_neu,
 b.nibrs_code AS code_alt,a.nibrs_code AS code_neu,
 b.counts AS counts_alt,a.counts AS counts_neu,
 b.counts_case AS counts_case_alt,a.counts_case AS counts_case_neu
FROM audit_before b FULL OUTER JOIN audit_after a USING(city,offense_id)
WHERE to_json(b) IS DISTINCT FROM to_json(a);
SELECT * FROM audit_delta ORDER BY city,offense_id;
-- NICHT_MEHR_IM_SILVER ist keine bewiesene Loeschung in der Quelle!

-- R05 Tages-/Wochen-/Monatsvergleich. Kategorien und Filter verwenden ihren
-- jeweiligen Vorher-/Nachher-Stand. So werden reine Mappingaenderungen sichtbar.
CREATE OR REPLACE TEMP VIEW audit_period_comparison AS
WITH base AS (
 SELECT 'vorher' AS stand,s.city,s.event_id,s.occurred_date_local AS d,s.counts,s.counts_case,
 coalesce(c.nibrs_category,'__UNMAPPED__') AS category
 FROM audit_before s CROSS JOIN audit_parameters_before p LEFT JOIN audit_categories_before c USING(nibrs_code)
 WHERE s.occurred_at_local>=CAST(p.scope_start AS TIMESTAMP)
 AND s.occurred_at_local<CAST(p.scope_end_exclusive AS TIMESTAMP)
 AND (NOT p.exclude_unfounded OR NOT coalesce(s.unfounded,false))
 UNION ALL
 SELECT 'nachher',s.city,s.event_id,s.occurred_date_local,s.counts,s.counts_case,
 coalesce(c.nibrs_category,'__UNMAPPED__')
 FROM audit_after s CROSS JOIN audit_parameters p LEFT JOIN audit_categories c USING(nibrs_code)
 WHERE s.occurred_at_local>=CAST(p.scope_start AS TIMESTAMP)
 AND s.occurred_at_local<CAST(p.scope_end_exclusive AS TIMESTAMP)
 AND (NOT p.exclude_unfounded OR NOT coalesce(s.unfounded,false))
), periods AS (
 SELECT 'TAG' AS ebene,d AS periode,* FROM base
 UNION ALL SELECT 'WOCHE',CAST(date_trunc('week',d) AS DATE),* FROM base
 UNION ALL SELECT 'MONAT',CAST(date_trunc('month',d) AS DATE),* FROM base
), agg AS (
 SELECT stand,ebene,periode,city,category,count(*) FILTER(WHERE counts) AS offenses,
 count(DISTINCT event_id) FILTER(WHERE counts) AS reports,
 count(*) FILTER(WHERE counts_case) AS hauptdelikte
 FROM periods GROUP BY 1,2,3,4,5
)
SELECT coalesce(b.ebene,a.ebene) AS ebene,coalesce(b.periode,a.periode) AS periode,
 coalesce(b.city,a.city) AS city,coalesce(b.category,a.category) AS category,
 b.offenses AS offenses_alt,a.offenses AS offenses_neu,
 b.reports AS reports_alt,a.reports AS reports_neu,
 b.hauptdelikte AS hauptdelikte_alt,a.hauptdelikte AS hauptdelikte_neu
FROM (SELECT * FROM agg WHERE stand='vorher') b
FULL OUTER JOIN (SELECT * FROM agg WHERE stand='nachher') a USING(ebene,periode,city,category)
WHERE b.offenses IS DISTINCT FROM a.offenses OR b.reports IS DISTINCT FROM a.reports
 OR b.hauptdelikte IS DISTINCT FROM a.hauptdelikte;
SELECT * FROM audit_period_comparison ORDER BY ebene,periode,city,category;
