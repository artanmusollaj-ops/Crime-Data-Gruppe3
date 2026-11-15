#!/usr/bin/env bash
#
# Haelt die Probe-VM an, ohne etwas zu loeschen (FR-47). Disk, Eimer,
# Schluessel und .env bleiben; ein gcp-starten.sh macht dort weiter.
# Ist sie schon gestoppt, tut es nichts (idempotent).
#
#   docker/gcp-stoppen.sh             # stoppen
#   docker/gcp-stoppen.sh --trocken   # nur zeigen, was geschaehe
#
# Im Stopp zahlt nur noch die Disk (30 GB, rund 3,60 $ im Monat) und der
# Eimer. Die externe Adresse ist ephemer und faellt mit dem Stopp weg.
#
set -Eeuo pipefail

SKRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=docker/gcp-gemeinsam.sh
source "${SKRIPT_DIR}/gcp-gemeinsam.sh"

hilfe() {
    # Der Kopf bis vor "set -Eeuo pipefail", ohne Rautenzeichen.
    awk 'NR > 2 && /^set -Eeuo/ { exit } NR > 2' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

main() {
    while (( $# )); do
        case "$1" in
            --trocken) TROCKEN=1 ;;
            -h|--help) hilfe; return 0 ;;
            *) warne "Unbekannt: $1"; hilfe >&2; return 64 ;;
        esac
        shift
    done

    local status
    status="$(vm_status)"
    case "${status}" in
        # Nur TERMINATED ist gestoppt. Eine angehaltene VM (SUSPENDED) zahlt
        # weiter fuer ihren Arbeitsspeicher und wird deshalb gestoppt.
        TERMINATED)
            melde "VM ${GCP_VM} ist schon angehalten (${status})."
            return 0 ;;
        "")
            if (( ! TROCKEN )); then
                melde "VM ${GCP_VM} gibt es nicht in ${GCP_PROJEKT}/${GCP_ZONE} - nichts zu stoppen."
                return 0
            fi ;;
    esac
    fuehre "${GCLOUD}" compute instances stop "${GCP_VM}" \
        --project "${GCP_PROJEKT}" --zone "${GCP_ZONE}"
    (( TROCKEN )) || melde "VM ${GCP_VM} angehalten; Disk und Eimer bleiben."
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
