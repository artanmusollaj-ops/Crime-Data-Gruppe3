"""Ingestion der Chicagoer Deliktdaten aus dem Socrata-Portal der Stadt.

Ein Aufruf schreibt einen Lauf nach ``data/raw/`` und ``data/bronze/`` unter
derselben Kennung: Raw haelt die API-Antworten Byte fuer Byte, Bronze wird
daraus abgeleitet. Gedeutet wird hier nichts - kein Datum, keine Zahl, kein
Code. Das gehoert in die Schichten darueber.

Die Besonderheit dieser Quelle ist der Nachweis: Vor dem Download wird die
Menge der ``id`` festgeschrieben, geladen wird per Keyset-Pagination, und
danach muss die geladene Menge exakt der festgeschriebenen entsprechen.
Vollstaendigkeit wird damit nicht behauptet, sondern belegt - nachzulesen an
einem einzelnen Lauf in `docs/eine-zahl.md`, Stufe 6.

Alles Weitere steht im Modul-Docstring von `chicago_pipeline.download_chicago`.
"""
