"""Der Weg vom Release nach Elasticsearch - groesstenteils ohne Elasticsearch.

Der Klient ist ``FalscherDienst``: ein paar Dictionaries, die sich aber wie
Elasticsearch **verhalten** - Dokumente liegen unter ihrer Kennung, ein
zweites Dokument mit derselben Kennung ersetzt das erste, und ``composite``
blaettert. Gerade diese Eigenheiten traegt das Modul als Zusicherung, und ein
Doppel, das sie nicht hat, pruefte sie nicht mit.

Fuenf Pruefungen fassen einen echten Dienst an - sie ueberspringen sich, wenn
keiner laeuft; zwei davon pruefen die Vorrichtung selbst, weil sie bis zum
5.10.2026 etwas versprach, was sie nicht tat. Drei fassen das echte Release an
und tragen deshalb ``referenzstand``.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from uuid import uuid4

import pytest

from serving import load_elasticsearch as le
from serving.load_clickhouse import LadeFehler


# --------------------------------------------------------------------------
# Werkzeug
# --------------------------------------------------------------------------


def beispiel(tmp_path: Path, *, ohne_koordinate: int = 1) -> Path:
    """Ein winziges fact_offense mit genau den Eigenheiten, auf die es ankommt.

    Zwei Staedte, ein Delikt ohne Koordinate und ohne Beschreibung - das sind
    die Faelle, an denen sich Ortsfeld und Volltext entscheiden.
    """
    import duckdb

    ziel = tmp_path / "part-0001.parquet"
    zeilen = [
        ("o1", "chicago", "2024-01-01 06:56:00", "2024-01-01", "13A",
         "ARSON: BY FIRE", 41.7, -87.6, "exact", "inside_city"),
        ("o2", "detroit", "2024-03-05 17:00:00", "2024-03-05", "23C",
         "THEFT FROM BUILDING", 42.3, -83.0, "exact", "inside_city"),
    ]
    werte = ", ".join(
        f"('{a}', '{b}', TIMESTAMP '{c}', DATE '{d}', '{e}', '{f}', "
        f"{g}::DOUBLE, {h}::DOUBLE, '{i}', '{j}')"
        for a, b, c, d, e, f, g, h, i, j in zeilen
    )
    fehlend = ", ".join(
        f"('x{n}', 'chicago', TIMESTAMP '2024-02-02 06:00:00', "
        f"DATE '2024-02-02', NULL::VARCHAR, NULL::VARCHAR, NULL::DOUBLE, "
        f"NULL::DOUBLE, 'unmapped', 'missing_coordinate')"
        for n in range(ohne_koordinate)
    )
    alle = werte + (", " + fehlend if fehlend else "")
    con = duckdb.connect()
    con.execute(
        f"COPY (SELECT * FROM (VALUES {alle}) AS t(offense_id, "
        f"reporting_city, occurred_at_utc, date, nibrs_code, "
        f"source_offense_description, latitude, longitude, mapping_status, "
        f"geo_status)) TO '{ziel}' (FORMAT PARQUET)")
    con.close()
    return ziel


class FalscherDienst:
    """Elasticsearch als Dictionaries - mit seinen Eigenheiten, nicht ohne.

    Dokumente liegen unter ihrer Kennung. Damit bildet das Doppel genau das
    ab, worauf der Schluesselnachweis des Moduls ruht: Zwei gleiche Kennungen
    ergeben ein Dokument, nicht zwei.
    """

    def __init__(self) -> None:
        self.indizes: dict[str, dict[str, dict]] = {}
        self.abbildungen: dict[str, dict] = {}
        self.aliase: dict[str, set[str]] = {}
        self.pfade: list[str] = []
        self.bulk_fehler = False

    # -- die beiden Methoden, die das Modul kennt -------------------------

    def anfrage(self, methode: str, pfad: str,
                koerper: dict | None = None) -> dict:
        self.pfade.append(f"{methode} {pfad}")
        nackt = pfad.split("?")[0]
        if methode == "PUT":
            name = nackt.strip("/")
            self.indizes[name] = {}
            self.abbildungen[name] = koerper or {}
            return {"acknowledged": True}
        if nackt.endswith("/_refresh"):
            return {"_shards": {"failed": 0}}
        if nackt.endswith("/_count"):
            return {"count": len(self.indizes[nackt.split("/")[1]])}
        if nackt.endswith("/_search"):
            return self._suche(nackt.split("/")[1], koerper or {})
        if nackt == "/_alias":
            # Wie Elasticsearch: **jeder** Index steht drin, auch der ohne
            # Alias. Genau deshalb faellt hier nichts mit 404 aus.
            namen = set(self.indizes) | set(self.aliase)
            return {i: {"aliases": {a: {} for a in self.aliase.get(i, ())}}
                    for i in namen}
        if nackt == "/_aliases":
            for schritt in (koerper or {})["actions"]:
                if "remove" in schritt:
                    self.aliase.get(schritt["remove"]["index"], set()).discard(
                        schritt["remove"]["alias"])
                else:
                    self.aliase.setdefault(
                        schritt["add"]["index"], set()).add(
                            schritt["add"]["alias"])
            return {"acknowledged": True}
        raise AssertionError(f"unerwarteter Aufruf: {methode} {pfad}")

    def massen(self, ndjson: str) -> dict:
        if self.bulk_fehler:
            # Genau so antwortet Elasticsearch: HTTP 200, Fehler im Rumpf.
            return {"errors": True,
                    "items": [{"index": {"error": {"type": "mapper_parsing"}}}]}
        zeilen = ndjson.strip("\n").split("\n")
        for kopf, rumpf in zip(zeilen[::2], zeilen[1::2]):
            anweisung = json.loads(kopf)["index"]
            self.indizes[anweisung["_index"]][anweisung["_id"]] = json.loads(rumpf)
        return {"errors": False, "items": []}

    # -- was Elasticsearch daraus macht ----------------------------------

    def _suche(self, name: str, koerper: dict) -> dict:
        zusammen = koerper["aggs"]["verteilung"]["composite"]
        felder = [next(iter(q)) for q in zusammen["sources"]]
        pfade = [q[f]["terms"]["field"] for q, f in zip(zusammen["sources"], felder)]

        zaehler: dict[tuple, int] = {}
        for dokument in self.indizes[name].values():
            schluessel = tuple(
                dokument.get(p.removesuffix(".keyword")) for p in pfade)
            zaehler[schluessel] = zaehler.get(schluessel, 0) + 1

        # ``composite`` ordnet aufsteigend und stellt den leeren Eimer nach
        # vorn - beides bildet das Doppel nach, sonst pruefte ``_ordne``
        # nichts.
        geordnet = sorted(zaehler.items(),
                          key=lambda p: tuple((v is not None, str(v))
                                              for v in p[0]))
        nach = koerper["aggs"]["verteilung"]["composite"].get("after")
        if nach:
            marke = tuple(nach[f] for f in felder)
            geordnet = [p for p in geordnet if tuple(
                str(v) for v in p[0]) > tuple(str(v) for v in marke)]
        seite = geordnet[:zusammen["size"]]

        eimer = [{"key": dict(zip(felder, s)), "doc_count": n} for s, n in seite]
        ergebnis: dict = {"buckets": eimer}
        if len(geordnet) > len(seite) and seite:
            ergebnis["after_key"] = dict(zip(felder, seite[-1][0]))
        return {"aggregations": {"verteilung": ergebnis}}


FAKT = le.INDIZES[0]


# --------------------------------------------------------------------------
# Abgelesen und entschieden
# --------------------------------------------------------------------------


def test_die_felder_kommen_aus_der_datei_nicht_aus_einer_liste(tmp_path):
    namen = [f.name for f in le.felder(beispiel(tmp_path))]
    assert namen[0] == "offense_id"
    assert "source_offense_description" in namen
    assert "dataset" not in namen      # die Hive-Spalte gehoert nicht hinein


def test_text_ist_die_ausnahme_keyword_die_voreinstellung(tmp_path):
    abb = le.mapping(le.felder(beispiel(tmp_path)), FAKT)["mappings"]["properties"]
    assert abb["reporting_city"] == {"type": "keyword"}
    assert abb["nibrs_code"] == {"type": "keyword"}


def test_ein_volltextfeld_behaelt_sein_keyword_unterfeld(tmp_path):
    abb = le.mapping(le.felder(beispiel(tmp_path)), FAKT)["mappings"]["properties"]
    # Ohne das Unterfeld scheitert jede Gruppierung ueber die Beschreibung.
    assert abb["source_offense_description"] == {
        "type": "text", "fields": {"keyword": {"type": "keyword"}}}


def test_ein_unentschiedener_typ_bricht_ab_statt_zu_raten():
    with pytest.raises(LadeFehler, match="kein Elasticsearch-Typ"):
        le.Feld("irgendwas", "decimal128(5, 2)").abbildung


def test_volltext_auf_einer_zahl_bricht_ab():
    ziel = le.Index(name="fact_offense", schluessel=("offense_id",),
                    verteilung=(), volltext=frozenset({"hour_of_day"}))
    le.NACH_NAME["fact_offense"] = ziel
    try:
        with pytest.raises(LadeFehler, match="durchsuchbar wird nur Text"):
            le.Feld("hour_of_day", "int8").abbildung
    finally:
        le.NACH_NAME["fact_offense"] = FAKT


def test_der_ort_ist_ein_feld_und_nicht_zwei(tmp_path):
    abb = le.mapping(le.felder(beispiel(tmp_path)), FAKT)["mappings"]["properties"]
    assert abb["standort"] == {"type": "geo_point"}
    # Verbraucht heisst verbraucht: Sonst laege dieselbe Angabe doppelt im
    # Index, und niemand wuesste, welche gilt.
    assert "latitude" not in abb and "longitude" not in abb


def test_eine_ortsspalte_die_keine_koordinate_ist_bricht_ab(tmp_path):
    ziel = le.Index(name="fact_offense", schluessel=("offense_id",),
                    verteilung=(), geo=("reporting_city", "longitude"))
    le.NACH_NAME["fact_offense"] = ziel
    try:
        with pytest.raises(LadeFehler, match="Gleitkommazahlen"):
            le.mapping(le.felder(beispiel(tmp_path)), ziel)
    finally:
        le.NACH_NAME["fact_offense"] = FAKT


def test_die_abbildung_ist_streng(tmp_path):
    abb = le.mapping(le.felder(beispiel(tmp_path)), FAKT)
    # Ohne 'strict' raet Elasticsearch den Typ einer neuen Gold-Spalte aus
    # dem ersten Wert - und niemand hat entschieden.
    assert abb["mappings"]["dynamic"] == "strict"
    assert abb["settings"]["number_of_replicas"] == 0


def test_der_indexname_traegt_das_release_und_ist_klein():
    name = le.indexname("2026-09-21T12-55-05Z", "fact_offense")
    assert name == "fact_offense-20260921t125505z"
    assert name == name.lower()        # Elasticsearch verlangt das
    assert ":" not in name and " " not in name


# --------------------------------------------------------------------------
# Die Dokumente
# --------------------------------------------------------------------------


def test_ohne_koordinate_fehlt_das_ortsfeld_statt_null_zu_sein(tmp_path):
    alle = dict(le.dokumente(beispiel(tmp_path), FAKT))
    assert alle["o1"]["standort"] == {"lat": 41.7, "lon": -87.6}
    # Ein 'null' wiese Elasticsearch als ungueltigen geo_point zurueck - und
    # 2'346 solcher Zeilen stehen im echten Release.
    assert "standort" not in alle["x0"]


def test_die_dokumentkennung_ist_der_schluessel(tmp_path):
    kennungen = [k for k, _ in le.dokumente(beispiel(tmp_path), FAKT)]
    assert kennungen == ["o1", "o2", "x0"]


def test_zeitstempel_und_datum_werden_zu_text(tmp_path):
    alle = dict(le.dokumente(beispiel(tmp_path), FAKT))
    assert alle["o1"]["occurred_at_utc"] == "2024-01-01T06:56:00"
    assert alle["o1"]["date"] == "2024-01-01"


def test_nan_wird_nichts_statt_ungueltigem_json():
    # json.dumps schriebe das nackte Wort NaN hin; Elasticsearch weist dann
    # den ganzen Stapel zurueck - wegen eines Wertes.
    assert le._wert(float("nan")) is None
    assert le._wert(float("inf")) is None
    assert le._wert(1.5) == 1.5
    assert "NaN" not in json.dumps({"a": le._wert(math.nan)})


def test_der_massenrumpf_traegt_zwei_zeilen_je_dokument(tmp_path):
    teil = list(le.dokumente(beispiel(tmp_path), FAKT))
    rumpf = le.massenrumpf("ziel", teil)
    zeilen = rumpf.strip("\n").split("\n")
    assert len(zeilen) == 2 * len(teil)
    assert rumpf.endswith("\n")        # ohne den letzten Umbruch: 400
    kopf = json.loads(zeilen[0])
    # 'index' und nicht 'create': Ein doppelter Schluessel soll ersetzen und
    # dadurch an der Zeilenzahl auffallen, nicht einen Fehlerhaufen erzeugen.
    assert set(kopf) == {"index"}
    assert kopf["index"]["_id"] == "o1"


# --------------------------------------------------------------------------
# Der Abgleich
# --------------------------------------------------------------------------


def test_die_verteilungsfrage_laesst_nichts_unter_den_tisch_fallen():
    frage = le.abgleich_anfrage(FAKT)
    quellen = frage["aggs"]["verteilung"]["composite"]["sources"]
    for quelle in quellen:
        feld = next(iter(quelle))
        # Ohne missing_bucket zaehlt Elasticsearch Zeilen ohne Wert gar nicht
        # mit - und der Abgleich saehe gruen aus, obwohl etwas fehlt.
        assert quelle[feld]["terms"]["missing_bucket"] is True
    assert frage["size"] == 0


def test_gruppiert_wird_auf_dem_keyword_unterfeld():
    index = le.Index(name="dim_offense", schluessel=("nibrs_code",),
                     verteilung=("nibrs_description",),
                     volltext=frozenset({"nibrs_description"}))
    quelle = le.abgleich_anfrage(index)["aggs"]["verteilung"]["composite"]["sources"][0]
    # Auf 'text' laesst sich nicht gruppieren.
    assert quelle["nibrs_description"]["terms"]["field"] == "nibrs_description.keyword"


def test_der_aliaswechsel_steht_in_einem_einzigen_aufruf():
    koerper = le.alias_umlegen("fact_offense", "neu", ["alt1", "alt2"])
    arten = [next(iter(s)) for s in koerper["actions"]]
    # Zwei Aufrufe haetten einen Moment, in dem der Alias auf nichts zeigt.
    assert arten == ["remove", "remove", "add"]
    assert koerper["actions"][-1]["add"]["index"] == "neu"


def test_ein_noch_unbekannter_alias_ist_leer_und_kein_fehler():
    """Der erste Lauf hat noch keinen Alias - und das ist der Normalfall.

    ``GET /_alias/<name>`` antwortete darauf mit 404 und liess den ersten
    Lauf scheitern. Gefragt wird deshalb die Gesamtliste.
    """
    antwort = {"alt": {"aliases": {"fact_offense": {}}},
               "fremd": {"aliases": {}}}
    assert le.bestehende_aliase(antwort, "fact_offense") == ["alt"]
    assert le.bestehende_aliase(antwort, "gibt_es_nicht") == []
    assert le.bestehende_aliase({}, "fact_offense") == []


def test_beide_seiten_ordnen_null_gleich():
    roh = [("b", 1), (None, 2), ("a", 3)]
    assert le._ordne(roh) == [("a", 3), ("b", 1), (None, 2)]


# --------------------------------------------------------------------------
# Der Ablauf
# --------------------------------------------------------------------------


def test_der_gute_fall_legt_den_alias_zuletzt_um(tmp_path):
    dienst = FalscherDienst()
    ergebnis = le.lade(dienst, "2026-09-21T12-55-05Z", beispiel(tmp_path),
                       index=FAKT)

    assert ergebnis["zeilen"] == 3
    ziel = "fact_offense-20260921t125505z"
    assert dienst.aliase[ziel] == {"fact_offense"}
    # Die Reihenfolge ist die Zusage: Erst wenn geprueft ist, wird sichtbar.
    assert dienst.pfade.index(f"POST /{ziel}/_refresh") < dienst.pfade.index(
        "POST /_aliases")


def test_ohne_auffrischen_wuerde_zu_frueh_gezaehlt(tmp_path):
    dienst = FalscherDienst()
    le.lade(dienst, "2026-09-21T12-55-05Z", beispiel(tmp_path), index=FAKT)
    ziel = "fact_offense-20260921t125505z"
    # Geschriebenes ist in Elasticsearch erst nach dem Auffrischen sichtbar.
    assert dienst.pfade.index(f"POST /{ziel}/_refresh") < dienst.pfade.index(
        f"GET /{ziel}/_count")


def test_eine_fehlende_zeile_laesst_den_alias_stehen(tmp_path):
    dienst = FalscherDienst()
    dienst.aliase["alter-stand"] = {"fact_offense"}
    parquet = beispiel(tmp_path)

    echt = le.dokumente

    def unvollstaendig(p, i):
        alle = list(echt(p, i))
        return iter(alle[:-1])         # eine Zeile verschluckt

    le.dokumente = unvollstaendig
    try:
        with pytest.raises(LadeFehler, match="zeilen"):
            le.lade(dienst, "2026-09-21T12-55-05Z", parquet, index=FAKT)
    finally:
        le.dokumente = echt

    assert dienst.aliase["alter-stand"] == {"fact_offense"}
    assert "POST /_aliases" not in dienst.pfade


def test_ein_doppelter_schluessel_faellt_an_der_zeilenzahl_auf(tmp_path):
    """Der Nachweis, auf dem die Schluesselzusage ruht.

    Es gibt keine exakte Eindeutigkeitsmessung in Elasticsearch -
    ``cardinality`` schaetzt. Stattdessen ersetzt eine zweite Kennung die
    erste, und die Zeilenzahl faellt. Genau das prueft dieser Test.
    """
    dienst = FalscherDienst()
    parquet = beispiel(tmp_path)
    echt = le.dokumente

    def doppelt(p, i):
        alle = list(echt(p, i))
        return iter([(alle[0][0], d) for _, d in alle])   # alle unter "o1"

    le.dokumente = doppelt
    try:
        with pytest.raises(LadeFehler, match="zeilen"):
            le.lade(dienst, "2026-09-21T12-55-05Z", parquet, index=FAKT)
    finally:
        le.dokumente = echt
    assert "POST /_aliases" not in dienst.pfade


def test_ein_fehler_im_stapel_bricht_ab_obwohl_http_200_kam(tmp_path):
    dienst = FalscherDienst()
    dienst.bulk_fehler = True
    with pytest.raises(LadeFehler, match="_bulk meldet Fehler"):
        le.lade(dienst, "2026-09-21T12-55-05Z", beispiel(tmp_path), index=FAKT)
    assert "POST /_aliases" not in dienst.pfade


def test_ein_feinerer_zeitstempel_bricht_ab(tmp_path):
    import duckdb

    ziel = tmp_path / "fein.parquet"
    con = duckdb.connect()
    con.execute(
        f"COPY (SELECT 'o1' AS offense_id, TIMESTAMP '2024-01-01 06:56:00.0005'"
        f" AS occurred_at_utc) TO '{ziel}' (FORMAT PARQUET)")
    con.close()
    with pytest.raises(LadeFehler, match="feiner als eine"):
        le.pruefe_zeitgenauigkeit(ziel, le.felder(ziel))


# --------------------------------------------------------------------------
# Gegen einen echten Dienst
# --------------------------------------------------------------------------
#
#     docker run -d --name crime-elasticsearch -p 19200:9200 \
#         -e discovery.type=single-node -e xpack.security.enabled=false \
#         docker.elastic.co/elasticsearch/elasticsearch:8.19.22
#     ELASTICSEARCH_URL=http://localhost:19200 python -m pytest tests/serving
#
# Jeder Test bekommt einen eigenen Namensraum und raeumt ihn weg. Das ist
# nicht Ordnungsliebe: Ein Test, der in den Namen des echten Standes greift,
# loescht ihn - genau das ist beim ClickHouse-Teil einmal passiert.
#
# Und das Wegraeumen ist selbst geprueft. Bis zum 5.10.2026 stand hier eine
# Platzhalter-Loeschung, die der Dienst ablehnt, und ihr Fehler wurde
# verschluckt: 681 Pruefindizes, 710 Shards auf einem 1-GiB-Heap. Siehe
# ``raeume_auf``.

ELASTICSEARCH = os.environ.get("ELASTICSEARCH_URL", "http://localhost:19200")


def raeume_auf(klient, praefix: str) -> None:
    """Loescht jeden Index des Praefixes - einzeln und mit seinem Namen.

    ``DELETE /{praefix}*`` sah aus wie die kurze Fassung davon und war keine:
    Elasticsearch laeuft mit ``action.destructive_requires_name`` und weist
    einen Platzhalter im Loeschpfad mit HTTP 400 zurueck. Der ``LadeFehler``
    wurde hier mit ``pass`` verschluckt, und so sammelten sich bis zum
    5.10.2026 **681 Pruefindizes** mit 710 Shards auf einem 1-GiB-Heap an -
    waehrend der Docstring der Vorrichtung versprach, sie raeume hinter sich
    auf.

    Gefragt wird mit dem Platzhalter: Lesend ist er erlaubt und antwortet mit
    einer leeren Liste, wenn nichts passt. Geloescht wird namentlich, und ein
    Fehler dabei faellt auf, statt verschluckt zu werden - eine Vorrichtung,
    die ihr Scheitern verschweigt, ist schlimmer als keine.
    """
    gefunden = klient.anfrage(
        "GET", f"/{praefix}*/_settings?filter_path=*.settings.index.uuid")
    for name in sorted(gefunden):
        klient.anfrage("DELETE", f"/{name}")


@pytest.fixture
def elastic():
    """Ein Klient mit eigenem Praefix - und er raeumt namentlich hinter sich auf."""
    klient = le.HttpKlient(ELASTICSEARCH)
    try:
        klient.anfrage("GET", "/")
    except Exception:
        pytest.skip(f"kein Elasticsearch unter {ELASTICSEARCH}")

    praefix = f"pruefung-{uuid4().hex[:12]}"
    try:
        yield klient, praefix
    finally:
        raeume_auf(klient, praefix)


def test_eine_platzhalter_loeschung_weist_der_dienst_zurueck(elastic):
    """Warum ``raeume_auf`` namentlich loescht - und nicht in einem Aufruf.

    Die Begruendung gehoert gemessen und nicht behauptet: Solange der Dienst
    mit ``action.destructive_requires_name`` laeuft, ist der kurze Weg keiner.
    """
    klient, praefix = elastic
    klient.anfrage("PUT", f"/{praefix}-eins")
    with pytest.raises(LadeFehler, match="Wildcard"):
        klient.anfrage("DELETE", f"/{praefix}*")


def test_die_vorrichtung_laesst_keinen_pruefindex_zurueck(elastic):
    """Die Zusage des Docstrings, an der Vorrichtung selbst geprueft.

    Bis zum 5.10.2026 versprach sie das und tat es nicht. Ein Test, der nur
    das Aufraeumen *aufruft*, haette das nicht gezeigt - gefragt wird deshalb
    danach, was uebrig ist.
    """
    klient, praefix = elastic
    for teil in ("a", "b"):
        klient.anfrage("PUT", f"/{praefix}-{teil}")

    raeume_auf(klient, praefix)

    uebrig = klient.anfrage(
        "GET", f"/{praefix}*/_settings?filter_path=*.settings.index.uuid")
    assert uebrig == {}, f"liegen geblieben: {sorted(uebrig)}"


def test_elasticsearch_nimmt_die_erzeugte_abbildung_an(tmp_path, elastic):
    klient, praefix = elastic
    name = f"{praefix}-fact"
    klient.anfrage("PUT", f"/{name}",
                   le.mapping(le.felder(beispiel(tmp_path)), FAKT))

    gelesen = klient.anfrage("GET", f"/{name}/_mapping")
    eigenschaften = gelesen[name]["mappings"]["properties"]
    assert eigenschaften["standort"]["type"] == "geo_point"
    assert eigenschaften["source_offense_description"]["type"] == "text"
    assert gelesen[name]["mappings"]["dynamic"] == "strict"


def test_die_strenge_abbildung_weist_eine_unbekannte_spalte_zurueck(
        tmp_path, elastic):
    """Die Zusicherung aus ``mapping`` - an der echten Umsetzung geprueft."""
    klient, praefix = elastic
    name = f"{praefix}-streng"
    klient.anfrage("PUT", f"/{name}",
                   le.mapping(le.felder(beispiel(tmp_path)), FAKT))

    antwort = klient.massen(le.massenrumpf(
        name, [("o1", {"offense_id": "o1", "neue_gold_spalte": 1})]))
    assert antwort["errors"] is True


def test_der_ganze_weg_gegen_einen_echten_dienst(tmp_path, elastic):
    klient, praefix = elastic
    index = le.Index(name=f"{praefix}-lauf", schluessel=FAKT.schluessel,
                     verteilung=FAKT.verteilung, volltext=FAKT.volltext,
                     geo=FAKT.geo)
    le.NACH_NAME[index.name] = index
    try:
        ergebnis = le.lade(klient, "2026-09-21T12-55-05Z",
                           beispiel(tmp_path), index=index)
    finally:
        del le.NACH_NAME[index.name]

    assert ergebnis["zeilen"] == 3
    # Und der Alias zeigt wirklich auf die Daten, nicht nur in der Antwort.
    gefunden = klient.anfrage(
        "POST", f"/{index.name}/_search",
        {"query": {"match": {"source_offense_description": "arson"}}})
    assert gefunden["hits"]["total"]["value"] == 1


# --------------------------------------------------------------------------
# Gegen das echte Release
# --------------------------------------------------------------------------


def test_die_indizes_erschoepfen_die_gold_tabellen():
    """Keine Gold-Tabelle faellt still daneben - weder heute noch als siebte.

    Bis zum 5.10.2026 trug ``INDIZES`` drei der sechs Tabellen; zwei lagen in
    ClickHouse, und ``dim_tract_acs`` lag in keinem der beiden Lader. Das war
    kein Fehler, den etwas gemeldet haette: Jeder Lauf war gruen, es fehlte
    nur der Nenner fuer jede Rate je 1'000 Einwohner. Genau diese Form von
    Luecke schliesst dieser Test.
    """
    from gold_pipeline import TABELLEN

    geladen = {i.name for i in le.INDIZES}
    fehlend = sorted(set(TABELLEN) - geladen)
    assert not fehlend, (
        f"{fehlend} steht in gold_pipeline.TABELLEN, aber nicht in INDIZES - "
        f"diese Gold-Tabelle liegt nirgends abfragbar. Eintrag in INDIZES "
        f"ergaenzen, mit Schluessel und verteilung.")
    # Die andere Haelfte: Kein Index ohne Quelle im Release. Bis zum
    # 14.10.2026 stand hier "steht nicht in gold_pipeline.TABELLEN", und
    # das war dasselbe, solange jeder Index eine Gold-Tabelle war.
    # ``rate_tract`` ist der erste, der es nicht ist - die Rate je Tract ist
    # eine Aggregation, und Gold aggregiert nicht. Geprueft wird deshalb,
    # was die Zusage immer meinte: dass die Quelle **im Release liegt**.
    from orchestration.release import VOLLSTAENDIG

    ohne_quelle = sorted(
        i.name for i in le.INDIZES
        if not any(i.quelle_im_release.startswith(f"{v}/") for v in VOLLSTAENDIG))
    assert not ohne_quelle, (
        f"{ohne_quelle} steht in INDIZES, aber die Quelle liegt in keinem "
        f"Release - orchestration.release.VOLLSTAENDIG ergaenzen oder den "
        f"Index entfernen.")
    # Und kein Name doppelt: ``NACH_NAME`` wuerde den zweiten still
    # gewinnen lassen, und ``Feld.abbildung`` entschiede nach ihm.
    assert len(geladen) == len(le.INDIZES)


def test_jeder_schluessel_ist_strukturell_eindeutig_statt_geraten():
    """Jeder Index braucht einen Schluessel, und raten gilt nicht.

    Der Schluessel wird zur Dokument-ID; darauf ruht die ganze
    Eindeutigkeitszusage des Moduls (siehe Modulkopf). Ein Index ohne
    Schluessel haette lauter Dokumente mit der ID ``""`` - genau eines am
    Ende.
    """
    for index in le.INDIZES:
        assert index.schluessel, f"{index.name} hat keinen Schluessel"
        assert len(set(index.schluessel)) == len(index.schluessel), index.name
        assert index.verteilung, (
            f"{index.name} hat keine verteilung - 'composite' ohne Quellen "
            f"ist keine Frage, und der Abgleich pruefte nur die Zeilenzahl")


def test_jeder_index_hat_eine_quelle_im_release():
    """Die Quelle muss im Release liegen - nicht zwingend in Gold.

    Bis zum 14.10.2026 stand hier ``gold/dataset={name}/``, und das war
    dasselbe, solange jeder Index eine Gold-Tabelle war. ``rate_tract`` ist
    der erste, der es nicht ist: Die Rate je Tract ist eine Aggregation, und
    Gold aggregiert nicht (AGENTS.md). Geprueft wird deshalb, was die Zusage
    immer meinte - dass ein Release die Quelle mitbringt. Der Dateiname
    bleibt verlangt: Ein Praefix allein waere ein Verzeichnis.
    """
    from orchestration.release import VOLLSTAENDIG

    for index in le.INDIZES:
        quelle = index.quelle_im_release
        assert quelle.endswith("/part-0001.parquet"), index.name
        assert any(quelle == f"{v}/part-0001.parquet" for v in VOLLSTAENDIG), (
            f"{index.name}: '{quelle}' liegt in keinem Release - "
            f"orchestration.release.VOLLSTAENDIG ergaenzen.")
        assert index.name in quelle, (
            f"{index.name}: die Quelle '{quelle}' traegt den Indexnamen "
            f"nicht - zwei Indizes aus derselben Datei waeren ein Versehen.")


def test_kein_index_gruppiert_ueber_eine_ortsspalte():
    for index in le.INDIZES:
        # Die Spalten gehen im Ortsfeld auf; eine Gruppierung darueber liefe
        # ins Leere, ohne dass es auffiele.
        assert not set(index.verteilung) & set(index.geo or ())


@pytest.mark.referenzstand
def test_fuer_jede_spalte_jedes_index_ist_ein_typ_entschieden():
    """Die Frage, die kein Doppel beantworten kann.

    Traegt Gold eine Spalte, fuer die niemand entschieden hat, was sie in
    Elasticsearch sein soll? Deshalb gegen das gebaute Release und nicht
    gegen das Beispiel.
    """
    wurzel = Path("data")
    kennung, verzeichnis = le.aktuelles_release(wurzel)
    for index in le.INDIZES:
        parquet = le.quelle(verzeichnis, index)
        # Wirft, sobald eine Spalte keinen Typ oder keine Entscheidung hat.
        abb = le.mapping(le.felder(parquet, index.name), index)
        vorhanden = set(abb["mappings"]["properties"])
        erwartet = {f.name for f in le.felder(parquet, index.name)}
        if index.geo:
            erwartet = (erwartet - set(index.geo)) | {"standort"}
        assert vorhanden == erwartet, f"{index.name} in Release {kennung}"


@pytest.mark.referenzstand
def test_die_rate_je_1000_einwohner_ist_aus_elasticsearch_allein_rechenbar():
    """Zaehler, Zeiger und Nenner - alle drei im selben Speicher.

    Vor Vertrag 6 trug ``dim_tract`` die Einwohnerzahl. Heute traegt
    ``fact_offense`` mit ``population_vintage`` nur den **Zeiger** auf den
    richtigen Nenner; der Nenner selbst steht in ``dim_tract_acs``. Lag diese
    Tabelle in keinem Index, fehlte Kibana genau er - und FR-27 und FR-31
    verlangen die Rate je 1'000 Einwohner. Das ist der Grund, aus dem alle
    sechs Tabellen hier liegen, und er gehoert gemessen.
    """
    wurzel = Path("data")
    kennung, verzeichnis = le.aktuelles_release(wurzel)

    def spalten(name: str) -> set[str]:
        index = le.NACH_NAME[name]
        return {f.name for f in le.felder(le.quelle(verzeichnis, index), name)}

    fakt, acs, tract = (spalten(n) for n in
                        ("fact_offense", "dim_tract_acs", "dim_tract"))
    assert {"offense_id", "tract_geoid", "population_vintage"} <= fakt, kennung
    assert {"geoid", "vintage", "population"} <= acs, kennung
    # Der Zeiger zeigt auf das Paar, das ``dim_tract_acs`` eindeutig macht -
    # sonst waere nicht entscheidbar, welche der vier Zeilen je Tract gilt.
    assert le.NACH_NAME["dim_tract_acs"].schluessel == ("geoid", "vintage")
    # Und die Einwohnerzahl steht genau einmal: Traegt ``dim_tract`` sie
    # wieder, gibt es zwei Nenner und keine Auskunft darueber, welcher gilt.
    assert "population" not in tract, (
        "dim_tract traegt wieder eine Einwohnerzahl - dann liegen zwei "
        "Nenner im Index, und population_vintage zeigt nur auf einen")


@pytest.mark.referenzstand
def test_zeit_und_zahlen_sind_im_index_filterbar():
    """Was die neuen drei Indizes koennen muessen, Spalte fuer Spalte.

    ``date`` als Datumstyp (sonst waere kein Zeitfilter in Kibana moeglich),
    ``year_is_complete`` als Wahrheitswert (2025 und 2026 sind unvollstaendig,
    und das muss filterbar sein), ``quality_flags`` als mehrwertige Kennung,
    die Einwohnerzahl als Ganzzahl.
    """
    _, verzeichnis = le.aktuelles_release(Path("data"))

    def eigenschaften(name: str) -> dict:
        index = le.NACH_NAME[name]
        parquet = le.quelle(verzeichnis, index)
        return le.mapping(le.felder(parquet, name), index)["mappings"]["properties"]

    kalender = eigenschaften("dim_date")
    assert kalender["date"] == {"type": "date"}
    assert kalender["year_is_complete"] == {"type": "boolean"}

    wetter = eigenschaften("dim_city_day")
    assert wetter["date"] == {"type": "date"}
    # Elasticsearch kennt keinen Listentyp: ein Feld, ein Typ, viele Werte.
    assert wetter["quality_flags"] == {"type": "keyword"}

    acs = eigenschaften("dim_tract_acs")
    assert acs["population"] == {"type": "long"}
    assert acs["poverty_rate"] == {"type": "double"}
