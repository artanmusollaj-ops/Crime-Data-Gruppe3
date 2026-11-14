"""Belegende Notebooks 34/37: fachliche Voraussetzungen und Analysesitzung."""
from __future__ import annotations

import json
from pathlib import Path

from storage.analysesitzung import AnalyseFehler, datensperre, _inventory


def benoetigte_dateien(notebook):
    """Die Parquet-Dateien, ohne die das Notebook nicht startet."""
    if notebook == "34":
        from gold_pipeline import TABELLEN as GOLD

        required = [f"gold/dataset={name}/part-0001.parquet" for name in GOLD]
        return required + ["silver/dataset=crime_offense/part-0001.parquet",
                           "silver/dataset=tract/vintage=2024/part-0001.parquet",
                           "silver/dataset=place/vintage=2024/part-0001.parquet"]
    if notebook == "37":
        return ["silver/dataset=source_change/part-0001.parquet"]
    raise AnalyseFehler("Unterstuetzt werden Notebook 34 und 37")


def hole_fehlende_analysetabellen(ablage):
    """Holt jede Tabelle der Notebooks 34 und 37, die lokal fehlt, aus dem Eimer.

    Nur fuer ``STORAGE_ANALYSEBESTAND_LOKAL``: ``run_all`` ruft es vor dem
    Bestaetigen auf. Ueberspringt ein Lauf eine Stufe, weil nichts neu ist,
    entsteht keine lokale Kopie. Am 14.11.2026 fehlte so auf srv01
    ``silver/source_change`` ("0 Paare neu"), und Notebook 37 startete nicht.
    Geholt wird der ganze Tabellenordner, Parquet und Manifest, erst in einen
    ``.part``-Ordner und dann in einem Zug an den festen Pfad.
    """
    import shutil

    tabellen = sorted({d.rsplit("/", 1)[0] for nb in ("34", "37")
                       for d in benoetigte_dateien(nb)})
    geholt = []
    for verzeichnis in tabellen:
        ziel = ablage.local_root / verzeichnis
        # lokal mit Absicht: gefragt ist genau die lokale Analysekopie, nicht
        # die Ablage - oben liegt die Tabelle ja.
        if (ziel / "part-0001.parquet").is_file():
            continue
        objekte = ablage.client.list(verzeichnis + "/")
        if not objekte:
            continue
        arbeit = ziel.parent / f".{ziel.name}.analyse.part"
        shutil.rmtree(arbeit, ignore_errors=True)
        try:
            for objekt in objekte:
                datei = arbeit / objekt.key[len(verzeichnis) + 1:]
                datei.parent.mkdir(parents=True, exist_ok=True)
                ablage.client.download(objekt.key, datei)
            shutil.rmtree(ziel, ignore_errors=True)
            arbeit.rename(ziel)
        finally:
            shutil.rmtree(arbeit, ignore_errors=True)
        geholt.append(verzeichnis)
    return geholt


def _pruefe(root, notebook):
    try:
        value = json.loads((root / ".analyse" / "stand.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AnalyseFehler("Kein bestaetigter Aufbau. Pipeline erfolgreich abschliessen; "
                            "im verwalteten Betrieb den Job-Datenordner waehlen.") from exc
    if value.get("version") != 1 or not value.get("run_id"):
        raise AnalyseFehler("Ungueltiger Herkunftsnachweis")
    files = value.get("files", {})
    needed = {"silver", "gold"} if notebook == "34" else {"silver"}
    if not needed.issubset(value.get("bereiche", [])):
        raise AnalyseFehler("Dieser Lauf hat die benoetigten Schichten nicht vollstaendig aufgebaut")
    required = benoetigte_dateien(notebook)
    if notebook == "37" and not any(
            p.startswith("bronze/") and p.endswith("/manifest.json") for p in files):
        raise AnalyseFehler("Notebook 37: Bronze-Manifeste fehlen im bestaetigten Stand")
    missing = [p for p in required if p not in files]
    if missing:
        raise AnalyseFehler("Benoetigte Daten fehlen im Nachweis: " + ", ".join(missing))
    if _inventory(root) != files:
        raise AnalyseFehler("Daten wurden seit dem bestaetigten Aufbau veraendert. Neu aufbauen.")
    return value


class Analysesitzung:
    """Explizit beenden; ein offener Jupyter-Kernel haelt die Sperre weiter.

    Nach beenden() muessen vor weiteren Abfragen die Startzellen erneut laufen.
    Bei einer fehlgeschlagenen Zelle kann beenden() weiterhin aufgerufen werden.
    """

    _laufend = None

    def __init__(self, data_root, notebook):
        if Analysesitzung._laufend is not None:
            raise AnalyseFehler("Im Kernel ist bereits eine Analysesitzung aktiv; zuerst beenden()")
        self.root = Path(data_root).resolve()
        self._gate = datensperre(self.root)
        self._connections = []
        self._gate.__enter__()
        self.aktiv = True
        self._storage_context = None
        try:
            self.herkunft = _pruefe(self.root, notebook)
            from storage import lokaler_analysebestand

            self._storage_context = lokaler_analysebestand(self.root)
            self._storage_context.__enter__()
            Analysesitzung._laufend = self
        except BaseException:
            self.beenden()
            raise

    def verbinde(self):
        from storage.duckdb import verbinde

        if not self.aktiv:
            raise AnalyseFehler("Analysesitzung beendet; Startzellen erneut ausfuehren")
        con = verbinde()
        self._connections.append(con)
        return con

    def anzeigen(self):
        print(f"Analysebestand: {self.root}")
        for name in ("run_id", "finished_at_utc", "code_commit", "release_id", "status"):
            print(f"{name}: {self.herkunft.get(name) or 'Zuordnung nicht nachgewiesen'}")
        if self.herkunft.get("code_dirty"):
            print("Code enthielt lokale Aenderungen; der Commit allein beschreibt ihn nicht.")
        elif self.herkunft.get("code_dirty") is None:
            print("Lokale Codeaenderungen waren beim Aufbau nicht pruefbar.")
        print("Datenzugriff gesperrt bis analyse.beenden() oder Kernel-Ende.")

    def beenden(self):
        if self.aktiv:
            try:
                for con in self._connections:
                    con.close()
            finally:
                try:
                    if self._storage_context is not None:
                        self._storage_context.__exit__(None, None, None)
                finally:
                    self._gate.__exit__(None, None, None)
                    self.aktiv = False
                    if Analysesitzung._laufend is self:
                        Analysesitzung._laufend = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.beenden()
