"""Die Kriminalitaetsquellen je Stadt, beschrieben in ``config/quellen.toml``.

Neben ``storage.config`` (wo die Daten liegen) steht hier, woher sie kommen.

Die Ingestion war bis November 2026 auf ihre Stadt geschrieben: Adresse,
Datensatz, Schluessel- und Zeitfelder standen als Konstanten im Code. Jetzt
stehen sie je Stadt in einer Datei, und der Adapter einer Plattform liest sie
von hier - Socrata in ``chicago_pipeline.download_chicago``, ArcGIS in
``detroit_pipeline.detroit_arcgis``. Eine weitere
Stadt auf derselben Plattform ist damit ein Eintrag in der Datei, kein neues
Modul; was ausserhalb der Ingestion noch dazugehoert, steht in
``docs/intern/dritte-stadt.md``.

Gelesen wird streng: ein unbekannter Schluessel bricht ebenso ab wie ein
fehlender. Ein Tippfehler in ``aenderungs_feld`` soll keinen Lauf ergeben, der
still jedes Mal den ganzen Jahrgang laedt.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

#: Der Name der Datei unter dem Konfigurationsverzeichnis.
QUELLDATEI = "quellen.toml"



def standard_config() -> Path:
    """``config/`` des Projekts, unabhaengig vom Arbeitsverzeichnis.

    Im Abbild liegt es unter ``/app/config``, das Paket unter
    ``/app/src/crime/storage`` (editierbar installiert) - die Eltern stimmen
    dort wie im Klon. Eine Funktion statt einer Konstante, damit die
    Code-Referenz keinen Rechnerpfad abdruckt.
    """
    return Path(__file__).resolve().parents[3] / "config"


class QuellenFehler(ValueError):
    """Die Quellbeschreibung fehlt, ist unvollstaendig oder widerspruechlich."""


@dataclass(frozen=True)
class SocrataQuelle:
    """Ein Datensatz auf einem Socrata-Portal (SODA-API).

    Der Adapter verlangt ein ganzzahliges ``id_feld``: darueber laufen die
    Keyset-Pagination und der Snapshot, der die Vollstaendigkeit belegt. Die
    beiden Zeitfelder muessen Socratas schwebende Zeitstempel fester Breite
    sein, weil das Wasserzeichen als Text verglichen wird.
    """

    name: str
    stadt: str
    anzeigename: str
    domain: str
    datensatz: str
    id_feld: str
    tatzeit_feld: str
    aenderungs_feld: str
    felder: tuple[str, ...]
    boolesche_felder: tuple[str, ...] = ()
    ortsfeld: str | None = None
    ortsunterfelder: tuple[str, ...] = ()

    plattform = "socrata"

    @property
    def api_url(self) -> str:
        return f"https://{self.domain}/resource/{self.datensatz}.json"

    @property
    def metadaten_url(self) -> str:
        return f"https://{self.domain}/api/views/{self.datensatz}.json"

    def pruefe(self) -> None:
        """Haelt die Felder gegeneinander; wirft ``QuellenFehler``."""
        if len(set(self.felder)) != len(self.felder):
            raise QuellenFehler(f"{self.name}: felder enthaelt Dubletten")
        noetig = [self.id_feld, self.tatzeit_feld, self.aenderungs_feld,
                  *self.boolesche_felder]
        if self.ortsfeld is not None:
            noetig.append(self.ortsfeld)
            if not self.ortsunterfelder:
                raise QuellenFehler(f"{self.name}: ortsfeld ohne ortsunterfelder")
        elif self.ortsunterfelder:
            raise QuellenFehler(f"{self.name}: ortsunterfelder ohne ortsfeld")
        fehlend = [feld for feld in noetig if feld not in self.felder]
        if fehlend:
            raise QuellenFehler(
                f"{self.name}: nicht in felder: {', '.join(fehlend)}")
        if self.ortsfeld in self.boolesche_felder:
            raise QuellenFehler(f"{self.name}: ortsfeld ist auch boolesch")


@dataclass(frozen=True)
class ArcGISQuelle:
    """Ein Feature Layer auf einem ArcGIS-Server (REST, ``FeatureServer``).

    Das Schema wird hier nicht gepinnt: Der Adapter friert es vor dem ersten
    Batch aus den Layer-Metadaten ein und haelt jedes Feature zusaetzlich
    verlustfrei als JSON. ``zeitzone`` ist die Ortszeit, in der ein Jahrgang
    und ein Tagesfenster geschnitten werden; abgefragt wird in UTC.
    """

    name: str
    stadt: str
    anzeigename: str
    layer_url: str
    datensatz: str
    quellsystem: str
    zeitzone: str
    tatzeit_feld: str
    aenderungs_feld: str
    kategorie_feld: str
    erstes_jahr: int

    plattform = "arcgis"

    def pruefe(self) -> None:
        """Wirft ``QuellenFehler`` bei einer unbrauchbaren Beschreibung."""
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError  # noqa: PLC0415
        try:
            ZoneInfo(self.zeitzone)
        except (ZoneInfoNotFoundError, ValueError) as fehler:
            raise QuellenFehler(
                f"{self.name}: unbekannte Zeitzone {self.zeitzone!r}") from fehler
        if not self.layer_url.startswith("https://"):
            raise QuellenFehler(f"{self.name}: layer_url muss https sein")
        if self.tatzeit_feld == self.aenderungs_feld:
            raise QuellenFehler(f"{self.name}: Tatzeit- und Aenderungsfeld gleich")


#: Die bekannten Plattformen und ihre Beschreibung. Eine Plattform ohne
#: Eintrag hier hat keinen Adapter; ``lade`` lehnt sie ab, statt zu raten.
PLATTFORMEN: dict[str, type] = {"socrata": SocrataQuelle, "arcgis": ArcGISQuelle}


def _passt(wert: Any, typ: str) -> bool:
    """Haelt einen TOML-Wert gegen die Annotation des Feldes."""
    if typ == "int":
        return type(wert) is int
    if typ == "tuple[str, ...]":
        return isinstance(wert, list) and all(isinstance(x, str) and x for x in wert)
    return isinstance(wert, str) and bool(wert)          # str und str | None


def _pfad(config_root: Path | None) -> Path:
    return (config_root or standard_config()) / QUELLDATEI


def _baue(name: str, eintrag: dict[str, Any]) -> Any:
    eintrag = dict(eintrag)
    plattform = eintrag.pop("plattform", None)
    klasse = PLATTFORMEN.get(plattform)
    if klasse is None:
        raise QuellenFehler(
            f"{name}: unbekannte Plattform {plattform!r}; "
            f"bekannt sind {', '.join(sorted(PLATTFORMEN))}")
    erlaubt = {f for f in klasse.__dataclass_fields__ if f != "name"}
    unbekannt = sorted(set(eintrag) - erlaubt)
    if unbekannt:
        raise QuellenFehler(f"{name}: unbekannte Schluessel {', '.join(unbekannt)}")
    typen = {f.name: f.type for f in fields(klasse)}
    for feld, wert in eintrag.items():
        if not _passt(wert, typen[feld]):
            art = {"int": "eine ganze Zahl", "tuple[str, ...]": "eine Liste von Text"}
            raise QuellenFehler(f"{name}: {feld} muss {art.get(typen[feld], 'Text')} sein")
    werte = {k: tuple(v) if isinstance(v, list) else v for k, v in eintrag.items()}
    try:
        quelle = klasse(name=name, **werte)
    except TypeError as fehler:
        raise QuellenFehler(f"{name}: {fehler}") from fehler
    quelle.pruefe()
    return quelle


def alle(config_root: Path | None = None) -> dict[str, Any]:
    """Alle beschriebenen Quellen, nach Name; wirft ``QuellenFehler``."""
    pfad = _pfad(config_root)
    try:
        daten = tomllib.loads(pfad.read_text(encoding="utf-8"))
    except FileNotFoundError as fehler:
        raise QuellenFehler(f"Quellbeschreibung fehlt: {pfad}") from fehler
    except tomllib.TOMLDecodeError as fehler:
        raise QuellenFehler(f"{pfad}: {fehler}") from fehler
    quellen = {name: _baue(name, eintrag) for name, eintrag in daten.items()}
    staedte = [q.stadt for q in quellen.values()]
    if len(set(staedte)) != len(staedte):
        raise QuellenFehler(f"{pfad}: zwei Eintraege fuer dieselbe Stadt")
    return quellen


def lade(name: str, config_root: Path | None = None) -> Any:
    """Die Quelle ``name``; wirft ``QuellenFehler``, wenn es sie nicht gibt."""
    quellen = alle(config_root)
    if name not in quellen:
        raise QuellenFehler(
            f"Keine Quelle {name!r} in {_pfad(config_root)}; "
            f"beschrieben sind {', '.join(sorted(quellen))}")
    return quellen[name]
