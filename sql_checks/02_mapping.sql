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
