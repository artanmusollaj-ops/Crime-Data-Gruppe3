"""Was von Raw, Bronze und den Releases bleiben muss - und was weg darf.

    python -m orchestration.aufraeumen              # zeigen, nichts loeschen
    python -m orchestration.aufraeumen --loeschen   # entbehrliche Laeufe und
                                                    # Releases loeschen, nur lokal
    python -m orchestration.aufraeumen --loeschen --auch-fern
                                                    # Laeufe und Releases auch
                                                    # auf SeaweedFS
    python -m orchestration.aufraeumen --pinnen LN1 # den heutigen Stand festhalten

Raw und Bronze wachsen mit jedem Lauf, und bis hierher sagte nichts, wann
etwas weg darf. Die Regel, je Quelle (``city=chicago``, ``dataset=noaa_ghcnd``,
...), juengster Lauf zuerst:

0. **Gepinnt bleibt.** Ein Lauf, auf den sich eine veroeffentlichte Zahl
   bezieht - eine Abgabe, eine Folie, ein Referenzstand -, steht in
   ``config/referenzstand.csv`` und wird nie aufgeraeumt. Diese Regel kam am
   14.9.2026 dazu, weil die drei folgenden der Historisierung im Weg stehen:
   Regel 2 haelt nur, was das **aktuelle** Silver nennt - nach einem Neubau
   werden die Laeufe des vorigen Stands entbehrlich, und eine Zahl von
   letzter Woche waere nicht mehr nachzubauen.
1. **Der juengste Lauf und der davor** bleiben. Der zweite ist der vorherige
   Schnappschuss - die einzige Moeglichkeit, eine Quelle gegen sich selbst zu
   pruefen. Detroit aendert abgeschlossene Faelle nachtraeglich (Notebook 13,
   Schritt 3), und das sieht man nur mit zwei Staenden.
2. **Von Silver genannt** bleibt. Jedes Silver-Manifest nennt unter
   ``derived_from`` die Laeufe, auf denen es ruht. Sie zu loeschen hiesse, den
   Stand nicht mehr erklaeren zu koennen.
4. **Dessen Unterschied noch nicht gezogen ist, bleibt.** Ein
   Vollschnappschuss traegt mehr als seinen Inhalt: Gegen seinen Vorgaenger
   gehalten sagt er, *was die Quelle geaendert hat*. Das zieht
   ``silver_pipeline.build_source_change`` heraus; bis dahin ist der Lauf
   unersetzlich. Danach genuegt die schmale Aenderungstabelle - 31,9 MB
   Schnappschuesse fuer 102 geaenderte Zeilen war das Verhaeltnis, das
   ``docs/intern/datenhistorie.md`` ausgerechnet hat. Diese Regel kam am
   1.10.2026 dazu, zusammen mit der Tabelle. Sie steht **zuletzt**, weil sie
   die einzige ist, die von allein vergeht: Ein Lauf, den sie haelt, wird
   durch einen Befehl frei.
3. **Die Basis eines Delta-Laufs** bleibt. Beide Staedte laden seit dem ersten
   vollen Schnappschuss nur Aenderungen - Chicago als ``mode: delta``, Detroit
   seit dem 18.9.2026 als ``extraction_mode: DELTA``; ohne den Schnappschuss
   darunter sind die Deltas wertlos. Ein Delta, das bleibt, haelt alles bis zum
   naechsten vollen Lauf fest.
5. Alles andere ist **entbehrlich**. Gezeigt wird es immer; geloescht nur mit
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

**Releases, seit dem 4.10.2026.** Daneben steht eine zweite Regel fuer
``releases/`` - *gepinnt plus die letzten acht*, wie
``docs/intern/datenhistorie.md`` 5.5 sie entschieden hat. Sie ist bewusst
schmaler als die Regel fuer Laeufe, denn ein Release traegt seine Herkunft
selbst und nichts im Projekt sucht das neueste: Alles geht ueber
``releases/AKTUELL.json``. Juengstes zuerst:

0. **Gepinnt bleibt** - dasselbe Register ``config/referenzstand.csv`` und
   dieselbe Lesefunktion wie bei Laeufen. Eine Release-Kennung steht dort in
   der Spalte ``run_id``; der Spaltenname wird dadurch unscharf, aber es gibt
   **ein** Register und nicht zwei.
1. **Das Release, auf das der Zeiger zeigt, bleibt** - auch wenn es aus der
   Reihe fiele. ClickHouse, Elasticsearch, Kibana, ``serving.pruefe_stand``
   und ``serving.build_einstieg`` loesen alle darueber auf; ein altes Release zu
   entfernen ist folgenlos, das aktuelle bricht fuenf Verbraucher auf einmal.
   Darum ist es eine eigene Regel und kein Nebeneffekt von "die letzten acht".
   Fehlt der Zeiger, sagt der Bericht das und laeuft weiter.
2. **Die letzten acht bleiben** (``RELEASES_N``) - zwei Monate woechentlicher
   Releases. Gezaehlt wird wie bei Laeufen ueber die Reihenfolge, ein
   gepinntes oder aktuelles Release belegt also einen der acht Plaetze.
3. Alles andere ist **entbehrlich**. Gezeigt wird es immer; geloescht
   **lokal** nur mit ``--loeschen`` und **auf SeaweedFS** erst mit
   ``--auch-fern`` dazu. Zwei Schalter, weil Laeufe lokal liegen und Releases
   oben als der gemeinsame Stand: Rund 900 Objekte aus dem geteilten Speicher
   zu entfernen soll zwei bewusste Entscheidungen kosten, nicht eine -
   dieselbe Haltung wie ``publish_table`` mit ``erzwingen=True``.

Unveraenderlich bleiben Releases dabei: Geloescht wird ein ganzes Release oder
keines, ein bestehendes wird nie ueberschrieben.

**Alte Fassungen, seit dem 18.10.2026 - und bis dahin die groesste Luecke
dieses Moduls.** Der Eimer ``urban-crime`` auf `srv01` hat Versionierung
eingeschaltet. Ein ``delete`` setzt dort eine Loeschmarkierung; die Fassung
darunter bleibt. Jedes Aufraeumen, das dieses Modul je gemacht hat, hat
damit **keinen Platz freigegeben** - und weil ``list_objects_v2`` nur die
aktuelle Fassung nennt, sah es niemand. Gemessen: 1'551 aktuelle Objekte mit
2,60 GiB, daneben 3'863 alte Fassungen mit 3,91 GiB und 2'381 Markierungen.
Sechzig Prozent, in einem Modul, dessen Aufgabe es ist, Platz zu zeigen.

Gefunden wurde es von aussen und aus einem fremden Anlass: Die naechtliche
Serversicherung nach Backblaze lief voll, und seit dem 24.9.2026 gab es kein
erfolgreiches Backup mehr. Der Filer meldete 6,99 GB, wo S3 2,60 GiB
zaehlte.

``alte_fassungen`` zaehlt sie jetzt je Schicht, und der Bericht laeuft
**immer** - auch ohne ``--loeschen``. Entfernt werden sie nur mit
``--fassungen --auch-fern``: Es ist die einzige Loeschung hier, die sich aus
keinem Lauf wiederherstellen laesst, denn eine alte Fassung liegt nirgends
sonst. Die **aktuelle** Fassung bleibt immer - was von ihr entbehrlich ist,
entscheiden die Regeln darueber.
"""

