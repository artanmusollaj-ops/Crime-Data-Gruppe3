"""Zeigen alle Orte denselben Stand? - eine Frage an drei Stellen.

    python -m serving.pruefe_stand           # Bericht, Rueckgabewert 0 oder 1
    python -m serving.pruefe_stand --knapp   # nur die Abweichungen
    python -m serving.pruefe_stand --betrieb server   # wie auf srv01

**Warum es diesen Schritt gibt.** Es gibt Orte, die behaupten, die Daten zu
zeigen: die Arbeits-Gold-Schicht (auf der die DuckDB-Sichten liegen),
Elasticsearch und die Kibana-Dashboards. Jeder prueft sich **beim Laden**
gegen das Release. Danach prueft niemand mehr, ob sie noch dasselbe sagen.

Das Szenario ist nicht ausgedacht: Ein neues Release entsteht, Gold wird neu
gebaut, Elasticsearch vergessen. Die Dashboards zeigen weiter den alten
Stand - ohne jeden Hinweis, weil der Alias brav auf den alten Index zeigt und
alle Zahlen in sich stimmig sind. Jede einzelne Stelle ist konsistent, und das
Ganze ist falsch.

**ClickHouse steht in der Liste und wird nicht geprueft.** Es wird seit dem
5.10.2026 nicht mehr geladen; das ganze Sternschema liegt in Elasticsearch
(siehe ``load_elasticsearch``). Ein Ort, der nicht geladen wird, kann keinen
Stand zeigen - der Bericht nennt ihn deshalb als **nicht geladen** und wird
davon nicht rot. Weggelassen wird er nicht: Eine Liste, in der ein Dienst
fehlt, der im ``docker-compose.yml`` steht, laesst offen, ob er vergessen oder
entschieden wurde. ``pruefe_clickhouse`` bleibt aufrufbar und geprueft, fuer
den Fall, dass jemand von Hand laedt.

**Das Release ist der Massstab.** Nicht eine der Engines, nicht die
Arbeitsschicht - ``releases/AKTUELL.json`` sagt, was gilt, und alles andere
wird dagegen gehalten. Genau deshalb traegt jede Tabelle und jeder Index die
Release-Kennung im Namen: damit diese Frage beantwortbar ist, ohne irgendwo
Buch zu fuehren.

**Was verglichen wird.**

===================  ===============================================
Arbeits-Gold         Pruefsumme je Datei gegen die des Releases
Elasticsearch        Index hinter jedem der sechs Aliase + Dokumentzahl
Kibana               Zeitfenster der Dashboards gegen den Datenbereich
ClickHouse           nichts - nicht geladen, siehe oben
===================  ===============================================

Kibana steht mit in der Liste, weil sein Stand nicht am Index haengt: Die
Dashboards bekommen ihr Zeitfenster beim Anlegen eingebacken (siehe
``build_kibana``). Deckt ein neues Release einen anderen Zeitraum ab, zeigen
sie weiter den alten Ausschnitt - auf aktuellen Daten, und damit womoeglich
auf einem leeren Diagramm.

**Auf srv01 sind es zwei Orte (seit dem 1.11.2026, C-9).** Dort ersetzt
das eigene Dashboard Elasticsearch und Kibana; es liest den Eimer selbst und
laedt hoechstens eine Minute nach einem neuen Release nach. ``--betrieb
server`` (oder ``SERVING_BETRIEB=server`` aus der Compose-Datei) prueft
deshalb Gold und das Dashboard, und nichts sonst - ein Befund ueber einen
Dienst, den es dort nicht gibt, waere eine Auskunft ins Leere. Lokal bleibt
der Bericht, wie er war.

===================  ===============================================
Dashboard            Release, das es geladen hat, gegen AKTUELL.json
===================  ===============================================

**Was dieses Modul nicht tut.** Es repariert nichts. Es sagt, was
auseinanderlaeuft, und welcher Befehl es zusammenbraechte. Ein Werkzeug, das
ungefragt nachlaedt, ist eins, das man nicht mehr fragen mag.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

# Aus ``load_clickhouse`` kommt noch die gemeinsame Release-Ermittlung. Sein
# ``HttpKlient`` nicht mehr: Seit dem 5.10.2026 fragt dieses Modul ClickHouse
# nicht mehr (siehe ``befund_clickhouse``). Und auch seine Tabellenliste
# ``ZIELE`` nicht mehr - sie kennt fuenf Tabellen, ``dim_tract_acs`` fehlt ihr
# so, wie sie den Ladern fehlte. Der Bericht meldete dadurch "5 Dateien
# gleich", wo sechs liegen: eine plausibel aussehende falsche Zahl. Geprueft
# wird jetzt ueber ``INDIZES``, und ein Test haelt das gegen
# ``gold_pipeline.TABELLEN`` - eine siebte Tabelle ist damit mitgeprueft,
# ohne dass jemand daran denken muss. ``ZIELE`` bleibt importiert: Die
# ClickHouse-Pruefung selbst ist unveraendert und voll getestet, sie wird nur
# nicht mehr aufgerufen.
from serving.load_clickhouse import STANDARD_URL as CLICKHOUSE_URL
from serving.load_clickhouse import ZIELE, LadeFehler, aktuelles_release
from serving.load_clickhouse import vorgabe_url as clickhouse_vorgabe
from serving.load_elasticsearch import INDIZES
from serving.load_elasticsearch import STANDARD_URL as ELASTICSEARCH_URL
from serving.load_elasticsearch import HttpKlient as ElasticKlient
from serving.load_elasticsearch import vorgabe_url as elasticsearch_vorgabe
from serving.build_kibana import BRETTER
from serving.build_kibana import STANDARD_URL as KIBANA_URL
from serving.build_kibana import HttpKlient as KibanaKlient
from serving.build_kibana import vorgabe_url as kibana_vorgabe

#: Wo das Dashboard lokal laeuft (``python -m serving.dashboard``). Auf srv01
#: setzt die Compose-Datei ``DASHBOARD_URL`` auf den Dienstnamen.
DASHBOARD_URL = "http://localhost:8050"

#: Die beiden Betriebsarten: welche Orte es gibt, die einen Stand zeigen.
BETRIEBE = ("lokal", "server")

#: Wie lange auf das Dashboard gewartet wird, bis es ein neues Release zeigt:
#: Es prueft hoechstens einmal je Minute (``PRUEFABSTAND_S``) und laedt dann
#: 15-25 Sekunden. Sechs Versuche im Abstand von 20 Sekunden decken beides.
DASHBOARD_VERSUCHE = 6
DASHBOARD_ABSTAND_S = 20.0


def dashboard_vorgabe() -> str:
    """Die Adresse aus der Umgebung, sonst die lokale - beim Aufruf gelesen."""
    return os.getenv("DASHBOARD_URL") or DASHBOARD_URL


def betrieb_vorgabe() -> str:
    """``SERVING_BETRIEB`` aus der Umgebung, sonst ``lokal``.

    Eine Umgebungsvariable und keine Flagge allein, weil der Konsolen-Worker
    dieses Modul aus ``platform_admin.serving_export`` ruft und dort dieselbe
    Variable entscheidet, ob Elasticsearch und Kibana beschickt werden. Zwei
    Angaben fuer eine Tatsache koennten auseinanderlaufen.
    """
    betrieb = os.getenv("SERVING_BETRIEB") or "lokal"
    if betrieb not in BETRIEBE:
        raise ValueError(f"SERVING_BETRIEB kennt nur {BETRIEBE}, nicht {betrieb!r}")
    return betrieb


#: Wieviel auf einmal gelesen wird, wenn eine Datei gehasht wird. 42 MB am
#: Stueck in den Speicher zu holen waere unnoetig.
BLOCK = 1 << 20


class Urteil:
    """Die vier Zustaende, die ein Ort haben kann."""

    GLEICH = "stimmt"
    ANDERS = "weicht ab"
    FEHLT = "nicht erreichbar"
    #: Kein Urteil, sondern eine Auskunft: Dieser Ort wird nicht beschickt und
    #: kann deshalb keinen Stand zeigen. Faerbt den Lauf nicht rot, wird aber
    #: auch im knappen Bericht gezeigt - sonst stuende dort "alles stimmt"
    #: ueber einem Dienst, in dem nichts liegt.
    NICHT_GELADEN = "nicht geladen"


@dataclass(frozen=True)
class Befund:
    """Was ein Ort ueber sich sagt."""

    ort: str
    urteil: str
    stand: str = ""
    #: Was zu tun waere. Leer, wenn nichts zu tun ist.
    abhilfe: str = ""

    @property
    def gut(self) -> bool:
        """Ist hier nichts zu tun?

        ``NICHT_GELADEN`` zaehlt mit: Ein Ort, der absichtlich leer bleibt,
        ist kein Grund, den Lauf rot zu faerben. Gezeigt wird er trotzdem -
        darum fragt ``bericht`` nach dem Urteil und nicht nach ``gut``.
        """
        return self.urteil in (Urteil.GLEICH, Urteil.NICHT_GELADEN)


class Klient(Protocol):
    def anfrage(self, *a: Any, **k: Any) -> Any: ...


# --------------------------------------------------------------------------
# Reine Funktionen - pruefbar ohne jeden Dienst
# --------------------------------------------------------------------------


def kennung_im_namen(release_id: str) -> str:
    """``2026-09-21T12-55-05Z`` -> ``20260921T125505Z``.

    Dieselbe Verkuerzung, die ``load_clickhouse.tabellenname`` und
    ``load_elasticsearch.indexname`` vornehmen. Verglichen wird in dieser
    Form und nicht zurueckuebersetzt: Aus ``20260921T125505Z`` laesst sich
    die urspruengliche Kennung nicht eindeutig wiederherstellen, und wer es
    doch versucht, baut eine zweite Stelle, an der geraten wird.
    """
    return re.sub(r"[^0-9A-Za-z]", "", release_id)


def traegt_kennung(name: str, release_id: str) -> bool:
    """Steht die Kennung des Releases am Ende dieses Namens?

    Gross- und Kleinschreibung spielt keine Rolle: ClickHouse laesst den
    Namen so stehen, wie er geschrieben wurde, Elasticsearch verlangt
    Kleinbuchstaben. Dieselbe Kennung sieht deshalb an beiden Orten
    verschieden aus.
    """
    return name.lower().endswith(kennung_im_namen(release_id).lower())


def tabelle_hinter_sicht(sicht_sql: str) -> str:
    """``SELECT * FROM default.fact_offense_2026…`` -> ``fact_offense_2026…``.

    ClickHouse haelt die Definition einer Sicht als Text vor. Das ist die
    einzige Stelle, an der steht, welchen Stand sie zeigt - die Sicht selbst
    heisst ja immer gleich.
    """
    treffer = re.search(r"FROM\s+(?:[\w.]+\.)?(\w+)", sicht_sql, re.IGNORECASE)
    if not treffer:
        raise LadeFehler(f"Aus dieser Sicht wird keine Tabelle erkennbar: "
                         f"{sicht_sql[:120]}")
    return treffer.group(1)


def pruefsumme(pfad: Path) -> str:
    kessel = hashlib.sha256()
    with pfad.open("rb") as datei:
        while brocken := datei.read(BLOCK):
            kessel.update(brocken)
    return kessel.hexdigest()


def fenster_passt(von: str, bis: str, daten_von: str, daten_bis: str) -> bool:
    """Deckt das Zeitfenster eines Dashboards die Daten ab?

    Verlangt wird kein exakter Treffer - ein Fenster darf grosszuegiger sein
    als die Daten, und `build_kibana` macht es bewusst um einen Tag weiter.
    Falsch wird es, wenn es die Daten **abschneidet**: Dann fehlt im
    Diagramm etwas, ohne dass jemand es sieht.
    """
    return von <= daten_von and bis >= daten_bis


# --------------------------------------------------------------------------
# Die vier Orte
# --------------------------------------------------------------------------


def pruefe_gold(datenwurzel: Path, verzeichnis: Path) -> Befund:
    """Steht in der Arbeitsschicht noch dasselbe wie im Release?

    Hier liegen die DuckDB-Sichten auf (``build_analysis_db`` zeigt auf
    ``data/gold/``, nicht auf ein Release). Laeuft die Strecke noch einmal,
    ohne dass ein Release geschnitten wird, zeigt DuckDB andere Zahlen als
    ClickHouse und Elasticsearch - und beide halten sich fuer richtig.

    Verglichen wird die Pruefsumme und nicht die Zeilenzahl: Zwei Dateien mit
    gleich vielen Zeilen koennen verschiedenen Inhalt haben, und genau das
    waere der Fall, den man am spaetesten bemerkt.
    """
    abweichend, fehlend = [], []
    for ziel in INDIZES:
        # **Derselbe schichtrelative Pfad auf beiden Seiten.** Hier stand
        # ``"gold" / f"dataset={ziel.name}"``, und das stimmt fuer sieben der
        # acht Indizes. ``rate_tract`` ist keine Gold-Tabelle - die Rate je
        # Tract ist eine Aggregation, und Gold aggregiert nicht (AGENTS.md);
        # sie entsteht in ``serving.build_comparison`` und liegt unter
        # ``serving/``. Die Release-Seite wusste das ueber
        # ``Index.quelle_im_release``, die Arbeitsschicht-Seite nicht.
        #
        # Die Folge war ein Befund, der eine vorhandene Tabelle als fehlend
        # meldete und zu einem Neubau riet, der nichts geaendert haette - am
        # 17.10.2026 auf ``srv01`` gesehen, als zum ersten Mal seit Langem
        # jemand ``pruefe_stand`` gelesen hat. **Die Testvorrichtung trug
        # denselben Denkfehler**: Sie legte die Arbeitskopie fuer jeden Index
        # unter ``gold/``, also auch fuer ``rate_tract`` - gegen den Code
        # gebaut und darum blind fuer ihn.
        arbeit = datenwurzel / ziel.quelle_im_release
        im_release = verzeichnis / ziel.quelle_im_release
        # Lokal mit Absicht, auf beiden Seiten: Verglichen wird die
        # **Arbeitsschicht** gegen das **eingesetzte** Release, und
        # beide liegen unten. Genau das ist die Frage dieser Pruefung -
        # ob der Stand, auf dem die DuckDB-Sichten ruhen, noch der des
        # Releases ist.
        if not arbeit.is_file() or not im_release.is_file():
            fehlend.append(ziel.name)
        elif pruefsumme(arbeit) != pruefsumme(im_release):
            abweichend.append(ziel.name)

    if fehlend:
        return Befund("Gold (Arbeitsschicht)", Urteil.FEHLT,
                      f"{', '.join(fehlend)} fehlt",
                      "python -m orchestration.run_all")
    if abweichend:
        return Befund(
            "Gold (Arbeitsschicht)", Urteil.ANDERS,
            f"{len(abweichend)} von {len(INDIZES)} weichen ab: "
            f"{', '.join(abweichend)}",
            "Entweder ein neues Release schneiden (orchestration.release) "
            "oder klaeren, warum Gold vom Release abweicht")
    return Befund("Gold (Arbeitsschicht)", Urteil.GLEICH,
                  f"{len(INDIZES)} Dateien gleich")


def befund_clickhouse() -> Befund:
    """Die Auskunft ueber den Ort, der nicht beschickt wird.

    Kein Dienst wird dafuer angefasst, und das ist der Punkt: Ob ClickHouse
    laeuft, ist belanglos, solange nichts darin liegt. Ein ``FEHLT`` waere
    irrefuehrend (es fehlt nichts, es wurde nichts geladen) und ein ``GLEICH``
    eine Luege.
    """
    return Befund(
        "ClickHouse", Urteil.NICHT_GELADEN,
        "wird seit dem 5.10.2026 nicht mehr geladen; das Sternschema liegt "
        "vollstaendig in Elasticsearch",
        # Keine Abhilfe: Es ist nichts zu beheben. Wer trotzdem laden will,
        # findet den Lader unberuehrt vor - und dann sagt ``pruefe_clickhouse``
        # wieder, ob er auf dem Stand ist.
        "")


def pruefe_clickhouse(klient: Klient, release_id: str) -> Befund:
    """Traegt die Tabelle hinter jeder Sicht die Kennung des Releases?

    Wird aus ``pruefe_alles`` nicht mehr aufgerufen - ClickHouse wird nicht
    geladen (siehe ``befund_clickhouse``). Die Pruefung bleibt, weil der Lader
    bleibt: Wer ihn von Hand aufruft, soll die Frage weiter stellen koennen.
    """
    try:
        sichten = dict(klient.abfrage(
            "SELECT name, as_select FROM system.tables "
            "WHERE database = currentDatabase() AND engine = 'View'"))
    except Exception as fehler:
        return Befund("ClickHouse", Urteil.FEHLT, str(fehler)[:90],
                      "docker compose up -d clickhouse")

    fehlend = [z.name for z in ZIELE if z.name not in sichten]
    if fehlend:
        return Befund("ClickHouse", Urteil.FEHLT,
                      f"ohne Sicht: {', '.join(fehlend)}",
                      "python -m serving.load_clickhouse")

    alt = [name for name, sql in sichten.items()
           if name in {z.name for z in ZIELE}
           and not traegt_kennung(tabelle_hinter_sicht(sql), release_id)]
    if alt:
        gezeigt = tabelle_hinter_sicht(sichten[alt[0]])
        return Befund("ClickHouse", Urteil.ANDERS,
                      f"{len(alt)} Sicht(en) auf einem anderen Stand, z.B. "
                      f"{gezeigt}", "python -m serving.load_clickhouse")
    return Befund("ClickHouse", Urteil.GLEICH, f"{len(ZIELE)} Sichten")


def pruefe_elasticsearch(klient: Klient, release_id: str) -> Befund:
    try:
        aliase = klient.anfrage("GET", "/_alias")
    except Exception as fehler:
        return Befund("Elasticsearch", Urteil.FEHLT, str(fehler)[:90],
                      "docker compose up -d elasticsearch")

    zeigt_auf: dict[str, list[str]] = {}
    for index, eintrag in aliase.items():
        for alias in eintrag.get("aliases", {}):
            zeigt_auf.setdefault(alias, []).append(index)

    fehlend = [i.name for i in INDIZES if i.name not in zeigt_auf]
    if fehlend:
        return Befund("Elasticsearch", Urteil.FEHLT,
                      f"ohne Alias: {', '.join(fehlend)}",
                      "python -m serving.load_elasticsearch")

    alt = [i.name for i in INDIZES
           if not all(traegt_kennung(x, release_id) for x in zeigt_auf[i.name])]
    if alt:
        return Befund("Elasticsearch", Urteil.ANDERS,
                      f"{len(alt)} Alias(e) auf einem anderen Stand, z.B. "
                      f"{zeigt_auf[alt[0]][0]}",
                      "python -m serving.load_elasticsearch")
    return Befund("Elasticsearch", Urteil.GLEICH, f"{len(INDIZES)} Aliase")


def pruefe_kibana(klient: Klient, daten_von: str, daten_bis: str) -> Befund:
    """Deckt das eingebackene Zeitfenster noch die Daten ab?

    Der eine Ort, dessen Stand nicht am Index haengt. Ein Dashboard mit einem
    Fenster von 2024 auf Daten von 2025 ist technisch in Ordnung und zeigt
    ein leeres Diagramm.
    """
    eng = []
    for brett in BRETTER:
        try:
            objekt = klient.anfrage(
                "GET", f"/api/saved_objects/dashboard/{brett.kennung}")
        except Exception as fehler:
            return Befund("Kibana", Urteil.FEHLT, str(fehler)[:90],
                          "python -m serving.build_kibana")
        merkmale = objekt["attributes"]
        if not merkmale.get("timeRestore"):
            eng.append(f"{brett.kennung} (ohne festes Fenster)")
        elif not fenster_passt(merkmale["timeFrom"], merkmale["timeTo"],
                               daten_von, daten_bis):
            eng.append(brett.kennung)

    if eng:
        return Befund("Kibana", Urteil.ANDERS,
                      f"Zeitfenster schneidet Daten ab: {', '.join(eng)}",
                      "python -m serving.build_kibana")
    return Befund("Kibana", Urteil.GLEICH, f"{len(BRETTER)} Dashboards")


class DashboardKlient:
    """Fragt das Dashboard, welchen Stand es zeigt."""

    def __init__(self, url: str):
        self.url = url.rstrip("/")

    def stand(self) -> dict:
        # /api/optionen und nicht /healthz: Nur eine Anfrage an den Bestand
        # laesst das Dashboard nachsehen, ob es nachladen muss. Die erste
        # nach einem Start laedt; daher die lange Wartezeit.
        with urllib.request.urlopen(f"{self.url}/api/optionen", timeout=120) as antwort:
            return json.load(antwort)["stand"]


def pruefe_dashboard(klient: Any, release_id: str, *,
                     versuche: int = DASHBOARD_VERSUCHE,
                     abstand: float = DASHBOARD_ABSTAND_S,
                     warte=time.sleep) -> Befund:
    """Zeigt das Dashboard das aktuelle Release?

    Es laedt selbst nach, aber nicht sofort: hoechstens einmal je Minute
    sieht es nach, ob sich Gold, ``comparison_month`` oder ``AKTUELL.json``
    geaendert haben. Direkt nach dem Publizieren zeigt es deshalb noch eine
    Weile das alte Release - das ist kein Befund. Erst wenn es nach den
    Versuchen noch dabei bleibt, weicht es ab.
    """
    abhilfe_start = "docker compose -f docker-compose.srv01.yml up -d dashboard"
    gezeigt = None
    for versuch in range(versuche):
        try:
            gezeigt = klient.stand().get("release")
        except Exception as fehler:
            return Befund("Dashboard", Urteil.FEHLT, str(fehler)[:90], abhilfe_start)
        if gezeigt == release_id:
            return Befund("Dashboard", Urteil.GLEICH, f"Release {release_id}")
        if versuch < versuche - 1:
            warte(abstand)
    return Befund("Dashboard", Urteil.ANDERS, f"zeigt Release {gezeigt or 'keines'}",
                  "docker compose -f docker-compose.srv01.yml restart dashboard")


# --------------------------------------------------------------------------
# Der Ablauf
# --------------------------------------------------------------------------


def datenbereich(verzeichnis: Path) -> tuple[str, str]:
    """Von wann bis wann das Release reicht - fuer die Kibana-Pruefung."""
    from storage.duckdb import verbinde

    parquet = verzeichnis / "gold/dataset=fact_offense/part-0001.parquet"
    con = verbinde()
    try:
        von, bis = con.execute(
            f"SELECT min(occurred_at_utc), max(occurred_at_utc) "
            f"FROM read_parquet('{parquet}')").fetchone()
    finally:
        con.close()
    return (von.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            bis.strftime("%Y-%m-%dT%H:%M:%S.000Z"))


def pruefe_alles(datenwurzel: Path, *, clickhouse: str = CLICKHOUSE_URL,
                 elasticsearch: str = ELASTICSEARCH_URL,
                 kibana: str = KIBANA_URL, dashboard: str = DASHBOARD_URL,
                 betrieb: str = "lokal",
                 dashboard_klient: Any = None) -> tuple[str, list[Befund]]:
    """Lokal drei Pruefungen und eine Auskunft, auf dem Server zwei Pruefungen.

    ``clickhouse`` wird nicht mehr gefragt und bleibt als Angabe stehen: Der
    Schalter ``--clickhouse`` ist dokumentiert, und ein Aufruf, der ihn
    mitgibt, soll nicht mit einem Typfehler abbrechen, sondern dieselbe
    Auskunft bekommen wie jeder andere.
    """
    if betrieb not in BETRIEBE:
        raise ValueError(f"--betrieb kennt nur {BETRIEBE}, nicht {betrieb!r}")
    kennung, verzeichnis = aktuelles_release(datenwurzel)
    if betrieb == "server":
        return kennung, [
            pruefe_gold(datenwurzel, verzeichnis),
            pruefe_dashboard(dashboard_klient or DashboardKlient(dashboard), kennung),
        ]
    von, bis = datenbereich(verzeichnis)
    return kennung, [
        pruefe_gold(datenwurzel, verzeichnis),
        pruefe_elasticsearch(ElasticKlient(elasticsearch), kennung),
        pruefe_kibana(KibanaKlient(kibana), von, bis),
        befund_clickhouse(),
    ]


def bericht(kennung: str, befunde: list[Befund], knapp: bool = False) -> str:
    zeilen = [f"Massstab: Release {kennung}", ""]
    # Gefragt wird nach dem Urteil und nicht nach ``gut``: ``NICHT_GELADEN``
    # faerbt den Lauf nicht rot, gehoert aber in jeden Bericht. Ein knapper
    # Bericht, der einen leeren Dienst verschweigt, laesst genau die Frage
    # offen, die er beantworten soll.
    zeigen = [b for b in befunde if not (knapp and b.urteil == Urteil.GLEICH)]
    if not zeigen:
        # Nicht "alle vier": Geprueft werden drei Orte, der vierte wird
        # nicht geladen und steht in diesem Zweig deshalb nie.
        zeilen.append("Alle geprueften Orte zeigen diesen Stand.")
        return "\n".join(zeilen)

    breite = max(len(b.ort) for b in zeigen)
    for b in zeigen:
        zeichen = "  " if b.gut else "! "
        zeilen.append(f"{zeichen}{b.ort:<{breite}}  {b.urteil:<16}  {b.stand}")
        if b.abhilfe:
            zeilen.append(f"{'':<{breite + 2}}  -> {b.abhilfe}")
    return "\n".join(zeilen)


def kommandozeile() -> argparse.ArgumentParser:
    """Die Kommandozeile - eigen, damit ihre Vorgaben pruefbar sind.

    Die drei Dienstadressen kommen aus derselben Quelle wie bei den
    Ladern und werden **beim Aufruf** gelesen, nicht beim Import.
    """
    zerleger = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    zerleger.add_argument("--data-root", type=Path, default=None)
    # Dieselben drei Vorgaben wie bei den Ladern, und aus derselben Quelle:
    # Wer die Dienste unter anderen Adressen beschickt, prueft sie dort auch.
    # Gelesen beim Aufruf, nicht beim Import; ein Argument sticht weiterhin.
    zerleger.add_argument("--clickhouse", default=clickhouse_vorgabe())
    zerleger.add_argument("--elasticsearch", default=elasticsearch_vorgabe())
    zerleger.add_argument("--kibana", default=kibana_vorgabe())
    zerleger.add_argument("--dashboard", default=dashboard_vorgabe())
    zerleger.add_argument("--betrieb", choices=BETRIEBE, default=betrieb_vorgabe(),
                          help="lokal: Gold, Elasticsearch, Kibana; "
                               "server: Gold und das Dashboard")
    zerleger.add_argument("--knapp", action="store_true",
                          help="nur zeigen, was abweicht")
    zerleger.add_argument("--json", action="store_true")
    return zerleger


def main(argv: list[str] | None = None) -> int:
    args = kommandozeile().parse_args(argv)

    from storage import for_root

    kennung, befunde = pruefe_alles(
        for_root(args.data_root).local_root, clickhouse=args.clickhouse,
        elasticsearch=args.elasticsearch, kibana=args.kibana,
        dashboard=args.dashboard, betrieb=args.betrieb)

    if args.json:
        print(json.dumps(
            {"release_id": kennung,
             "befunde": [vars(b) for b in befunde]}, indent=2,
            ensure_ascii=False))
    else:
        print(bericht(kennung, befunde, args.knapp))

    # Ein Rueckgabewert, mit dem sich etwas anfangen laesst: Das hier kann in
    # einem Datenlauf stehen und ihn rot faerben.
    return 0 if all(b.gut for b in befunde) else 1


if __name__ == "__main__":
    raise SystemExit(main())
