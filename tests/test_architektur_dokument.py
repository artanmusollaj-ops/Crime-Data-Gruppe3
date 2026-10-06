"""Prueft ``docs/architektur-ist-und-ziel.md`` - den Architekturtext fuer LN1.

Das Dokument hat zwei Teile, und seine wichtigste Zusage ist die Trennung:
**Teil A beschreibt, was laeuft; Teil B, was geplant ist.** Genau diese Grenze
verwischt in einem Konzeptpapier am schnellsten - ein Baustein wird gebaut, der
Text bleibt im Futur stehen, oder schlimmer: Ein Plan wandert unbemerkt in den
Ist-Teil.

Geprueft wird deshalb zweierlei:

* **Teil A gegen den Code** - Stufen, Pakete, Schichten, Kontrollen. Das
  braucht keine gebauten Daten und laeuft auf jedem Pull Request.
* **Teil B gegen die Abwesenheit** - solange der Text sagt, etwas sei nicht
  gebaut, darf es auch nicht dastehen.

Die Zahlen aus den Daten (347'957, 1'748, 31'565) traegt Teil A bewusst im
**Referenzstand**, wie jedes andere Abgabedokument; sie sind dort bewacht, wo
sie herkommen, und werden hier nur gegen README und AENDERUNGEN gehalten.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOKUMENT = PROJECT_ROOT / "docs" / "architektur-ist-und-ziel.md"
QUELLE = PROJECT_ROOT / "src" / "crime"

if str(QUELLE) not in sys.path:
    sys.path.insert(0, str(QUELLE))


@pytest.fixture(scope="module")
def text() -> str:
    if not DOKUMENT.is_file():
        pytest.skip(f"{DOKUMENT} fehlt")
    return DOKUMENT.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def teil_a(text) -> str:
    return text[text.index("# Teil A"):text.index("# Teil B")]


@pytest.fixture(scope="module")
def teil_b(text) -> str:
    return text[text.index("# Teil B"):]


def zahl(text: str, muster: str) -> int:
    treffer = re.search(muster, text)
    assert treffer, f"nicht gefunden: {muster}"
    return int(treffer.group(1).replace("'", ""))


# --------------------------------------------------------------------------
# Teil A gegen den Code
# --------------------------------------------------------------------------


def test_die_stufenzahl_stimmt(teil_a):
    """Vierzehn - und je Gruppe die richtige Zahl."""
    from orchestration.run_all import GRUPPEN, STUFEN

    assert "vierzehn Stufen" in teil_a
    assert len(STUFEN) == 14
    for gruppe in GRUPPEN:
        echt = sum(1 for s in STUFEN if s.gruppe == gruppe)
        zeile = next((z for z in teil_a.splitlines()
                      if z.startswith(f"| {gruppe} |")), None)
        assert zeile, f"keine Zeile fuer die Gruppe {gruppe}"
        assert f"| {echt} |" in zeile, f"{gruppe}: {zeile}"


def test_die_pakete_stimmen(teil_a):
    """Zehn, und jedes wird im Bild genannt."""
    pakete = sorted(p.name for p in QUELLE.iterdir()
                    if p.is_dir() and (p / "__init__.py").is_file())
    assert len(pakete) == 10 and "zehn Pakete" in teil_a
    fehlend = [p for p in pakete if p.replace("_pipeline", "_\npipeline") not in teil_a
               and p not in teil_a]
    assert not fehlend, f"diese Pakete fehlen im Bild: {fehlend}"


def test_das_fundament_ist_wirklich_eines(teil_a):
    """Die Aussage, die das Bild traegt - und die der Waechter schon gefangen hat."""
    assert "`manifeste` und `storage` dürfen keine" in teil_a
    import tests.test_architekturbilder as ab  # noqa: PLC0415

    assert hasattr(ab, "test_die_fundamente_haengen_an_nichts"), (
        "der Test, auf den sich das Dokument beruft, heisst anders"
    )


def test_die_kontrollzahlen_stimmen_mit_der_landkarte(teil_a):
    """42 und 28 - dieselben Zahlen wie in zaehlperspektiven.md."""
    nb = json.loads((PROJECT_ROOT / "notebooks" / "35_kontrollen.ipynb")
                    .read_text(encoding="utf-8"))
    for zelle in nb["cells"]:
        quelle = "".join(zelle["source"])
        if "KONTROLLEN = [" not in quelle:
            continue
        for knoten in ast.parse(quelle).body:
            if getattr(getattr(knoten, "targets", [None])[0], "id", "") == "KONTROLLEN":
                kontrollen = ast.literal_eval(knoten.value)
                break
    hart = [k for k in kontrollen if k[3] == "hart"]
    assert zahl(teil_a, r"(\d+) Kontrollen, davon") == len(kontrollen)
    assert zahl(teil_a, r"davon (\d+) mit Abbruch") == len(hart) - 3


# Nur so weit, wie ein Sternschema je kommen wird.
ZAHLWORT = {4: "vier", 5: "fünf", 6: "sechs", 7: "sieben", 8: "acht"}


def test_die_schichten_und_ihre_tabellen_stimmen(teil_a):
    """Die Zahl kommt aus den Registern, nicht aus diesem Test.

    Bis zum 3.10.2026 stand die Fuenf hier zweimal verdrahtet - als Zahl und
    als Wort -, und eine sechste Sterntabelle liess beide Haelften gleichzeitig
    falsch werden. Gelesen wird jetzt ``TABELLEN``; der Test prueft, dass das
    Dokument dasselbe sagt.
    """
    from gold_pipeline import TABELLEN as GOLD
    from serving.build_comparison import TABELLEN as SERVING

    assert f"{ZAHLWORT[len(GOLD)]} Sterntabellen" in teil_a, (
        f"{len(GOLD)} Gold-Tabellen - das Dokument nennt eine andere Zahl"
    )
    assert f"{ZAHLWORT[len(SERVING)]} Vergleichstabellen" in teil_a, (
        f"{len(SERVING)} Vergleichstabellen - das Dokument nennt eine andere Zahl"
    )
    for schicht in ("raw", "bronze", "silver", "gold", "serving", "releases"):
        assert f"**{schicht}**" in teil_a, f"die Schicht {schicht} fehlt in der Tabelle"


def test_die_drei_betriebsarten_stehen_drin(teil_a):
    from storage import BACKENDS

    for modus in BACKENDS:
        assert f"| `{modus}` |" in teil_a, f"der Modus {modus} fehlt"
    assert len(BACKENDS) == 3


def test_die_testzahlen_stimmen_mit_dem_readme(teil_a):
    """Dieselbe Zahl an zwei Stellen darf nur einmal veralten."""
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    hier = zahl(teil_a, r"([\d']+) Tests ohne Netz")
    dort = zahl(readme, r"\*\*([\d']+) Tests\*\*, alle ohne")
    assert hier == dort, f"Architekturtext {hier}, README {dort}"
    assert zahl(teil_a, r"([\d']+) davon — die übrigen") == \
        zahl(readme, r"\*\*([\d']+) der [\d']+ Tests\*\*")


def test_die_referenzzahlen_stimmen_mit_den_uebrigen_dokumenten(teil_a):
    """Der gepinnte Stand, nicht der gebaute - und an beiden Stellen derselbe.

    Die Muster verlangen nebenbei, dass beide Dokumente ihre Ratenzeilen
    gleich beschriften (``| Chicago |``). Das Jahr, fuer das sie gelten, steht
    in dem Satz darueber, nicht in der Zeile - sonst zerfaellt genau dieser
    Abgleich, und ``orchestration.drift`` liest denselben Kopfabschnitt.
    """
    aenderungen = (PROJECT_ROOT / "docs" / "intern" / "AENDERUNGEN.md").read_text(encoding="utf-8")
    for muster_hier, muster_dort in (
        (r"Bei ([\d']+) Zeilen liegt jede realistische", r"`gold/fact_offense` \| \*\*([\d']+)\*\*"),
        (r"`silver/crime_offense` \| ([\d']+) Zeilen", r"`silver/crime_offense` \| ([\d']+) Zeilen"),
        (r"`gold/fact_offense` \| \*\*([\d']+)\*\*", r"`gold/fact_offense` \| \*\*([\d']+)\*\*"),
        (r"Chicago \| ([\d']+) Delikte", r"Chicago \| ([\d']+) Delikte"),
        (r"Detroit \| ([\d']+) Delikte", r"Detroit \| ([\d']+) Delikte"),
    ):
        assert zahl(teil_a, muster_hier) == zahl(aenderungen, muster_dort)


# --------------------------------------------------------------------------
# Teil B gegen die Abwesenheit
# --------------------------------------------------------------------------


# Zwei Dateien standen hier und sind inzwischen gebaut: ``docker-compose.yml``
# seit dem 28.9.2026 (nur fuer die drei Analysedienste), das ``Dockerfile``
# seit dem 6.10.2026 (das Abbild der Strecke, noch ohne Betrieb). Beide
# bleiben in dieser Liste - sie wandern nur von "darf nicht existieren" nach
# "muss als Ausnahme benannt sein". Genau das ist die Zusage, die der Text
# gibt: nicht, dass nichts gebaut wird, sondern dass kein Gebautes
# unbeschrieben im Plan steht.
GEPLANT = {
    "Elasticsearch": (),
    "Grafana": (),
}

#: Was existiert und deshalb in Teil B ausdruecklich als Ausnahme dastehen
#: muss - je Datei die Jahreszahl, an der sie entstand.
AUSNAHMEN = ("docker-compose.yml", "Dockerfile", "Dockerfile.jupyter")


def test_teil_b_behauptet_nichts_gebautes(teil_b):
    """Solange der Text sagt 'nichts davon ist gebaut', muss das stimmen.

    Faellt dieser Test, ist ein Baustein entstanden - dann gehoert er nach
    Teil A, mit Zahlen, oder in die Liste der benannten Ausnahmen.
    """
    assert "Nichts in diesem Teil ist gebaut" in teil_b
    gefunden = [d for dateien in GEPLANT.values() for d in dateien
                if (PROJECT_ROOT / d).exists()]
    assert not gefunden, (
        f"{gefunden} existiert - Teil B sagt, nichts davon sei gebaut. "
        "Entweder den Text nach Teil A ziehen oder die Datei erklaeren."
    )
    for paket in ("elasticsearch", "grafana"):
        assert paket not in (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")


@pytest.mark.parametrize("datei", AUSNAHMEN)
def test_jedes_gebaute_wird_als_ausnahme_benannt(teil_b, datei):
    """Eine Datei, die es gibt, darf nicht als Plan dastehen.

    Das ist die Haelfte der Zusage, die beim ``docker-compose.yml`` ueber eine
    Woche fehlte: Der Satz "nichts davon ist gebaut" stand weiter da, waehrend
    drei Dienste liefen. Beim ``Dockerfile`` soll das nicht wieder passieren -
    es existiert, also muss der Text es nennen.
    """
    assert (PROJECT_ROOT / datei).exists(), (
        f"{datei} gibt es nicht (mehr) - dann gehoert es aus AUSNAHMEN heraus "
        "und wieder in GEPLANT"
    )
    assert f"`{datei}`" in teil_b, (
        f"{datei} existiert, Teil B nennt es aber nicht als Ausnahme"
    )


def test_der_widerspruch_zum_ausblick_wird_benannt(teil_b):
    """OpenSearch wurde verworfen; Elasticsearch kommt trotzdem - das gehoert gesagt.

    Ein Konzept, das eine eigene frueheren Bewertung stillschweigend umkehrt,
    ist an genau dieser Stelle nicht mehr nachpruefbar.
    """
    ausblick = (PROJECT_ROOT / "docs" / "ausblick.md").read_text(encoding="utf-8")
    assert "falsche **Form**" in ausblick, (
        "der Ausblick bewertet OpenSearch nicht mehr so - dann stimmt die "
        "Aufloesung in Teil B nicht mehr"
    )
    assert "Der Widerspruch, offen benannt" in teil_b
    assert "ausblick.md" in teil_b
    assert "Serving-Index" in teil_b and "kein Bestand" in teil_b


def test_jeder_baustein_nennt_was_er_kostet(teil_b):
    """Ein Plan ohne Preis ist ein Wunsch."""
    abschnitte = re.findall(r"^## B\.\d[^\n]*", teil_b, re.M)
    assert len(abschnitte) >= 7, f"nur {len(abschnitte)} Bausteine: {abschnitte}"
    assert teil_b.count("**Was es kostet.**") + teil_b.count("**Was es kostet**") >= 4
    assert "**Offen:**" in teil_b


def test_die_offenen_punkte_stehen_am_schluss(text):
    assert "Was dieser Text nicht behauptet" in text
    assert "datenhistorie.md" in text, "die offene Drift gehoert erwaehnt"


# --------------------------------------------------------------------------
# Der Einseiter
# --------------------------------------------------------------------------
# docs/architektur-einseiter.html ist dasselbe in klein: zum Ausdrucken und
# in den Leistungsnachweis legen. Seine Zusage steht im Namen - eine Seite -
# und seine Zahlen sind dieselben wie im langen Text. Beides veraltet, sobald
# jemand eine der beiden Dateien allein anfasst.

EINSEITER = PROJECT_ROOT / "docs" / "architektur-einseiter.html"
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


@pytest.fixture(scope="module")
def blatt() -> str:
    if not EINSEITER.is_file():
        pytest.skip(f"{EINSEITER} fehlt")
    return EINSEITER.read_text(encoding="utf-8")


def test_der_einseiter_traegt_dieselben_zahlen(blatt, text):
    """Dieselbe Zahl an zwei Stellen darf nur einmal veralten."""
    # Diese Liste ist von Hand gefuehrt und muss nach einem Neubau mitgezogen
    # werden - sie sagt, **welche** Zahlen an beiden Stellen stehen muessen,
    # und das laesst sich aus den Daten nicht ableiten.
    for wert in ("1'875'378", "1'851'950", "94,5", "133,1", "42 Kontrollen",
                 "1'055", "23,3 %", "55,9 %"):
        assert wert in blatt, f"{wert} fehlt im Einseiter"
        assert wert in text or wert.replace("'", "") in text, (
            f"{wert} steht im Einseiter, aber nicht im langen Text"
        )


def test_der_einseiter_nennt_die_gepruefte_testzahl(blatt):
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    assert zahl(blatt, r"<b>([\d']+)</b><span>Tests") == \
        zahl(readme, r"\*\*([\d']+) Tests\*\*, alle ohne")


def test_der_einseiter_haelt_ist_und_ziel_auseinander(blatt):
    """Die Aussage des Blattes, nicht seine Verzierung."""
    assert "nichts davon ist gebaut" in blatt
    assert 'class="ist"' in blatt and 'class="ziel"' in blatt
    assert "Absichtserklärung" in blatt, "die Begründung der Trennung fehlt"


def test_der_einseiter_ist_selbsttragend(blatt):
    """Kein Bild von aussen - er muss auch ohne Netz drucken.

    Erlaubt ist allein die Schriftart von Google Fonts; faellt sie aus, greift
    die Ersatzkette. Ein ``<img>`` oder ein externes SVG waere im Ausdruck ein
    weisses Rechteck.
    """
    assert "<img" not in blatt and "<script" not in blatt
    fremd = re.findall(r'(?:src|href)="(https?://[^"]+)"', blatt)
    assert all("fonts.googleapis.com" in u or "fonts.gstatic.com" in u for u in fremd), fremd
    assert blatt.count("<svg") == 2, "zwei Bilder, beide inline"


def test_beide_bilder_haben_eine_beschreibung(blatt):
    """Ein Bild ohne Beschreibung ist fuer einen Screenreader nichts."""
    assert blatt.count('role="img"') == 2
    assert blatt.count("aria-label=") == 2


@pytest.mark.referenzstand
def test_der_einseiter_passt_auf_eine_seite():
    """Die Zusage im Namen - gemessen, nicht behauptet.

    Gedruckt wird mit Chrome nach PDF und die Zahl der Seiten gezaehlt. Ohne
    Chrome wird uebersprungen; die Pruefung gehoert an den Rechner, an dem
    jemand das Blatt auch wirklich ausdruckt.
    """
    import subprocess
    import tempfile

    if not CHROME.exists():
        pytest.skip("Chrome nicht vorhanden - Seitenzahl nicht messbar")
    with tempfile.TemporaryDirectory() as ordner:
        pdf = Path(ordner) / "blatt.pdf"
        fertig = subprocess.run(
            [str(CHROME), "--headless", "--disable-gpu", "--no-pdf-header-footer",
             f"--print-to-pdf={pdf}", EINSEITER.as_uri()],
            capture_output=True, timeout=120,
        )
        assert pdf.is_file(), fertig.stderr.decode()[-400:]
        seiten = len(re.findall(rb"/Type\s*/Page[^s]", pdf.read_bytes()))
    assert seiten == 1, f"{seiten} Seiten - der Einseiter ist keiner mehr"
