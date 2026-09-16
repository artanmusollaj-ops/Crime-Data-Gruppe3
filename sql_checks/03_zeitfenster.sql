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
