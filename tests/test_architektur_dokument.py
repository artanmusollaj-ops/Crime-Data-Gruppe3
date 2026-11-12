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
    """So viele, wie der Bauplan fuehrt - und je Gruppe die richtige Zahl.

    **Das Zahlwort wird abgeleitet, nicht getippt.** Bis zum 16.10.2026
    stand hier ``"vierzehn Stufen" in teil_a`` und ``len(STUFEN) == 14``:
    zwei Literale, die derselbe Handgriff haette nachziehen muessen. Als
    ``build_source_change`` in den Bauplan kam, fiel der Test - zu Recht -,
    aber er sagte nur, dass "vierzehn" fehle, nicht dass das Dokument
    nachzuziehen sei. Jetzt nennt er die erwartete Zahl.
    """
    from serving.build_einstieg import ZAHLWORT

    from orchestration.run_all import GRUPPEN, STUFEN

    wort = ZAHLWORT[len(STUFEN)]
    assert f"{wort} Stufen" in teil_a, (
        f"der Bauplan fuehrt {len(STUFEN)} Stufen, das Dokument nennt eine "
        f"andere Zahl - erwartet: '{wort} Stufen'")
    for gruppe in GRUPPEN:
        echt = sum(1 for s in STUFEN if s.gruppe == gruppe)
        zeile = next((z for z in teil_a.splitlines()
                      if z.startswith(f"| {gruppe} |")), None)
        assert zeile, f"keine Zeile fuer die Gruppe {gruppe}"
        assert f"| {echt} |" in zeile, f"{gruppe}: {zeile}"


def test_die_pakete_stimmen(teil_a):
    """Elf inklusive der integrierten Konsole; jedes wird genannt."""
    pakete = sorted(p.name for p in QUELLE.iterdir()
                    if p.is_dir() and (p / "__init__.py").is_file())
    assert len(pakete) == 11 and "elf Pakete" in teil_a
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

#: Welche **Dateien** existieren und deshalb in Teil B mit Datum dastehen
#: muessen. Seit dem 11.10.2026 heissen sie dort nicht mehr "Ausnahmen" - die
#: Zusage ist nicht Abwesenheit, sondern Datierung -, aber die Verknuepfung
#: bleibt dieselbe und bleibt noetig: Eine gebaute Datei, die der Text nicht
#: nennt, steht unbeschrieben im Plan.
#:
#: Nicht jeder gebaute Baustein ist eine Datei. Der laufende Stapel auf srv01
#: und die Access-Anwendung bei Cloudflare sind keine, und diese Liste kann
#: sie nicht fassen - dafuer prueft
#: ``test_teil_b_behauptet_nichts_gebautes`` die Datierung der Aufzaehlung.
#:
#: ``docker-compose.srv01.yml`` fehlte hier vom 6. bis zum 9.10.2026 - also
#: genau der Fehler, den der Kommentar darueber beschreibt, ein zweites Mal:
#: Die Datei entstand, Teil B nannte sie bei ``:280`` und ``:345``, aber die
#: Liste wuchs nicht mit, und damit war die Nennung unbewacht. Aufgefallen
#: ist es nicht beim Bauen, sondern beim Nachzaehlen von aussen. Wer hier
#: eine Datei dazulegt, legt sie in dieselbe Liste - sie ist der einzige Ort,
#: der "gebaut" mit "beschrieben" verknuepft.
AUSNAHMEN = ("docker-compose.yml", "docker-compose.srv01.yml",
             "Dockerfile", "Dockerfile.jupyter")


def test_teil_b_behauptet_nichts_gebautes(teil_b):
    """Teil B verspricht nicht mehr Abwesenheit, sondern Datierung.

    Bis zum 11.10.2026 stand hier der Satz "Nichts in diesem Teil ist gebaut"
    - erst ohne, dann mit einer, zuletzt mit vier Ausnahmen. Am 11.10. liefen
    drei Dienste auf srv01, beide Abbilder waren per Digest gepinnt und ein
    Zeitplan stand: Der Satz waere eine Luege mit fuenf Ausnahmen geworden.

    An seiner Stelle steht jetzt die umgekehrte Zusage - **jeder Baustein
    sagt selbst, ob er gebaut ist, seit wann, und was ihn belegt; was kein
    Datum traegt, ist Plan**. Dieser Test haelt beides: dass die Zusage
    dasteht, und dass jeder als gebaut aufgefuehrte Baustein ein Datum
    nennt. Eine Aufzaehlung ohne Datum waere die Rueckkehr zum alten
    Problem in neuer Form.
    """
    assert "Jeder Baustein dieses Teils sagt selbst" in teil_b, (
        "die Zusage von Teil B fehlt - steht dort wieder eine Behauptung "
        "ueber Abwesenheit, muss sie gegen die Wirklichkeit gehalten werden"
    )
    assert "Was kein Datum trägt, ist Plan" in teil_b

    # Jeder aufgezaehlte Baustein nennt ein Datum. Das Muster ist die
    # Aufzaehlung selbst ("*Die vierte, seit dem 8.10.2026:*"), nicht eine
    # Liste von Dateinamen - der vierte und fuenfte Baustein sind gar keine
    # Dateien, sondern ein laufender Stapel und eine Einrichtung bei
    # Cloudflare.
    bausteine = re.findall(r"\*Die (\w+), (?:ebenfalls )?seit dem "
                           r"(\d{1,2}\.\d{1,2}\.\d{4}):\*", teil_b)
    assert len(bausteine) >= 5, (
        f"nur {len(bausteine)} datierte Bausteine in Teil B, erwartet sind "
        "mindestens fuenf - ist einer ohne Datum dazugekommen?"
    )
    ohne_datum = re.findall(r"\*Die (\w+)(?:, (?:ebenfalls )?seit)?:\*", teil_b)
    assert not ohne_datum, (
        f"{ohne_datum} steht ohne Datum da - Teil B verspricht ein Datum je "
        "Baustein"
    )
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
    for wert in ("1'909'461", "1'887'009", "94,5", "134,0", "42 Kontrollen",
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
    """Die Aussage des Blattes, nicht seine Verzierung.

    Bis zum 11.10.2026 stand im Ziel-Teil "nichts davon ist gebaut". Seit auf
    srv01 drei Dienste laufen, waere das falsch; der Einseiter sagt jetzt
    "teils gebaut, je Baustein datiert" - dieselbe Umstellung, die Teil B von
    ``architektur-ist-und-ziel.md`` gemacht hat, und aus demselben Grund.
    Die Trennung Ist/Ziel bleibt die Aussage des Blattes; nur traegt sie
    jetzt Daten statt einer Verneinung.
    """
    assert "teils gebaut, je Baustein datiert" in blatt, (
        "der Ziel-Teil sagt nicht mehr, wie er zum Ist steht - stuende dort "
        "wieder eine Verneinung, muesste sie gegen srv01 gehalten werden"
    )
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
