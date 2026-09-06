"""Ingestion der Referenzdaten des US Census Bureau.

``download_tiger`` laedt die Geometrien der Census Tracts (TIGER/Line),
``download_acs`` die Attribute derselben Tracts (ACS 5-Jahres-Schaetzungen).
Beide Quellen teilen Vintage, Bundesstaat und den Schluessel ``GEOID``.

Die Tracts sind der gemeinsame Nenner, ueber den sich Chicago und Detroit
vergleichen lassen: Beide Staedte liefern Koordinaten, aber ihre eigenen
Raumeinheiten (community_area, ward, Bezirk) sind es nicht.
"""

# Die Bundesstaaten der beiden Staedte. Die FIPS-Nummer ist der Schluessel, den
# auch die Dateinamen und Abfragen der Quellen verwenden. Sie steht hier, damit
# beide Module sie teilen, ohne voneinander abzuhaengen - die ACS-Ingestion
# braucht kein GDAL.
STATES = {
    "17": "illinois",  # Cook County, Chicago
    "26": "michigan",  # Wayne County, Detroit
}
