"""Haelt ``docker-compose.srv01.yml`` an den Zusagen des Serverbetriebs.

Die Beschreibung des Serverbetriebs ist die eine Datei, deren Fehler man erst
im Betrieb sieht: Ein fehlendes Speicherlimit faellt auf, wenn eine Maschine
mit fuenfzehn fremden Diensten anfaengt auszulagern; ein versehentliches
Traefik-Label an einem Datenspeicher, wenn ihn jemand findet. Beides
sind keine Abstuerze, sondern Zustaende - und genau deshalb stehen sie hier
als Tests.

Geprueft wird **jede Zeile der Matrix** aus dem Plan:

* jeder Dienst hat eine Speichergrenze, und es ist die am 6.10.2026 auf
  ``srv01`` **gemessene** (NFR-5, FR-13);
* die Summe passt in das Gemessene - Dauerbetrieb plus das groessere
  Zeitweilige;
* der Pipeline-Dienst traegt weder ``ports:`` noch ein Traefik-Label noch
  ``unless-stopped`` (FR-9);
* das Dashboard ersetzt seit dem 1.11.2026 Elasticsearch und Kibana, liest
  den Eimer und haengt keinen Datentraeger ein (C-9);
* jeder Webdienst traegt die vollstaendigen Labels samt der
  ``X-Forwarded-Proto``-Middleware (FR-10);
* Jupyter haengt ``data/`` als ``:ro`` ein und liest die DuckDB aus dem
  Release (E9);
* die Hostnamen folgen ``urbancrime-<dienst>.datenwerft.ch`` (FR-22);
* keine Zeile traegt ein Geheimnis (FR-18).

PyYAML ist inzwischen in den Entwicklungsabhaengigkeiten deklariert. Der
BaseLoader laesst Skalare wie bisher als Zeichenketten stehen und liest auch
die fuer E-5 benoetigte lange Volume-Syntax. Flussfolgen fuer Befehle bleiben
als Rohtext erhalten, damit die bestehenden Befehlspruefungen gleich arbeiten.

Dass der Leser nicht etwas anderes sieht als Docker, ist am 6.10.2026
nachgemessen worden: ``docker compose config --format json`` ueber alle
Profile, verglichen wurden Dienstnamen, Speichergrenzen, Netze, Labels,
Umgebungswerte, ``ports`` und die Datentraeger - alles gleich. Als Test
gehoert der Vergleich nicht hierher, weil er ohne Docker uebersprungen wuerde
und damit genau dort nichts prueft, wo die Suite laeuft; als Messung steht er
hier. Der Befehl steht in der Verifikation des Plans und laesst sich
jederzeit wiederholen.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRV01 = PROJECT_ROOT / "docker-compose.srv01.yml"
ENTWICKLUNG = PROJECT_ROOT / "docker-compose.yml"
DOKUMENT = PROJECT_ROOT / "docs" / "storage-architektur.md"

# --------------------------------------------------------------------------
# Die gemessenen Grenzen (FR-13, am 6.10.2026 auf srv01 gemessen)
# --------------------------------------------------------------------------
# Diese Zahlen stehen hier als Literal, weil sie eine **Messung** sind und
# nicht aus dem Code folgen. Wer sie aendert, hat entweder neu gemessen - dann
# gehoert das Datum mitgeaendert - oder er raet.
GRENZEN_MIB = {
    # 1.11.2026 (C-9): Elasticsearch (1'792) und Kibana (1'024) sind auf srv01
    # durch das eigene Dashboard ersetzt. Auf srv01 gemessen: Spitze 429 MiB
    # beim ersten Laden, danach rund 300 (lokal 476 beziehungsweise 412).
    "dashboard": 640,
    # Am 16.10.2026 stand hier fuer einen Tag 2'048, weil ich die Grenze fuer
    # die Ursache hielt. Der Bau braucht gestuft 256 MB; zurueck auf die
    # Messung. Begruendung in der Compose-Datei.
    "pipeline": 1280,        # 1,25 GiB; zeitweilig
    # 30.10.2026: Der Konsolen-Worker fuehrt dieselben Pipelines aus wie
    # ``pipeline`` und nie gleichzeitig mit ihr (eine Sperre) - dieselbe
    # Messung, derselbe Platz.
    "worker": 1280,
    # 30.10.2026: Webdienst der Konsole, lokal gemessen 92 MiB nach 210
    # Anfragen (gunicorn, ein Prozess, vier Threads); die Reserve deckt das
    # Impact-Archiv, das zweimal im Speicher liegt. Auf srv01 nachzumessen.
    "admin": 160,
    "jupyter": 768,          # 768 MiB; zeitweilig
    # 12.10.2026, FR-31: ein nginx, das eine statische Datei ausliefert. Die
    # 32 MiB sind nicht gemessen, sondern das obere Ende der bekannten
    # Spanne (16-32) - gemessen ist der **Platz**, in den sie passen muessen:
    # 229 MiB waren frei gegen das am 6.10.2026 Verfuegbare, mit diesem
    # Dienst sind es 197.
    "start": 32,
}

# Verfuegbar waren am 6.10.2026 **4'325 MiB** neben 31 Containern. Dazu kommt,
# was das Deckeln von cadvisor auf 256 MiB freigibt: Es belegte 1'047 MiB,
# 29 % des gesamten Containerspeichers. Der Plan nennt die Freigabe mit
# **792 MiB**; gerechnet sind es 791. Die Pruefung unten haelt mit beiden, der
# Abstand ist tausendfach groesser als die Rundung.
VERFUEGBAR_MIB = 4325
CADVISOR_FREI_MIB = 792

# Variablennamen, die ein Geheimnis tragen koennen. Ein Wert dahinter waere in
# dieser Datei ein committetes Geheimnis (FR-18).
GEHEIM = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL)")


# --------------------------------------------------------------------------
# Ein Leser fuer die Teilmenge von YAML, die diese Datei benutzt
# --------------------------------------------------------------------------


def lade(text: str) -> dict:
    """YAML mit String-Skalaren und unveraenderten Inline-Befehlsfolgen."""
    import yaml

    class Leser(yaml.BaseLoader):
        def construct_sequence(self, node, deep=False):
            if node.flow_style:
                return text[node.start_mark.index:node.end_mark.index]
            return super().construct_sequence(node, deep=deep)

    return yaml.load(text, Loader=Leser)


def mount_info(eintrag):
    """Kurze und lange Compose-Volume-Syntax fuer die bestehenden Waechter."""
    if isinstance(eintrag, dict):
        return (eintrag["source"], eintrag["target"],
                str(eintrag.get("read_only", "false")).lower() == "true")
    teile = eintrag.split(":")
    return teile[0], teile[1], "ro" in teile[2:]


BEISPIEL = """
name: probe
services:
  eins:
    image: a:1
    mem_limit: 512m
    environment:
      WERT: "ja"
      GEHEIM:
      URL: http://host:9200
    networks:
      - proxy
    labels:
      traefik.enable: "true"
    healthcheck:
      test: ["CMD", "x"]
      retries: 3
volumes:
  daten:
