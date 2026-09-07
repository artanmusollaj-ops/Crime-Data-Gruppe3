"""Ingestion der taeglichen Wetterreihen des GHCN-Daily (NOAA).

Die Quelle liefert eine CSV je Station mit der vollstaendigen Messreihe, bei
den beiden Flughaefen zurueck bis 1946. Ein API-Schluessel ist nicht noetig.

Der Unterschied zu allen anderen Quellen des Projekts liegt in der Join-Achse.
Census und die Falldaten treffen sich raeumlich ueber ``GEOID``; Wetter ist
kein Tract-Merkmal. Eine Station gilt fuer die ganze Stadt, verbunden wird
also ueber **Datum und Stadt**. Deshalb heisst der Partitionsschluessel hier
``station=`` und nicht ``state=``.
"""

# Je Stadt die Flughafenstation - dort messen die laengsten und
# vollstaendigsten Reihen. Midway ist zusaetzlich bekannt, aber nicht Teil des
# Standardlaufs: zwei Stationen fuer dieselbe Stadt braucht erst, wer
# innerstaedtische Unterschiede auswerten will.
STATIONS = {
    "USW00094846": {
        "city": "chicago",
        "name": "Chicago O'Hare International Airport",
        "default": True,
    },
    "USW00094847": {
        "city": "detroit",
        "name": "Detroit Metro Airport",
        "default": True,
    },
    "USW00014819": {
        "city": "chicago",
        "name": "Chicago Midway Airport",
        "default": False,
    },
}

DEFAULT_STATIONS = tuple(
    station for station, info in STATIONS.items() if info["default"]
)
