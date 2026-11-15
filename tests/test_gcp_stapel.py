"""Haelt die Google-Cloud-Probe (FR-44, FR-47) an den Zusagen ihres Plans.

Der Stapel in Google Cloud ist eine Probe, kein Betrieb, und er kostet Geld,
solange er laeuft. Was hier geprueft wird, sind deshalb die Zusagen, deren
Bruch man erst auf der Rechnung saehe oder im Netz:

* ``docker-compose.gcp.yml``: jeder Dienst mit Grenze, und die Grenzen sind
  die auf srv01 gemessenen; fremde Abbilder per Digest, das eigene ohne
  Vorgabe; Ports nur an 127.0.0.1; kein Geheimnis; keine srv01-Namen; die
  Pipeline mit denselben DuckDB-Grenzen wie auf srv01, damit der Vergleich
  der Releases einer der Umgebung ist.
* ``docker/gcp-*.sh``: ``set -Eeuo pipefail``, gueltige Shell, das Label an
  jeder Ressource, die es tragen kann, nur SSH ueber IAP, keine statische
  Adresse, Abendstopp um 20:00 Europe/Zurich, Budget mit drei Schwellen,
  der HMAC-Schluessel nie auf dem Bildschirm, Abbau nur mit Bestaetigung,
  Starten und Stoppen idempotent.
* FR-44: Der Unterschied zu srv01 steht nur in ``.env`` und Compose - kein
  GCP-Sonderweg unter ``src/``.

**Wie die Skripte geprueft werden, ohne Google Cloud anzufassen.** Zwei
Wege. Der Trockenmodus (``--trocken``) gibt jeden verändernden Befehl nur
aus und fragt nichts; seine Ausgabe ist die Liste dessen, was ein echter
Lauf taete. Fuer die Verzweigungen eines echten Laufs (Projekt fehlt,
Abrechnung aus, Ressource besteht schon) steht ein **falsches gcloud** im
Temporaerverzeichnis: Es schreibt jeden Aufruf in ein Protokoll und
antwortet nach Umgebungsvariablen. Das Protokoll ist der Beweis, dass ein
Abbruch *vor* dem ersten ``create`` kommt.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
from pathlib import Path

import pytest

from tests.test_abbild_ohne_srv01 import zeichenketten
from tests.test_srv01_compose import GEHEIM, GRENZEN_MIB, lade, mib


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GCP = PROJECT_ROOT / "docker-compose.gcp.yml"
SRV01 = PROJECT_ROOT / "docker-compose.srv01.yml"
ENTWICKLUNG = PROJECT_ROOT / "docker-compose.yml"
VORLAGE = PROJECT_ROOT / ".env.gcp.example"
DOCKER = PROJECT_ROOT / "docker"
GEMEINSAM = DOCKER / "gcp-gemeinsam.sh"
STARTUP = DOCKER / "gcp-startup.sh"
#: Die vier Skripte, die man aufruft. ``gcp-gemeinsam.sh`` wird nur eingelesen.
SKRIPTE = {name: DOCKER / f"gcp-{name}.sh"
           for name in ("aufbauen", "starten", "stoppen", "abbauen")}
ALLE_SKRIPTE = [*SKRIPTE.values(), GEMEINSAM, STARTUP]

#: Was es heute ist, wenn sich nichts geaendert hat (Plan, Decisions).
LABEL = "zweck=urbancrime-probe"
IAP = "35.235.240.0/20"

#: Auf srv01 bis zum 1.11.2026 gemessen (C-9; tests/test_srv01_compose.py,
#: Kommentar zu GRENZEN_MIB). Die uebrigen Grenzen sind die dort aktuellen.
GRENZEN_GCP_MIB = {
    "dashboard": GRENZEN_MIB["dashboard"],
    "pipeline": GRENZEN_MIB["pipeline"],
    "elasticsearch": 1792,
    "kibana": 1024,
}
#: e2-standard-2 hat 8 GB; 2 GiB bleiben System, Docker und Seitencache.
VM_MIB = 8192
RESERVE_MIB = 2048

#: Woran eine srv01-Annahme in einer Zeile ausserhalb eines Kommentars zu
#: erkennen ist - die Liste aus tests/test_abbild_ohne_srv01.py und dazu
#: der Eingang von srv01 (Traefik, Cloudflare).
SRV01_MUSTER = re.compile(r"srv01|datenwerft|/srv/|urbancrime_|traefik|cloudflare",
                          re.IGNORECASE)


# --------------------------------------------------------------------------
# Die Compose-Beschreibung
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def text() -> str:
    assert GCP.is_file(), f"{GCP} fehlt - die Beschreibung der Probe"
    return GCP.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def beschreibung(text) -> dict:
    return lade(text)


@pytest.fixture(scope="module")
def dienste(beschreibung) -> dict:
    return beschreibung["services"]


@pytest.fixture(scope="module")
def srv01() -> dict:
    return lade(SRV01.read_text(encoding="utf-8"))["services"]


def test_der_stapel_ist_pipeline_dashboard_elasticsearch_und_kibana(dienste):
    """Plan, Intent: ein ganzer Stapel inklusive Elasticsearch und Kibana."""
    assert set(dienste) == set(GRENZEN_GCP_MIB), sorted(dienste)


def test_jeder_dienst_hat_die_auf_srv01_gemessene_grenze(dienste):
    falsch = {name: d.get("mem_limit") for name, d in dienste.items()
              if not d.get("mem_limit") or mib(d["mem_limit"]) != GRENZEN_GCP_MIB[name]}
    assert not falsch, f"ohne oder mit anderer Grenze als gemessen: {falsch}"


def test_die_summe_der_grenzen_passt_auf_die_vm(dienste, text):
    summe = sum(mib(d["mem_limit"]) for d in dienste.values())
    assert summe <= VM_MIB - RESERVE_MIB, (
        f"{summe} MiB verplant - auf 8 GB bleiben dann keine {RESERVE_MIB} MiB "
        "fuer System, Docker und Seitencache")
    assert f"{summe:,}".replace(",", "'") in text, (
        "der Kopf der Compose-Datei nennt eine andere Summe als die Dienste")


def test_jede_grenze_nennt_ihre_herkunft(text, dienste):
    zeilen = text.splitlines()
    ohne = []
    for name, dienst in dienste.items():
        nummer = next(i for i, z in enumerate(zeilen)
                      if z.strip() == f"mem_limit: {dienst['mem_limit']}"
                      and i > next(j for j, y in enumerate(zeilen) if y == f"  {name}:"))
        davor = "\n".join(zeilen[max(0, nummer - 4):nummer])
        if "gemessen" not in davor:
            ohne.append(name)
    assert not ohne, f"mem_limit ohne Herkunft (\"gemessen ...\") darueber: {ohne}"


def test_fremde_abbilder_sind_per_digest_gepinnt(dienste):
    """Eine Marke laesst sich umhaengen, ein Digest nicht."""
    ungepinnt = {name: d["image"] for name, d in dienste.items()
                 if not d["image"].startswith("${PIPELINE_IMAGE")
                 and not re.search(r"@sha256:[0-9a-f]{64}$", d["image"])}
    assert not ungepinnt, f"ohne Digest: {ungepinnt}"


def test_das_eigene_abbild_hat_keine_vorgabe(dienste):
    """Auf srv01 steht ``:-urban-crime:latest`` als Vorgabe, weil dort die
    .env den Digest immer setzt. Hier waere die Vorgabe ein lokal gebauter
    Name, den die VM nicht kennt - oder schlimmer, ein anderer Bau als auf
    srv01, und der Vergleich der Releases verglich zwei Abbilder."""
    eigene = {name: d["image"] for name, d in dienste.items()
              if d["image"].startswith("${PIPELINE_IMAGE")}
    assert set(eigene) == {"dashboard", "pipeline"}
    falsch = {n: i for n, i in eigene.items() if not i.startswith("${PIPELINE_IMAGE:?")}
    assert not falsch, f"PIPELINE_IMAGE mit Vorgabe statt Pflicht: {falsch}"


def test_elasticsearch_und_kibana_sind_die_fassung_der_entwicklung(dienste):
    entwicklung = lade(ENTWICKLUNG.read_text(encoding="utf-8"))["services"]
    for name in ("elasticsearch", "kibana"):
        marke = dienste[name]["image"].split("@", 1)[0]
        assert marke == entwicklung[name]["image"], (
            f"{name}: {marke} hier, {entwicklung[name]['image']} in docker-compose.yml")


def test_kein_dienst_wird_hier_gebaut(dienste):
    assert not [n for n, d in dienste.items() if "build" in d]


def test_ports_nur_an_localhost_und_nur_dashboard_und_kibana(dienste):
    """Plan, Always: Zugang nur ueber ``gcloud compute ssh`` mit Weiterleitung."""
    offen = {name: d.get("ports") for name, d in dienste.items() if d.get("ports")}
    assert set(offen) == {"dashboard", "kibana"}, offen
    falsch = [p for ports in offen.values() for p in ports if not p.startswith("127.0.0.1:")]
    assert not falsch, f"nicht an 127.0.0.1 gebunden: {falsch}"


def test_die_weiterleitung_trifft_die_ports_der_compose(dienste):
    """``gcp-starten.sh`` leitet weiter, was die Compose-Datei bindet."""
    gebunden = {p.split(":")[1] for d in dienste.values() for p in d.get("ports") or []}
    treffer = re.search(r'GCP_PORTS="([^"]+)"', GEMEINSAM.read_text(encoding="utf-8"))
    assert treffer and set(treffer.group(1).split()) == gebunden, (treffer, gebunden)


def test_kein_externes_netz(beschreibung):
    """srv01 tritt proxy und monitoring bei; die Probe tritt nirgends bei."""
    extern = [n for n, netz in (beschreibung.get("networks") or {}).items()
              if str((netz or {}).get("external", "false")).lower() == "true"]
    assert not extern, f"externe Netze: {extern}"


def test_kein_geheimnis_steht_in_der_beschreibung(dienste):
    gefunden = [f"{name}: {variable}"
                for name, dienst in dienste.items()
                for variable, wert in (dienst.get("environment") or {}).items()
                if GEHEIM.search(variable) and wert]
    assert not gefunden, f"Geheimnis in der Compose-Datei: {gefunden}"


def test_jede_variable_ohne_wert_steht_in_der_vorlage(dienste):
    """Eine Variable ohne Wert kommt aus der .env - also muss die Vorlage sie
    nennen, sonst erreicht sie den Container nie, und niemand sucht dort."""
    vorlage = {z.split("=", 1)[0] for z in VORLAGE.read_text(encoding="utf-8").splitlines()
               if z and not z.startswith("#") and "=" in z}
    fehlt = sorted({variable for d in dienste.values()
                    for variable, wert in (d.get("environment") or {}).items()
                    if not wert} - vorlage)
    assert not fehlt, f"in .env.gcp.example nicht genannt: {fehlt}"
    assert "PIPELINE_IMAGE" in vorlage


def test_jede_variable_der_vorlage_erreicht_einen_container(dienste, text):
    """Die Gegenrichtung: Eine Zeile der Vorlage, die kein Dienst nennt, wirkt
    nicht - und sieht doch aus wie eine Einstellung (so stand ``S3_USE_SSL``
    zuerst darin). Zaehlt als genannt: ohne Wert unter ``environment:`` oder
    als ``${...}`` in der Datei (``PIPELINE_IMAGE``)."""
    vorlage = {z.split("=", 1)[0] for z in VORLAGE.read_text(encoding="utf-8").splitlines()
               if z and not z.startswith("#") and "=" in z}
    genannt = {variable for d in dienste.values()
               for variable, wert in (d.get("environment") or {}).items() if not wert}
    genannt |= set(re.findall(r"\$\{([A-Z_][A-Z0-9_]*)", text))
    wirkungslos = sorted(vorlage - genannt)
    assert not wirkungslos, f"in .env.gcp.example, aber in keinem Container: {wirkungslos}"


def test_die_schluessel_liegen_ausserhalb_des_repositorys():
    """Entscheid vom 15.11.2026: unter ~/.config/urbancrime-probe/, Modus 600."""
    vorlage = VORLAGE.read_text(encoding="utf-8")
    assert "~/.config/urbancrime-probe/" in vorlage
    assert ".env.gcp im" not in vorlage, "die Vorlage legt die .env ins Repository"
    gemeinsam = GEMEINSAM.read_text(encoding="utf-8")
    assert ': "${GCP_ZUSTAND:=${HOME}/.config/urbancrime-probe}"' in gemeinsam


def test_das_ghcr_token_geht_nicht_in_den_verlauf():
    for pfad in (VORLAGE, SKRIPTE["starten"]):
        inhalt = pfad.read_text(encoding="utf-8")
        assert "echo $GHCR_TOKEN" not in inhalt and "echo \\$GHCR_TOKEN" not in inhalt, pfad.name
        assert "read -rs GHCR_TOKEN" in inhalt and "unset GHCR_TOKEN" in inhalt, pfad.name


def test_die_vorlage_traegt_keinen_schluessel():
    gesetzt = [z for z in VORLAGE.read_text(encoding="utf-8").splitlines()
               if z and not z.startswith("#") and "=" in z
               and GEHEIM.search(z.split("=", 1)[0]) and z.split("=", 1)[1].strip()]
    assert not gesetzt, f"Werte in der Vorlage: {gesetzt}"


def test_die_vorlage_ist_versioniert_und_die_env_nicht():
    """``.env.*`` in .gitignore, ausser den Vorlagen."""
    fertig = subprocess.run(
        ["git", "check-ignore", "--no-index", ".env.gcp", ".env.srv01", ".env.gcp.example"],
        cwd=PROJECT_ROOT, capture_output=True, text=True)
    ignoriert = set(fertig.stdout.split())
    assert {".env.gcp", ".env.srv01"} <= ignoriert, fertig.stdout
    assert ".env.gcp.example" not in ignoriert


def test_die_pipeline_ist_ein_stapellauf(dienste):
    pipeline = dienste["pipeline"]
    assert pipeline.get("profiles") == ["stapel"]
    assert not pipeline.get("ports") and pipeline.get("restart") != "unless-stopped"


def test_die_pipeline_baut_wie_auf_srv01(dienste, srv01):
    """Der Vergleich der Releases soll einer der Umgebung sein: Was den Bau
    bestimmt, ist auf beiden Seiten gleich."""
    hier, dort = dienste["pipeline"]["environment"], srv01["pipeline"]["environment"]
    for variable in ("STORAGE_BACKEND", "DUCKDB_MEMORY_LIMIT", "DUCKDB_THREADS",
                     "DUCKDB_TEMP_DIRECTORY", "DATA_LOCK_ROOT"):
        assert hier.get(variable) == dort.get(variable), (
            f"{variable}: {hier.get(variable)!r} hier, {dort.get(variable)!r} auf srv01")
    assert dienste["pipeline"]["mem_limit"] == srv01["pipeline"]["mem_limit"]


def test_pruefe_stand_prueft_hier_elasticsearch_und_kibana(dienste):
    umgebung = dienste["pipeline"]["environment"]
    assert umgebung["SERVING_BETRIEB"] == "lokal"
    for variable, dienst in (("ELASTICSEARCH_URL", "elasticsearch"),
                             ("KIBANA_URL", "kibana"), ("DASHBOARD_URL", "dashboard")):
        assert re.fullmatch(rf"http://{dienst}:\d+", umgebung[variable]), umgebung[variable]
    assert umgebung["STAPEL_COMPOSE"] == GCP.name


def test_kibana_wartet_auf_elasticsearch(dienste):
    assert dienste["kibana"]["depends_on"]["elasticsearch"]["condition"] == "service_healthy"


def test_jeder_dienst_verbietet_neue_privilegien_und_rotiert(dienste):
    for name, d in dienste.items():
        assert "no-new-privileges:true" in (d.get("security_opt") or []), name
        assert ((d.get("logging") or {}).get("options") or {}).get("max-size"), name


# --------------------------------------------------------------------------
# Keine srv01-Namen, und FR-44: kein GCP-Sonderweg im Code
# --------------------------------------------------------------------------


def ohne_kommentare(pfad: Path) -> list[tuple[int, str]]:
    return [(n, z) for n, z in enumerate(pfad.read_text(encoding="utf-8").splitlines(), 1)
            if z.strip() and not z.strip().startswith("#")]


@pytest.mark.parametrize("pfad", [GCP, VORLAGE, *ALLE_SKRIPTE], ids=lambda p: p.name)
def test_keine_srv01_namen(pfad):
    befunde = [f"{pfad.name}:{n}: {z.strip()[:80]}"
               for n, z in ohne_kommentare(pfad) if SRV01_MUSTER.search(z)]
    assert not befunde, "srv01 in der Probe:\n" + "\n".join(befunde)


#: Woran ein GCP-Sonderweg im Code zu erkennen waere: ``gcp``, ``gcs`` oder
#: ``google`` irgendwo in einem Bezeichner oder einer Zeichenkette - auch
#: ``gcp_modus``, ``ist_gcs`` oder ``== "google"``.
SONDERWEG = re.compile(r"gcp|gcs|google", re.IGNORECASE)
#: Was "google" enthaelt und kein Speicherweg ist: die Webschriften der
#: Startseite (``serving.build_einstieg``). Eine Ausnahme je Fundstelle,
#: damit eine neue nicht mitrutscht.
KEIN_SONDERWEG = ("fonts.googleapis.com",)


def sonderweg(wert: str) -> bool:
    for ausnahme in KEIN_SONDERWEG:
        wert = wert.replace(ausnahme, "")
    return bool(SONDERWEG.search(wert))


def bezeichner(quelltext: str) -> list[tuple[int, str]]:
    gefunden = []
    for knoten in ast.walk(ast.parse(quelltext)):
        if isinstance(knoten, ast.Name):
            gefunden.append((knoten.lineno, knoten.id))
        elif isinstance(knoten, ast.Attribute):
            gefunden.append((knoten.lineno, knoten.attr))
        elif isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            gefunden.append((knoten.lineno, knoten.name))
        elif isinstance(knoten, ast.arg):
            gefunden.append((knoten.lineno, knoten.arg))
    return gefunden


def test_fr44_kein_gcp_sonderweg_unter_src():
    """Given der Unterschied srv01 gegen GCP, when er aufgelistet wird, then
    steht er nur in ``.env`` und Compose, nicht im Code unter ``src/``.

    Durchsucht werden Zeichenketten (ohne Docstrings) und Bezeichner. Ein
    Docstring darf Cloud Storage nennen - als Erklaerung, nicht als Weiche.
    """
    dateien = sorted((PROJECT_ROOT / "src").rglob("*.py"))
    assert len(dateien) > 50
    befunde = []
    for pfad in dateien:
        quelltext = pfad.read_text(encoding="utf-8")
        name = pfad.relative_to(PROJECT_ROOT).as_posix()
        for zeile, wert in [*zeichenketten(quelltext), *bezeichner(quelltext)]:
            if sonderweg(wert):
                befunde.append(f"{name}:{zeile}: {wert[:80]!r}")
    assert not befunde, (
        "GCP-Sonderweg im Code - FR-44 verlangt Konfiguration:\n" + "\n".join(befunde))


def test_der_sonderwegwaechter_findet_was_er_finden_soll():
    quelltext = ('"""Laeuft auch gegen Cloud Storage (GCS)."""\n'
                 'def lade(gcp_modus):\n'
                 '    if gcp_modus:\n'
                 '        return "https://storage.googleapis.com"\n'
                 'X = "https://fonts.googleapis.com"\n')
    quelltext += ('ist_gcs = 1\n'
                  'if ziel == "google":\n'
                  '    pass\n')
    treffer = sorted({z for z, w in [*zeichenketten(quelltext), *bezeichner(quelltext)]
                      if sonderweg(w)})
    # 2/3: gcp_modus, 4: die Adresse, 6: ist_gcs, 7: "google". Nicht 1 (der
    # Docstring) und nicht 5 (die Webschriften).
    assert treffer == [2, 3, 4, 6, 7], treffer


# --------------------------------------------------------------------------
# Die Skripte: Form
# --------------------------------------------------------------------------


@pytest.mark.parametrize("pfad", [*SKRIPTE.values(), STARTUP], ids=lambda p: p.name)
def test_jedes_skript_bricht_beim_ersten_fehler_ab(pfad):
    zeilen = [z for _, z in ohne_kommentare(pfad)]
    assert zeilen[0] == "set -Eeuo pipefail", f"{pfad.name}: erste Anweisung {zeilen[0]!r}"
    assert os.access(pfad, os.X_OK), f"{pfad.name} ist nicht ausfuehrbar"


@pytest.mark.parametrize("pfad", ALLE_SKRIPTE, ids=lambda p: p.name)
def test_jedes_skript_ist_gueltige_shell(pfad, benutzbares_bash):
    fertig = subprocess.run(["bash", "-n", str(pfad)], capture_output=True, text=True)
    assert fertig.returncode == 0, fertig.stderr


def test_die_vorgaben_sind_die_des_plans():
    text = GEMEINSAM.read_text(encoding="utf-8")
    for variable, wert in (("GCP_PROJEKT", "urbancrime"), ("GCP_REGION", "europe-west6"),
                           ("GCP_ZONE", "europe-west6-a"), ("GCP_VM", "urbancrime-probe"),
                           ("GCP_MASCHINE", "e2-standard-2"), ("GCP_DISK_GB", "30"),
                           ("GCP_ABENDSTOPP", "0 20 * * *"),
                           ("GCP_ZEITZONE", "Europe/Zurich")):
        assert f': "${{{variable}:={wert}}}"' in text, f"{variable} nicht mit {wert!r}"
    assert "urbancrime-probe-%s" in text, "der Eimer heisst nicht urbancrime-probe-<nummer>"


def test_das_startskript_meldet_was_der_aufbau_abwartet():
    """Der Aufbau stoppt die VM erst nach dieser Zeile; stimmen die beiden
    nicht ueberein, wartet er jedes Mal fuenfzehn Minuten umsonst."""
    startup = STARTUP.read_text(encoding="utf-8")
    assert 'readonly MARKE="urbancrime-startup"' in startup and 'melde "fertig"' in startup
    assert "'urbancrime-startup: fertig'" in SKRIPTE["aufbauen"].read_text(encoding="utf-8")


def test_das_startskript_bereitet_elasticsearch_vor_und_holt_nichts_per_pipe():
    startup = STARTUP.read_text(encoding="utf-8")
    assert "vm.max_map_count=262144" in startup
    code = "\n".join(z for _, z in ohne_kommentare(STARTUP))
    assert not re.search(r"curl[^\n|]*\|\s*(ba)?sh", code), "curl | sh im Startskript"
    assert "docker-compose-v2" in startup


# --------------------------------------------------------------------------
# Die Skripte: der Trockenmodus
# --------------------------------------------------------------------------


def rufe(skript: str, *argumente: str, tmp_path: Path, gcloud: Path | None = None,
         stdin: str | None = None, **umgebung: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GCP_")}
    env.update(GCP_ZUSTAND=str(tmp_path / "zustand"),
               GCLOUD=str(gcloud or tmp_path / "kein-gcloud"),
               GCP_WARTE_S="0", GCP_PAUSE_S="0", **umgebung)
    return subprocess.run(["bash", str(SKRIPTE[skript]), *argumente],
                          capture_output=True, text=True, env=env,
                          input=stdin, stdin=None if stdin is not None else subprocess.DEVNULL)


def zeilen(ausgabe: str, befehl: str) -> list[str]:
    return [z for z in ausgabe.splitlines() if befehl in z]


@pytest.fixture
def aufbau(tmp_path, benutzbares_bash) -> str:
    fertig = rufe("aufbauen", "--trocken", tmp_path=tmp_path)
    assert fertig.returncode == 0, fertig.stderr
    return fertig.stdout


def test_der_trockenlauf_braucht_kein_gcloud(aufbau):
    """GCLOUD zeigt auf eine Datei, die es nicht gibt - und es geht trotzdem."""
    assert aufbau.count("[trocken]") >= 10


def test_jede_ressource_mit_label_traegt_es(aufbau):
    for befehl in ("compute instances create", "storage buckets create", "compute disks add-labels"):
        gefunden = zeilen(aufbau, befehl)
        assert gefunden and all(f"--labels={LABEL}" in z for z in gefunden), (befehl, gefunden)


def test_nur_ssh_ueber_iap_und_keine_statische_adresse(aufbau):
    regeln = zeilen(aufbau, "firewall-rules create")
    assert len(regeln) == 1
    assert "--rules=tcp:22" in regeln[0] and f"--source-ranges={IAP}" in regeln[0]
    assert not zeilen(aufbau, "addresses create"), "statische Adresse angelegt"
    vm = zeilen(aufbau, "compute instances create")[0]
    assert "--address" not in vm and "--network urbancrime-probe-netz" in vm
    assert "--no-service-account" in vm and "--no-scopes" in vm


def test_kein_load_balancer_kein_nat_keine_datenbank(aufbau):
    """Plan, Never: keine dauerhaft laufenden Kostenstellen ausser Disk und Eimer."""
    for verboten in ("routers create", "nats create", "forwarding-rules", "sql ",
                     "container clusters", "backend-services"):
        assert verboten not in aufbau, verboten


def test_die_vm_ist_die_entschiedene(aufbau):
    vm = zeilen(aufbau, "compute instances create")[0]
    assert "--machine-type=e2-standard-2" in vm and "--zone europe-west6-a" in vm
    groesse = int(re.search(r"--boot-disk-size=(\d+)GB", vm).group(1))
    assert groesse <= 30, f"Disk {groesse} GB - hoechstens 30"
    assert "startup-script=" in vm and "gcp-startup.sh" in vm


def test_der_aufbau_endet_mit_gestoppter_vm(aufbau):
    befehle = [z for z in aufbau.splitlines()
               if z.startswith("[trocken]") and " compute instances " in z]
    assert befehle and " compute instances stop urbancrime-probe " in befehle[-1], befehle


def test_der_abendstopp_ist_gesetzt(aufbau):
    """Given ein Abend, when 20:00 vorbei ist, then ist die VM gestoppt."""
    plan = zeilen(aufbau, "resource-policies create instance-schedule")
    assert len(plan) == 1
    assert r"--vm-stop-schedule=0\ 20\ \*\ \*\ \*" in plan[0]
    assert "--timezone=Europe/Zurich" in plan[0] and "--region europe-west6" in plan[0]
    assert "--vm-start-schedule" not in plan[0], "der Zeitplan startet die VM auch"
    vm = zeilen(aufbau, "compute instances create")[0]
    assert "--resource-policies=urbancrime-probe-abendstopp" in vm
    # Ohne diese Rolle stoppt der Zeitplan nichts.
    rolle = zeilen(aufbau, "compute-system.iam.gserviceaccount.com")
    assert rolle and "--role=roles/compute.instanceAdmin.v1" in rolle[0]


def test_das_budget_hat_drei_schwellen_und_zaehlt_das_guthaben_nicht(aufbau):
    budget = zeilen(aufbau, "billing budgets create")
    assert len(budget) == 1
    betrag = float(re.search(r"--budget-amount=(\d+)", budget[0]).group(1))
    schwellen = [float(s) for s in re.findall(r"--threshold-rule=percent=([0-9.]+)", budget[0])]
    assert sorted(round(betrag * s) for s in schwellen) == [15, 30, 45]
    assert "--credit-types-treatment=exclude-all-credits" in budget[0]
    assert "--filter-projects=projects/urbancrime" in budget[0]


def test_der_eimer_ist_unversioniert_und_ohne_weiches_loeschen(aufbau):
    eimer = zeilen(aufbau, "storage buckets create")[0]
    assert "--soft-delete-duration=0" in eimer and "--location europe-west6" in eimer
    assert "--public-access-prevention" in eimer and "versioning" not in aufbau


def test_der_hmac_schluessel_wird_nur_auf_den_eimer_berechtigt(aufbau):
    bindungen = zeilen(aufbau, "add-iam-policy-binding")
    eimer = [z for z in bindungen if "storage buckets" in z]
    assert len(eimer) == 1 and "--role=roles/storage.objectAdmin" in eimer[0]
    projekt = [z for z in bindungen if "projects add-iam-policy-binding" in z]
    assert all("urbancrime-probe-speicher" not in z for z in projekt), (
        "das Eimerkonto bekommt eine Rolle im ganzen Projekt")


@pytest.mark.parametrize("skript", ["starten", "stoppen", "abbauen"])
def test_jedes_skript_hat_einen_trockenmodus(skript, tmp_path, benutzbares_bash):
    fertig = rufe(skript, "--trocken", tmp_path=tmp_path)
    assert fertig.returncode == 0, fertig.stderr
    assert "[trocken]" in fertig.stdout


def test_der_start_nennt_die_weiterleitung(tmp_path, benutzbares_bash):
    fertig = rufe("starten", "--trocken", tmp_path=tmp_path)
    ssh = [z for z in fertig.stdout.splitlines() if "compute ssh" in z and " -L " in z]
    assert ssh, fertig.stdout
    assert "--tunnel-through-iap" in ssh[0]
    assert "-L 8050:localhost:8050" in ssh[0] and "-L 5601:localhost:5601" in ssh[0]


# --------------------------------------------------------------------------
# Die Skripte: ein echter Lauf gegen ein falsches gcloud
# --------------------------------------------------------------------------


FALSCHES_GCLOUD = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >> "${GCLOUD_PROTOKOLL}"
case "$*" in
    "projects describe"*)
        [[ -n "${FAKE_OHNE_PROJEKT:-}" ]] && exit 1
        echo 627957638734 ;;
    "billing projects describe"*billingEnabled*) echo "${FAKE_ABRECHNUNG:-True}" ;;
    "billing projects describe"*) echo "billingAccounts/000000-000000-000000" ;;
    "storage hmac list"*) [[ -n "${FAKE_HMAC_LISTE:-}" ]] && printf '%b\n' "${FAKE_HMAC_LISTE}" ;;
    "storage hmac create"*) printf 'GOOGKENNUNG\tGEHEIMNIS-DARF-NIE-ERSCHEINEN\n' ;;
    *add-iam-policy-binding*)
        # Die ersten FAKE_BINDUNG_SCHEITERT Bindungen scheitern: Das neue
        # Dienstkonto ist noch nicht sichtbar.
        zaehler="${GCLOUD_PROTOKOLL}.bindungen"
        n=$(( $(cat "${zaehler}" 2>/dev/null || echo 0) + 1 ))
        echo "${n}" > "${zaehler}"
        (( n <= ${FAKE_BINDUNG_SCHEITERT:-0} )) && exit 1 ;;
    "compute instances describe"*)
        [[ -n "${FAKE_OHNE_VM:-}" ]] && exit 1
        echo "${FAKE_VM_STATUS:-TERMINATED}" ;;
    "compute instances get-serial-port-output"*) echo "urbancrime-startup: fertig" ;;
    "billing budgets list"*) [[ -z "${FAKE_OHNE_BUDGET:-}" ]] && echo "billingAccounts/x/budgets/y" ;;
    *describe*) [[ -n "${FAKE_NICHTS_DA:-}" ]] && exit 1 ;;
esac
exit 0
"""


