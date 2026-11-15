# shellcheck shell=bash
#
# Was die vier Skripte fuer die Google-Cloud-Probe teilen (FR-44, FR-47):
# Namen, Vorgaben, der Trockenmodus und die beiden Arten, gcloud zu rufen.
# Wird eingelesen, nicht ausgefuehrt:
#
#     source docker/gcp-gemeinsam.sh
#
# **Alles ist ueberschreibbar.** Projekt, Region, Zone, VM-Name und Eimer
# kommen aus Variablen mit Vorgaben (Plan, Implementation Notes). Wer ein
# zweites Projekt probt, setzt GCP_PROJEKT und sonst nichts.
#
# **Warum ein Trockenmodus.** Jeder Befehl, der etwas anlegt, startet,
# stoppt oder loescht, geht durch ``fuehre``. Mit --trocken gibt ``fuehre``
# nur aus, was es taete, und lesende Abfragen (``frage``) fragen gar nicht
# erst - die Skripte laufen dann ohne Netz, ohne gcloud und ohne Konto.
# Genau so pruefen sie die Tests (tests/test_gcp_stapel.py), und genau so
# sieht man vor dem ersten echten Lauf, was er kostet.
#
# **Keine Bash-4-Konstrukte.** macOS liefert Bash 3.2, und dort laufen die
# Tests; kein assoziatives Feld, kein ${x,,}, kein mapfile (dieselbe Regel
# wie in docker/srv01-abbild-einsetzen.sh).

: "${GCP_PROJEKT:=urbancrime}"
# Zuerich (Entscheid vom 15.11.2026).
: "${GCP_REGION:=europe-west6}"
: "${GCP_ZONE:=europe-west6-a}"
: "${GCP_VM:=urbancrime-probe}"
# Leer heisst: urbancrime-probe-<projektnummer>, beim ersten Gebrauch
# aufgeloest (``eimer``). Eimernamen sind weltweit eindeutig; die
# Projektnummer macht ihn das, ohne dass jemand einen Namen erfindet.
: "${GCP_EIMER:=}"
# e2-standard-2: zwei vCPU, 8 GB (Entscheid vom 15.11.2026).
: "${GCP_MASCHINE:=e2-standard-2}"
# Hoechstens 30 GB (Plan, Kosten). pd-balanced statt pd-standard: Der Bau
# liest und schreibt Parquet, und pd-standard drosselt bei 30 GB auf wenige
# hundert IOPS.
: "${GCP_DISK_GB:=30}"
: "${GCP_DISK_TYP:=pd-balanced}"
: "${GCP_ABBILD_FAMILIE:=ubuntu-2404-lts-amd64}"
: "${GCP_ABBILD_PROJEKT:=ubuntu-os-cloud}"
# Woher die VM die Compose-Datei holt. Das Repository ist oeffentlich. Der
# Zweig ist ein Metadatum der VM und wird bei jedem Start geholt
# (gcp-startup.sh); solange docker-compose.gcp.yml nicht auf main liegt,
# setzt ihn "gcp-starten.sh --zweig <zweig>".
: "${GCP_REPO_URL:=https://github.com/artanmusollaj-ops/Crime-Data-Gruppe3.git}"
: "${GCP_REPO_ZWEIG:=main}"
# Der Abendstopp (Entscheid vom 15.11.2026): taeglich 20:00 Zuericher Zeit.
: "${GCP_ABENDSTOPP:=0 20 * * *}"
: "${GCP_ZEITZONE:=Europe/Zurich}"
# Budget mit drei Schwellen bei 15, 30 und 45 von 60 (Plan, Always). Die
# Waehrung ist die des Rechnungskontos; ein Studienguthaben in Dollar
# braucht USD, ein Konto in Franken CHF.
: "${GCP_BUDGET_BETRAG:=60}"
: "${GCP_BUDGET_WAEHRUNG:=USD}"
: "${GCP_BUDGET_SCHWELLEN:=0.25 0.50 0.75}"
# Wohin die HMAC-Schluessel geschrieben werden: auf den Rechner, der
# aufbaut, ausserhalb des Repositorys, nur fuer den Besitzer lesbar.
: "${GCP_ZUSTAND:=${HOME}/.config/urbancrime-probe}"
: "${GCLOUD:=gcloud}"

