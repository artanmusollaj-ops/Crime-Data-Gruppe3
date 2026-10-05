#!/usr/bin/env python3
"""Erzeugt ``docs/intern/platzbedarf.md`` aus der gemessenen Belegung.

    python tools/build_platzbedarf.py
    python tools/build_platzbedarf.py --data-root data --ziel /tmp/p.md

**Warum erzeugt und nicht geschrieben.** Die Hochrechnung des Platzbedarfs
stand bis zum 4.10.2026 an zwei handgeschriebenen Stellen - und genau die
waren es, an denen sie schon einmal veraltet war: Das Addendum zum LN2-PRD
rechnete den 5,5-Faktor auf 580 MB und kam auf 3,2 GB, FR-52 rechnete mit
3,5 GB, und die Ausgangswerte (``raw 158 MB``, ``releases 202 MB``) stimmten zu
dem Zeitpunkt beide nicht mehr. Eine Zahl, die aus einer Messung folgt, gehoert
nicht in Prosa, sondern in einen Generator.

Dasselbe Muster wie ``tools/build_feldkatalog.py``: Gerechnet wird in
``orchestration.platzbedarf``, gesetzt wird hier, und ``docs/README.md`` fuehrt
die Datei unter "Erzeugt - nie von Hand ändern".

**Gemessen wird immer lokal.** Auch mit ``STORAGE_BACKEND=hybrid``, in dem die
Ablage den gemeinsamen Bestand auf SeaweedFS mitzaehlen wuerde. Das Dokument
soll sagen, was unter ``data/`` liegt, und nicht, wer es gebaut hat - sonst
waere es nicht reproduzierbar (``orchestration.platzbedarf.nur_lokal``).

**Kein Erzeugungszeitstempel.** Wie bei ``tools/build_einstieg.py``: Ein
``date.today()`` in der Datei hiesse, dass ein zweiter Lauf eine andere Datei
liefert, und der Waechter darauf koennte nie gruen sein. Das Messdatum ist
deshalb der **Stand der Daten** - die Kennung des jüngsten Release
beziehungsweise des jüngsten Laufs -, und das Datum der Zeilenzahlen steht in
``config/zeilen_je_jahrgang.csv``.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROJEKT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJEKT / "src" / "crime"))

from census_pipeline import NEWEST_VINTAGE  # noqa: E402
from orchestration import platzbedarf as pb  # noqa: E402
from storage import release  # noqa: E402

ZIEL = PROJEKT / "docs" / "intern" / "platzbedarf.md"
WERKZEUG = "tools/build_platzbedarf.py"


# ``orchestration.platzbedarf`` transliteriert Umlaute - das ist die Regel fuer
# den Python-Quelltext. In Markdown gilt sie nicht, und dieses Werkzeug schreibt
# Markdown. Die Rueckuebersetzung steht hier und nicht dort, damit beide
# Konventionen bleiben, wo sie gelten.
DEUTSCH = {
    "waechst": "wächst",
    "Staende": "Stände",
    "Groesse": "Grösse",
    " x ": " × ",
}


#: Dezimalpunkt zu Dezimalkomma. ``platzbedarf`` schreibt fuer das Terminal
#: ``42.9``, der Rest des Projekts schreibt ``42,9``.
DEZIMAL = re.compile(r"(?<=\d)\.(?=\d)")


def deutsch(text: str) -> str:
    for transliteriert, geschrieben in DEUTSCH.items():
        text = text.replace(transliteriert, geschrieben)
    return DEZIMAL.sub(",", text)


#: Kleine Zahlen stehen in den Dokumenten als Wort. Darueber als Ziffer.
ZAHLWORT = ("null", "ein", "zwei", "drei", "vier", "fünf", "sechs", "sieben",
            "acht", "neun", "zehn", "elf", "zwölf")


def zahlwort(n: int) -> str:
    return ZAHLWORT[n] if 0 <= n < len(ZAHLWORT) else str(n)


def bereich_von(jahre: tuple[int, ...]) -> str:
    """``2021–2026`` - oder ``2024``, wenn es nur eines ist.

    ``--jahre 2024`` schrieb sonst "2024–2024" durch das ganze Dokument.
    """
    return f"{jahre[0]}–{jahre[-1]}" if len(jahre) > 1 else str(jahre[0])


def mb(bytes_: int) -> str:
    return pb.megabyte(bytes_) + " MB"


def gb(bytes_: int) -> str:
    return f"{bytes_ / 1e9:.2f}".replace(".", ",") + " GB"


def stand(ablage) -> str:
    """Der Stand, auf dem die Messung ruht - abgeleitet, nicht datiert.

    Die Kennung des jüngsten Release ist ein UTC-Zeitstempel in einer Form,
    die lexikographisch sortiert; liegt noch kein Release, nennt die Funktion
    den jüngsten Lauf. Beides steht in den Daten und ist damit bei einem
    zweiten Lauf dasselbe.
    """
    kennungen = sorted(
        teile[1].removeprefix("release=")
        for rel in ablage.groessen_unter(release.RELEASES)
        if (teile := rel.split("/")) and len(teile) > 2 and teile[1].startswith("release=")
    )
    if kennungen:
        return f"Release `{kennungen[-1]}`"
    laeufe = sorted(lauf.relativ.rsplit("/", 1)[-1]
                    for schicht in ("bronze", "raw") for lauf in ablage.laeufe(schicht))
    return f"Lauf `{laeufe[-1]}`" if laeufe else "kein gebauter Stand"


def kopf(jahre: tuple[int, ...]) -> list[str]:
    bereich = bereich_von(jahre)
    return [
        "# Platzbedarf: gemessen und hochgerechnet",
        "",
        "**Erzeugt, nicht geschrieben** — die Zahlen hier kommen aus einer "
        "Messung über `storage` und einer Rechnung je Quelle, nicht aus einem",
        f"Faktor. Geschrieben von [`{WERKZEUG}`](../../{WERKZEUG}), gerechnet "
        "in [`orchestration.platzbedarf`](../../src/crime/orchestration/platzbedarf.py).",
        "",
        "```bash",
        "python tools/build_platzbedarf.py",
        "```",
        "",
        f"Die Frage dahinter ist FR-40: Was kostet der Mehrjahreslauf {bereich}? "
        "Und daran hängt FR-52 — ob die Datenabgabe in Moodles 1-GB-Grenze",
        "passt. Bis zum 4.10.2026 war die Antwort **ein Faktor**: 1'874'417 "
        "Zeilen gegen 348'341 sind das 5,38-Fache, aufgerundet 5,5, angewandt",
        "auf ganz `data/`. Daran war dreierlei falsch — ein Zeilenverhältnis "
        "ist kein Byteverhältnis, nicht alles wächst mit den Jahren, und die",
        "Basis war der angehäufte Bestand statt eines Jahrgangs. Aus dem einen "
        "Faktor sind vier Regeln geworden.",
        "",
    ]


def schichtentabelle(schichten: tuple[pb.Schicht, ...], stand_: str) -> list[str]:
    ganz = pb.summe(schichten)
    zeilen = [
        "## 1 Gemessen: die Belegung je Schicht",
        "",
        f"Stand der Daten: {stand_}. Gemessen über "
        "`storage.Storage.bytes_unter` — `.part`-Verzeichnisse zählen nicht,",
        "und im Hybridmodus wird eine Datei, die lokal und auf SeaweedFS "
        "liegt, einmal gezählt. Dieses Dokument misst **nur lokal**.",
        "",
        "**Dieselbe Tabelle steht in `docs/architektur-ist-und-ziel.md` (A.1) "
        "und als SVG-Text in `docs/architektur-einseiter.html`.**",
        "`tests/test_platzbedarf_dokumente.py` hält beide gegen diese Messung; "
        "eine Stelle allein nachzuziehen genügt nicht.",
        "",
        "| Schicht | Grösse | Dateien |",
        "| --- | ---: | ---: |",
    ]
    for s in schichten:
        zeilen.append(f"| **{s.name}** | {mb(s.bytes)} | {s.dateien} |")
    zeilen += [
        f"| zusammen | **{mb(ganz.bytes)}** | {ganz.dateien} |",
        "",
    ]
    return zeilen


def und(namen: list[str]) -> str:
    """``['raw', 'bronze']`` → "`raw` und `bronze`", mit Komma ab drei.

    Steht hier und nicht bei ``zahlwort``, weil nur dieses Dokument Schichten
    in einem Satz aufzaehlt.
    """
    teile = [f"`{n}`" for n in namen]
    if not teile:
        return "keine Schicht"
    if len(teile) == 1:
        return teile[0]
    return ", ".join(teile[:-1]) + " und " + teile[-1]


def regeltabelle(gerechnet: tuple[pb.Hochgerechnet, ...], jahre: tuple[int, ...],
                 zeilen_: pb.Zeilen) -> list[str]:
    bereich = bereich_von(jahre)
    # Das Beispiel kommt aus der Messung: die Quelle mit den meisten Laeufen.
    # Ausgeschrieben waere es eine Zahl, die beim naechsten Lauf veraltet -
    # genau die Sorte, die dieses Dokument ersetzt.
    reichste = max((h.basis for h in gerechnet), key=lambda b: b.laeufe)
    # Welcher Stand die Basis der Releases-Regel ist, muss dastehen: Es ist der
    # groesste, nicht der juengste, und die Staende unterscheiden sich.
    release_basis = [h.basis for h in gerechnet
                     if h.basis.schicht == release.RELEASES and h.basis.staende > 1]
    staende = max((b.laeufe for b in release_basis), default=0)
    stand_bytes = sum(b.bytes for b in release_basis)
    # Was ein Lauf traegt, ist je Schicht verschieden - und der Satz dazu wird
    # gemessen, nicht geschrieben. Bis zum 4.10.2026 stand hier "Basis ist der
    # Jahrgang 2024, den die gebauten Laeufe tragen". Fuer raw und bronze
    # stimmt das weiter: Dort liegt je Jahr ein eigener Lauf, und ein Lauf ist
    # eine Basis. Silver, Gold, Serving und Releases werden dagegen ersetzt und
    # tragen seit dem Mehrjahresbau alle sechs Jahrgaenge in denselben Dateien
    # - ``Basis.jahre`` sagt es, und ``_regel`` teilt sie wieder heraus.
    # Haette der Satz dagestanden, haette das erzeugte Dokument beim naechsten
    # Lauf etwas Falsches behauptet.
    # Eine Schicht gilt als mehrjaehrig, sobald **eine** ihrer Basen Jahre
    # traegt: Ein Release-Stand haelt neben den sechs Jahrgaengen auch
    # Markendateien (``release.json``, ``AKTUELL.json``), und die haengen an
    # keinem Jahr. Nach Basen statt nach Schichten gefragt, stuende
    # ``releases`` in beiden Listen - so stand es beim ersten Versuch da.
    mehrjahrig = sorted({h.basis.schicht for h in gerechnet if h.basis.jahre})
    einjahrig = sorted({h.basis.schicht for h in gerechnet} - set(mehrjahrig))
    basissatz = (
        f"Basis ist **ein** Jahrgang je Quelle. In {und(einjahrig)} liegt je "
        f"Jahr ein eigener Lauf, ein Lauf ist also schon eine Basis. In "
        f"{und(mehrjahrig)} stehen dagegen alle Jahrgänge in denselben "
        f"Dateien — {bereich} in einem Stand —, und dort teilt die Rechnung "
        f"die {zahlwort(len(jahre))} Jahrgänge wieder heraus."
        if mehrjahrig and einjahrig else
        f"Basis ist **ein** Jahrgang je Quelle; die gebauten Läufe tragen "
        f"{bereich}, und die Rechnung teilt die {zahlwort(len(jahre))} "
        f"Jahrgänge wieder heraus."
        if mehrjahrig else
        f"Basis ist der Jahrgang {pb.BASISJAHR}, den die gebauten Läufe "
        f"tragen.")
    zeilen = [
        f"## 2 Gerechnet: {zahlwort(len(pb.ERKLAERUNG))} Regeln für {bereich}",
        "",
        basissatz,
        "Basis **je Quelle und Vintage** ist dabei der *grösste* Lauf,",
        f"nicht die Summe ihrer Läufe: `{reichste.schicht}/{reichste.quelle}` "
        f"trägt heute {zahlwort(reichste.laeufe)} Läufe. Sie zu addieren",
        "hiesse, das Anhäufen mitzurechnen — dieselbe Falle wie „den Bestand "
        "aus Bronze lesen“, diesmal in der Basis.",
        "",
        "Die Zeilen je Stadt und Jahr sind gemessene Fremddaten und stehen mit "
        f"Datum und Adresse in `config/{pb.ZEILEN_DATEI}`",
        f"(gemessen am {zeilen_.gemessen_am}).",
        "",
        "| Regel | Wie sie rechnet | Basis je Jahrgang | " + bereich + " |",
        "| --- | --- | ---: | ---: |",
    ]
    for name, (jetzt, dann) in pb.je_regel(gerechnet).items():
        zeilen.append(f"| **{name}** | {deutsch(pb.ERKLAERUNG[name])} "
                      f"| {mb(jetzt)} | {mb(dann)} |")
    hoch = sum(h.bytes for h in gerechnet)
    jetzt_ganz = sum(h.basis.bytes for h in gerechnet)
    # Welche Jahre kein eigenes Vintage haben, sagt vintages_for - nicht eine
    # Jahreszahl im Satz. Mit --jahre 2021-2023 stand hier sonst "braucht 3,
    # nicht sechs: Für 2025 und 2026 ...", und keines der beiden Jahre war
    # ueberhaupt gefragt.
    vintages = pb.vintages_for(jahre)
    leihjahre = [j for j in jahre if j not in vintages]
    # Die Grenze ist das juengste veroeffentlichte Vintage, nicht das
    # grösste des gefragten Bereichs: Mit --jahre 2021-2023 stand hier sonst
    # "erst Jahre jenseits von 2023 borgen eines".
    geborgt = (
        f"Für {' und '.join(str(j) for j in leihjahre)} gibt es kein "
        f"ACS-5-Jahres-Vintage, sie borgen das von {NEWEST_VINTAGE}"
        if leihjahre else
        f"Jedes Jahr hier hat sein eigenes; erst Jahre nach "
        f"{NEWEST_VINTAGE} borgen eines")
    # "ein" steht vor einem Hauptwort, "eines" allein - zahlwort() liefert die
    # erste Form, hier braucht es die zweite.
    wieviele = "eines" if len(vintages) == 1 else zahlwort(len(vintages))
    vintagesatz = (
        f"{bereich} braucht {wieviele} davon, nicht {zahlwort(len(jahre))}:"
        if len(vintages) < len(jahre) else
        f"{bereich} braucht {wieviele} davon:")
    zeilen += [
        f"| zusammen | | {mb(jetzt_ganz)} | **{mb(hoch)}** ({gb(hoch)}) |",
        "",
        "Warum die Regeln verschieden rechnen:",
        "",
        "* **Taten** — Detroits Zeile kostet in Bronze rund dreimal so viel "
        "wie Chicagos. Ein Zeilenverhältnis über beide Städte hinweg",
        "  wäre deshalb falsch; gerechnet wird je Stadt mit ihren eigenen "
        "Bytes je Zeile.",
        "* **Census** — es wachsen nicht die Jahre, sondern die **Vintages**. "
        f"{vintagesatz}",
        f"  {geborgt} (`census_pipeline.vintage_for`).",
        "* **konstant** — GHCN-Daily liefert immer die ganze Reihe einer "
        "Station. Ein längerer Bereich kostet dort keine Byte mehr als ein",
        "  einzelner Jahrgang. Dasselbe gilt für Marken und Zeiger.",
        f"* **Releases** — `aufraeumen.RELEASES_N` = "
        f"{pb.RELEASES_N} Stände bleiben liegen. Ein Release ist dabei kein "
        "Fass mit einer Grösse, sondern eine",
        "  eingefrorene Kopie von Gold und Serving; sein **Inhalt** wird "
        "zuerst hochgerechnet und erst dann mit der Zahl der Stände genommen.",
        f"  Gemessen ist der **grösste** der {zahlwort(staende)} liegenden "
        f"Stände, {mb(stand_bytes)} — die Stände unterscheiden sich",
        "  untereinander um Zehntel-MB, und die grössere Zahl ist hier die "
        "ehrlichere.",
        "",
    ]
    return zeilen


def quellentabelle(gerechnet: tuple[pb.Hochgerechnet, ...],
                   jahre: tuple[int, ...]) -> list[str]:
    bereich = bereich_von(jahre)
    zeilen = [
        "## 3 Je Quelle: Basis, Regel, Ergebnis",
        "",
        "Eine Zeile je Quelle und Schicht. „Läufe“ sagt, aus wie vielen Läufen "
        "der Bestand dieser Quelle besteht — die Basis ist der grösste",
        "davon.",
    ]
    schicht = None
    for h in gerechnet:
        if h.basis.schicht != schicht:
            schicht = h.basis.schicht
            zeilen += [
                "",
                f"### `{schicht}`",
                "",
                f"| Quelle | Läufe | Basis je Jahrgang | Regel | {bereich} |",
                "| --- | ---: | ---: | --- | ---: |",
            ]
        zeilen.append(
            f"| `{h.basis.quelle}` | {h.basis.laeufe} | {mb(h.basis.bytes)} "
            f"| {h.basis.regel}: {deutsch(h.wie)} | {mb(h.bytes)} |"
        )
    return zeilen + [""]


def schluss(schichten: tuple[pb.Schicht, ...],
            gerechnet: tuple[pb.Hochgerechnet, ...],
            ein_jahrgang: tuple[pb.Hochgerechnet, ...],
            jahre: tuple[int, ...]) -> list[str]:
    bereich = bereich_von(jahre)
    hoch = sum(h.bytes for h in gerechnet)
    je = pb.je_schicht(gerechnet)
    ohne_releases = hoch - je.get(release.RELEASES, (0, 0))[1]
    ganz = pb.summe(schichten)
    # Die beiden Zahlen, die der Satz unten aus der Messung nimmt - nicht aus
    # einer Erinnerung: die Quelle mit den meisten Laeufen und die Zahl der
    # liegenden Release-Staende.
    reichste = max((h.basis for h in gerechnet), key=lambda b: b.laeufe)
    staende = max((h.basis.laeufe for h in gerechnet
                   if h.basis.schicht == release.RELEASES), default=0)
    # Verglichen wird mit **derselben Rechnung fuer einen Jahrgang**, nicht mit
    # dem heutigen data/. Das heutige data/ haeuft Laeufe und Releases an; es
    # gegen eine Hochrechnung fuer einen Lauf je Quelle zu halten waere genau
    # der Fehler, den dieses Dokument korrigiert.
    einer = sum(h.bytes for h in ein_jahrgang)
    faktor = f"{hoch / einer:.2f}".replace(".", ",")
    nur_abgeleitet = sum(
        h.bytes for h in gerechnet
        if h.basis.schicht not in (release.RELEASES, "raw")
    )
    # Die Aussage wird gerechnet, nicht behauptet. Ein erster Entwurf schrieb
    # "in jedem Fall ueberschritten" und nannte darunter 0,90 GB.
    if ohne_releases > 1_000_000_000:
        grenze = (f"Ohne `releases/` ebenfalls ({gb(ohne_releases)}), "
                  f"erst ohne `raw/` dazu wird es knapp "
                  f"({gb(nur_abgeleitet)}).")
    elif nur_abgeleitet > 1_000_000_000:
        grenze = (f"Ohne `releases/` liegt er mit {gb(ohne_releases)} knapp "
                  f"darunter - ohne jede Reserve.")
    else:
        grenze = (f"Ohne `releases/` liegt er mit {gb(ohne_releases)} knapp "
                  f"darunter, ohne `raw/` dazu mit {gb(nur_abgeleitet)} "
                  f"deutlich. Reserve ist das keine: "
                  f"Ein Jahrgang mehr hebt ihn wieder darüber.")
    return [
        "## 4 Was daraus folgt",
        "",
        f"* **{bereich} braucht {mb(hoch)} ({gb(hoch)})**. Dieselbe Rechnung "
        f"für **einen** Jahrgang ({pb.BASISJAHR}) ergibt {mb(einer)} — "
        f"{bereich} ist also",
        f"  das **{faktor}-Fache eines Jahrgangs** und nicht das 5,5-Fache. "
        "Verglichen wird dabei Rechnung mit Rechnung: Das heutige",
        f"  `data/` ({mb(ganz.bytes)}) hält {zahlwort(reichste.laeufe)} "
        f"`{reichste.quelle}`-Läufe und {zahlwort(staende)} Release-Stände und "
        "ist mit keiner",
        "  der beiden Zahlen vergleichbar — genau diese Verwechslung steckte "
        "im alten Faktor.",
        f"* **Ohne `releases/` sind es {mb(ohne_releases)}** "
        f"({gb(ohne_releases)}), ohne `releases/` **und** `raw/` noch "
        f"{mb(nur_abgeleitet)} ({gb(nur_abgeleitet)}).",
        "  Das sind die Zahlen, die für FR-52 zählen: Eine Abgabe braucht "
        f"nicht {zahlwort(pb.RELEASES_N)} Stände, und sie braucht die",
        "  Beweisstücke nicht mitzuschicken.",
        f"* **Moodles Grenze von 1 GB**: Der ganze Bestand liegt mit "
        f"{gb(hoch)} weit darüber. {grenze}",
        "  Entschieden ist das nicht hier, sondern in FR-52 — entweder eine "
        "Stichprobe mit Link auf den Vollbestand oder die Abgabe über den",
        "  Abgabebranch statt über Moodle.",
        "* **Gerechnet ist ein Lauf je Quelle und Jahrgang**, nicht ein "
        "`data/`, das wochenlang mitläuft. Was darüber hinaus anfällt, ist eine",
        "  Frage der Aufbewahrung und nicht der Hochrechnung: "
        "`python -m orchestration.aufraeumen` sagt, was weg darf.",
        "",
        "## 5 Nachmessen",
        "",
        "```bash",
        "python -m orchestration.platzbedarf --data-root data",
        "python -m orchestration.platzbedarf --jahre 2021-2026 --json",
        "```",
        "",
        "Nach jedem Neubau gehört `python tools/build_platzbedarf.py` dazu, "
        "sonst nennt `pytest -m referenzstand` die Stelle.",
    ]


def baue(data_root: Path | None = None, jahre: tuple[int, ...] = tuple(range(2021, 2027)),
         config_root: Path | None = None) -> str:
    ablage = pb.nur_lokal(data_root)
    zeilen_ = pb.zeilen_je_jahrgang(config_root or PROJEKT / "config")
    schichten = pb.belegung(ablage)
    basis = pb.basis_je_jahrgang(ablage)
    gerechnet = pb.hochrechnung(basis, jahre, zeilen_) if basis else ()

    teile = kopf(jahre) + schichtentabelle(schichten, stand(ablage))
    if not gerechnet:
        teile += [
            "## 2 Keine Hochrechnung",
            "",
            "Unter `data/` liegt nichts Gebautes — ohne eine gemessene Basis "
            "gibt es nichts hochzurechnen, und geschätzt wird hier nichts.",
            "Erst `python -m orchestration.run_all` laufen lassen, dann "
            "`python tools/build_platzbedarf.py`.",
        ]
    else:
        ein_jahrgang = pb.hochrechnung(basis, (pb.BASISJAHR,), zeilen_)
        teile += (regeltabelle(gerechnet, jahre, zeilen_)
                  + quellentabelle(gerechnet, jahre)
                  + schluss(schichten, gerechnet, ein_jahrgang, jahre))
    return "\n".join(teile).rstrip("\n") + "\n"


def main(argv: list[str] | None = None) -> int:
    zerleger = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # --data-root wie an jedem Stufenmodul; --ziel nach dem Muster von
    # tools/build_einstieg.py, damit der Waechter zweimal nach tmp bauen kann,
    # ohne die abgelegte Datei anzufassen.
    zerleger.add_argument("--data-root", type=Path, default=PROJEKT / "data")
    zerleger.add_argument("--config-root", type=Path, default=PROJEKT / "config")
    zerleger.add_argument("--jahre", default="2021-2026")
    zerleger.add_argument("--ziel", type=Path, default=ZIEL)
    args = zerleger.parse_args(argv)

    text = baue(args.data_root, pb.jahre_aus(args.jahre), args.config_root)
    args.ziel.parent.mkdir(parents=True, exist_ok=True)
    args.ziel.write_text(text, encoding="utf-8")
    try:
        name = args.ziel.relative_to(PROJEKT)
    except ValueError:
        name = args.ziel
    print(f"{name} geschrieben ({args.ziel.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