@pytest.fixture
def gcloud(tmp_path, benutzbares_bash) -> Path:
    pfad = tmp_path / "gcloud"
    pfad.write_text(FALSCHES_GCLOUD, encoding="utf-8")
    pfad.chmod(0o755)
    return pfad


def echt(skript: str, *argumente: str, tmp_path: Path, gcloud: Path,
         stdin: str | None = None, **umgebung: str) -> tuple[subprocess.CompletedProcess, list[str]]:
    protokoll = tmp_path / "protokoll.txt"
    protokoll.write_text("", encoding="utf-8")
    fertig = rufe(skript, *argumente, tmp_path=tmp_path, gcloud=gcloud, stdin=stdin,
                  GCLOUD_PROTOKOLL=str(protokoll), **umgebung)
    return fertig, protokoll.read_text(encoding="utf-8").splitlines()


VERAENDERND = re.compile(r"\b(create|delete|enable|start|stop|rm|add-labels|"
                         r"add-iam-policy-binding|update)\b")


def test_ohne_projekt_wird_nichts_angelegt(tmp_path, gcloud):
    fertig, aufrufe = echt("aufbauen", tmp_path=tmp_path, gcloud=gcloud, FAKE_OHNE_PROJEKT="1")
    assert fertig.returncode != 0
    assert "nicht gefunden" in fertig.stderr
    assert not [a for a in aufrufe if VERAENDERND.search(a)], aufrufe


