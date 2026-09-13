"""Was von Raw und Bronze bleiben muss - und was weg darf.

    python -m orchestration.aufraeumen             # zeigen, nichts loeschen
    python -m orchestration.aufraeumen --loeschen  # entbehrliche Laeufe loeschen

Raw und Bronze wachsen mit jedem Lauf, und bis hierher sagte nichts, wann
etwas weg darf. Die Regel, je Quelle (``city=chicago``, ``dataset=noaa_ghcnd``,
...), juengster Lauf zuerst:

1. **Der juengste Lauf und der davor** bleiben. Der zweite ist der vorherige
   Schnappschuss - die einzige Moeglichkeit, eine Quelle gegen sich selbst zu
   pruefen. Detroit aendert abgeschlossene Faelle nachtraeglich (Notebook 13,
   Schritt 3), und das sieht man nur mit zwei Staenden.
2. **Von Silver genannt** bleibt. Jedes Silver-Manifest nennt unter
   ``derived_from`` die Laeufe, auf denen es ruht. Sie zu loeschen hiesse, den
   Stand nicht mehr erklaeren zu koennen.
3. **Die Basis eines Delta-Laufs** bleibt. Chicago laedt seit dem ersten vollen
   Schnappschuss nur Aenderungen (``mode: delta``); ohne den Schnappschuss
   darunter sind die Deltas wertlos. Ein Delta, das bleibt, haelt alles bis zum
   naechsten vollen Lauf fest.
4. Alles andere ist **entbehrlich**. Gezeigt wird es immer; geloescht nur mit
   ``--loeschen``, und dann Raw und Bronze zusammen - ein Bronze ohne sein Raw
   waere ein Ergebnis ohne Beweisstueck, ein Raw ohne Bronze ein Beweis ohne
   Ergebnis.

Ein Lauf gilt als Einheit: Ein ACS-Lauf liegt in zwei Verzeichnissen
(``state=17`` und ``state=26``), ein NOAA-Lauf in zwei Stationen. Sie kommen
und gehen zusammen.

Was die Regel bewusst nicht tut: von allein laufen. ``data/`` ist nicht
versioniert, die Regel gilt je Rechner, und Loeschen ist ein Handgriff, den
man sieht. In GitHub Actions laeuft jeder Datenlauf auf einer frischen
Maschine und braucht sie nicht.
"""

from __future__ import annotations

import argparse
import logging
import shutil
from pathlib import Path
from typing import Any, NamedTuple

from manifeste import fertige_laeufe, tabellen
from storage import for_root


LOG = logging.getLogger("aufraeumen")

SCHNAPPSCHUESSE = 2   # der juengste Lauf und der davor
DELTA_MODI = frozenset({"delta", "incremental"})

JUENGSTER = "juengster Lauf"
VORHERIGER = "vorheriger Schnappschuss"
GENANNT = "von Silver genannt"
BASIS = "Basis eines Delta-Laufs"


class Bestand(NamedTuple):
    """Ein Bronze-Lauf mit seinem Raw-Gegenstueck, ueber alle Partitionen."""

    quelle: str
    run_id: str
    abgeschlossen: str
    delta: bool
    bronze: tuple[Path, ...]
    raw: tuple[Path, ...]
    zeilen: int

    @property
    def ohne_raw(self) -> bool:
        return not self.raw

    @property
    def bytes(self) -> int:
        return sum(
            f.stat().st_size
            for verzeichnis in self.bronze + self.raw
            for f in verzeichnis.rglob("*") if f.is_file()
        )


class Entscheid(NamedTuple):
    bestand: Bestand
    grund: str | None   # None heisst: entbehrlich

    @property
    def bleibt(self) -> bool:
        return self.grund is not None


def ist_delta(manifest: dict[str, Any]) -> bool:
    # Chicago: mode = full_snapshot | delta. Detroit: extraction_mode = FULL | INCREMENTAL.
    modus = str(manifest.get("mode") or manifest.get("extraction_mode") or "")
    return modus.lower() in DELTA_MODI


def bestaende(data_root: Path) -> dict[str, list[Bestand]]:
    """Alle fertigen Bronze-Laeufe, je Quelle, juengster zuerst.

    Die Quelle ist der erste Pfadteil unter ``bronze/`` - dieselbe Einteilung
    wie im Gesamtmanifest von ``run_all``. Das Raw-Gegenstueck ist das
    Verzeichnis mit demselben relativen Pfad unter ``raw/``; fehlt es, ist der
    Lauf ``ohne_raw``.
    """
    bronze = data_root / "bronze"
    raw = data_root / "raw"
    gruppen: dict[tuple[str, str], dict[str, Any]] = {}
    for lauf in fertige_laeufe(bronze, streng=False):
        relativ = lauf.verzeichnis.relative_to(bronze)
        eintrag = gruppen.setdefault((relativ.parts[0], lauf.run_id), {
            "abgeschlossen": "", "delta": ist_delta(lauf.manifest),
            "bronze": [], "raw": [], "zeilen": 0,
        })
        eintrag["abgeschlossen"] = max(eintrag["abgeschlossen"], lauf.abgeschlossen_um)
        eintrag["bronze"].append(lauf.verzeichnis)
        if (raw / relativ).is_dir():
            eintrag["raw"].append(raw / relativ)
        eintrag["zeilen"] += lauf.zeilen

    je_quelle: dict[str, list[Bestand]] = {}
    for (quelle, run_id), e in gruppen.items():
        je_quelle.setdefault(quelle, []).append(Bestand(
            quelle, run_id, e["abgeschlossen"], e["delta"],
            tuple(e["bronze"]), tuple(e["raw"]), e["zeilen"],
        ))
    for laeufe in je_quelle.values():
        laeufe.sort(key=lambda b: (b.abgeschlossen, b.run_id), reverse=True)
    return dict(sorted(je_quelle.items()))