from __future__ import annotations

import argparse
import csv
import logging
import shutil
from datetime import date
from pathlib import Path
from typing import Any, NamedTuple

from manifeste import MANIFEST
from storage import Storage, for_root, paths, release

#: Die beiden Schichten, die dieses Werkzeug aufraeumt. Als Konstante, damit
#: der Praefix und der Schnitt darunter dieselbe Zeichenkette lesen.
BRONZE = "bronze"
RAW = "raw"


LOG = logging.getLogger("aufraeumen")

SCHNAPPSCHUESSE = 2   # der juengste Lauf und der davor
DELTA_MODI = frozenset({"delta", "incremental"})

REFERENZSTAND_DATEI = "referenzstand.csv"
SPALTEN = ("run_id", "quelle", "grund", "seit")

GEPINNT = "Referenzstand"
JUENGSTER = "juengster Lauf"
VORHERIGER = "vorheriger Schnappschuss"
GENANNT = "von Silver genannt"
BASIS = "Basis eines Delta-Laufs"
UNGEZOGEN = "Unterschied nicht gezogen"

#: Wie viele Releases ausser den gepinnten und dem aktuellen bleiben. Acht
#: sind zwei Monate woechentlicher Releases - die Begruendung steht in
#: ``docs/intern/datenhistorie.md`` 5.5. Das PRD zum LN2 fuehrte unter E6
#: fuenf; am 4.10.2026 nachverhandelt auf acht.
RELEASES_N = 8

AKTUELL = "aktueller Zeiger"
JUENGSTE_N = f"unter den letzten {RELEASES_N}"


class Bestand(NamedTuple):
    """Ein Bronze-Lauf mit seinem Raw-Gegenstueck, ueber alle Partitionen."""

    quelle: str
    run_id: str
    abgeschlossen: str
    delta: bool
    #: Ablagepfade, keine lokalen Pfade.
    #:
    #: **Der Unterschied ist der Grund, warum es diesen Umbau gab.** Bis zum
    #: 16.10.2026 standen hier ``Path``-Objekte aus dem lokalen
    #: Dateisystem - und im ``s3``-Modus gibt es die nicht: Die lokale Kopie
    #: wird nach dem Publizieren entfernt. Auf ``srv01`` sah das Werkzeug
    #: deshalb **keinen einzigen** Lauf und meldete, es sei nichts
    #: aufzuraeumen, waehrend auf SeaweedFS 141 Laeufe lagen und der
    #: Silver-Bau an ihnen erstickte.
    bronze: tuple[str, ...]
    raw: tuple[str, ...]
    zeilen: int
    #: Die Ablagewurzel, unter der ``bronze`` und ``raw`` liegen. Sie steht
    #: hier, damit ``bytes`` ueber ``storage`` zaehlen kann statt ueber offene
    #: Pfade. **Pflicht**, ohne Vorgabewert: Mit ``None`` lag jedes
    #: Verzeichnis ausserhalb der Wurzel, und ``bytes`` meldete 0 - ein
    #: fehlender Wert haette sich als falsches Ergebnis gezeigt, nicht als
    #: Fehler.
    data_root: Path

    @property
    def ohne_raw(self) -> bool:
        return not self.raw

    @property
    def bytes(self) -> int:
        """Was das Loeschen dieses Laufs freigibt - Bronze und Raw zusammen.

        Gezaehlt wird ueber ``Storage.bytes_unter``: Die Byte-Summe ueber ein
        Praefix steht seit dem 4.10.2026 einmal im Projekt und nicht dreimal
        ausgeschrieben. **Ohne ``lokal=True``** seit dem 16.10.2026: Laeufe
        werden nicht mehr nur lokal aufgeraeumt, und im ``s3``-Modus laege
        die Summe sonst immer bei null - eine Zahl, die kein Fehler ist,
        sondern eine falsche Antwort.

        Die Entscheidung haengt an keiner dieser Zahlen: ``entscheide``
        kennt nur Reihenfolge, Register und Manifeste. Diese Summe steht im
        Bericht und sonst nirgends.

        Ein Lauf, unter dem **nirgends** etwas liegt, ist ein **Fehler**,
        kein uebersprungener Posten: Stillschweigend weggelassen zeigte sich
        die falsche Wurzel als zu kleine Zahl statt als Abbruch - genau die
        Falle, die ``AGENTS.md`` unter dem fehlenden Census-Schluessel
        beschreibt. Seit die Pfade relativ sind, kann kein Schluessel mehr
        "ausserhalb" liegen; die Frage lautet jetzt, ob die Ablage ihn
        ueberhaupt kennt.
        """
        ablage = for_root(self.data_root)
        summe = 0
        for rel in self.bronze + self.raw:
            bytes_hier = ablage.bytes_unter(rel)
            if bytes_hier == 0 and not ablage.exists(rel, MANIFEST):
                raise ValueError(
                    f"Unter '{rel}' liegt nichts - weder lokal unter "
                    f"{ablage.local_root} noch oben. Die Belegung dieses "
                    f"Laufs liesse sich nur zu klein angeben.")
            summe += bytes_hier
        return summe


class Entscheid(NamedTuple):
    bestand: Bestand
    grund: str | None   # None heisst: entbehrlich

    @property
    def bleibt(self) -> bool:
        return self.grund is not None