def test_ohne_abrechnung_wird_nichts_angelegt(tmp_path, gcloud):
    fertig, aufrufe = echt("aufbauen", tmp_path=tmp_path, gcloud=gcloud, FAKE_ABRECHNUNG="False")
    assert fertig.returncode != 0
    assert "Abrechnung" in fertig.stderr
    assert not [a for a in aufrufe if VERAENDERND.search(a)], aufrufe


def test_ein_zweiter_aufbau_legt_nichts_doppelt_an(tmp_path, gcloud):
    """Alles besteht schon - dann darf kein ``create`` kommen."""
    (tmp_path / "zustand").mkdir()
    (tmp_path / "zustand" / "hmac.env").write_text("S3_ACCESS_KEY=x\n", encoding="utf-8")
    fertig, aufrufe = echt("aufbauen", tmp_path=tmp_path, gcloud=gcloud,
                           FAKE_HMAC_LISTE="GOOGKENNUNG\\tACTIVE")
    assert fertig.returncode == 0, fertig.stderr
    angelegt = [a for a in aufrufe if re.search(r"\bcreate\b", a)]
    assert not angelegt, angelegt


def test_der_hmac_schluessel_erscheint_nie_auf_dem_bildschirm(tmp_path, gcloud):
    fertig, aufrufe = echt("aufbauen", tmp_path=tmp_path, gcloud=gcloud, FAKE_NICHTS_DA="1",
                           FAKE_OHNE_VM="1", FAKE_OHNE_BUDGET="1")
    assert fertig.returncode == 0, fertig.stderr
    assert any(a.startswith("storage hmac create") for a in aufrufe)
    geheim = "GEHEIMNIS-DARF-NIE-ERSCHEINEN"
    assert geheim not in fertig.stdout and geheim not in fertig.stderr
    datei = tmp_path / "zustand" / "hmac.env"
    assert geheim in datei.read_text(encoding="utf-8")
    assert "S3_ENDPOINT=storage.googleapis.com" in datei.read_text(encoding="utf-8")
    if os.name == "posix":
        assert datei.stat().st_mode & 0o777 == 0o600
    # Und ein frischer Aufbau legt alles an, mit dem Label.
    for befehl in ("compute networks create", "storage buckets create",
                   "compute instances create", "billing budgets create"):
        assert any(a.startswith(befehl) for a in aufrufe), befehl