"""


def test_der_leser_liest_was_er_lesen_soll():
    """Der Leser ist selbst Code und braucht deshalb einen Waechter.

    Geprueft wird genau, was die Datei an Formen benutzt: verschachtelte
    Abbildungen, eine Liste, ein Schluessel ohne Wert, ein Wert mit
    Doppelpunkt darin, eine Flussfolge und ein Abschnitt am Dateiende.
    """
    gelesen = lade(BEISPIEL)
    assert gelesen["name"] == "probe"
    dienst = gelesen["services"]["eins"]
    assert dienst["image"] == "a:1"
    assert dienst["mem_limit"] == "512m"
    assert dienst["environment"] == {"WERT": "ja", "GEHEIM": "", "URL": "http://host:9200"}
    assert dienst["networks"] == ["proxy"]
    assert dienst["labels"]["traefik.enable"] == "true"
    assert dienst["healthcheck"] == {"test": '["CMD", "x"]', "retries": "3"}
    assert gelesen["volumes"] == {"daten": ""}


@pytest.fixture(scope="module")
def text() -> str:
    assert SRV01.is_file(), f"{SRV01} fehlt - die Beschreibung des Serverbetriebs"
    return SRV01.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def beschreibung(text) -> dict:
    return lade(text)


@pytest.fixture(scope="module")
def dienste(beschreibung) -> dict:
    gefunden = beschreibung["services"]
    assert gefunden, "keine Dienste in der Beschreibung"
    return gefunden


def mib(grenze: str) -> int:
    """``1792m`` -> 1792. Docker rechnet k/m/g in Potenzen von 1024."""
    treffer = re.fullmatch(r"(\d+)([kmg])?", grenze.strip(), re.I)
    assert treffer, f"keine lesbare Speicherangabe: {grenze!r}"
    zahl = int(treffer.group(1))
    einheit = (treffer.group(2) or "b").lower()
    return {"b": zahl // 1024 // 1024, "k": zahl // 1024, "m": zahl, "g": zahl * 1024}[einheit]


# --------------------------------------------------------------------------
# Jeder Dienst hat eine Grenze - und es ist die gemessene
# --------------------------------------------------------------------------


def test_jeder_dienst_hat_eine_speichergrenze(dienste):
    """NFR-5: *Ein Dienst ohne Grenze startet nicht.*

    Der Test nennt den Dienst, nicht nur die Tatsache - sonst sucht ihn
    jemand in einer Datei mit vier Diensten und zweihundert Zeilen.
    """
    ohne = sorted(name for name, d in dienste.items() if not d.get("mem_limit"))
    assert not ohne, (
        f"Dienste ohne mem_limit: {ohne}. Auf srv01 sind 7,7 GiB die bindende "
        "Grenze, und ein Dienst ohne Limit nimmt sich, was er findet."
    )


def test_die_grenzen_sind_die_gemessenen(dienste):
    """FR-13, am 6.10.2026 gemessen - nicht die Schaetzung von vorher.

    Die Schaetzung lag 1'307 MiB ueber dem Verfuegbaren. Steht hier wieder
    eine andere Zahl, ist sie entweder neu gemessen oder geraten; dieser Test
    verlangt die Entscheidung.
    """
    assert set(dienste) == set(GRENZEN_MIB), (
        f"Dienste und gemessene Grenzen passen nicht zusammen: "
        f"{sorted(set(dienste) ^ set(GRENZEN_MIB))}"
    )
    falsch = {name: d["mem_limit"] for name, d in dienste.items()
              if mib(d["mem_limit"]) != GRENZEN_MIB[name]}
    assert not falsch, f"abweichend von der Messung vom 6.10.2026: {falsch}"


def test_jede_grenze_nennt_ihre_herkunft(text, dienste):
    """Eine Zahl ohne Herkunft ist in drei Wochen eine geratene.

    Verlangt wird, dass in den Zeilen vor jedem ``mem_limit`` die Messung
    genannt ist - FR-13 und ein Datum. Seit dem 30.10.2026 nicht mehr nur der
    6.10.: Die Konsole hat eine eigene Messung, und die Regel verlangt die
    Herkunft, nicht ein bestimmtes Datum.
    """
    zeilen = text.splitlines()
    stellen = [i for i, z in enumerate(zeilen) if z.strip().startswith("mem_limit:")]
    assert len(stellen) == len(dienste), (
        f"{len(stellen)} mem_limit-Zeilen bei {len(dienste)} Diensten"
    )
    for i in stellen:
        umfeld = "\n".join(zeilen[max(0, i - 6):i])
        assert "FR-13" in umfeld and re.search(r"\b\d{1,2}\.\d{1,2}\.2026\b", umfeld), (
            f"Zeile {i + 1} ({zeilen[i].strip()}) nennt die Herkunft ihrer Grenze "
            "nicht - erwartet sind FR-13 und das Messdatum in den Zeilen darueber"
        )


def test_die_summe_der_grenzen_passt_in_das_gemessene(dienste):
    """Dauerbetrieb plus das groessere Zeitweilige - nachgerechnet.

    Die Einteilung kommt aus der Datei selbst und nicht aus einer Liste hier:
    Ein Dienst mit ``profiles`` startet nicht mit ``up -d``, ist also
    zeitweilig. Wer ein Profil entfernt, macht aus einem zeitweiligen Dienst
    einen dauernden - und dieser Test rechnet das mit.
    """
    dauernd = {n: mib(d["mem_limit"]) for n, d in dienste.items() if not d.get("profiles")}
    zeitweilig = {n: mib(d["mem_limit"]) for n, d in dienste.items() if d.get("profiles")}
    assert dauernd and zeitweilig, (
        f"Einteilung leer - dauernd {sorted(dauernd)}, zeitweilig {sorted(zeitweilig)}"
    )
    summe = sum(dauernd.values()) + max(zeitweilig.values())
    budget = VERFUEGBAR_MIB + CADVISOR_FREI_MIB
    assert summe <= budget, (
        f"{summe} MiB verlangt, {budget} MiB vorhanden "
        f"({VERFUEGBAR_MIB} gemessen frei + {CADVISOR_FREI_MIB} aus dem "
        f"gedeckelten cadvisor). Dauerbetrieb {dauernd}, zeitweilig {zeitweilig}."
    )


def test_der_dauerbetrieb_ist_entschieden(dienste):
    """Die Zusage von FR-13, als Einteilung und nicht nur als Satz.

    **Bis zum 12.10.2026 waren es zwei.** Dieser Test hiess
    ``test_der_dauerbetrieb_ist_elasticsearch_und_kibana`` und hielt genau
    das fest. FR-31 verlangt eine Einstiegsseite, die erreichbar ist - und
    was erreichbar sein soll, muss laufen, wenn jemand die Adresse aufruft.
    Aus zwei dauernden Diensten werden damit drei.

    **Das ist eine Entscheidung und keine Nebenwirkung.** Sie steht hier und
    nicht nur in einer geaenderten Zahl, weil der Dauerbetrieb die Groesse
    ist, an der die Rechnung von FR-13 haengt: Elasticsearch, Kibana und
    ``start`` belegen zusammen 2'848 MiB, das groessere Zeitweilige 1'280 -
    **4'128** von 4'325 gemessen verfuegbaren MiB, also **197 MiB frei**
    (vorher 4'096 und 229). Ein nginx passt mit 16-32 MiB hinein, und nichts,
    was wesentlich mehr braucht. Wer einen vierten dauernden Dienst dazulegt,
    faellt hier durch und soll genau das: nachrechnen, nicht ein Profil
    weglassen.

    **Am 30.10.2026 der vierte: der Webdienst der Engineering-Konsole.**
    Nachgerechnet: 2'848 + 160 = 3'008 MiB dauernd, dazu das groessere
    Zeitweilige mit 1'280 - **4'288** von 4'325, also 37 MiB frei. Der
    Konsolen-Worker ist **nicht** dabei: Er laeuft getaktet als Stapellauf
    (docker/srv01-konsole-takt.sh), weil er die Pipelines ausfuehrt und deren
    1'280 MiB dauernd belegt haette - rund 1,3 GiB ueber dem Budget.

    **Am 1.11.2026 fallen zwei und kommt einer (C-9).** Elasticsearch und
    Kibana weichen dem eigenen Dashboard: 640 + 160 + 32 = 832 MiB dauernd,
    mit dem Zeitweiligen **2'112** von 4'325 - rund 2,2 GiB frei statt 37.
    Entschieden ist nur der Server; lokal bleiben beide in
    docker-compose.yml (``test_die_entwicklungsfassung_bleibt_lauffaehig``).
    """
    dauernd = sorted(n for n, d in dienste.items() if not d.get("profiles"))
    assert dauernd == ["admin", "dashboard", "start"], (
        f"Dauerbetrieb ist {dauernd}; FR-13 rechnet seit dem 1.11.2026 mit "
        "dem Dashboard (640 MiB), der Einstiegsseite (32 MiB) und dem "
        "Konsolen-Webdienst (160 MiB); Pipeline, Konsolen-Worker und Jupyter "
        "sind zeitweilig"
    )


# --------------------------------------------------------------------------
# Der Pipeline-Dienst: ein Stapellauf, kein Webdienst (FR-9)
# --------------------------------------------------------------------------


def test_die_pipeline_hat_keinen_port_und_kein_label(dienste):
    pipeline = dienste["pipeline"]
    assert "ports" not in pipeline, (
        "der Pipeline-Dienst hat ein ports: - er ist ein Stapellauf, und auf "
        "srv01 gibt es fuer Webdienste ueberhaupt kein ports:"
    )
    assert not pipeline.get("labels"), (
        f"Traefik-Label am Stapellauf: {pipeline.get('labels')}"
    )


def test_die_pipeline_laeuft_einmal_durch(dienste):
    """*Mit unless-stopped wird aus einem Wochenlauf eine Dauerschleife.*"""
    neustart = dienste["pipeline"].get("restart", "")
    assert "unless-stopped" not in neustart and "always" not in neustart, (
        f"restart: {neustart!r} - der Lauf wuerde endlos neu starten und jede "
        "Runde neue Bronze-Laeufe anhaeufen"
    )
    assert neustart.startswith("on-failure") or neustart in {"no", '"no"'}, (
        f"restart: {neustart!r} - erwartet ist on-failure oder no (FR-9)"
    )


def test_die_pipeline_ist_nicht_im_netz_proxy(dienste):
    assert "proxy" not in dienste["pipeline"]["networks"], (
        "der Stapellauf liegt im Netz proxy - dort gehoeren nur geroutete "
        "Webdienste hin"
    )


# --------------------------------------------------------------------------
# Das Dashboard statt Elasticsearch und Kibana (1.11.2026, C-9)
# --------------------------------------------------------------------------


def test_srv01_traegt_weder_elasticsearch_noch_kibana(beschreibung):
    """Entschieden ist der Server, nicht das Projekt.

    Bis zum 1.11.2026 hielt ``test_beide_fassungen_binden_dieselbe_elastic_version``
    die beiden Fassungen auf derselben Elastic-Version. Mit den Diensten auf
    srv01 entfiel der Gegenstand; geblieben ist die Gegenrichtung: Kommt einer
    der beiden zurueck, ohne dass FR-13 neu gerechnet ist, faellt es hier auf
    und nicht erst an ``docker stats``.
    """
    zurueck = sorted({"elasticsearch", "kibana"} & set(beschreibung["services"]))
    assert not zurueck, f"wieder in der Serverfassung: {zurueck}"
    alte = sorted({"elasticsearch-daten", "kibana-daten"}
                  & set(beschreibung.get("volumes") or {}))
    assert not alte, f"Datentraeger ohne Dienst: {alte}"


def test_das_dashboard_liest_den_eimer_und_haengt_nichts_ein(dienste):
    """Es schreibt nichts, also braucht es keinen Datentraeger.

    ``arbeitsdaten`` traegt waehrend eines Laufs einen halben Zwischenstand
    und danach nur, was ``holen --einsetzen`` hinlegt. Der Eimer ist der
    Bestand; von dort liest das Dashboard Gold und ``comparison_month``.
    """
    dashboard = dienste["dashboard"]
    assert "volumes" not in dashboard, dashboard.get("volumes")
    umgebung = dashboard["environment"]
    assert umgebung["STORAGE_BACKEND"] == "s3"
    for variable in ("S3_ENDPOINT", "S3_BUCKET", "S3_ACCESS_KEY", "S3_SECRET_KEY"):
        assert variable in umgebung, f"{variable} erreicht das Dashboard nicht"


def test_das_dashboard_laeuft_in_einem_prozess(dienste):
    """Mehrere Prozesse hielten den Bestand je einmal und luden ihn je
    einmal - die Ladespitze ist das Teure, und die Grenze rechnet mit einer."""
    befehl = dienste["dashboard"]["command"]
    assert befehl[befehl.index("--workers") + 1] == "1", befehl
    assert befehl[-1] == "serving.dashboard.app:create_app()", befehl


def test_der_stapellauf_findet_das_dashboard(dienste):
    """``pruefe_stand --betrieb server`` fragt das Dashboard nach seinem
    Stand; Pipeline und Worker muessen es im Stapelnetz erreichen."""
    for name in ("pipeline", "worker"):
        umgebung = dienste[name]["environment"]
        assert umgebung.get("SERVING_BETRIEB") == "server", name
        assert umgebung.get("DASHBOARD_URL") == "http://dashboard:8050", name
        assert "ELASTICSEARCH_URL" not in umgebung and "KIBANA_URL" not in umgebung, (
            f"{name}: zeigt noch auf einen Dienst, den es hier nicht gibt")
        assert set(dienste[name]["networks"]) & set(dienste["dashboard"]["networks"])


# --------------------------------------------------------------------------
# Die Webdienste: vollstaendige Labels (FR-10)
# --------------------------------------------------------------------------


def webdienste(dienste: dict) -> dict:
    return {n: d for n, d in dienste.items()
            if (d.get("labels") or {}).get("traefik.enable") == "true"}


def test_es_gibt_mindestens_einen_webdienst(dienste):
    """Sonst prueft die Reihe darunter nichts, ohne rot zu werden."""
    assert "dashboard" in webdienste(dienste), (
        "das Dashboard ist nicht als Webdienst beschriftet - es zeigt die "
        "Daten und muss erreichbar sein"
    )


def test_jeder_webdienst_traegt_die_vollstaendigen_labels(dienste):
    """Ein halber Satz Labels macht den Dienst privat, nur unbemerkt."""
    fehlend = {}
    for name, dienst in webdienste(dienste).items():
        labels = dienst["labels"]
        verlangt = [
            "traefik.docker.network",
            f"traefik.http.routers.urbancrime-{name}.rule",
            f"traefik.http.routers.urbancrime-{name}.entrypoints",
            f"traefik.http.routers.urbancrime-{name}.middlewares",
            f"traefik.http.routers.urbancrime-{name}.service",
            f"traefik.http.services.urbancrime-{name}.loadbalancer.server.port",
        ]
        luecken = [v for v in verlangt if v not in labels]
        if luecken:
            fehlend[name] = luecken
    assert not fehlend, f"unvollstaendige Traefik-Labels: {fehlend}"


def test_jeder_webdienst_traegt_die_x_forwarded_proto_middleware(dienste):
    """*Ohne sie baut ein Dienst http://-Weiterleitungen hinter dem Edge-TLS.*

    Geprueft wird beides: dass die Middleware definiert ist **und** dass der
    Router sie benutzt. Eine definierte, aber nicht verwendete Middleware ist
    der Fehler, den man nicht sieht.
    """
    for name, dienst in webdienste(dienste).items():
        labels = dienst["labels"]
        definiert = [k for k, v in labels.items()
                     if k.endswith("headers.customrequestheaders.X-Forwarded-Proto")
                     and v == "https"]
        assert definiert, (
            f"{name}: keine X-Forwarded-Proto: https-Middleware definiert"
        )
        benutzt = labels[f"traefik.http.routers.urbancrime-{name}.middlewares"]
        namen = [k.split(".")[3] for k in definiert]
        assert benutzt in namen, (
            f"{name}: der Router benutzt {benutzt!r}, definiert ist {namen}"
        )


def test_jeder_webdienst_liegt_im_netz_proxy(dienste):
    for name, dienst in webdienste(dienste).items():
        assert "proxy" in dienst["networks"], (
            f"{name} traegt Traefik-Labels, liegt aber nicht im Netz proxy - "
            "Traefik findet es dann nicht"
        )
        assert dienst["labels"]["traefik.docker.network"] == "proxy"


def test_kein_webdienst_veroeffentlicht_einen_port(dienste):
    """*Avoid ports: for web applications* - es umgeht den ganzen Eingang."""
    mit_port = sorted(n for n in webdienste(dienste) if "ports" in dienste[n])
    assert not mit_port, f"Webdienste mit ports: {mit_port}"


def test_der_geroutete_port_ist_der_container_port(dienste):
    """Punkt 3 der Serververeinbarung - und ein Fehler, der still 502 ergibt."""
    erwartet = {"dashboard": "8050", "jupyter": "8888", "start": "80", "admin": "8765"}
    for name, dienst in webdienste(dienste).items():
        port = dienst["labels"][
            f"traefik.http.services.urbancrime-{name}.loadbalancer.server.port"]
        assert port == erwartet[name], f"{name}: Port {port}, erwartet {erwartet[name]}"


# --------------------------------------------------------------------------
# Die Hostnamen (FR-22) und die Tunnel-Route (FR-12)
# --------------------------------------------------------------------------


HOSTREGEL = re.compile(r"^Host\(`([^`]+)`\)$")


def test_die_hostnamen_folgen_dem_muster(dienste):
    """``urbancrime-<dienst>.datenwerft.ch`` - damit **eine**
    Access-Anwendung ueber ``urbancrime-*`` jeden kuenftigen Dienst mitdeckt.

    ``infra-*`` ist der Infrastruktur vorbehalten, und die dortige
    Wildcard-Policy greift fuer dieses Projekt nicht (FR-21).
    """
    gefunden = []
    for name, dienst in webdienste(dienste).items():
        regel = dienst["labels"][f"traefik.http.routers.urbancrime-{name}.rule"]
        treffer = HOSTREGEL.match(regel)
        assert treffer, f"{name}: keine einfache Host-Regel: {regel!r}"
        host = treffer.group(1)
        gefunden.append(host)
        assert host == f"urbancrime-{name}.datenwerft.ch", (
            f"{name}: Hostname {host!r} folgt nicht urbancrime-<dienst>.datenwerft.ch"
        )
    assert not [h for h in gefunden if h.startswith("infra-")], (
        f"infra-* ist der Infrastruktur vorbehalten: {gefunden}"
    )


def test_die_tunnel_route_zeigt_nie_auf_einen_oeffentlichen_hostnamen():
    """FR-12 - und es ist eine Cloudflare-Einstellung, keine Compose-Zeile.

    *Pointing the tunnel to http://example.datenwerft.ch sends traffic back
    through Cloudflare and can produce a loop or a 403 response.* Bewachen
    laesst sich dann nur die Anleitung: Sie muss ``http://traefik:80`` nennen
    und darf keinen oeffentlichen Hostnamen als Ursprung hinschreiben.
    """
    doku = DOKUMENT.read_text(encoding="utf-8")
    abschnitt = doku[doku.index("## 16 ·"):]
    assert "http://traefik:80" in abschnitt, (
        "Abschnitt 16 nennt die Tunnel-Route nicht - ohne sie richtet sie "
        "jemand nach Gefuehl ein"
    )
    falsch = re.findall(r"Service URL:\s*\S*urbancrime\S*", abschnitt)
    assert not falsch, f"oeffentlicher Hostname als Tunnel-Ursprung: {falsch}"


# --------------------------------------------------------------------------
# Jupyter: lesend (E9)
# --------------------------------------------------------------------------


def test_jupyter_haengt_data_schreibgeschuetzt_ein(dienste):
    """*Damit kann 12_detroit_bronze_ingestion strukturell nicht in den echten
    Bestand schreiben* - der Schreibversuch scheitert am Dateisystem."""
    daten = [v for v in dienste["jupyter"]["volumes"] if ":/app/data" in v]
    assert len(daten) == 1, f"kein eindeutiger data/-Einhaengepunkt: {daten}"
    assert daten[0].endswith(":ro"), (
        f"{daten[0]} ist nicht schreibgeschuetzt - E9 verlangt :ro"
    )


def test_jupyter_hat_einen_beschreibbaren_arbeitsbereich(dienste):
    """Lesend heisst nicht unbenutzbar: Ein Notebook muss sich speichern lassen."""
    beschreibbar = [v for v in dienste["jupyter"]["volumes"]
                    if not mount_info(v)[2] and not mount_info(v)[1].startswith("/app/data")]
    assert beschreibbar, (
        "Jupyter hat nur schreibgeschuetzte Einhaengepunkte - dann laesst sich "
        "kein Notebook speichern"
    )


def test_jupyter_liest_die_duckdb_aus_dem_release(text):
    """E9, ausdruecklich: die **selbstaendige** Datenbank aus dem Release.

    ``data/serving/analyse.duckdb`` traegt 17 Sichten mit absoluten Pfaden auf
    den Entwicklungsrechner und ist im Container wertlos. Der Unterschied
    laesst sich in Compose nur als Weg und als Begruendung hinschreiben -
    bewacht wird deshalb beides.
    """
    abschnitt = text[text.index("  jupyter:"):]
    assert "releases/release=" in abschnitt, (
        "der Jupyter-Block sagt nicht, dass die Datenbank aus dem Release kommt"
    )
    assert "data/serving/analyse.duckdb" in abschnitt, (
        "der Jupyter-Block nennt nicht, welche Datenbank gerade **nicht** "
        "gemeint ist - und das ist die, die naheliegt"
    )


def test_kein_dienst_haengt_die_entwicklungsdatenbank_ein(beschreibung, dienste):
    """Sie ist rechnerlokal und waere im Container stillschweigend leer."""
    verirrt = []
    for name, dienst in dienste.items():
        for einhang in dienst.get("volumes") or []:
            if "serving/analyse.duckdb" in mount_info(einhang)[0]:
                verirrt.append(f"{name}: {einhang}")
    assert not verirrt, f"data/serving/analyse.duckdb eingehaengt: {verirrt}"
    assert "arbeitsdaten" in beschreibung["volumes"]


# --------------------------------------------------------------------------
# Die Einstiegsseite: ausgeliefert, nicht eingehaengt (FR-31)
# --------------------------------------------------------------------------


def test_die_startseite_kommt_aus_einem_datentraeger(dienste, beschreibung):
    """*Ein Bind-Mount aus dem Repository zeigte das Release des letzten
    ``git pull``, nicht das geladene.*

    Geprueft wird beides, was den Unterschied macht: dass die Seite aus einem
    **benannten** Datentraeger kommt - demselben Weg, den die Pipeline fuer
    ``arbeitsdaten`` schon geht - und dass der Dienst sie nur **liest**. Ein
    schreibender nginx waere der einzige Ort im Stapel, an dem ein Webdienst
    etwas veraendern koennte.
    """
    einhaenge = dienste["start"]["volumes"]

    # **Gezaehlt wird, was unter der Dokumentwurzel liegt**, und nicht, wie
    # viele Einhaengungen es gibt. Die erste Fassung zaehlte alle und war
    # damit nicht ueber ihre eigene Begruendung hinaus richtig: Gefaehrlich
    # ist, was nginx *ausliefert*. Am 18.10.2026 kam eine zweite Einhaengung
    # dazu - die Auslieferungsregeln nach ``/etc/nginx/conf.d/`` -, und die
    # liegt ausserhalb der Wurzel. Der Waechter haette eine richtige
    # Aenderung gemeldet, und das ist die Sorte, die abgeschaltet wird.
    WURZEL = "/usr/share/nginx/html"
    unter_wurzel = [e for e in einhaenge
                    if e.split(":")[1] == WURZEL
                    or e.split(":")[1].startswith(WURZEL + "/")]
    assert len(unter_wurzel) == 1, (
        f"unter {WURZEL} haengt {unter_wurzel} - eine Seite braucht genau "
        "einen Einhaengepunkt, und jeder weitere ist etwas, das nginx "
        "mitausliefert"
    )
    quelle, _, rest = unter_wurzel[0].partition(":")
    assert quelle in beschreibung["volumes"], (
        f"{quelle!r} ist kein benannter Datentraeger dieses Stapels - ein "
        "Bind-Mount zeigte das Release des letzten git pull"
    )
    assert rest.endswith(":ro"), (
        f"{unter_wurzel[0]} ist nicht schreibgeschuetzt"
    )
    # Und jede weitere Einhaengung liest ebenfalls nur.
    for weitere in [e for e in einhaenge if e not in unter_wurzel]:
        assert weitere.endswith(":ro"), (
            f"{weitere} ist nicht schreibgeschuetzt - ein schreibender nginx "
            f"waere der einzige Ort im Stapel, an dem ein Webdienst etwas "
            f"veraendern koennte")


def test_der_healthcheck_der_startseite_prueft_unsere_seite(dienste):
    """HTTP 200 genuegt hier nicht - es kommt auch ohne Datenlauf zurueck.

    Am 12.10.2026 am laufenden Docker nachgestellt: Ein leerer benannter
    Datentraeger wird beim ersten Start **aus dem Abbild befuellt**, und das
    ``:ro`` auf der lesenden Seite verhindert das nicht. Danach liegen nginx'
    eigene ``index.html`` (896 Bytes, *Welcome to nginx!*) und ``50x.html``
    darin, ``curl -fs`` antwortet mit 200, und der Dienst meldete sich
    **gesund**, ohne dass je eine Seite erzeugt worden waere - hinter Access
    ausgeliefert haette er die Willkommensseite von nginx.

    Geprueft wird deshalb ein Kennzeichen unserer Seite. ``pruefe_stand``
    daneben heisst dasselbe eine Ebene hoeher: Ein Dienst, der nicht sagen
    kann, *was* er zeigt, sagt nichts.
    """
    pruefung = dienste["start"]["healthcheck"]["test"]
    assert "serving.build_einstieg" in pruefung, (
        f"der Healthcheck prueft kein Kennzeichen unserer Seite: {pruefung}. "
        "Ein blosses HTTP 200 kommt auch von nginx' Willkommensseite, die "
        "Docker beim ersten Start in den Datentraeger legt"
    )


def test_der_stapellauf_schreibt_die_seite_in_denselben_datentraeger(dienste):
    """Sonst liefert der Dienst eine Datei aus, die niemand erneuert.

    Die Seite entsteht im Stapellauf aus dem Release - das ist die Zusage von
    FR-31, dass die ausgelieferte Seite das Release zeigt, das auf ``srv01``
    wirklich liegt. Dafuer muss derselbe Datentraeger in beiden Diensten
    stehen, und im Stapellauf **ohne** ``:ro``.
    """
    gelesen = dienste["start"]["volumes"][0].split(":")[0]
    geschrieben = [v for v in dienste["pipeline"]["volumes"]
                   if v.split(":")[0] == gelesen]
    assert geschrieben, (
        f"der Stapellauf haengt {gelesen!r} nicht ein - dann schreibt die "
        "Seite niemand, und start liefert aus, was zuletzt darin lag"
    )
    assert not geschrieben[0].endswith(":ro"), (
        f"{geschrieben[0]}: der Lauf muss die Seite schreiben koennen"
    )


# --------------------------------------------------------------------------
# DuckDB von innen (FR-61)
# --------------------------------------------------------------------------


def test_duckdb_lagert_dorthin_aus_wo_der_dienst_schreiben_darf(dienste):
    """Ein Auslagerungsverzeichnis auf einem ``:ro``-Datentraeger waere schlimmer
    als keines: DuckDB scheiterte dann beim Auslagern statt bei der Abfrage.

    ``jupyter`` haengt ``arbeitsdaten`` schreibgeschuetzt ein und hat mit
    ``jupyter-arbeit`` einen eigenen Datentraeger; ``pipeline`` schreibt in
    ``arbeitsdaten``. Geprueft wird gegen die Einhaengungen des Dienstes,
    nicht gegen eine Liste hier.
    """
    from storage.duckdb import grenzen

    for name in ("pipeline", "jupyter"):
        ziel = grenzen(dienste[name]["environment"]).get("temp_directory")
        if ziel is None:
            continue                     # der Test darueber meldet das schon
        schreibbar = []
        for einhaengung in dienste[name].get("volumes", []):
            teile = str(einhaengung).split(":")
            if len(teile) >= 2 and "ro" not in teile[2:]:
                schreibbar.append(teile[1])
        assert any(ziel.startswith(f"{pfad}/") or ziel == pfad
                   for pfad in schreibbar), (
            f"{name}: '{ziel}' liegt auf keinem beschreibbaren Datentraeger "
            f"(beschreibbar: {schreibbar})")


def test_duckdb_wird_von_innen_begrenzt_und_zwar_unterhalb_des_containers(dienste):
    """*Ohne memory_limit nimmt DuckDB rund 80 % des Arbeitsspeichers der
    Maschine* - nicht des Containers. Das Container-Limit allein toetet den
    Prozess, statt ihn zu bremsen.
    """
    from storage.duckdb import grenzen

    for name in ("pipeline", "jupyter", "dashboard"):
        umgebung = dienste[name]["environment"]
        gesetzt = grenzen(umgebung)
        assert "memory_limit" in gesetzt, (
            f"{name}: DUCKDB_MEMORY_LIMIT fehlt oder ist leer - storage.duckdb "
            "setzt dann nichts, und DuckDB rechnet mit der ganzen Maschine"
        )
        assert "threads" in gesetzt, f"{name}: DUCKDB_THREADS fehlt"
        innen = int(re.fullmatch(r"(\d+)MB", gesetzt["memory_limit"]).group(1))
        aussen = mib(dienste[name]["mem_limit"])
        assert innen < aussen, (
            f"{name}: DuckDB darf {innen} MB nehmen, der Container nur "
            f"{aussen} MiB - die innere Grenze muss darunter liegen"
        )
        # **Und ein Ausweg, sonst ist die Grenze eine Wand.** Am 16.10.2026
        # starb der Lauf bei ``silver crime_offense`` mit "854.6 MiB/854.4
        # MiB used" - das sind genau die 896 MB von oben. Ohne
        # Auslagerungsverzeichnis bricht DuckDB an seiner eigenen Grenze ab,
        # statt auf Platte auszuweichen.
        #
        # **Korrektur vom selben Tag.** Hier stand "Nachgemessen: dieselbe
        # Abfrage scheitert ohne und laeuft mit". Das war falsch - mit
        # gesetztem ``temp_directory`` ist dieselbe Abfrage zweimal weiter an
        # derselben Grenze gescheitert. Auslagern hilft, wo DuckDB auslagern
        # *kann*; dieser Plan hat offenbar einen Operator, der es nicht kann.
        # Verlangt bleibt das Verzeichnis trotzdem: Ohne ist die Grenze
        # sicher eine Wand, mit ist sie es manchmal.
        # Das Dashboard verdichtet einmal je Release und darf scheitern
        # statt auszulagern: Es hat keinen Datentraeger, und eine Spitze
        # ueber 256 MB ist dort ein Befund, kein Lauf, der verloren geht.
        if name == "dashboard":
            continue
        assert "temp_directory" in gesetzt, (
            f"{name}: DUCKDB_TEMP_DIRECTORY fehlt - die Speichergrenze ist "
            f"dann eine Wand statt einer Bremse")


# --------------------------------------------------------------------------
# Haertung, Protokolle, Geheimnisse
# --------------------------------------------------------------------------


def test_jeder_dienst_verbietet_neue_privilegien(dienste):
    ohne = sorted(name for name, d in dienste.items()
                  if "no-new-privileges:true" not in (d.get("security_opt") or []))
    assert not ohne, f"ohne no-new-privileges: {ohne}"


def test_jeder_dienst_rotiert_seine_protokolle(dienste):
    """FR-9 verlangt es fuer den Stapellauf; die Platte teilen alle."""
    ohne = sorted(name for name, d in dienste.items()
                  if not ((d.get("logging") or {}).get("options") or {}).get("max-size"))
    assert not ohne, f"ohne Logrotation: {ohne}"


def test_kein_geheimnis_steht_in_der_beschreibung(dienste):
    """FR-18: Namen ja, Werte nein.

    Ein Schluessel ohne Wert heisst in Compose *hole ihn aus der Umgebung*;
    genau so kommen die Geheimnisse aus der ignorierten ``.env`` des Stapels
    herein, ohne dass eine Zeile davon im Repository liegt.
    """
    gefunden = []
    for name, dienst in dienste.items():
        for variable, wert in (dienst.get("environment") or {}).items():
            if GEHEIM.search(variable) and wert:
                gefunden.append(f"{name}: {variable}={wert}")
    assert not gefunden, f"Geheimnis in der Compose-Datei: {gefunden}"


def test_die_geheimnisse_werden_ueberhaupt_erwartet(dienste):
    """Die Gegenrichtung: Der Lauf braucht CENSUS_API_KEY, und zwar vorher.

    *Ein fehlender Schluessel zeigt sich als falsches Ergebnis, nicht als
    Fehler* - die Census-API antwortet ohne Schluessel mit HTTP 200 und einer
    HTML-Seite. Steht die Variable nicht in der Beschreibung, erreicht sie den
    Container nie, und niemand sucht an dieser Stelle.
    """
    umgebung = dienste["pipeline"]["environment"]
    for variable in ("CENSUS_API_KEY", "S3_ACCESS_KEY", "S3_SECRET_KEY"):
        assert variable in umgebung, f"{variable} erreicht den Container nicht"
    assert umgebung.get("STORAGE_BACKEND") == "s3", (
        "der Ablagemodus ist entschieden (s3) und gehoert nicht in die .env - "
        "ein Serverlauf in local publizierte nichts und saehe gruen aus"
    )


def test_kein_abbild_wird_auf_dem_server_gebaut(beschreibung, text):
    """FR-3/E7: *large frontend builds have previously exhausted RAM.*"""
    mit_bau = sorted(n for n, d in beschreibung["services"].items() if "build" in d)
    assert not mit_bau, f"build: auf srv01 - verboten: {mit_bau}"
    assert "Registry" in text, (
        "die Datei sagt nicht, woher die Abbilder kommen - ohne das baut sie "
        "der naechste doch auf dem Host"
    )


def test_das_traefik_netz_ist_extern(beschreibung):
    """Es gehoert der Ingress-Beschreibung; dieser Stapel tritt bei."""
    assert beschreibung["networks"]["proxy"]["external"] == "true", (
        "proxy muss external sein - sonst legt dieser Stapel ein zweites, "
        "leeres Netz dieses Namens an und Traefik findet nichts darin"
    )


# --------------------------------------------------------------------------
# Die Entwicklungsfassung bleibt, was sie ist
# --------------------------------------------------------------------------


def test_die_entwicklungsfassung_bleibt_lauffaehig():
    """Der Serverbetrieb ist eine eigene Beschreibung, keine Umwidmung.

    ``docker-compose.yml`` bindet Ports an 127.0.0.1 und kennt kein Traefik -
    genau richtig auf dem Entwicklungsrechner und genau falsch auf srv01.
    Wer die beiden zusammenlegt, hat in einem der beiden Faelle unrecht.
    """
    entwicklung = ENTWICKLUNG.read_text(encoding="utf-8")
    assert "127.0.0.1:" in entwicklung, (
        "die Entwicklungsfassung bindet keine Ports mehr an 127.0.0.1 - "
        "entweder ist sie umgewidmet worden oder sie oeffnet jetzt Dienste"
    )
    assert "traefik" not in entwicklung.lower(), (
        "Traefik-Labels in der Entwicklungsfassung - dort gibt es kein Traefik"
    )
    gelesen = lade(entwicklung)
    assert set(gelesen["services"]) == {"clickhouse", "elasticsearch", "kibana"}, (
        "die Entwicklungsfassung traegt andere Dienste als die drei "
        "Analysedienste - dann stimmt die Arbeitsteilung der beiden Dateien nicht"
    )


# --------------------------------------------------------------------------
# Der Sicherungssatz (18.10.2026)
# --------------------------------------------------------------------------


def test_der_sicherungssatz_hat_ein_eigenes_volume(dienste, beschreibung):
    """Er darf nicht in ``arbeitsdaten`` liegen, und das ist gemessen.

    Am 18.10.2026 nachgesehen: ``/app/data`` im Container ist das benannte
    Volume ``urbancrime_arbeitsdaten``, und das steht **nicht** in
    ``backup.volumes`` der Serverpolicy. Ein Satz, der dorthin geschrieben
    wird, ist da - und wird nie gesichert. Genau diese Verwechslung hat mich
    beim Entwurf einmal erwischt.
    """
    pipeline = dienste["pipeline"]
    einhaengungen = pipeline["volumes"]
    assert "sicherung:/app/sicherung" in einhaengungen, (
        f"der Sicherungssatz braucht sein eigenes Volume, eingehaengt sind "
        f"{einhaengungen}")
    assert "sicherung" in (beschreibung.get("volumes") or {}), \
        "das Volume fehlt im Volumeblock - Docker legte es dann als anonymes an"


def test_das_modul_schreibt_in_dieses_volume_und_nicht_daneben(dienste):
    """``SICHERUNG_ROOT`` muss **innerhalb** der Einhaengung liegen.

    Zeigte es daneben, schriebe der Satz in die Containerschicht: beim
    naechsten ``run --rm`` weg, und in keiner Sicherung je gewesen.
    """
    pipeline = dienste["pipeline"]
    ziel = pipeline["environment"]["SICHERUNG_ROOT"]
    ziele = [e.split(":")[1] for e in pipeline["volumes"] if ":" in e]
    assert any(ziel == m or ziel.startswith(m.rstrip("/") + "/")
               for m in ziele), (
        f"SICHERUNG_ROOT={ziel} liegt in keiner Einhaengung ({ziele})")
    assert not ziel.startswith("/app/data"), (
        "unter /app/data liegt 'arbeitsdaten', und das wird nicht gesichert")


def test_start_liegt_im_netz_monitoring_und_zwar_mit_alias(dienste, beschreibung):
    """Sonst schreibt der Betriebsstand ins Leere (FR-30).

    Bis zum 18.10.2026 lag ``start`` nur in ``proxy`` und ``urbancrime``,
    Prometheus in ``monitoring``. Die Metrikdatei war damit geschrieben und
    **unerreichbar** - und genau so sieht ein Betriebsblick aus, der nichts
    meldet, ohne dass etwas kaputt ist.

    **Der Alias ist kein Schmuck.** Compose setzt den Dienstnamen als
    Netzalias, und auf ``monitoring`` liegen zehn fremde Stapel: ``start``
    ist dort ein Name, den jeder zweite haben koennte.
    """
    netze = dienste["start"]["networks"]
    assert "monitoring" in netze, (
        f"start liegt in {sorted(netze)} - Prometheus kommt dann nicht hin")
    aliasse = (netze["monitoring"] or {}).get("aliases", [])
    assert aliasse, "ohne Alias heisst es auf dem geteilten Netz nur 'start'"
    erklaert = beschreibung["networks"].get("monitoring") or {}
    assert erklaert.get("external") == "true", (
        f"monitoring muss external sein, erklaert ist {erklaert} - sonst "
        f"legt dieser Stapel ein zweites, leeres Netz dieses Namens an und "
        f"Prometheus sieht nichts darin")


def test_das_ablagedokument_scrapet_genau_diesen_alias(dienste):
    """Zwei Seiten einer Zuordnung, und die eine liegt ausserhalb des Repos.

    Der Scrape-Block wird im Monitoring-Stapel eingetragen; das Ablagedokument
    nennt ihn zum Einsetzen. Heisst der Alias hier anders als das Ziel dort,
    scrapet Prometheus einen Namen, den kein Dienst traegt - und meldet eine
    Luecke, keinen Fehler.
    """
    doku = PROJECT_ROOT / "docs" / "storage-architektur.md"
    if not doku.is_file():
        pytest.skip("docs/storage-architektur.md fehlt")
    netze = dienste["start"]["networks"]
    aliasse = (netze["monitoring"] or {}).get("aliases", [])
    text = doku.read_text(encoding="utf-8")
    assert any(f"targets: [{a}:" in text for a in aliasse), (
        f"das Ablagedokument scrapet keinen der Aliasse {aliasse} - "
        f"der Block dort gehoert mitgezogen")


def test_der_betriebsstand_wird_als_prometheus_text_ausgeliefert(dienste):
    """Prometheus 3 raet den Typ nicht mehr.

    Am 18.10.2026 scrapete Prometheus den Betriebsstand erstmals und lehnte
    ihn ab: *„received unsupported Content-Type 'application/octet-stream'"*.
    ``serving.betriebsstand`` schreibt ``metrics``, eine Datei **ohne
    Endung**; nginx kennt dafuer keinen Typ. Die Verdrahtung war in Ordnung,
    der Endpunkt nicht - und das sah aus wie ein Netzproblem.

    Geprueft wird deshalb die Deklaration dort, wo ausgeliefert wird, und
    nicht eine Rueckfallregel im fremden Monitoring-Stapel: Jeder weitere
    Verbraucher dieses Endpunkts bekaeme sonst weiter den falschen Typ.
    """
    conf = next((e.split(":")[0] for e in dienste["start"]["volumes"]
                 if e.split(":")[1].startswith("/etc/nginx/")), None)
    assert conf, (
        f"start haengt keine nginx-Konfiguration ein: "
        f"{dienste['start']['volumes']}")
    pfad = (PROJECT_ROOT / conf.lstrip("./")).resolve()
    assert pfad.is_file(), f"{pfad} fehlt im Repository"
    text = pfad.read_text(encoding="utf-8")

    assert "location = /metrics" in text, (
        "die Konfiguration nennt /metrics nicht - dann gilt weiter der "
        "Standardtyp application/octet-stream")

    # **Die Direktive, nicht die Datei.** Die erste Fassung suchte
    # "version=0.0.4" im ganzen Text - und fand es im Kommentarkopf, der die
    # Fehlermeldung von Prometheus zitiert. Eine Mutationsprobe, die den Typ
    # auf blankes "text/plain" setzte, blieb dadurch gruen. Gesucht wird
    # jetzt die Zeile, die wirkt.
    # Bis zum **letzten** Semikolon der Zeile, nicht zum ersten: Der Typ
    # selbst traegt Semikolons ("text/plain; version=0.0.4; charset=utf-8"),
    # und ein Muster mit [^;]+ erfasste nur '"text/plain'.
    direktiven = re.findall(r"^\s*default_type\s+(.+);\s*$", text, re.M)
    assert direktiven, f"keine default_type-Direktive in {pfad.name}"
    assert any("text/plain" in d and "version=0.0.4" in d for d in direktiven), (
        f"der Typ muss das Textformat von Prometheus samt Version nennen, "
        f"deklariert ist {direktiven}")
    # Und die Seite selbst muss weiter ausgeliefert werden.
    assert "index.html" in text and "/usr/share/nginx/html" in text, (
        "die Konfiguration ersetzt die Vorgabe des Abbilds - ohne Wurzel und "
        "Indexdatei liefert nginx die Einstiegsseite nicht mehr aus")


# --------------------------------------------------------------------------
# Die Engineering-Konsole: Webdienst dauernd, Worker getaktet (30.10.2026)
# --------------------------------------------------------------------------


def test_der_konsolen_worker_ist_ein_stapellauf(dienste):
    """Er fuehrt die Pipelines aus und braucht deren Platz - also nicht dauernd.

    Ein Takt startet ihn mit ``run --rm``, er erledigt hoechstens einen
    Auftrag und endet. ``restart`` waere hier dieselbe Dauerschleife, vor der
    FR-9 die Pipeline schuetzt.
    """
    worker = dienste["worker"]
    assert worker.get("profiles"), "ohne Profil startet er mit up -d und bleibt"
    assert worker.get("restart") == "no"
    assert "--once" in worker["command"], "ohne --once endet der Lauf nie"
    assert "labels" not in worker and "ports" not in worker
    assert "proxy" not in worker["networks"]


def test_der_worker_traegt_was_die_pipeline_traegt(dienste):
    """Er ruft dieselben Module auf; fehlt ihm eine Variable der Pipeline,
    laeuft derselbe Bau unter der Konsole anders als unter dem Cron."""
    pipeline, worker = dienste["pipeline"]["environment"], dienste["worker"]["environment"]
    fehlend = sorted(set(pipeline) - set(worker))
    assert not fehlend, f"dem Worker fehlt, was die Pipeline hat: {fehlend}"
    abweichend = {k: (pipeline[k], worker[k]) for k in pipeline if pipeline[k] != worker[k]}
    assert not abweichend, f"Worker und Pipeline setzen verschieden: {abweichend}"
    assert set(dienste["pipeline"]["volumes"]) <= set(dienste["worker"]["volumes"])


def test_admin_und_worker_pruefen_git_unter_demselben_schutz(dienste):
    """Der Worker merged, der Webdienst zeigt den Modus an - zeigten sie
    Verschiedenes, saehe der Reviewer einen Schutz, der nicht gilt."""
    from platform_admin.gitops import PROTECTION_MODES

    admin = dienste["admin"]["environment"]["ADMIN_GIT_SCHUTZ"]
    worker = dienste["worker"]["environment"]["ADMIN_GIT_SCHUTZ"]
    assert admin == worker, (admin, worker)
    assert admin in PROTECTION_MODES, f"{admin!r}: die Konsole startete nicht"


def test_der_kontrollzustand_liegt_in_einem_eigenen_datentraeger(beschreibung, dienste):
    """Review-Entscheidungen lassen sich nicht nachrechnen.

    ``arbeitsdaten`` ist Zwischenstand und wird nicht gesichert; die
    SQLite-Datenbank der Konsole liegt deshalb in ``konsole``, das in die
    Serversicherung gehoert wie ``sicherung``.
    """
    for name in ("admin", "worker"):
        assert "konsole:/app/data/admin" in dienste[name]["volumes"], name
    assert "konsole" in beschreibung["volumes"]


def test_die_oeffentliche_adresse_ist_die_geroutete(dienste):
    """Die Konsole prueft Origin und Host gegen ADMIN_PUBLIC_ORIGIN; stimmt
    sie nicht mit der Traefik-Regel ueberein, lehnt sie jede Anfrage ab."""
    admin = dienste["admin"]
    regel = admin["labels"]["traefik.http.routers.urbancrime-admin.rule"]
    host = HOSTREGEL.match(regel).group(1)
    assert admin["environment"]["ADMIN_PUBLIC_ORIGIN"] == f"https://{host}"


def test_die_konsole_kennt_ihre_geheimnisse_nur_aus_der_env(dienste):
    for name, variablen in (("admin", ("CF_ACCESS_AUD", "ADMIN_METRICS_TOKEN",
                                       "ADMIN_ROLE_BINDINGS")),
                            ("worker", ("ADMIN_GITHUB_TOKEN",))):
        umgebung = dienste[name]["environment"]
        for variable in variablen:
            assert umgebung.get(variable, None) == "", f"{name}: {variable}"


def test_nur_der_worker_haelt_das_github_token(dienste):
    """Der Webdienst ist von aussen erreichbar, der Worker nicht. Deshalb
    reiht der Webdienst Veroeffentlichungen nur ein, und das Token, das
    Branches anlegt und mergt, kommt nie in den erreichbaren Prozess."""
    admin = dienste["admin"]["environment"]
    assert "ADMIN_GITHUB_TOKEN" not in admin
    assert admin["ADMIN_DEFER_PUBLICATION"] == "1"
    assert "ADMIN_GITHUB_TOKEN" in dienste["worker"]["environment"]


def test_e5_teilt_den_sperrdatentraeger_zwischen_leser_und_schreibern(beschreibung, dienste):
    assert "datensperren" in beschreibung["volumes"]
    for name in ("pipeline", "worker", "jupyter"):
        service = dienste[name]
        assert service["environment"]["DATA_LOCK_ROOT"] == "/app/datensperren"
        mounts = [mount_info(v) for v in service["volumes"]]
        assert ("datensperren", "/app/datensperren", False) in mounts


def test_e5_jupyter_sieht_nur_den_job_unterordner_der_konsole(text):
    import yaml

    service = yaml.safe_load(text)["services"]["jupyter"]
    console_mounts = [v for v in service["volumes"] if mount_info(v)[0] == "konsole"]
    assert len(console_mounts) == 1
    jobs = console_mounts[0]
    assert jobs["type"] == "volume"
    assert jobs["target"] == "/app/data/admin/jobs"
    assert jobs["read_only"] is True
    assert jobs["volume"] == {"subpath": "jobs", "nocopy": True}
    # Die Daten bleiben ebenfalls nur lesbar, der Notebook-Arbeitsraum getrennt.
    assert "arbeitsdaten:/app/data:ro" in service["volumes"]
    assert "jupyter-arbeit:/app/arbeit" in service["volumes"]


def test_e5_die_jobwurzel_ist_ausdruecklich_waehlbar(dienste):
    assert dienste["jupyter"]["environment"]["CRIME_ANALYSIS_ROOT"] == \
        "${CRIME_ANALYSIS_ROOT:-/app/data}"


def test_der_leser_traegt_auch_die_lange_volume_syntax():
    gelesen = lade("""services:
  jupyter:
    volumes:
      - type: volume
        source: konsole
        target: /app/data/admin/jobs
        read_only: true
        volume:
          subpath: jobs
          nocopy: true
""")
    mount = gelesen["services"]["jupyter"]["volumes"][0]
    assert mount_info(mount) == ("konsole", "/app/data/admin/jobs", True)
    assert mount["volume"] == {"subpath": "jobs", "nocopy": "true"}