def genannt_in_silver(data_root: Path) -> set[str]:
    """Jede Kennung, die ein Silver-Manifest unter ``derived_from`` nennt.

    Die Form ist je Tabelle anders - ``crime_offense`` fuehrt Listen je Stadt,
    die uebrigen eine Liste von Eintraegen mit ``run_id``. Gesammelt wird
    deshalb jede Zeichenkette darin; verglichen wird gegen Kennung und
    Verzeichnisnamen des Laufs, weil Chicago ``run_<Zeit>`` schreibt und
    Detroit die nackte UUID.
    """
    kennungen: set[str] = set()

    def sammle(wert: Any) -> None:
        if isinstance(wert, str):
            kennungen.add(wert)
        elif isinstance(wert, dict):
            for v in wert.values():
                sammle(v)
        elif isinstance(wert, list):
            for v in wert:
                sammle(v)

    for tabelle in tabellen(data_root, ("silver",)):
        sammle(tabelle.manifest.get("derived_from"))
    return kennungen


def entscheide(laeufe: list[Bestand], genannt: set[str]) -> list[Entscheid]:
    """Die Regel, angewandt auf eine Quelle. ``laeufe`` juengster zuerst."""
    gruende: list[str | None] = []
    for i, b in enumerate(laeufe):
        if i == 0:
            gruende.append(JUENGSTER)
        elif i < SCHNAPPSCHUESSE:
            gruende.append(VORHERIGER)
        elif b.run_id in genannt or any(v.name in genannt for v in b.bronze):
            gruende.append(GENANNT)
        else:
            gruende.append(None)

    # Ein Delta, das bleibt, braucht alles Aeltere bis zum naechsten vollen
    # Lauf. Ein Delta, das geht, braucht nichts mehr.
    braucht_basis = False
    for i, b in enumerate(laeufe):
        if gruende[i] is None and braucht_basis:
            gruende[i] = BASIS
        if gruende[i] is not None:
            braucht_basis = b.delta
    return [Entscheid(b, g) for b, g in zip(laeufe, gruende)]


def bericht(data_root: Path) -> list[Entscheid]:
    genannt = genannt_in_silver(data_root)
    alle: list[Entscheid] = []
    for laeufe in bestaende(data_root).values():
        alle.extend(entscheide(laeufe, genannt))
    return alle


def zeige(entscheide: list[Entscheid]) -> None:
    quelle = None
    for e in entscheide:
        b = e.bestand
        if b.quelle != quelle:
            quelle = b.quelle
            print(f"\n{quelle}")
        vermerk = e.grund or "ENTBEHRLICH"
        if b.ohne_raw:
            vermerk += " · ohne Raw"
        if b.delta:
            vermerk += " · Delta"
        print(f"  {b.run_id[:28]:<29} {b.abgeschlossen[:16]:<17} "
              f"{b.zeilen:>9,} Zeilen {b.bytes / 1e6:>7.1f} MB  {vermerk}")
    entbehrlich = [e for e in entscheide if not e.bleibt]
    print(f"\n{len(entscheide)} Laeufe, {len(entbehrlich)} entbehrlich, "
          f"{sum(e.bestand.bytes for e in entbehrlich) / 1e6:.1f} MB frei.")


def loesche(entscheide: list[Entscheid], data_root: Path) -> list[Path]:
    """Loescht, was entbehrlich ist - Raw und Bronze zusammen.

    Leer gewordene Partitionsverzeichnisse (``ingest_date=...``) gehen mit;
    die Schichtwurzeln ``raw/`` und ``bronze/`` bleiben.
    """
    geloescht: list[Path] = []
    for e in entscheide:
        if e.bleibt:
            continue
        for verzeichnis in e.bestand.bronze + e.bestand.raw:
            shutil.rmtree(verzeichnis)
            geloescht.append(verzeichnis)
            LOG.info("geloescht: %s", verzeichnis)
            schicht = data_root / verzeichnis.relative_to(data_root).parts[0]
            eltern = verzeichnis.parent
            while eltern != schicht and eltern.is_dir() and not any(eltern.iterdir()):
                eltern.rmdir()
                eltern = eltern.parent
    return geloescht


def arguments() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Zeigt, welche Raw- und Bronze-Laeufe bleiben muessen und "
                    "welche entbehrlich sind. Loescht nur auf Wunsch."
    )
    p.add_argument("--data-root", type=Path, default=None,
                   help="lokale Wurzel (Vorgabe: LOCAL_DATA_ROOT oder data). Aufgeraeumt wird nur lokal")
    p.add_argument("--loeschen", action="store_true",
                   help="entbehrliche Laeufe wirklich loeschen, Raw und Bronze zusammen")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def main() -> int:
    args = arguments()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    data_root = for_root(args.data_root).local_root
    alle = bericht(data_root)
    zeige(alle)
    entbehrlich = [e for e in alle if not e.bleibt]
    if not entbehrlich:
        return 0
    if not args.loeschen:
        print("Nichts geloescht. Mit --loeschen gehen die entbehrlichen Laeufe weg.")
        return 0
    frei = sum(e.bestand.bytes for e in entbehrlich)
    geloescht = loesche(alle, data_root)
    print(f"{len(geloescht)} Verzeichnisse geloescht, {frei / 1e6:.1f} MB frei.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