@pytest.mark.parametrize("liste,datei", [
    ("GOOGALT\\tINACTIVE", True),     # nur ein deaktivierter Schluessel
    ("GOOGKENNUNG\\tACTIVE", False),  # aktiv, aber die Datei fehlt
])
def test_ein_neuer_schluessel_wenn_keiner_aktiv_ist_oder_die_datei_fehlt(
        tmp_path, gcloud, liste, datei):
    if datei:
        (tmp_path / "zustand").mkdir()
        (tmp_path / "zustand" / "hmac.env").write_text("S3_ACCESS_KEY=alt\n", encoding="utf-8")
    fertig, aufrufe = echt("aufbauen", tmp_path=tmp_path, gcloud=gcloud, FAKE_HMAC_LISTE=liste)
    assert fertig.returncode == 0, fertig.stderr
    assert any(a.startswith("storage hmac create") for a in aufrufe), aufrufe
    assert "GEHEIMNIS-DARF-NIE-ERSCHEINEN" in (tmp_path / "zustand" / "hmac.env").read_text(
        encoding="utf-8")


def test_das_neue_konto_bekommt_seine_bindung_im_zweiten_anlauf(tmp_path, gcloud):
    """IAM macht ein neues Dienstkonto erst nach Sekunden sichtbar."""
    fertig, aufrufe = echt("aufbauen", tmp_path=tmp_path, gcloud=gcloud,
                           FAKE_HMAC_LISTE="GOOGKENNUNG\\tACTIVE", FAKE_BINDUNG_SCHEITERT="2")
    assert fertig.returncode == 0, fertig.stderr
    eimer = [a for a in aufrufe if a.startswith("storage buckets add-iam-policy-binding")]
    assert len(eimer) == 3, aufrufe