# Das Label jeder Ressource, die es tragen kann (Plan, Always).
readonly GCP_LABELS="zweck=urbancrime-probe"
# Abgeleitete Namen: alles haengt am VM-Namen, damit Aufbau und Abbau
# dieselben Dinge meinen.
GCP_NETZ="${GCP_VM}-netz"
GCP_SUBNETZ="${GCP_VM}-netz-${GCP_REGION}"
GCP_FIREWALL="${GCP_VM}-ssh-iap"
# Die zweite Regel: Kibana (tcp:5601), ebenfalls nur aus dem IAP-Bereich.
# Durch sie kommt der Tunneldienst, der Kibana nach aussen bringt
# (gcloud compute start-iap-tunnel, Entscheid vom 15.11.2026).
GCP_FIREWALL_KIBANA="${GCP_VM}-kibana-iap"
GCP_ZEITPLAN="${GCP_VM}-abendstopp"
GCP_KONTO_NAME="${GCP_VM}-speicher"
# Das Konto des Tunneldienstes: darf einen IAP-Tunnel auf Port 5601 oeffnen
# und die eine VM sehen, sonst nichts - kein SSH, kein Eimer.
GCP_TUNNEL_NAME="${GCP_VM}-tunnel"
GCP_BUDGET_NAME="${GCP_VM}-budget"
# Der einzige Weg herein: SSH ueber Identity-Aware Proxy. Das ist der
# Adressbereich, aus dem IAP die Verbindungen aufbaut (Google-Dokumentation
# "Using IAP for TCP forwarding", Abschnitt "Create a firewall rule").
readonly GCP_IAP_BEREICH="35.235.240.0/20"
# Die Ports, die ``gcp-starten.sh`` weiterleitet: Dashboard und Kibana. Die
# Compose-Datei bindet das Dashboard an 127.0.0.1 der VM, Kibana an alle
# Adressen; von aussen ist trotzdem nur 5601 offen, und nur fuer den
# IAP-Bereich (GCP_FIREWALL_KIBANA).
readonly GCP_PORTS="8050 5601"
# Der eine Port, den das Tunnelkonto erreichen darf.
readonly GCP_KIBANA_PORT="5601"
# Wo der Stapel auf der VM liegt (gcp-startup.sh legt ihn dorthin).
readonly GCP_STAPEL_DIR="/opt/urbancrime"

TROCKEN=0

melde() { printf '%s\n' "$*"; }
warne() { printf '%s\n' "$*" >&2; }

# Ein verändernder Befehl. Im Trockenmodus nur ausgegeben.
fuehre() {
    if (( TROCKEN )); then
        printf '[trocken]'
        printf ' %q' "$@"
        printf '\n'
        return 0
    fi
    printf '+' >&2
    printf ' %q' "$@" >&2
    printf '\n' >&2
    "$@"
}

# Wiederholt einen Befehl, bis er gelingt: hoechstens GCP_VERSUCHE Mal,
# GCP_PAUSE_S Sekunden dazwischen. Gebraucht direkt nach dem Anlegen eines
# Dienstkontos - IAM macht es erst nach einigen Sekunden sichtbar, und eine
# Bindung oder ein HMAC-Schluessel davor scheitert mit "does not exist"
# (Google-Dokumentation "Create service accounts", Hinweis zur Konsistenz).
wiederhole() {
    local versuch=1
    while true; do
        "$@" && return 0
        if (( versuch >= ${GCP_VERSUCHE:-6} )); then
            return 1
        fi
        warne "Versuch ${versuch} gescheitert, Pause ${GCP_PAUSE_S:-10} s: $1 ${2:-} ${3:-}"
        sleep "${GCP_PAUSE_S:-10}"
        versuch=$(( versuch + 1 ))
    done
}

# Ein lesender Befehl. Im Trockenmodus nicht ausgefuehrt und "unbekannt"
# (Rueckgabe 1) - der Aufrufer zeigt dann, was er anlegen wuerde.
frage() {
    if (( TROCKEN )); then
        return 1
    fi
    "$@" 2>/dev/null
}

# Die Projektnummer; im Trockenmodus ein Platzhalter, ausser sie ist gesetzt.
projektnummer() {
    if [[ -n "${GCP_PROJEKTNUMMER:-}" ]]; then
        printf '%s\n' "${GCP_PROJEKTNUMMER}"
    elif (( TROCKEN )); then
        printf '%s\n' "<projektnummer>"
    else
        "${GCLOUD}" projects describe "${GCP_PROJEKT}" --format='value(projectNumber)'
    fi
}

eimer() {
    if [[ -n "${GCP_EIMER}" ]]; then
        printf '%s\n' "${GCP_EIMER}"
    else
        printf 'urbancrime-probe-%s\n' "$(projektnummer)"
    fi
}

konto_email() {
    printf '%s@%s.iam.gserviceaccount.com\n' "${GCP_KONTO_NAME}" "${GCP_PROJEKT}"
}

tunnel_email() {
    printf '%s@%s.iam.gserviceaccount.com\n' "${GCP_TUNNEL_NAME}" "${GCP_PROJEKT}"
}

# Wohin der Schluessel des Tunnelkontos kommt (Modus 600).
tunnel_schluessel() {
    printf '%s/tunnel-schluessel.json\n' "${GCP_ZUSTAND}"
}

# Der Zustand der VM: RUNNING, TERMINATED, ... oder leer, wenn es sie nicht
# gibt (und im Trockenmodus).
vm_status() {
    frage "${GCLOUD}" compute instances describe "${GCP_VM}" \
        --project "${GCP_PROJEKT}" --zone "${GCP_ZONE}" \
        --format='value(status)' || true
}

# Die SSH-Befehle mit Port-Weiterleitung, einer je Zeile.
ssh_befehle() {
    local weiter="" port
    for port in ${GCP_PORTS}; do
        weiter="${weiter} -L ${port}:localhost:${port}"
    done
    melde "  ${GCLOUD} compute ssh ${GCP_VM} --project ${GCP_PROJEKT} --zone ${GCP_ZONE} --tunnel-through-iap --${weiter} -N"
    melde "  Dashboard: http://localhost:8050   Kibana: http://localhost:5601"
    melde "  Eine Shell auf der VM: ${GCLOUD} compute ssh ${GCP_VM} --project ${GCP_PROJEKT} --zone ${GCP_ZONE} --tunnel-through-iap"
}
