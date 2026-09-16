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