def test_starten_ist_idempotent(tmp_path, gcloud):
    fertig, aufrufe = echt("starten", tmp_path=tmp_path, gcloud=gcloud, FAKE_VM_STATUS="RUNNING")
    assert fertig.returncode == 0, fertig.stderr
    assert not [a for a in aufrufe if "instances start" in a]
    fertig, aufrufe = echt("starten", tmp_path=tmp_path, gcloud=gcloud, FAKE_VM_STATUS="TERMINATED")
    assert fertig.returncode == 0, fertig.stderr
    assert [a for a in aufrufe if a.startswith("compute instances start urbancrime-probe")]


def test_starten_ohne_vm_verweist_auf_den_aufbau(tmp_path, gcloud):
    fertig, aufrufe = echt("starten", tmp_path=tmp_path, gcloud=gcloud, FAKE_OHNE_VM="1")
    assert fertig.returncode == 1 and "gcp-aufbauen.sh" in fertig.stderr
    assert not [a for a in aufrufe if VERAENDERND.search(a)]


DIGEST = "ghcr.io/x/urban-crime@sha256:" + "a" * 64


def test_starten_mit_env_legt_sie_nur_fuer_root_ab(tmp_path, gcloud):
    env = tmp_path / "vm.env"
    env.write_text(f"PIPELINE_IMAGE={DIGEST}\nS3_SECRET_KEY=geheim\n", encoding="utf-8")
    fertig, aufrufe = echt("starten", "--env", str(env), tmp_path=tmp_path, gcloud=gcloud,
                           FAKE_VM_STATUS="RUNNING")
    assert fertig.returncode == 0, fertig.stderr
    assert "geheim" not in fertig.stdout + fertig.stderr
    kopie = [a for a in aufrufe if a.startswith("compute scp")]
    assert kopie and "--tunnel-through-iap" in kopie[0]
    setzen = [a for a in aufrufe if "install -D -m 600 -o root" in a]
    assert setzen and "/opt/urbancrime/.env" in setzen[0]


