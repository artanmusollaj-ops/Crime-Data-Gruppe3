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

# Das juengste ACS-5-Jahres-Vintage, das es gibt. Am 3.10.2026 an der
# Census-API gemessen: 2025 und 2026 sind nicht veroeffentlicht und werden es
# bis zur Abgabe auch nicht sein.
#
# Die Regel steht hier und nicht bei ihren beiden Benutzern. Der Gesamtlauf
# braucht sie, um zu wissen, welche Vintages er laedt; Gold braucht sie, um
# jeder Tat ihren Nenner zuzuordnen. Zweimal geschrieben waere sie zweimal zu
# pflegen - und die Fassung, die niemand anpasst, ist die, die rechnet.
NEWEST_VINTAGE = 2024


def vintage_for(year: int) -> int:
    """Which ACS vintage serves as the denominator for this year.

    Up to and including ``NEWEST_VINTAGE`` every year has its own. Beyond it
    the newest available one stays in use - that is not an extrapolation but a
    **borrowed** population, and it has to be labelled as such wherever a rate
    is shown.
    """
    return min(year, NEWEST_VINTAGE)


def vintages_for(years) -> tuple[int, ...]:
    """The vintages these years need, each one once, ascending."""
    return tuple(sorted({vintage_for(y) for y in years}))
