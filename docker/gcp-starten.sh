#!/usr/bin/env bash
#
# Startet die Probe-VM und nennt die Befehle, mit denen man an Dashboard und
# Kibana kommt (FR-47). Laeuft sie schon, startet es nichts (idempotent).
#
#   docker/gcp-starten.sh                    # starten
#   docker/gcp-starten.sh --env .env.gcp     # starten und die .env der VM setzen
#   docker/gcp-starten.sh --zweig <zweig>    # vorher den Zweig der VM setzen
#   docker/gcp-starten.sh --nur-kibana       # starten, nur Elasticsearch und Kibana
#   docker/gcp-starten.sh --trocken          # nur zeigen, was geschaehe
#
# **--nur-kibana** (Entscheid vom 15.11.2026): Kibana fuer den Tunneldienst,
# der es nach aussen bringt, ohne Dashboard und ohne Bau. Nach dem Start der
# VM kopiert tools/kopiere_release.py das aktuelle Release des Quelleimers in
# den Eimer der Probe (--von ${GCP_ZUSTAND}/quelle.env, --nach .../hmac.env;
# Python aus GCP_PYTHON, Vorgabe python). Dann stoppt es auf der VM das
# Dashboard, startet nur elasticsearch und kibana, setzt mit holen aktuell
# --einsetzen das Release ein und fragt serving.pruefe_stand: Stimmt der
# Stand, wird nichts geladen; sonst load_elasticsearch, build_kibana und noch
# einmal pruefe_stand. Fehlt das Release, bricht es mit Hinweis ab - die VM
# laeuft dann weiter.
#
# **--zweig ZWEIG** setzt das Metadatum repo-zweig. Das Startskript holt
# und spult diesen Zweig bei jedem Start vor; laeuft die VM schon, gilt er
# ab dem naechsten Start.
#
# **--env DATEI** kopiert eine fertige .env (aus .env.gcp.example und der
# hmac.env von gcp-aufbauen.sh) ueber IAP auf die VM nach
# /opt/urbancrime/.env, Modus 600, root. Die Datei geht nie durch die
# Ausgabe; ein zweites --env ersetzt die erste.
#
# Um 20:00 Zuericher Zeit stoppt der Zeitplan die VM ohnehin. Wer frueher
# fertig ist: docker/gcp-stoppen.sh.
#
set -Eeuo pipefail

SKRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=docker/gcp-gemeinsam.sh
source "${SKRIPT_DIR}/gcp-gemeinsam.sh"

# Die Adresse, unter der ein Tunneldienst Kibana zeigt (auf srv01: Dienst
# kibana in docker-compose.srv01.yml). Ohne Vorgabe - die Probe nennt keinen
# Server (tests/test_gcp_stapel.py, test_keine_srv01_namen); gesetzt, etwa in
# der Shell, steht sie in der Ausgabe.
: "${GCP_KIBANA_ADRESSE:=}"

