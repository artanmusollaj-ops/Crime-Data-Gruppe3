"""Haelt `docs/ausblick.md` an der Wirklichkeit fest.

Das Dokument besteht zur Haelfte aus Saetzen der Form *"hier fehlt etwas"*.
Genau die veralten, sobald jemand die Luecke schliesst - und dann steht in
einem Ausblick eine Aufgabe, die laengst erledigt ist. Dieselbe Drift, die
Tabelle 5.3 des Konzepts dreimal erwischt hat.

Geprueft wird deshalb: Solange das Dokument eine Luecke **behauptet**, muss
sie noch da sein. Wer eine schliesst, faellt hier durch und zieht den
Ausblick mit. Die Messwerte bleiben ungeprueft - sie tragen ein Datum und
beschreiben einen Stand, nicht eine Zusage.

Ist ein Punkt umgesetzt, verschwindet sein Waechter hier und die Zusage wird
dort geprueft, wo sie gilt: Die Herkunftskette (Punkt 1·A, erledigt am 14.9.)
haelt seither ``tests/gold_pipeline/test_build_gold.py`` fest.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUSBLICK = PROJECT_ROOT / "docs" / "ausblick.md"
QUELLE = PROJECT_ROOT / "src" / "crime"


@pytest.fixture(scope="module")
def text() -> str:
    assert AUSBLICK.exists(), f"{AUSBLICK} fehlt"
    return AUSBLICK.read_text(encoding="utf-8")


def code(*teile: str) -> str:
    return (QUELLE.joinpath(*teile)).read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Die behaupteten Luecken
# --------------------------------------------------------------------------


def test_studienstaedte_steht_nur_noch_einmal(text):
    """Umgekehrter Waechter: zusammengefuehrt am 14.9.2026.

    Wer die Zuordnung wieder abschreibt, faellt hier durch - und bei der
    dritten Stadt haette es sonst einen halben Tag Fehlersuche gekostet.
    """
    if "zusammengeführt am 14.9.2026" not in text:
        pytest.skip("Das Dokument fuehrt den Punkt nicht als erledigt")
    # as_posix(), nicht str(): Auf Windows waere es silver_pipeline\\__init__.py,
    # und der erste Anlauf ist genau daran gescheitert.
    treffer = [
        p.relative_to(QUELLE).as_posix() for p in QUELLE.rglob("*.py")
        if "STUDIENSTAEDTE = {" in p.read_text(encoding="utf-8")
    ]
    assert treffer == ["silver_pipeline/__init__.py"], (
        f"STUDIENSTAEDTE wird an {len(treffer)} Stellen definiert: {treffer}. "
        "Der Ausblick sagt, es sei zusammengefuehrt."
    )


def test_der_s3_client_ist_wirklich_fest_verdrahtet(text):
    """Behauptet in Abschnitt 4: Region und Adressierungsstil sind fix."""
    if "fest verdrahtet" not in text:
        pytest.skip("Das Dokument behauptet es nicht mehr")
    backend = code("storage", "backend.py")
    assert 'region_name="us-east-1"' in backend, (
        "Die Region ist nicht mehr fest verdrahtet - Abschnitt 4 anpassen"
    )
    assert '"addressing_style": "path"' in backend, (
        "Der Adressierungsstil ist nicht mehr fest verdrahtet - Abschnitt 4 anpassen"
    )


def test_duckdb_hat_wirklich_keine_grenzen(text):
    """Behauptet in Abschnitt 3: kein memory_limit, keine threads-Einstellung."""
    if "memory_limit" not in text:
        pytest.skip("Das Dokument behauptet es nicht mehr")
    gesetzt = [
        str(p.relative_to(QUELLE))
        for p in QUELLE.rglob("*.py")
        if re.search(r"SET\s+(memory_limit|threads)", p.read_text(encoding="utf-8"))
    ]
    assert not gesetzt, (
        f"Es gibt jetzt Grenzen in {gesetzt} - Abschnitt 3 anpassen"
    )


def test_alle_quellen_haben_vertragsversionen(text):
    """Umgekehrter Waechter: Punkt 2 ist seit dem 14.9. gebaut.

    Vorher stand hier "nur fuer Detroit". Jetzt muessen es alle sein - wer
    eine Quelle ohne Vertrag laesst, macht aus einem erledigten Punkt wieder
    eine Luecke.
    """
    if "erledigt am 14.9." not in text:
        pytest.skip("Das Dokument fuehrt den Punkt nicht als erledigt")
    # Die drei Versionen liegen in drei Modulen - bronze_ und raw_ in
    # extract_detroit, window_ in detroit_arcgis. Gesucht wird deshalb im Paket.
    detroit = "".join(
        p.read_text(encoding="utf-8")
        for p in sorted((QUELLE / "detroit_pipeline").glob("*.py"))
    )
    fehlend = [v for v in ("bronze_contract_version", "raw_contract_version",
                           "window_contract_version") if v not in detroit]
    assert not fehlend, (
        f"Detroits Vertragsversionen {fehlend} sind weg - Abschnitt 2 verliert "
        "sein Vorbild"
    )
    ohne = [
        pfad for pfad in ("chicago_pipeline/download_chicago.py",
                          "census_pipeline/download_acs.py",
                          "census_pipeline/download_tiger.py",
                          "weather_pipeline/download_noaa.py")
        if "CONTRACT_VERSION" not in code(*pfad.split("/"))
    ]
    assert not ohne, (
        f"{ohne} haben keine Vertragsversion mehr - der Ausblick sagt, der "
        "Punkt sei erledigt"
    )


def test_die_herkunftskette_bleibt_geschlossen(text):
    """Umgekehrter Waechter: Punkt 1- A ist seit dem 14.9. gebaut.

    Das Dokument fuehrt ihn als erledigt - dann muss der Code es auch
    weiterhin tun. Wer ``herkunft_der_quelle`` entfernt, macht aus einem
    erledigten Punkt wieder eine Luecke, ohne es zu merken.
    """
    if "erledigt 14.9.2026" not in text:
        pytest.skip("Das Dokument fuehrt den Punkt nicht als erledigt")
    assert "def herkunft_der_quelle" in code("gold_pipeline", "build_gold.py"), (
        "Gold nennt seine Quelle wieder nur als Pfad - der Ausblick sagt, "
        "der Punkt sei erledigt"
    )
    assert "def eingabe_abdruck" in code("manifeste", "__init__.py"), (
        "Der Eingabe-Abdruck ist weg - Abschnitt 1 anpassen"
    )


def test_die_code_version_steht_in_den_manifesten(text):
    """Umgekehrter Waechter zu Vorschlag 1, gebaut am 14.9."""
    if "Code-Version in jedem Manifest" not in text:
        pytest.skip("Das Dokument fuehrt es nicht als erledigt")
    assert "def code_stand" in code("manifeste", "__init__.py"), (
        "code_stand ist weg - Abschnitt 2 anpassen"
    )
    gefunden = [
        str(p.relative_to(QUELLE))
        for p in QUELLE.rglob("*.py")
        if '"code_version": code_stand()' in p.read_text(encoding="utf-8")
    ]
    assert len(gefunden) >= 9, (
        f"nur {len(gefunden)} Manifeste tragen die Code-Version: {gefunden}"
    )


def test_das_aufraeumen_kennt_gepinnte_laeufe(text):
    """Umgekehrter Waechter: Stufe B ist seit dem 14.9. gebaut."""
    if "erledigt 14.9.2026 (#79)" not in text:
        pytest.skip("Das Dokument fuehrt Stufe B nicht als erledigt")
    quelle = code("orchestration", "aufraeumen.py")
    assert "def gepinnte_laeufe" in quelle and "def pinne" in quelle, (
        "Das Aufraeumen kennt keine gepinnten Laeufe mehr - Abschnitt 1 anpassen"
    )


# --------------------------------------------------------------------------
# Form
# --------------------------------------------------------------------------


def test_die_verweise_zeigen_auf_vorhandene_dateien(text):
    """Ein Ausblick, der auf nichts zeigt, ist eine Behauptung."""
    fehlend = [
        z for z in re.findall(r"\]\(([a-z0-9_.-]+\.md)\)", text)
        if not (AUSBLICK.parent / z).exists()
    ]
    assert not fehlend, f"verlinkt, aber nicht vorhanden: {fehlend}"


def test_artans_punkte_sind_als_solche_gekennzeichnet(text):
    """Wer etwas beigetragen hat, soll es im Dokument wiederfinden."""
    assert text.count("Artan") >= 2, "Die Herkunft der beiden Punkte fehlt"


def test_das_konzept_verweist_auf_den_ausblick():
    konzept = (PROJECT_ROOT / "docs" / "ln1_konzept.md").read_text(encoding="utf-8")
    assert "ausblick.md" in konzept, "Kapitel 11 nennt den Ausblick nicht"


# --------------------------------------------------------------------------
# Abschnitt 5: die Analyseplattform
# --------------------------------------------------------------------------


def test_es_gibt_weiterhin_keinen_wuerfel(text):
    """Die Zusage aus Abschnitt 5 - und aus Konzept 5.2, zweimal gemessen.

    Ein vorberechnetes Aggregat fuer das Dashboard waere 86 Prozent so gross
    wie die Faktentabelle und wuerfe jede Dimension weg, die niemand vorher
    festgelegt hat. Wer es doch materialisiert, faellt hier durch.
    """
    if "Das Format ist der Würfel" not in text:
        pytest.skip("Das Dokument sagt es nicht mehr")
    gold = PROJECT_ROOT / "data" / "gold"
    wuerfel = [p.name for p in gold.glob("dataset=*")
               if p.name.startswith(("dataset=fact_tract", "dataset=fact_city",
                                     "dataset=agg_", "dataset=dashboard"))]
    assert not wuerfel, f"vorberechnete Aggregate in Gold: {wuerfel}"
    # Ein Wuerfel waere eine **geschriebene** Parquet-Datei. Weder GROUP BY
    # noch der Dateiname allein sagen etwas: Ersteres steht in den Docstrings
    # als Abfragebeispiel, Letzteres ist die Konstante zum Lesen.
    serving = PROJECT_ROOT / "src" / "crime" / "serving"
    schreibt = re.compile(r"COPY\s.*\sTO\s'|write_table\(|to_parquet\(")
    materialisiert = [
        p.name for p in serving.glob("*.py")
        if schreibt.search(p.read_text(encoding="utf-8"))
    ]
    assert not materialisiert, (
        f"{materialisiert} schreibt Parquet in der Serving-Schicht - Abschnitt 5 "
        "sagt, aggregiert wird in der Abfrage, nicht im Speicher"
    )


def test_das_konzept_verspricht_weiterhin_keine_aggregate(text):
    """Abschnitt 5 beruft sich woertlich auf Konzept 5.2."""
    if "Keine vorberechneten Aggregate" not in text:
        pytest.skip("Das Dokument beruft sich nicht darauf")
    konzept = (PROJECT_ROOT / "docs" / "ln1_konzept.md").read_text(encoding="utf-8")
    assert "Keine vorberechneten Aggregate" in konzept, (
        "Die Zusage steht nicht mehr im Konzept - Abschnitt 5 zitiert ins Leere"
    )


def test_die_beiden_bauarten_nennen_vorhandene_artefakte(text):
    """Die Karte ist geloest - solange das GeoJSON-Werkzeug existiert."""
    if "1'055 Tract-Umrisse" not in text:
        pytest.skip("Das Dokument nennt sie nicht")
    assert (PROJECT_ROOT / "src" / "crime" / "serving" / "export_geojson.py").exists()
    assert (PROJECT_ROOT / "src" / "crime" / "serving" / "build_analysis_db.py").exists()


# --------------------------------------------------------------------------
# Abschnitt 6: der Veroeffentlichungsstand, wie er ab LN2 gebaut wird
# --------------------------------------------------------------------------
# Ein externer Rat vom 17.9.2026 hat den Bau bestaetigt und dabei einen
# Verzeichnisbaum mit drei vorberechneten Aggregaten vorgeschlagen. Der
# Abschnitt lehnt sie begruendet ab - und genau solche Ablehnungen sind das,
# was ein halbes Jahr spaeter niemand mehr erinnert, wenn derselbe Vorschlag
# ein zweites Mal kommt.

AGGREGATE = ("comparison_day", "comparison_week", "comparison_month",
             "partition_quality")


def test_der_versionspfad_ist_gebaut_und_der_abschnitt_sagt_es(text):
    """Am 17.9.2026 wurde die Luecke geschlossen - der Abschnitt darf sie nicht
    mehr als offen fuehren, und die Zusage liegt dort, wo sie gilt."""
    if "Versionspfad plus ein Verweis" not in text:
        pytest.skip("Das Dokument beschreibt den Bau nicht mehr")
    assert (QUELLE / "storage" / "release.py").is_file()
    assert (PROJECT_ROOT / "tests" / "storage" / "test_release.py").is_file()
    assert "**Gebaut am 17.9.2026" in text
    assert "**Offen.** Die fünf Gold-Tabellen" not in text


def test_die_aggregate_liegen_in_serving_nicht_in_gold(text):
    """Die Entscheidung vom 17.9.2026: gebaut, aber nicht in Gold.

    Ein erster Entwurf lehnte sie ab; Christian hat entschieden, dass fuer ein
    Studienprojekt der gebaute Gegenentwurf zaehlt. Der Abschnitt sagt seither,
    wo sie liegen - und Konzept 5.2 sagt weiterhin: keine Aggregate in Gold.
    """
    if "Was ein Release enthält" not in text:
        pytest.skip("Der Abschnitt nennt den Inhalt eines Release nicht")
    for name in AGGREGATE:
        assert f"`{name}`" in text, f"{name} wird im Ausblick nicht genannt"
    assert "serving.build_comparison" in text
    gold = PROJECT_ROOT / "data" / "gold"
    if gold.is_dir():
        gebaut = {p.name.removeprefix("dataset=") for p in gold.iterdir() if p.is_dir()}
        drin = gebaut & set(AGGREGATE)
        assert not drin, (
            f"{sorted(drin)} ist in Gold gebaut worden - sie gehoeren nach serving/, "
            "Konzept 5.2 sagt 'keine Aggregate in Gold'"
        )
    konzept = (PROJECT_ROOT / "docs" / "ln1_konzept.md").read_text(encoding="utf-8")
    assert "Keine vorberechneten Aggregate in Gold" in konzept


def test_die_beiden_historien_werden_auseinandergehalten(text):
    """Release-Historie und Quellhistorie sind zwei Fragen, nicht eine.

    Beide Dokumente sagen es, und zwar gegenseitig: Ohne den Verweis landet
    am Freitag eine Entscheidung auf dem Tisch, die gar nicht ansteht.
    """
    if "datenhistorie.md" not in text:
        pytest.skip("Abschnitt 6 verweist nicht auf das Entscheidungspapier")
    assert "veröffentlichten" in text and "Quelländerungen" in text
    papier = PROJECT_ROOT / "docs" / "datenhistorie.md"
    if not papier.is_file():
        pytest.skip("das Entscheidungspapier fehlt")
    gegenrichtung = papier.read_text(encoding="utf-8")
    assert "ausblick.md" in gegenrichtung, (
        "datenhistorie.md verweist nicht zurueck - dann trennt nur eine Seite "
        "die beiden Fragen"
    )
