-- OPTIONAL: NACH 00_setup und VOR dem erneuten ETL-Aufbau ausfuehren.
-- In derselben DuckDB-Verbindung bleiben! TEMP-Tabellen halten die Kopie im Speicher.
-- Nicht nochmals ausfuehren, bevor 06 verglichen hat: sonst wird der alte Stand ersetzt.
CREATE OR REPLACE TEMP TABLE audit_before AS SELECT * FROM audit_silver;
CREATE OR REPLACE TEMP TABLE audit_parameters_before AS SELECT * FROM audit_parameters;
CREATE OR REPLACE TEMP TABLE audit_categories_before AS SELECT * FROM audit_categories;
CREATE OR REPLACE TEMP TABLE audit_ref_map_before AS SELECT * FROM audit_ref_map;
SELECT 'Snapshot im Speicher; nun ETL separat ausfuehren' AS hinweis,count(*) AS zeilen FROM audit_before;