class ReleaseStand(NamedTuple):
    """Ein Release im Inventar - ``wo`` ist ``lokal``, ``oben`` oder ``beide``."""

    release_id: str
    erstellt: str
    bytes: int
    wo: str


class ReleaseEntscheid(NamedTuple):
    release_: ReleaseStand
    grund: str | None   # None heisst: entbehrlich
    #: Der Grund aus ``config/referenzstand.csv``, wenn das Release dort
    #: steht - "LN1", "referenzstand", was auch immer dort getippt wurde.
    #: Getrennt von ``grund``, weil ``grund`` die **Regel** nennt, die das
    #: Release haelt, und die Regel heisst immer "Referenzstand". Wofuer
    #: gepinnt wurde, weiss nur das Register, und im Bericht steht es seit
    #: dem 5.10.2026 dabei: Zwei Releases sind gepinnt, eines fuer LN1 und
    #: eines als laufender Referenzstand, und "Referenzstand" allein liess
    #: sie gleich aussehen.
    pin: str = ""

    @property
    def bleibt(self) -> bool:
        return self.grund is not None


class Geraeumt(NamedTuple):
    """Was ein Loeschlauf wirklich entfernt hat - je Ort getrennt."""

    lokal: list[ReleaseEntscheid]
    oben: list[ReleaseEntscheid]
    schluessel: list[str]


def megabyte(entscheide: list[ReleaseEntscheid]) -> float:
    return sum(e.release_.bytes for e in entscheide) / 1e6


def ist_delta(manifest: dict[str, Any]) -> bool:
    # Chicago: mode = full_snapshot | delta.
    # Detroit: extraction_mode = FULL | DELTA | INCREMENTAL.
    modus = str(manifest.get("mode") or manifest.get("extraction_mode") or "")
    return modus.lower() in DELTA_MODI


def laufname(rel: str) -> str:
    """Der Laufname aus einem Ablagepfad - sein letztes Segment.

    Einmal benannt statt viermal ausgeschrieben: Bis zum 16.10.2026 stand
    dort ``Path.name``, und als aus den Pfaden Ablageschluessel wurden,
    schlug das an vier Stellen fehl. Die fuenfte haette man uebersehen.
    """
    return rel.rsplit("/", 1)[-1]


