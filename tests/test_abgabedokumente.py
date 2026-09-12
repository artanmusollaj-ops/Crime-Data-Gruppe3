"""Prueft die Zahlen in den Abgabedokumenten gegen die gebauten Daten.

``tests/test_aenderungen.py`` bewacht den Kopfabschnitt von ``AENDERUNGEN.md``.
Das genuegte nicht: Beim Neubau von Silver und Gold am 12.9. blieben fuenf
Zahlen in ``ln1_konzept.md`` und ``projektabsprache.md`` stehen - 344'607 statt
344'617, 85'335 statt 85'345, Detroits Rate 132,5 statt 132,6. Alle Tests waren
gruen, weil keiner diese Dateien ansieht.

Genau das ist die teuerste Art Fehler in einer Abgabe: Eine Zahl auf einer Folie
stimmt nicht mit der Zahl im Konzept ueberein, und niemand weiss mehr, welche
die richtige ist.

Geprueft werden deshalb die Zahlen, die eine Aussage tragen - Zeilenzahlen der
Schichten, die Raten je Einwohner, das Korn. **Nicht** geprueft wird der
Fliesstext: Er beschreibt Entscheidungen und Vergangenes und soll sich nicht
mit jedem Ladelauf aendern.

Fehlt eine Datei oder eine Schicht, wird uebersprungen statt rot: Die Tests
muessen auch in einem frischen Klon ohne ``data/`` durchlaufen.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
KONZEPT = PROJECT_ROOT / "docs" / "ln1_konzept.md"
ABSPRACHE = PROJECT_ROOT / "docs" / "projektabsprache.md"
README = PROJECT_ROOT / "README.md"

SILVER = PROJECT_ROOT / "data" / "silver"
GOLD = PROJECT_ROOT / "data" / "gold"


def parquet(schicht: Path, dataset: str) -> Path | None:
    """Die Datei einer Tabelle - flach oder unter einem ``vintage=``.

    ``tract`` und ``place`` haengen an einem Zensusjahrgang und liegen deshalb
    eine Ebene tiefer als die uebrigen. Wer das hier fest verdrahtet, baut
    denselben Fehler ein, den dieser Test verhindern soll.
    """
    wurzel = schicht / f"dataset={dataset}"
    flach = wurzel / "part-0001.parquet"
    if flach.exists():
        return flach
    treffer = sorted(wurzel.glob("vintage=*/part-0001.parquet"))
    return treffer[-1] if treffer else None


@pytest.fixture(scope="module")
def con():
    duckdb = pytest.importorskip("duckdb")
    verbindung = duckdb.connect()
    yield verbindung
    verbindung.close()


@pytest.fixture(scope="module")
def konzept() -> str:
    return KONZEPT.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def absprache() -> str:
    return ABSPRACHE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def readme() -> str:
    return README.read_text(encoding="utf-8")


def zeilen(con, pfad: Path | None) -> int:
    if pfad is None or not pfad.exists():
        pytest.skip(f"nicht gebaut: {pfad}")
    return con.execute(f"SELECT count(*) FROM read_parquet('{pfad}')").fetchone()[0]


def genannt(text: str, muster: str) -> int:
    """Eine Zahl aus dem Dokument, mit Apostroph als Tausendertrenner."""
    treffer = re.search(muster, text)
    assert treffer, f"Muster nicht im Dokument gefunden: {muster}"
    return int(treffer.group(1).replace("'", ""))


# --------------------------------------------------------------------------
# Die Zeilenzahlen der Schichten
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "dataset,muster",
    [
        ("crime_offense", r"\| `crime_offense` \|[^|]*\| \*\*gebaut\*\*, ([0-9']+) Zeilen \|"),
        ("tract", r"\| `tract` \|[^|]*\| \*\*gebaut\*\*, ([0-9']+) Zeilen \|"),
        ("place", r"\| `place` \|[^|]*\| \*\*gebaut\*\*, ([0-9']+) Zeilen \|"),
        ("weather_day", r"\| `weather_day` \|[^|]*\| \*\*gebaut\*\*, ([0-9']+) Zeilen \|"),
    ],
)
def test_silber_tabelle_in_82(con, konzept, dataset, muster):
    """Kapitel 8.2 nennt je Silver-Tabelle ihre Zeilenzahl."""
    assert genannt(konzept, muster) == zeilen(con, parquet(SILVER, dataset)), dataset


@pytest.mark.parametrize(
    "dataset,muster",
    [
        ("fact_offense", r"\| `fact_offense` \| \*\*eine Tat\*\* \| ([0-9']+) \|"),
        ("dim_tract", r"\| `dim_tract` \|[^|]*\| ([0-9']+) \|"),
        ("dim_offense", r"\| `dim_offense` \| ein NIBRS-Delikt \| ([0-9']+) \|"),
        ("dim_date", r"\| `dim_date` \| ein Kalendertag \| ([0-9']+) \|"),
        ("dim_city_day", r"\| `dim_city_day` \|[^|]*\| ([0-9']+) \|"),
    ],
)
def test_gold_tabelle_in_52(con, konzept, dataset, muster):
    """Kapitel 5.2 nennt je Gold-Tabelle ihre Zeilenzahl."""
    assert genannt(konzept, muster) == zeilen(con, parquet(GOLD, dataset)), dataset


# --------------------------------------------------------------------------
# Das Korn - die Zahl, an der Detroit und Chicago auseinandergehen
# --------------------------------------------------------------------------


def test_detroits_korn_in_der_kurzfassung(con, konzept):
    """Kapitel 1: "88'685 Anklagen zu N Taten"."""
    pfad = parquet(SILVER, "crime_offense")
    if pfad is None:
        pytest.skip("Silver nicht gebaut")
    echt = con.execute(
        f"SELECT count(*) FILTER (WHERE counts), count(*) FROM read_parquet('{pfad}') "
        "WHERE city = 'detroit'"
    ).fetchone()
    anklagen = genannt(konzept, r"\| Detroit, Jahrgang 2024 \| ([0-9']+) Anklagen zu")
    taten = genannt(konzept, r"\| Detroit, Jahrgang 2024 \| [0-9']+ Anklagen zu ([0-9']+) Taten \|")
    assert (taten, anklagen) == echt


def test_gold_korn_in_der_absprache(con, absprache):
    """Die Absprache nennt dieselbe Gold-Zeilenzahl wie das Konzept."""
    assert genannt(absprache, r"Gold kommt damit auf ([0-9']+)\)") == zeilen(
        con, parquet(GOLD, "fact_offense")
    )


# --------------------------------------------------------------------------
# Die Rate je Einwohner - was am ehesten auf eine Folie kommt
# --------------------------------------------------------------------------


@pytest.mark.parametrize("stadt", ["Chicago", "Detroit"])
def test_rate_je_einwohner(con, konzept, stadt):
    fakt, dim = parquet(GOLD, "fact_offense"), parquet(GOLD, "dim_tract")
    if fakt is None or dim is None:
        pytest.skip("Gold nicht gebaut")
    echt = dict(
        (z[0], (z[1], z[2], z[3]))
        for z in con.execute(f"""
            WITH e AS (
                SELECT city, sum(population) AS n FROM read_parquet('{dim}')
                WHERE city IS NOT NULL GROUP BY 1
            )
            SELECT t.city, count(*), any_value(e.n),
                   round(count(*) * 1000.0 / any_value(e.n), 1)
            FROM read_parquet('{fakt}') f
            JOIN read_parquet('{dim}') t ON t.geoid = f.tract_geoid
            JOIN e ON e.city = t.city
            WHERE t.city IS NOT NULL GROUP BY 1
        """).fetchall()
    )
    treffer = re.search(
        rf"\| {stadt} \| ([0-9']+) \| ([0-9']+) \| \*\*([0-9]+,[0-9])\*\* \|", konzept
    )
    assert treffer, f"Ratenzeile fuer {stadt} nicht gefunden"
    delikte = int(treffer.group(1).replace("'", ""))
    einwohner = int(treffer.group(2).replace("'", ""))
    rate = float(treffer.group(3).replace(",", "."))
    assert (delikte, einwohner) == echt[stadt.lower()][:2]
    assert rate == pytest.approx(echt[stadt.lower()][2], abs=0.05)


# --------------------------------------------------------------------------
# H3: die Tabelle in 8.5
# --------------------------------------------------------------------------


def test_h3_tabelle_in_85(con, konzept):
    """Die Tatkorn-Zahlen, mit denen H3 teilweise falsifiziert wird."""
    fakt = parquet(GOLD, "fact_offense")
    silber = parquet(SILVER, "crime_offense")
    if fakt is None or silber is None:
        pytest.skip("Gold oder Silver nicht gebaut")
    je_stadt = dict(con.execute(f"""
        SELECT s.city, count(*) FROM read_parquet('{fakt}') f
        JOIN read_parquet('{silber}') s ON s.offense_id = f.offense_id
        GROUP BY 1
    """).fetchall())
    gesamt = zeilen(con, fakt)

    assert genannt(konzept, r"über die ([0-9']+) Delikte des Jahrgangs 2024") == gesamt
    treffer = re.search(
        r"\| Delikte \(Tatkorn\) \| ([0-9']+) \| ([0-9']+) \| ([0-9']+) \|", konzept
    )
    assert treffer, "Tatkorn-Zeile in 8.5 nicht gefunden"
    chi, det, zusammen = (int(g.replace("'", "")) for g in treffer.groups())
    assert (chi, det, zusammen) == (
        je_stadt["chicago"], je_stadt["detroit"], gesamt
    )


# --------------------------------------------------------------------------
# README - die erste Seite, die jemand liest
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "dataset,schicht,muster",
    [
        ("crime_offense", SILVER, r"`silver/crime_offense` \| ([0-9']+) Zeilen"),
        ("fact_offense", GOLD, r"`gold/fact_offense` \| ([0-9']+) Zeilen"),
        ("tract", SILVER, r"\| `tract` \| ein Census Tract \| ([0-9']+) \|"),
        ("place", SILVER, r"\| `place` \|[^|]*\| ([0-9']+) \|"),
        ("weather_day", SILVER, r"\| `weather_day` \|[^|]*\| ([0-9']+) \|"),
    ],
)
def test_readme_nennt_die_zeilenzahlen(con, readme, dataset, schicht, muster):
    """Der Kopf des README nennt den Stand der Schichten."""
    assert genannt(readme, muster) == zeilen(con, parquet(schicht, dataset)), dataset


@pytest.mark.parametrize("stadt", ["Chicago", "Detroit"])
def test_readme_nennt_die_raten(con, readme, stadt):
    fakt, dim = parquet(GOLD, "fact_offense"), parquet(GOLD, "dim_tract")
    if fakt is None or dim is None:
        pytest.skip("Gold nicht gebaut")
    echt = dict(
        (z[0], (z[1], z[2]))
        for z in con.execute(f"""
            WITH e AS (
                SELECT city, sum(population) AS n FROM read_parquet('{dim}')
                WHERE city IS NOT NULL GROUP BY 1
            )
            SELECT t.city, count(*), round(count(*) * 1000.0 / any_value(e.n), 1)
            FROM read_parquet('{fakt}') f
            JOIN read_parquet('{dim}') t ON t.geoid = f.tract_geoid
            JOIN e ON e.city = t.city
            WHERE t.city IS NOT NULL GROUP BY 1
        """).fetchall()
    )
    treffer = re.search(
        rf"\| {stadt} \| ([0-9']+) Delikte .*?\*\*([0-9]+,[0-9])\*\* je 1'000",
        readme,
    )
    assert treffer, f"Ratenzeile fuer {stadt} nicht im README"
    delikte = int(treffer.group(1).replace("'", ""))
    rate = float(treffer.group(2).replace(",", "."))
    assert delikte == echt[stadt.lower()][0]
    assert rate == pytest.approx(echt[stadt.lower()][1], abs=0.05)


def test_readme_nennt_die_testzahl(readme):
    """"Erwartet werden N bestandene Tests" - die Zusage an jeden, der neu klont.

    Steht dort eine zu hohe Zahl, glaubt der Nächste, seine Einrichtung sei
    kaputt. Steht eine zu niedrige, faellt nicht auf, dass Tests fehlen.
    """
    genannte = {
        int(z.replace("'", ""))
        for z in re.findall(r"\*\*([0-9']+) (?:bestandene )?Tests?\*\*", readme)
    }
    assert genannte, "Das README nennt keine Testzahl"
    fertig = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only",
         "-o", "addopts=", "-p", "no:cacheprovider"],
        capture_output=True, text=True, cwd=PROJECT_ROOT,
    )
    treffer = re.search(r"([0-9]+) tests? collected", fertig.stdout)
    if treffer is None:
        pytest.skip(f"Sammellauf lieferte keine Zahl: {fertig.stdout[-200:]}")
    gesammelt = int(treffer.group(1))
    assert genannte == {gesammelt}, (
        f"README nennt {sorted(genannte)} Tests, gesammelt werden {gesammelt}"
    )