hilfe() {
    # Der Kopf bis vor "set -Eeuo pipefail", ohne Rautenzeichen.
    awk 'NR > 2 && /^set -Eeuo/ { exit } NR > 2' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

ssh_auf_vm() {
    "${GCLOUD}" compute ssh "${GCP_VM}" --project "${GCP_PROJEKT}" \
        --zone "${GCP_ZONE}" --tunnel-through-iap "$@"
}

# Direkt nach dem Start nimmt die VM noch keine SSH-Verbindung an.
warte_auf_ssh() {
    if (( TROCKEN )); then
        return 0
    fi
    local versuch
    for versuch in 1 2 3 4 5 6 7 8 9 10 11 12; do
        if ssh_auf_vm --command true >/dev/null 2>&1; then
            return 0
        fi
        melde "SSH noch nicht bereit (Versuch ${versuch} von 12), Pause 10 s"
        sleep 10
    done
    warne "SSH ueber IAP antwortet nicht - Firewall ${GCP_FIREWALL} und die IAP-Rolle pruefen."
    return 1
}

# Der Vergleich der Releases ist nur einer der Umgebung, wenn beide Seiten
# dasselbe Abbild fahren - also verlangt die .env einen Digest, keine Marke.
pruefe_abbild() {
    local datei="$1" zeile
    if [[ ! -f "${datei}" ]]; then
        warne "--env ${datei}: keine Datei"
        return 1
    fi
    zeile="$(grep -E '^PIPELINE_IMAGE=' "${datei}" | tail -n 1 || true)"
    if [[ ! "${zeile}" =~ @sha256:[0-9a-f]{64}$ ]]; then
        warne "--env ${datei}: PIPELINE_IMAGE ohne @sha256:-Digest - nichts kopiert."
        warne "  Den Digest der Vergleichsumgebung uebernehmen, keine Marke."
        return 1
    fi
}

env_setzen() {
    local datei="$1"
    if [[ ! -f "${datei}" ]]; then
        warne "--env ${datei}: keine Datei"
        return 1
    fi
    warte_auf_ssh
    fuehre "${GCLOUD}" compute scp "${datei}" "${GCP_VM}:/tmp/urbancrime.env" \
        --project "${GCP_PROJEKT}" --zone "${GCP_ZONE}" --tunnel-through-iap
    fuehre "${GCLOUD}" compute ssh "${GCP_VM}" --project "${GCP_PROJEKT}" \
        --zone "${GCP_ZONE}" --tunnel-through-iap --command \
        "sudo install -D -m 600 -o root -g root /tmp/urbancrime.env ${GCP_STAPEL_DIR}/.env && rm -f /tmp/urbancrime.env"
}

# Die Befehle fuer --nur-kibana auf der VM, als eine Zeile fuer
# "gcloud compute ssh --command". Zuerst immer "holen aktuell --einsetzen":
# pruefe_stand misst gegen das lokal eingesetzte Release in arbeitsdaten, und
# nach einem neuen Release im Eimer saehe es sonst weiter "stimmt". Holen
# ueberspringt, was schon gleich da ist. Erst danach ist pruefe_stand der
# Schalter - nur fuer load_elasticsearch (baut jedes Mal neu, Alias umlegen,
# rund 4,5 Minuten) und build_kibana. Das Dashboard (restart: unless-stopped)
# kaeme nach einem vollen Start bei jedem Boot wieder; hier wird es gestoppt.
kibana_auf_vm_befehl() {
    local verzeichnis="$1" c
    c="sudo docker compose -f docker-compose.gcp.yml"
    printf '%s' "set -e; cd ${verzeichnis}; C=\"${c}\"; \$C stop dashboard; "
    printf '%s' "\$C up -d --wait elasticsearch kibana; "
    printf '%s' "\$C run --rm pipeline python -m orchestration.release holen aktuell --einsetzen; "
    printf '%s' "if \$C run --rm pipeline python -m serving.pruefe_stand --knapp; then "
    printf '%s' "echo 'pruefe_stand: Stand stimmt - Laden uebersprungen'; "
    printf '%s' "else \$C run --rm pipeline python -m serving.load_elasticsearch; "
    printf '%s' "\$C run --rm pipeline python -m serving.build_kibana; "
    printf '%s' "\$C run --rm pipeline python -m serving.pruefe_stand; fi"
    printf '\n'
}

# Das Release des Quelleimers in den Eimer der Probe (tools/kopiere_release.py).
# Vorgabe "python": das Python der aktiven Umgebung, das dotenv und storage
# kennt; ein System-python3 hat beides meist nicht.
release_kopieren() {
    local werkzeug
    werkzeug="$(cd "${SKRIPT_DIR}/.." && pwd)/tools/kopiere_release.py"
    if ! fuehre "${GCP_PYTHON:-python}" "${werkzeug}" --release aktuell \
            --von "${GCP_ZUSTAND}/quelle.env" --nach "${GCP_ZUSTAND}/hmac.env"; then
        warne "kopiere_release ist gescheitert, der Grund steht darueber."
        warne "  Quelle: ${GCP_ZUSTAND}/quelle.env, Ziel: ${GCP_ZUSTAND}/hmac.env"
        warne "  Die VM ${GCP_VM} laeuft weiter; stoppen mit docker/gcp-stoppen.sh."
        return 1
    fi
}

# Wo Kibana ankommt: ueber den Tunneldienst, oder hier mit -L 5601.
kibana_zugang() {
    if [[ -n "${GCP_KIBANA_ADRESSE}" ]]; then
        melde "  ${GCP_KIBANA_ADRESSE}   (Tunneldienst, Konto $(tunnel_email))"
    fi
    melde "  ${GCLOUD} compute ssh ${GCP_VM} --project ${GCP_PROJEKT} --zone ${GCP_ZONE} --tunnel-through-iap -- -L ${GCP_KIBANA_PORT}:localhost:${GCP_KIBANA_PORT} -N"
    melde "  Kibana: http://localhost:${GCP_KIBANA_PORT}"
}

# Wann der Zeitplan die VM als Naechstes stoppt. Bis zum 15.11.2026 stand hier
# fest "um 20:00" - auch nach einem Start um 20:49, der bis zum naechsten Abend
# lief. Gelesen werden Minute und Stunde aus GCP_ABENDSTOPP (Cron, taeglich);
# GCP_JETZT_HHMM ersetzt die Uhr, fuer die Tests.
abendstopp_hinweis() {
    local minute stunde jetzt stopp tag
    read -r minute stunde _ <<< "${GCP_ABENDSTOPP}"
    stopp=$(( 10#${stunde} * 100 + 10#${minute} ))
    jetzt="${GCP_JETZT_HHMM:-$(TZ="${GCP_ZEITZONE}" date +%H%M)}"
    tag="heute"
    if (( 10#${jetzt} >= stopp )); then
        tag="erst morgen"
    fi
    melde "$(printf 'Die VM stoppt %s um %02d:%02d (%s) - frueher: docker/gcp-stoppen.sh' \
        "${tag}" "$(( 10#${stunde} ))" "$(( 10#${minute} ))" "${GCP_ZEITZONE}")"
}

nur_kibana() {
    release_kopieren
    warte_auf_ssh
    if ! fuehre "${GCLOUD}" compute ssh "${GCP_VM}" --project "${GCP_PROJEKT}" \
            --zone "${GCP_ZONE}" --tunnel-through-iap --command \
            "$(kibana_auf_vm_befehl "${GCP_STAPEL_DIR}")"; then
        warne "Einspielen auf der VM gescheitert, der Grund steht darueber - die VM ${GCP_VM} laeuft weiter."
        return 1
    fi
    melde ""
    melde "Kibana laeuft auf ${GCP_VM}:${GCP_KIBANA_PORT}, erreichbar unter:"
    kibana_zugang
    melde ""
    abendstopp_hinweis
}

main() {
    local env_datei="" zweig="" kibana=0
    while (( $# )); do
        case "$1" in
            --trocken) TROCKEN=1 ;;
            --nur-kibana) kibana=1 ;;
            --env) shift; env_datei="${1:-}"
                   [[ -n "${env_datei}" ]] || { warne "--env braucht eine Datei"; return 64; } ;;
            --zweig) shift; zweig="${1:-}"
                     [[ -n "${zweig}" ]] || { warne "--zweig braucht einen Namen"; return 64; } ;;
            -h|--help) hilfe; return 0 ;;
            *) warne "Unbekannt: $1"; hilfe >&2; return 64 ;;
        esac
        shift
    done

    if [[ -n "${env_datei}" ]]; then
        pruefe_abbild "${env_datei}"
    fi

    local status
    status="$(vm_status)"
    if [[ -z "${status}" ]] && (( ! TROCKEN )); then
        warne "VM ${GCP_VM} gibt es nicht in ${GCP_PROJEKT}/${GCP_ZONE} - zuerst docker/gcp-aufbauen.sh."
        return 1
    fi
    if [[ -n "${zweig}" ]]; then
        fuehre "${GCLOUD}" compute instances add-metadata "${GCP_VM}" \
            --project "${GCP_PROJEKT}" --zone "${GCP_ZONE}" --metadata=repo-zweig="${zweig}"
        if [[ "${status}" == "RUNNING" ]]; then
            melde "Zweig ${zweig} gilt ab dem naechsten Start der VM."
        fi
    fi
    if [[ "${status}" == "RUNNING" ]]; then
        melde "VM ${GCP_VM} laeuft schon."
    else
        fuehre "${GCLOUD}" compute instances start "${GCP_VM}" \
            --project "${GCP_PROJEKT}" --zone "${GCP_ZONE}"
    fi

    if [[ -n "${env_datei}" ]]; then
        env_setzen "${env_datei}"
    fi

    if (( kibana )); then
        nur_kibana
        return
    fi

    melde ""
    melde "Weiterleitung (in einem eigenen Terminal offen lassen):"
    ssh_befehle
    melde ""
    melde "Auf der VM (cd ${GCP_STAPEL_DIR}):"
    melde "  read -rs GHCR_TOKEN && printf '%s' \"\$GHCR_TOKEN\" | sudo docker login ghcr.io -u <konto> --password-stdin && unset GHCR_TOKEN   # einmal je VM"
    melde "  sudo docker compose -f docker-compose.gcp.yml up -d --wait"
    melde "  # vorpruefung nur vor einem Lauf mit Ingestion - sie verlangt CENSUS_API_KEY, den --ohne-ingestion nicht braucht"
    melde "  # --jahre wie im Release, gegen das verglichen wird (release.json, years)"
    melde "  sudo docker compose -f docker-compose.gcp.yml run --rm pipeline python -m orchestration.run_all --ohne-ingestion --jahre 2021-2026"
    melde "  sudo docker compose -f docker-compose.gcp.yml run --rm pipeline python -m orchestration.release holen aktuell --einsetzen"
    melde "  sudo docker compose -f docker-compose.gcp.yml run --rm pipeline python -m serving.load_elasticsearch"
    melde "  sudo docker compose -f docker-compose.gcp.yml run --rm pipeline python -m serving.build_kibana"
    melde "  sudo docker compose -f docker-compose.gcp.yml run --rm pipeline python -m serving.pruefe_stand"
    melde ""
    abendstopp_hinweis
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