@pytest.mark.parametrize("abbild", ["", "ghcr.io/x/urban-crime:aktuell",
                                    "ghcr.io/x/urban-crime@sha256:kurz"])
def test_starten_mit_env_verlangt_einen_digest(tmp_path, gcloud, abbild):
    env = tmp_path / "vm.env"
    env.write_text(f"PIPELINE_IMAGE={abbild}\n", encoding="utf-8")
    fertig, aufrufe = echt("starten", "--env", str(env), tmp_path=tmp_path, gcloud=gcloud,
                           FAKE_VM_STATUS="TERMINATED")
    assert fertig.returncode == 1 and "@sha256:" in fertig.stderr
    assert not [a for a in aufrufe if VERAENDERND.search(a) or a.startswith("compute scp")]


def test_starten_setzt_den_zweig_vor_dem_start(tmp_path, gcloud):
    fertig, aufrufe = echt("starten", "--zweig", "fr-44-47-google-cloud", tmp_path=tmp_path,
                           gcloud=gcloud, FAKE_VM_STATUS="TERMINATED")
    assert fertig.returncode == 0, fertig.stderr
    metadaten = [i for i, a in enumerate(aufrufe) if a.startswith("compute instances add-metadata")]
    start = [i for i, a in enumerate(aufrufe) if a.startswith("compute instances start")]
    assert metadaten and start and metadaten[0] < start[0], aufrufe
    assert "--metadata=repo-zweig=fr-44-47-google-cloud" in aufrufe[metadaten[0]]


