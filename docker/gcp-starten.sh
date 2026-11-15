#!/usr/bin/env bash
#
# Startet die Probe-VM und nennt die Befehle, mit denen man an Dashboard und
# Kibana kommt (FR-47). Laeuft sie schon, startet es nichts (idempotent).
#
#   docker/gcp-starten.sh                    # starten
#   docker/gcp-starten.sh --env .env.gcp     # starten und die .env der VM setzen
#   docker/gcp-starten.sh --zweig <zweig>    # vorher den Zweig der VM setzen
#   docker/gcp-starten.sh --trocken          # nur zeigen, was geschaehe
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

main() {
    local env_datei="" zweig=""
    while (( $# )); do
        case "$1" in
            --trocken) TROCKEN=1 ;;
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

    melde ""
    melde "Weiterleitung (in einem eigenen Terminal offen lassen):"
    ssh_befehle
    melde ""
    melde "Auf der VM (cd ${GCP_STAPEL_DIR}):"
    melde "  read -rs GHCR_TOKEN && printf '%s' \"\$GHCR_TOKEN\" | sudo docker login ghcr.io -u <konto> --password-stdin && unset GHCR_TOKEN   # einmal je VM"
    melde "  sudo docker compose -f docker-compose.gcp.yml up -d --wait"
    melde "  sudo docker compose -f docker-compose.gcp.yml run --rm pipeline python -m orchestration.vorpruefung"
    melde "  # --jahre wie im Release, gegen das verglichen wird (release.json, years)"
    melde "  sudo docker compose -f docker-compose.gcp.yml run --rm pipeline python -m orchestration.run_all --ohne-ingestion --jahre 2021-2026"
    melde "  sudo docker compose -f docker-compose.gcp.yml run --rm pipeline python -m orchestration.release holen aktuell --einsetzen"
    melde "  sudo docker compose -f docker-compose.gcp.yml run --rm pipeline python -m serving.load_elasticsearch"
    melde "  sudo docker compose -f docker-compose.gcp.yml run --rm pipeline python -m serving.build_kibana"
    melde "  sudo docker compose -f docker-compose.gcp.yml run --rm pipeline python -m serving.pruefe_stand"
    melde ""
    melde "Die VM stoppt um 20:00 (${GCP_ZEITZONE}); frueher: docker/gcp-stoppen.sh"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