def bestaende(data_root: Path) -> dict[str, list[Bestand]]:
    """Alle fertigen Bronze-Laeufe, je Quelle, juengster zuerst.

    Die Quelle ist der erste Pfadteil unter ``bronze/`` - dieselbe Einteilung
    wie im Gesamtmanifest von ``run_all``. Das Raw-Gegenstueck ist das
    Verzeichnis mit demselben relativen Pfad unter ``raw/``; fehlt es, ist der
    Lauf ``ohne_raw``.

    **Gelesen wird ueber die Ablage, nicht ueber das Dateisystem.** Bis zum
    16.10.2026 lief hier ``fertige_laeufe`` auf ``data_root/bronze`` - im
    ``s3``-Modus ein leeres Verzeichnis, denn die lokale Kopie wird nach dem
    Publizieren entfernt. Das Werkzeug meldete auf ``srv01`` folglich, es
    sei nichts aufzuraeumen, waehrend dort 141 Laeufe lagen. ``Storage.laeufe``
    sieht beides und entscheidet nach dem Modus.
    """
    ablage = for_root(data_root)
    gruppen: dict[tuple[str, str], dict[str, Any]] = {}
    for lauf in ablage.laeufe(BRONZE, streng=False, fehler=SystemExit):
        innerhalb = lauf.relativ[len(BRONZE) + 1:]
        quelle = innerhalb.split("/", 1)[0]
        eintrag = gruppen.setdefault((quelle, lauf.run_id), {
            "abgeschlossen": "", "delta": ist_delta(lauf.manifest),
            "bronze": [], "raw": [], "zeilen": 0,
        })
        eintrag["abgeschlossen"] = max(eintrag["abgeschlossen"], lauf.abgeschlossen_um)
        eintrag["bronze"].append(lauf.relativ)
        roh = f"{RAW}/{innerhalb}"
        # Erst die Ablage, dann lokal - und das zweite ist lokal mit Absicht:
        # Ein Raw-Verzeichnis **ohne** Manifest zaehlt trotzdem, denn es
        # belegt Platz. Oben gibt es ohne Manifest keinen Lauf; unten liegt
        # er als Verzeichnis da.
        if ablage.exists(roh, MANIFEST) or ablage.local_path(roh).is_dir():
            eintrag["raw"].append(roh)
        eintrag["zeilen"] += lauf.zeilen

    je_quelle: dict[str, list[Bestand]] = {}
    for (quelle, run_id), e in gruppen.items():
        je_quelle.setdefault(quelle, []).append(Bestand(
            quelle, run_id, e["abgeschlossen"], e["delta"],
            tuple(e["bronze"]), tuple(e["raw"]), e["zeilen"], data_root,
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

    # Ueber die Ablage, nicht ueber das Dateisystem: Im ``s3``-Modus liegt
    # lokal keine Silver-Tabelle, und diese Regel haette **nichts**
    # geschuetzt - sie haette Laeufe freigegeben, auf denen das aktuelle
    # Silver ruht. Am 16.10.2026 gefunden, bevor etwas geloescht wurde.
    for tabelle in for_root(data_root).tabellen(("silver",)):
        sammle(tabelle.manifest.get("derived_from"))
    return kennungen


def kennungen_aus(data_root: Path, schichten: tuple[str, ...]) -> set[str]:
    """Jede Zeichenkette unter ``derived_from`` der genannten Schichten."""
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

    for tabelle in for_root(data_root).tabellen(schichten):
        sammle(tabelle.manifest.get("derived_from"))
    return kennungen


def gepinnte_laeufe(config_root: Path) -> dict[str, str]:
    """Das Register: Lauf-Kennung -> Grund. Leer, wenn es die Datei nicht gibt.

    Die Datei ist **versioniert**, anders als ``data/``: Ein Referenzstand ist
    eine Verabredung des Teams, kein Zustand eines Rechners. Seit die Laeufe
    auf SeaweedFS liegen, gelten die Kennungen fuer beide.
    """
    pfad = config_root / REFERENZSTAND_DATEI
    if not pfad.exists():
        return {}
    with pfad.open(encoding="utf-8", newline="") as datei:
        return {
            zeile["run_id"]: zeile.get("grund", "")
            for zeile in csv.DictReader(datei)
            if zeile.get("run_id")
        }


def stand_der_auswertung(data_root: Path) -> set[str]:
    """Jede Lauf-Kennung, auf der das gebaute Gold ruht.

    Das ist der Ertrag der geschlossenen Herkunftskette (#77): Ein
    Gold-Manifest nennt seine Silver-Quelle samt deren eigener Herkunft, und
    darin stehen die Bronze-Laeufe. Der Referenzstand laesst sich damit
    **ableiten** statt von Hand pflegen - und er beschreibt genau das, worauf
    die veroeffentlichten Zahlen beruhen.
    """
    return kennungen_aus(data_root, ("gold",))


def entscheide(laeufe: list[Bestand], genannt: set[str],
               gepinnt: dict[str, str] | None = None,
               ungezogen: set[str] | None = None) -> list[Entscheid]:
    """Die Regel, angewandt auf eine Quelle. ``laeufe`` juengster zuerst."""
    gepinnt = gepinnt or {}
    ungezogen = ungezogen or set()

    def ist_gepinnt(b: Bestand) -> bool:
        # ``b.bronze`` traegt Ablagepfade; der Laufname ist ihr letztes
        # Segment. Detroit pinnt seine nackte UUID, Chicago den ganzen
        # ``run_...``-Namen - beide stehen so im Pfad.
        return b.run_id in gepinnt or any(
            laufname(rel) in gepinnt for rel in b.bronze)

    gruende: list[str | None] = []
    for i, b in enumerate(laeufe):
        if ist_gepinnt(b):
            gruende.append(GEPINNT)
        elif i == 0:
            gruende.append(JUENGSTER)
        elif i < SCHNAPPSCHUESSE:
            gruende.append(VORHERIGER)
        elif b.run_id in genannt or any(
                laufname(rel) in genannt for rel in b.bronze):
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

    # Zuletzt, und das ist Absicht: ``UNGEZOGEN`` ist der **schwaechste**
    # Grund. Er geht weg, sobald jemand build_source_change laufen laesst;
    # ``BASIS`` und die uebrigen sind strukturell. Stuende er weiter vorn,
    # verdeckte eine voruebergehende Bedingung die dauerhafte, und der
    # Bericht saehe nach "einmal ziehen, dann darf es weg" aus, wo in
    # Wahrheit ein Delta darueber haengt.
    for i, b in enumerate(laeufe):
        if gruende[i] is None and (
                b.run_id in ungezogen
                or any(laufname(rel) in ungezogen for rel in b.bronze)):
            gruende[i] = UNGEZOGEN
    return [Entscheid(b, g) for b, g in zip(laeufe, gruende)]


def ungezogen_laut_tabelle(data_root: Path) -> set[str]:
    """Spaet importiert, damit ``aufraeumen`` ohne Silver-Code lauffaehig bleibt.

    Fehlt das Modul oder scheitert die Auskunft, gibt es **keine** Freigabe,
    sondern eine leere Menge: Diese Regel darf nur zusaetzlich halten, nie
    zusaetzlich loeschen.
    """
    try:
        from silver_pipeline.build_source_change import ungezogene_laeufe

        return ungezogene_laeufe(data_root)
    except Exception as fehler:          # noqa: BLE001 - Auskunft, kein Zwang
        LOG.warning("Aenderungstabelle nicht lesbar (%s) - Regel 2a greift "
                    "nicht. Die uebrigen Regeln gelten unveraendert.", fehler)
        return set()


def bericht(data_root: Path, config_root: Path | None = None) -> list[Entscheid]:
    genannt = genannt_in_silver(data_root)
    gepinnt = gepinnte_laeufe(config_root) if config_root else {}
    ungezogen = ungezogen_laut_tabelle(data_root)
    alle: list[Entscheid] = []
    for laeufe in bestaende(data_root).values():
        alle.extend(entscheide(laeufe, genannt, gepinnt, ungezogen))
    return alle


def pinne(data_root: Path, config_root: Path, grund: str, *,
          jetzt: date | None = None) -> list[str]:
    """Haelt den Stand fest, auf dem die gebauten Gold-Tabellen ruhen.

    Abgeleitet, nicht getippt: Welche Laeufe das sind, steht in den
    Manifesten. Wer eine Zahl in eine Abgabe uebernimmt, pinnt danach - und
    die Laeufe dahinter ueberleben jedes Aufraeumen.

    Bereits gepinnte Laeufe bleiben unveraendert; ihr erster Grund zaehlt.
    """
    vorhanden = gepinnte_laeufe(config_root)
    quelle_von = {
        b.run_id: b.quelle
        for laeufe in bestaende(data_root).values() for b in laeufe
    }
    quelle_von.update({
        laufname(rel): b.quelle
        for laeufe in bestaende(data_root).values() for b in laeufe
        for rel in b.bronze
    })
    neu = sorted(k for k in stand_der_auswertung(data_root)
                 if k in quelle_von and k not in vorhanden)
    if not neu:
        return []

    pfad = config_root / REFERENZSTAND_DATEI
    pfad.parent.mkdir(parents=True, exist_ok=True)
    frisch = not pfad.exists()
    tag = (jetzt or date.today()).isoformat()
    with pfad.open("a", encoding="utf-8", newline="") as datei:
        schreiber = csv.writer(datei, lineterminator="\n")
        if frisch:
            schreiber.writerow(SPALTEN)
        for kennung in neu:
            schreiber.writerow([kennung, quelle_von[kennung], grund, tag])
    return neu


# ---------------------------------------------------------------------------
# Releases: gepinnt plus die letzten acht
# ---------------------------------------------------------------------------


def releases(storage: Storage) -> list[ReleaseStand]:
    """Das Inventar, juengstes zuerst - lokal und auf SeaweedFS vereint.

    Gezaehlt wird nicht selbst: ``storage.release.liste`` liefert schon
    Kennung, Zeitpunkt, Groesse und Ort. Sortiert wird ueber die **Kennung**,
    nicht ueber ``created_at_utc`` - die Kennung ist derselbe Zeitstempel in
    einer Form, die lexikographisch sortiert, und sie ist immer da.
    """
    gefunden = [
        ReleaseStand(str(e["release_id"]), str(e.get("created_at_utc") or ""),
                     int(e.get("bytes") or 0), str(e.get("wo") or ""))
        for e in release.liste(storage)
    ]
    gefunden.sort(key=lambda r: r.release_id, reverse=True)
    return gefunden


#: Ein Praefix unter ``releases/``, das Dateien traegt, aber kein
#: ``release.json``.
class HalbesRelease(NamedTuple):
    kennung: str
    dateien: int
    bytes: int
    wo: str


def halbe_releases(storage: Storage) -> list[HalbesRelease]:
    """Was ein abgebrochener Upload liegenlaesst - und was niemand sah.

    ``publiziere`` schickt ``release.json`` **zuletzt** hinauf, und das ist
    richtig: Ohne es kann ein halb hochgebrachtes Release nie fuer ein
    Release gehalten werden, denn ``storage.release.liste`` findet Releases
    genau an diesem Manifest. Nur hiess das auch: **niemand findet die
    Reste.**

    Am 17.10.2026 scheiterte ein Upload am 26. von 28 Objekten - SeaweedFS
    antwortete mit ``InternalError`` - und liess 182,3 MB unter
    ``releases/release=2026-10-17T09-28-52Z/`` liegen. Der Lauf meldete das
    Release korrekt als gescheitert, der Zeiger blieb auf dem alten, und
    nichts davon war falsch. Die 182 MB blieben trotzdem, unsichtbar fuer
    jedes Werkzeug.

    Gezaehlt wird je Praefix; ``release.json`` entscheidet. Lokal zaehlt ein
    Verzeichnis ohne Manifest mit - ein abgebrochenes ``erstelle`` benennt
    sein ``.part`` nicht um, aber ein Abbruch *nach* dem Umbenennen und *vor*
    dem Upload sieht genauso aus.
    """
    gefunden: dict[str, list[int]] = {}
    orte: dict[str, set[str]] = {}

    # Lokal mit Absicht, und ausdruecklich geprueft: Dies ist die **lokale
    # Haelfte** des Inventars - die ferne zaehlt darunter ueber
    # `client.list`. Der Zweig haengt an `config.liest_lokal`, laeuft im
    # `s3`-Modus also nicht.
    lokal = storage.local_path(release.RELEASES)
    if storage.config.liest_lokal and lokal.is_dir():
        for verzeichnis in sorted(lokal.glob("release=*")):
            if not verzeichnis.is_dir():
                continue
            rel = verzeichnis.relative_to(lokal).as_posix()
            if paths.versteckt(rel):
                continue
            # Lokal mit Absicht: dieselbe lokale Haelfte.
            if (verzeichnis / release.RELEASE_MANIFEST).is_file():
                continue
            # Lokal mit Absicht, und ausdruecklich geprueft: Dies ist die
            # **lokale Haelfte** des Inventars - die ferne zaehlt darunter
            # ueber `client.list`. Der Zweig haengt an
            # `config.liest_lokal`, laeuft im `s3`-Modus also nicht.
            dateien = [d for d in verzeichnis.rglob("*") if d.is_file()]
            kennung = release.kennung_aus(verzeichnis)
            gefunden[kennung] = [len(dateien),
                                 sum(d.stat().st_size for d in dateien)]
            orte.setdefault(kennung, set()).add("lokal")

    if storage.config.remote:
        je_praefix: dict[str, list[int]] = {}
        mit_manifest: set[str] = set()
        for objekt in storage.client.list(release.RELEASES + "/"):
            teile = objekt.key.split("/")
            if len(teile) < 3 or not teile[1].startswith("release="):
                continue
            kennung = release.kennung_aus(teile[1])
            if objekt.key.endswith("/" + release.RELEASE_MANIFEST):
                mit_manifest.add(kennung)
            zaehler = je_praefix.setdefault(kennung, [0, 0])
            zaehler[0] += 1
            zaehler[1] += objekt.size or 0
        for kennung, (n, b) in je_praefix.items():
            if kennung in mit_manifest:
                continue
            vorhanden = gefunden.setdefault(kennung, [0, 0])
            vorhanden[0] += n
            vorhanden[1] += b
            orte.setdefault(kennung, set()).add("oben")

    return sorted(
        (HalbesRelease(k, n, b, "+".join(sorted(orte[k])))
         for k, (n, b) in gefunden.items()),
        key=lambda h: h.kennung, reverse=True)


def zeige_halbe(halbe: list[HalbesRelease]) -> None:
    if not halbe:
        return
    print(f"\n{release.RELEASES} - halb hochgebracht")
    for h in halbe:
        print(f"  {h.kennung[:28]:<29} {h.dateien:>4} Dateien "
              f"{h.bytes / 1e6:>7.1f} MB  {h.wo:6} ohne "
              f"{release.RELEASE_MANIFEST}")
    print(f"\n{len(halbe)} halbe(s) Release, "
          f"{sum(h.bytes for h in halbe) / 1e6:.1f} MB. Sie koennen nie fuer "
          f"ein Release gehalten werden - aber sie belegen Platz.")


def loesche_halbe(halbe: list[HalbesRelease], storage: Storage, *,
                  auch_fern: bool = False) -> list[str]:
    """Die Reste wegraeumen - lokal immer, oben erst mit ``auch_fern``.

    **Ein halbes Release ist nie gepinnt und nie der Zeiger.** Beides haengt
    an einer Kennung, die ``release.json`` traegt; ohne das Manifest kann
    weder ``config/referenzstand.csv`` darauf zeigen noch ``AKTUELL.json``.
    Deshalb braucht es hier keine Regel - es gibt nichts zu schuetzen.
    """
    weg: list[str] = []
    for h in halbe:
        rel = f"{release.RELEASES}/release={h.kennung}"
        verzeichnis = storage.local_path(rel)
        # Lokal mit Absicht: das lokale Loeschen eines Releases. Oben
        # geschieht es getrennt und nur mit `auch_fern`.
        if verzeichnis.is_dir():
            shutil.rmtree(verzeichnis)
            LOG.info("halbes Release lokal geloescht: %s", rel)
            weg.append(rel)
        if auch_fern and storage.config.remote:
            schluessel = storage.entferne_oben(rel)
            if schluessel:
                LOG.info("halbes Release oben geloescht: %s (%d Objekte)",
                         rel, len(schluessel))
                weg.extend(schluessel)
    return weg


#: Je Schicht die alten Fassungen - was ein Loeschen in einem versionierten
#: Eimer eben nicht freigibt.
class Fassungsstand(NamedTuple):
    schicht: str
    objekte: int
    markierungen: int
    bytes: int


def alte_fassungen(storage: Storage) -> list[Fassungsstand]:
    """Was oben liegt, obwohl es als geloescht gilt - je Schicht.

    **Der Befund vom 18.10.2026.** Der Eimer ``urban-crime`` auf `srv01` hat
    Versionierung eingeschaltet. Jedes Aufraeumen, das dieses Modul je
    gemacht hat, setzte damit nur Loeschmarkierungen: 1'551 aktuelle Objekte
    mit 2,60 GiB, daneben **3'863 alte Fassungen mit 3,91 GiB** und 2'381
    Markierungen. Sechzig Prozent des Eimers waren Reste - und dieses Modul,
    das zeigen soll, was Platz belegt, sah keinen einzigen davon.

    Gefunden wurde es von aussen: Der Filer meldete 6,99 GB, wo
    ``list_objects_v2`` 2,60 GiB zaehlte. Die Serversicherung nach Backblaze
    trug die Differenz jede Nacht mit und lief dort voll; seit dem 24.9.2026
    gab es kein erfolgreiches Backup mehr.

    Gezeigt wird **immer**, auch ohne ``--loeschen`` - der Sinn des Moduls.
    """
    if not storage.config.remote:
        return []
    je_schicht: dict[str, list[int]] = {}
    for f in storage.client.fassungen(""):
        if f.aktuell and not f.markierung:
            continue
        # Eine *aktuelle* Loeschmarkierung zaehlt mit: Sie ist der Grund,
        # warum die Fassung darunter unsichtbar ist, und sie belegt einen
        # Eintrag im Filer.
        schicht = f.key.split("/", 1)[0] or "(Wurzel)"
        eintrag = je_schicht.setdefault(schicht, [0, 0, 0])
        if f.markierung:
            eintrag[1] += 1
        else:
            eintrag[0] += 1
            eintrag[2] += f.size
    stand = [Fassungsstand(s, o, m, b) for s, (o, m, b) in je_schicht.items()]
    stand.sort(key=lambda x: -x.bytes)
    return stand


def zeige_fassungen(stand: list[Fassungsstand]) -> None:
    if not stand:
        return
    print("\nAlte Fassungen oben (versionierter Eimer)")
    for s in stand:
        print(f"  {s.schicht:<20} {s.objekte:>5} alte Fassungen "
              f"{s.bytes / 1e6:>8.1f} MB  {s.markierungen:>5} Markierungen")
    print(f"\n{sum(s.objekte for s in stand)} alte Fassungen, "
          f"{sum(s.bytes for s in stand) / 1e6:.1f} MB, "
          f"{sum(s.markierungen for s in stand)} Loeschmarkierungen. "
          f"**Ein Loeschen hat sie nie freigegeben** - in einem versionierten "
          f"Eimer setzt es eine Markierung. Sie zaehlen in jeder Sicherung "
          f"des Datentraegers mit.")


def loesche_fassungen(storage: Storage, *, auch_fern: bool = False) -> tuple[int, int]:
    """Alte Fassungen und Markierungen endgueltig weg. Gibt (Objekte, Bytes).

    **Nur mit ``auch_fern``**, wie bei Releases: Das ist der gemeinsame
    Speicher, und es ist die einzige Loeschung in diesem Modul, die sich
    nicht aus einem Lauf wiederherstellen laesst - eine alte Fassung ist
    nirgends sonst. Was weggeht, ist dennoch definiert: **nie die aktuelle
    Fassung**. Was aktuell ist, bleibt, auch wenn es entbehrlich waere; das
    entscheidet die Release- und Laufregel und nicht diese Funktion.
    """
    if not (auch_fern and storage.config.remote):
        return (0, 0)
    anzahl = bytes_frei = 0
    for f in storage.client.fassungen(""):
        if f.aktuell and not f.markierung:
            continue
        storage.client.entferne_fassung(f.key, f.version)
        anzahl += 1
        bytes_frei += f.size
    LOG.info("alte Fassungen entfernt: %d Objekte, %.1f MB",
             anzahl, bytes_frei / 1e6)
    return (anzahl, bytes_frei)


def aktuelles_release(storage: Storage) -> str | None:
    """Die Kennung aus ``releases/AKTUELL.json``, oder None, wenn er fehlt."""
    zeiger = release.aktuell(storage)
    if not zeiger:
        return None
    return str(zeiger.get("release_id") or "") or None


def entscheide_releases(stand: list[ReleaseStand],
                        gepinnt: dict[str, str] | None = None,
                        aktuell: str | None = None,
                        n: int = RELEASES_N) -> list[ReleaseEntscheid]:
    """Die Regel, angewandt auf das Inventar. ``stand`` juengstes zuerst.

    ``gepinnt`` ist dasselbe Register wie bei Laeufen; erkannt wird die blanke
    Kennung **und** der Verzeichnisname ``release=<Kennung>``, weil
    ``ist_gepinnt`` fuer Laeufe schon beides vergleicht.
    """
    gepinnt = gepinnt or {}
    entschieden: list[ReleaseEntscheid] = []
    for i, r in enumerate(stand):
        pin = ""
        if r.release_id in gepinnt or f"release={r.release_id}" in gepinnt:
            grund: str | None = GEPINNT
            pin = (gepinnt.get(r.release_id)
                   or gepinnt.get(f"release={r.release_id}") or "")
        elif aktuell and r.release_id == aktuell:
            grund = AKTUELL
        elif i < n:
            grund = JUENGSTE_N
        else:
            grund = None
        entschieden.append(ReleaseEntscheid(r, grund, pin))
    return entschieden


def release_bericht(storage: Storage, config_root: Path | None = None,
                    n: int = RELEASES_N) -> tuple[list[ReleaseEntscheid], str | None]:
    """Die Entscheide je Release und die Kennung des Zeigers (oder None)."""
    gepinnt = gepinnte_laeufe(config_root) if config_root else {}
    zeiger = aktuelles_release(storage)
    return entscheide_releases(releases(storage), gepinnt, zeiger, n), zeiger


def zeige_releases(entscheide: list[ReleaseEntscheid], aktuell: str | None) -> None:
    """Je Release eine Zeile plus Summe - im Stil von ``zeige``, mit ``wo``."""
    print(f"\n{release.RELEASES}")
    if aktuell is None:
        print(f"  (kein {release.AKTUELL} - der Zeiger fehlt. Die Regel laeuft, "
              f"haelt aber kein Release aus diesem Grund.)")
    for e in entscheide:
        r = e.release_
        # Beim gepinnten Release steht der Grund aus dem Register dabei. Ohne
        # ihn hiessen beide Zeilen "Referenzstand", und welches davon das
        # abgegebene LN1 ist, stuende nur in der CSV.
        grund = e.grund or "ENTBEHRLICH"
        if e.pin:
            grund = f"{grund} ({e.pin})"
        print(f"  {r.release_id:<29} {r.erstellt[:16]:<17} "
              f"{r.wo:>9} {r.bytes / 1e6:>7.1f} MB  {grund}")
    entbehrlich = [e for e in entscheide if not e.bleibt]
    print(f"\n{len(entscheide)} Releases, {len(entbehrlich)} entbehrlich, "
          f"{sum(e.release_.bytes for e in entbehrlich) / 1e6:.1f} MB frei.")


def loesche_releases(entscheide: list[ReleaseEntscheid], storage: Storage, *,
                     auch_fern: bool = False) -> Geraeumt:
    """Loescht entbehrliche Releases: lokal immer, oben nur mit ``auch_fern``.

    Je Release zuerst das lokale Verzeichnis, dann - wenn verlangt - alle
    Objekte unter demselben Praefix auf SeaweedFS, ``release.json`` zuletzt.
    Ein fehlgeschlagenes Loeschen bricht ab und laesst den Rest stehen;
    ``releases/AKTUELL.json`` liegt ausserhalb jedes Release-Praefixes und
    wird nie angefasst.

    Zurueck kommt, **was wirklich weg ist** - nicht, was entbehrlich war. Ein
    Release, das nur oben liegt, hat kein lokales Verzeichnis: Ohne
    ``auch_fern`` passiert dafuer nichts, und der Bericht darf keine
    freigegebenen Bytes behaupten.
    """
    lokal: list[ReleaseEntscheid] = []
    oben: list[ReleaseEntscheid] = []
    schluessel: list[str] = []
    for e in entscheide:
        if e.bleibt:
            continue
        rel = f"{release.RELEASES}/release={e.release_.release_id}"
        verzeichnis = storage.local_path(rel)
            # Lokal mit Absicht: dasselbe - hier wird die lokale Kopie
            # entfernt, oben uebernimmt `entferne_oben`.
        if verzeichnis.is_dir():
            shutil.rmtree(verzeichnis)
            lokal.append(e)
            LOG.info("geloescht: %s", verzeichnis)
        if auch_fern:
            weg = storage.entferne_oben(rel, zuletzt=release.RELEASE_MANIFEST)
            if weg:
                oben.append(e)
                schluessel.extend(weg)
    return Geraeumt(lokal, oben, schluessel)


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


def loesche(entscheide: list[Entscheid], data_root: Path, *,
            auch_fern: bool = False) -> list[str]:
    """Loescht, was entbehrlich ist - Raw und Bronze zusammen.

    Lokal immer, auf SeaweedFS erst mit ``auch_fern``. Dieselbe Trennung wie
    bei den Releases, und aus demselben Grund: Was oben liegt, sieht auch
    jemand anders.

    **Warum es das ferne Loeschen braucht.** Bis zum 16.10.2026 raeumte
    dieses Werkzeug nur lokal auf - und im ``s3``-Modus gibt es lokal nichts,
    weil die Arbeitskopie nach dem Publizieren entfernt wird. Auf ``srv01``
    haeuften sich deshalb Laeufe an, ohne dass es jemand sah: 141
    Parquet-Dateien, zehn Vollschnappschuesse je Jahrgang, und jeder
    gescheiterte Versuch legte zwei weitere nach.

    **Freigeben tun die Regeln davon wenig** - der erste Trockenlauf mit
    sehendem Blick nach oben zaehlte am 16.10.2026 *einen* entbehrlichen Lauf
    von 158. Was haelt, ist Regel 3: Beide Staedte laden nur Deltas, und ein
    Delta haelt alles bis zum naechsten Vollabzug. Dieses Werkzeug macht den
    Bestand also zuerst *sichtbar*; aufgeloest wird die Kette von einem
    geglueckten Vollabzug, nicht von hier.

    Leer gewordene Partitionsverzeichnisse (``ingest_date=...``) gehen lokal
    mit; die Schichtwurzeln ``raw/`` und ``bronze/`` bleiben. Oben gibt es
    keine Verzeichnisse, nur Praefixe - dort faellt das weg.

    Zurueck kommen die Ablagepfade dessen, was wirklich weg ist.
    """
    ablage = for_root(data_root)
    geloescht: list[str] = []
    for e in entscheide:
        if e.bleibt:
            continue
        for rel in e.bestand.bronze + e.bestand.raw:
            weg = False
            verzeichnis = ablage.local_path(rel)
            # Lokal mit Absicht: Dies *ist* das lokale Loeschen. Was oben
            # liegt, nimmt `entferne_oben` weiter unten - und nur mit
            # `auch_fern`.
            if verzeichnis.is_dir():
                shutil.rmtree(verzeichnis)
                weg = True
                LOG.info("geloescht: %s", verzeichnis)
                schicht = data_root / Path(rel).parts[0]
                eltern = verzeichnis.parent
                # Lokal mit Absicht: Leer gewordene Partitionsverzeichnisse
                # gibt es nur unten - oben gibt es keine Verzeichnisse, nur
                # Praefixe.
                while (eltern != schicht and eltern.is_dir()
                       and not any(eltern.iterdir())):
                    eltern.rmdir()
                    eltern = eltern.parent
            if auch_fern and ablage.config.remote:
                # Manifest zuletzt - wie bei den Releases. Bricht es
                # dazwischen ab, sagt das Manifest noch "fertig", und der
                # halbe Lauf faellt beim naechsten Lesen auf statt still zu
                # fehlen.
                if ablage.entferne_oben(rel, zuletzt=MANIFEST):
                    weg = True
                    LOG.info("oben geloescht: %s", rel)
            if weg:
                geloescht.append(rel)
    return geloescht


def arguments() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Zeigt, welche Raw- und Bronze-Laeufe und welche Releases "
                    "bleiben muessen und welche entbehrlich sind. Loescht nur "
                    "auf Wunsch - Laeufe lokal, Releases lokal und mit "
                    "--auch-fern auch auf SeaweedFS."
    )
    p.add_argument("--data-root", type=Path, default=None,
                   help="lokale Wurzel (Vorgabe: LOCAL_DATA_ROOT oder data). Laeufe werden "
                        "nur lokal aufgeraeumt; Releases auf Wunsch auch auf SeaweedFS")
    p.add_argument("--config-root", type=Path, default=Path("config"),
                   help="wo das Register referenzstand.csv liegt (Vorgabe: config)")
    p.add_argument("--loeschen", action="store_true",
                   help="entbehrliche Laeufe wirklich loeschen (Raw und Bronze zusammen) "
                        "und entbehrliche Releases - diese lokal")
    p.add_argument("--auch-fern", action="store_true",
                   help="entbehrliche Laeufe und Releases ausserdem auf "
                        "SeaweedFS loeschen. Wirkt nur zusammen mit "
                        "--loeschen. Im s3-Modus ist das der einzige Weg: "
                        "Lokal liegt dort nichts")
    p.add_argument("--fassungen", action="store_true",
                   help="ausserdem die alten Fassungen und Loeschmarkierungen "
                        "endgueltig entfernen - das Einzige, was in einem "
                        "versionierten Eimer wirklich Platz freigibt. "
                        "Braucht --loeschen und --auch-fern, und ist nicht "
                        "rueckholbar: eine alte Fassung liegt nirgends sonst")
    p.add_argument("--pinnen", metavar="GRUND",
                   help="den Stand, auf dem das gebaute Gold ruht, ins Register "
                        "aufnehmen - er ueberlebt danach jedes Aufraeumen")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def main() -> int:
    args = arguments()
    if args.loeschen or args.pinnen:
        from storage.verwaltet import sperre
        sperre(for_root(args.data_root).local_root)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    ablage = for_root(args.data_root)
    data_root = ablage.local_root
    if args.pinnen:
        neu = pinne(data_root, args.config_root, args.pinnen)
        ziel = args.config_root / REFERENZSTAND_DATEI
        if neu:
            print(f"{len(neu)} Lauf/Laeufe als '{args.pinnen}' festgehalten in {ziel}:")
            for kennung in neu:
                print(f"  {kennung}")
            print("\nDie Datei ist versioniert - bitte mit committen.")
        else:
            print(f"Nichts hinzugefuegt: Der Stand steht schon in {ziel}.")
        print()

    alle = bericht(data_root, args.config_root)
    zeige(alle)
    entbehrlich = [e for e in alle if not e.bleibt]

    rel_entscheide, zeiger = release_bericht(ablage, args.config_root)
    zeige_releases(rel_entscheide, zeiger)
    rel_entbehrlich = [e for e in rel_entscheide if not e.bleibt]
    halbe = halbe_releases(ablage)
    zeige_halbe(halbe)
    fassungen = alte_fassungen(ablage)
    zeige_fassungen(fassungen)

    if args.auch_fern and not args.loeschen:
        print("\n--auch-fern wirkt nur mit --loeschen. Trockenlauf: Auf "
              "SeaweedFS wurde nichts angefasst.")
    if not args.loeschen:
        if entbehrlich or rel_entbehrlich or halbe:
            print("\nNichts geloescht. Mit --loeschen gehen die entbehrlichen "
                  "Laeufe und Releases weg - Releases nur lokal, erst mit "
                  "--auch-fern auch auf SeaweedFS. Halbe Releases ebenso.")
        if fassungen:
            print("\nDie alten Fassungen gehen mit --fassungen --auch-fern "
                  "weg, und nur damit: Sie sind die einzige Loeschung hier, "
                  "die sich aus keinem Lauf wiederherstellen laesst.")
        return 0
    # Vor dem ersten Loeschen, nicht danach: ``storage.client`` wirft unter
    # STORAGE_BACKEND=local, und das ist die Vorgabe. Ein Abbruch mitten in
    # loesche_releases haette das erste lokale Verzeichnis schon mitgenommen.
    if args.auch_fern and not ablage.config.remote:
        print(f"\n--auch-fern braucht eine Ablage mit S3, STORAGE_BACKEND="
              f"{ablage.backend} kennt keine. Nichts geloescht.")
        return 2

    if entbehrlich:
        frei = sum(e.bestand.bytes for e in entbehrlich)
        geloescht = loesche(alle, data_root, auch_fern=args.auch_fern)
        print(f"{len(geloescht)} Lauf-Praefixe geloescht, {frei / 1e6:.1f} MB frei.")
    if halbe:
        weg = loesche_halbe(halbe, ablage, auch_fern=args.auch_fern)
        print(f"{len(halbe)} halbe(s) Release geraeumt, "
              f"{sum(h.bytes for h in halbe) / 1e6:.1f} MB frei "
              f"({len(weg)} Pfade/Objekte).")
    if args.fassungen and fassungen:
        anzahl, frei = loesche_fassungen(ablage, auch_fern=args.auch_fern)
        print(f"{anzahl} alte Fassungen und Markierungen entfernt, "
              f"{frei / 1e6:.1f} MB frei - und diesmal wirklich frei.")
    if rel_entbehrlich:
        geraeumt = loesche_releases(rel_entscheide, ablage, auch_fern=args.auch_fern)
        print(f"{len(geraeumt.lokal)} Release(s) lokal geloescht, "
              f"{megabyte(geraeumt.lokal):.1f} MB frei.")
        if args.auch_fern:
            print(f"{len(geraeumt.oben)} Release(s) auf SeaweedFS geloescht "
                  f"({len(geraeumt.schluessel)} Objekte), "
                  f"{megabyte(geraeumt.oben):.1f} MB frei.")
        else:
            uebrig = [e for e in rel_entbehrlich
                      if e.release_.wo in ("oben", "beide")]
            print(f"Auf SeaweedFS unveraendert: {len(uebrig)} entbehrliche "
                  f"Release(s), {megabyte(uebrig):.1f} MB - dafuer braucht es "
                  f"--auch-fern.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