def test_das_startskript_holt_den_zweig_bei_jedem_start():
    """Nicht nur beim ersten: Ein Holen im Block ``if [[ ! -d .git ]]``
    liesse die VM auf dem Stand ihres ersten Starts."""
    code = "\n".join(z for _, z in ohne_kommentare(STARTUP))
    erst = code[code.index('if [[ ! -d "${ZIEL}/.git" ]]'):]
    erst = erst[:erst.index("\nfi\n")]
    assert "fetch" not in erst, "das Holen steht nur im Block fuer den ersten Start"
    assert 'fetch -q origin' in code and "merge -q --ff-only" in code
    assert "metadatum repo-zweig" in code
    assert "--depth" not in code, "ein flacher Stand laesst sich nicht vorspulen"


def test_stoppen_haelt_an_ohne_zu_loeschen(tmp_path, gcloud):
    fertig, aufrufe = echt("stoppen", tmp_path=tmp_path, gcloud=gcloud, FAKE_VM_STATUS="RUNNING")
    assert fertig.returncode == 0, fertig.stderr
    assert [a for a in aufrufe if a.startswith("compute instances stop urbancrime-probe")]
    assert not [a for a in aufrufe if re.search(r"\b(delete|rm)\b", a)]
    fertig, aufrufe = echt("stoppen", tmp_path=tmp_path, gcloud=gcloud, FAKE_VM_STATUS="TERMINATED")
    assert fertig.returncode == 0
    assert not [a for a in aufrufe if "instances stop" in a], "zweimal gestoppt"


