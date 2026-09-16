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
