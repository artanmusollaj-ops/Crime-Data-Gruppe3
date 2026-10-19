"""Jeder offene Punkt hat einen Verantwortlichen, ein Datum und einen Beleg.

**Warum es das Dokument gibt.** Bis zum 19.10.2026 standen offene Punkte an
drei Orten: die Anforderungen in ``fr-stand.md``, zurueckgestellte Befunde in
einer Datei ausserhalb des Repositories (seit dem 15.10. nicht gepflegt, zur
Haelfte erledigt), alles Betriebliche verstreut in ``AENDERUNGEN.md``. Auf
die Frage "was ist noch offen?" gab es keine Antwort ohne Suche.

**Warum es diesen Waechter braucht.** Eine Liste offener Punkte verfaellt auf
zwei Arten. Ein Punkt ohne Verantwortlichen bleibt liegen, weil ihn jeder fuer
den des anderen haelt - er ist dann kein Punkt, sondern ein Wunsch. Und eine
Zahl, die aus einem anderen Dokument abgeschrieben ist, veraltet dort, wo
niemand hinsieht. Beides wird hier gehalten.

Was er **nicht** prueft: ob ein Punkt wirklich noch offen ist. Das ist eine
Aussage ueber die Welt - der Beleg daneben ist der Grund, warum sie sich
nachpruefen laesst.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOKUMENT = PROJECT_ROOT / "docs" / "intern" / "offene-punkte.md"
FR_STAND = PROJECT_ROOT / "docs" / "intern" / "fr-stand.md"

#: Wer einen Punkt tragen kann. Ein dritter Name hiesse, dass jemand
#: Verantwortung bekommt, der davon nichts weiss.
WER = frozenset({"Christian", "Artan", "beide"})

#: Die offenen Abschnitte und ihr Kennungsbuchstabe.
ABSCHNITTE = {"Entscheidungen": "E", "Auf dem Server": "S", "Im Code": "C"}


def felder(zeile: str) -> list[str]:
    """Wie Markdown trennt: an Pipes, die nicht maskiert sind."""
    return [f.strip() for f in re.split(r"(?<!\\)\|", zeile)][1:-1]


@pytest.fixture(scope="module")
def text() -> str:
    if not DOKUMENT.is_file():
        pytest.skip(f"{DOKUMENT} fehlt")
    return DOKUMENT.read_text(encoding="utf-8")


def abschnitt(text: str, titel: str) -> str:
    anfang = text.index(f"## {titel}")
    rest = text[anfang + 3:]
    naechster = re.search(r"^## ", rest, re.M)
    return rest[: naechster.start()] if naechster else rest


@pytest.fixture(scope="module")
def offen(text) -> list[tuple[str, list[str]]]:
    """(Abschnitt, Felder) je offener Zeile."""
    zeilen = []
    for titel in ABSCHNITTE:
        for z in abschnitt(text, titel).splitlines():
            f = felder(z) if z.startswith("|") else []
            if len(f) == 5 and re.fullmatch(r"[A-Z]-\d+", f[0]):
                zeilen.append((titel, f))
    return zeilen


def test_es_gibt_offene_punkte(offen):
    """Sonst prueft alles darunter nichts und bleibt gruen."""
    assert len(offen) >= 5, f"nur {len(offen)} offene Zeilen gelesen"


def test_jeder_punkt_hat_einen_verantwortlichen(offen):
    """Der Kern. Ein Punkt ohne Verantwortlichen ist ein Wunsch."""
    fehler = [f"{f[0]}: Wer = {f[2]!r}" for _, f in offen if f[2] not in WER]
    assert not fehler, (
        f"erlaubt sind {sorted(WER)}:\n  " + "\n  ".join(fehler))


def test_jeder_punkt_hat_ein_datum_und_einen_beleg(offen):
    """Ohne Datum weiss niemand, wie lange es schon liegt.

    Und ohne Beleg ist "offen" eine Meinung: Wer nachsehen will, ob der
    Punkt noch gilt, braucht eine Stelle, an der er nachsehen kann.
    """
    fehler = []
    for _, f in offen:
        if not re.fullmatch(r"\d{1,2}\.\d{1,2}\.\d{4}", f[3]):
            fehler.append(f"{f[0]}: seit = {f[3]!r}")
        if len(f[4]) < 8:
            fehler.append(f"{f[0]}: kein Beleg")
    assert not fehler, "\n".join(fehler)


def test_die_kennung_passt_zum_abschnitt_und_ist_eindeutig(offen):
    """Eine Kennung wird zitiert - in Commits, in Gespraechen.

    Stuende dieselbe zweimal da, zeigte ein Zitat auf zwei Punkte.
    """
    kennungen = [f[0] for _, f in offen]
    doppelt = sorted({k for k in kennungen if kennungen.count(k) > 1})
    assert not doppelt, f"doppelt vergeben: {doppelt}"
    falsch = [f"{f[0]} steht unter '{t}'" for t, f in offen
              if not f[0].startswith(ABSCHNITTE[t] + "-")]
    assert not falsch, "\n".join(falsch)


def test_die_anforderungszahlen_stimmen_mit_fr_stand_ueberein(text):
    """Abgeschrieben heisst: veraltet dort, wo niemand hinsieht.

    Das Dokument nennt den Stand der Anforderungen, weil er die Frage
    "was ist offen?" vervollstaendigt. Die Zahlen gehoeren aber
    ``fr-stand.md``; steht hier eine andere, ist dieses Dokument das, das
    falsch ist - und dass zwei Dokumente dieselbe Aussage fuehren, ohne
    dass ein Waechter beide erfasst, hat am 11.10.2026 acht Aussagen auf
    einmal veralten lassen.
    """
    if not FR_STAND.is_file():
        pytest.skip("fr-stand.md fehlt")
    stand = FR_STAND.read_text(encoding="utf-8")
    zaehlung = {}
    for name in ("erfüllt", "teilweise", "offen", "zurückgestellt"):
        m = re.search(rf"\|\s*\S+ {name}\s*\|\s*(\d+)\s*\|", stand)
        assert m, f"fr-stand.md nennt keine Summe fuer '{name}'"
        zaehlung[name] = int(m.group(1))

    m = re.search(r"(\d+) erfüllt, (\d+) teilweise,\s*\**(\d+) offen\**, (\d+)\s*zurückgestellt",
                  text)
    assert m, "das Dokument nennt den Stand der Anforderungen nicht"
    genannt = dict(zip(("erfüllt", "teilweise", "offen", "zurückgestellt"),
                       map(int, m.groups())))
    assert genannt == zaehlung, (
        f"offene-punkte.md nennt {genannt}, fr-stand.md zaehlt {zaehlung}")


def test_erledigtes_traegt_ein_datum_oder_einen_verweis(text):
    """Erledigt ohne Wann ist so gut wie geloescht."""
    fehler = []
    for z in abschnitt(text, "Erledigt").splitlines():
        f = felder(z) if z.startswith("|") else []
        if len(f) != 4 or f[0] in ("aus", "---") or set(f[0]) <= {"-"}:
            continue
        if not (re.search(r"\d{1,2}\.\d{1,2}\.\d{4}", f[2]) or "dort" in f[2]
                or "fr-stand" in f[2]):
            fehler.append(f"{f[0]}: erledigt = {f[2]!r}")
    assert not fehler, "\n".join(fehler)