def test_eine_angehaltene_vm_wird_gestoppt(tmp_path, gcloud):
    """SUSPENDED zahlt weiter fuer den Arbeitsspeicher - das ist nicht gestoppt."""
    fertig, aufrufe = echt("stoppen", tmp_path=tmp_path, gcloud=gcloud, FAKE_VM_STATUS="SUSPENDED")
    assert fertig.returncode == 0, fertig.stderr
    assert [a for a in aufrufe if a.startswith("compute instances stop urbancrime-probe")]


def test_abbau_ohne_bestaetigung_loescht_nichts(tmp_path, gcloud):
    """Kein Terminal, kein ``--bestaetige``: Exit 1, kein einziger Loeschbefehl."""
    fertig, aufrufe = echt("abbauen", tmp_path=tmp_path, gcloud=gcloud)
    assert fertig.returncode == 1, fertig.stdout
    assert "nichts geloescht" in fertig.stderr
    assert not [a for a in aufrufe if VERAENDERND.search(a)], aufrufe


def test_abbau_mit_falscher_bestaetigung_loescht_nichts(tmp_path, gcloud):
    for falsch in ("ja", "y", "urbancrime-probe"):
        fertig, aufrufe = echt("abbauen", "--bestaetige", falsch, tmp_path=tmp_path, gcloud=gcloud)
        assert fertig.returncode == 1, falsch
        assert not [a for a in aufrufe if VERAENDERND.search(a)], (falsch, aufrufe)


def test_abbau_mit_bestaetigung_nimmt_alles_mit(tmp_path, gcloud):
    (tmp_path / "zustand").mkdir()
    hmac = tmp_path / "zustand" / "hmac.env"
    hmac.write_text("S3_SECRET_KEY=x\n", encoding="utf-8")
    fertig, aufrufe = echt("abbauen", "--bestaetige", "urbancrime", tmp_path=tmp_path,
                           gcloud=gcloud, FAKE_HMAC_LISTE="GOOGKENNUNG")
    assert fertig.returncode == 0, fertig.stderr
    for befehl in ("compute instances delete urbancrime-probe",
                   "compute resource-policies delete", "storage rm --recursive gs://urbancrime-probe-627957638734",
                   "storage hmac delete GOOGKENNUNG", "iam service-accounts delete",
                   "compute firewall-rules delete", "compute networks delete",
                   "billing budgets delete", "projects remove-iam-policy-binding urbancrime"):
        assert any(a.startswith(befehl) for a in aufrufe), befehl
    vm = next(a for a in aufrufe if a.startswith("compute instances delete"))
    assert "--delete-disks=all" in vm
    rolle = next(a for a in aufrufe if a.startswith("projects remove-iam-policy-binding"))
    assert "compute-system.iam.gserviceaccount.com" in rolle
    assert "--role=roles/compute.instanceAdmin.v1" in rolle
    # Das ganze Schluesselverzeichnis, nicht nur die eine Datei.
    assert not hmac.exists() and not (tmp_path / "zustand").exists()


def test_abbau_ohne_bestaetigung_laesst_die_schluessel_liegen(tmp_path, gcloud):
    (tmp_path / "zustand").mkdir()
    hmac = tmp_path / "zustand" / "hmac.env"
    hmac.write_text("S3_SECRET_KEY=x\n", encoding="utf-8")
    fertig, _ = echt("abbauen", tmp_path=tmp_path, gcloud=gcloud)
    assert fertig.returncode == 1 and hmac.exists()
