#!/usr/bin/env bash
#
# Baut die Google-Cloud-Probe ab: VM samt Disk, Eimer samt Inhalt,
# HMAC-Schluessel, Dienstkonto, Tunnelkonto, Zeitplan, beide Firewall-Regeln,
# Netz und Budget - alles, was gcp-aufbauen.sh anlegt. **Nicht umkehrbar**: Was im Eimer liegt, ist
# danach weg. Deshalb nur nach ausdruecklicher Bestaetigung (Plan, Always).
#
#   docker/gcp-abbauen.sh                         # fragt nach der Projekt-ID
#   docker/gcp-abbauen.sh --bestaetige urbancrime # ohne Rueckfrage
#   docker/gcp-abbauen.sh --trocken               # nur zeigen, was geschaehe
#
# Bestaetigt ist nur, wer die **Projekt-ID** eintippt oder mit --bestaetige
# nennt - nicht "ja", nicht "y". Ohne Terminal und ohne --bestaetige loescht
# das Skript nichts und endet mit 1.
#
# Mit abgebaut wird die Rolle roles/compute.instanceAdmin.v1, die
# gcp-aufbauen.sh dem Compute-Dienstagenten fuer den Abendstopp gibt, und
# das Verzeichnis ${GCP_ZUSTAND} (Vorgabe ~/.config/urbancrime-probe/) mit
# den Schluesseln darin. Nicht abgebaut werden die aktivierten APIs: Sie
# kosten nichts.
#
set -Eeuo pipefail

SKRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=docker/gcp-gemeinsam.sh
source "${SKRIPT_DIR}/gcp-gemeinsam.sh"

hilfe() {
    # Der Kopf bis vor "set -Eeuo pipefail", ohne Rautenzeichen.
    awk 'NR > 2 && /^set -Eeuo/ { exit } NR > 2' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

bestaetigt() {
    local genannt="$1" eingabe=""
    if (( TROCKEN )); then
        melde "[trocken] ohne Bestaetigung - es wird nichts geloescht"
        return 0
    fi
    if [[ -n "${genannt}" ]]; then
        [[ "${genannt}" == "${GCP_PROJEKT}" ]] && return 0
        warne "--bestaetige ${genannt} ist nicht das Projekt ${GCP_PROJEKT} - nichts geloescht."
        return 1
    fi
    if [[ ! -t 0 ]]; then
        warne "Keine Bestaetigung (kein Terminal, kein --bestaetige) - nichts geloescht."
        return 1
    fi
    warne "Loescht VM, Disk, Eimer gs://$(eimer) mit Inhalt und die Schluessel in ${GCP_PROJEKT}."
    read -r -p "Zur Bestaetigung die Projekt-ID eintippen: " eingabe || true
    if [[ "${eingabe}" == "${GCP_PROJEKT}" ]]; then
        return 0
    fi
    warne "Nicht bestaetigt - nichts geloescht."
    return 1
}

gibt_es() {
    frage "$@" >/dev/null
}

main() {
    local genannt=""
    while (( $# )); do
        case "$1" in
            --trocken) TROCKEN=1 ;;
            --bestaetige) shift; genannt="${1:-}"
                          [[ -n "${genannt}" ]] || { warne "--bestaetige braucht die Projekt-ID"; return 64; } ;;
            -h|--help) hilfe; return 0 ;;
            *) warne "Unbekannt: $1"; hilfe >&2; return 64 ;;
        esac
        shift
    done

    bestaetigt "${genannt}" || return 1

    local name email tunnel kennung konto budget
    name="$(eimer)"
    email="$(konto_email)"

    # Die VM zuerst: Sie haelt den Zeitplan, und ohne sie laesst er sich
    # loeschen. --delete-disks=all nimmt die Boot-Disk mit.
    if gibt_es "${GCLOUD}" compute instances describe "${GCP_VM}" \
            --project "${GCP_PROJEKT}" --zone "${GCP_ZONE}" || (( TROCKEN )); then
        fuehre "${GCLOUD}" compute instances delete "${GCP_VM}" \
            --project "${GCP_PROJEKT}" --zone "${GCP_ZONE}" --delete-disks=all --quiet
    fi
    if gibt_es "${GCLOUD}" compute resource-policies describe "${GCP_ZEITPLAN}" \
            --project "${GCP_PROJEKT}" --region "${GCP_REGION}" || (( TROCKEN )); then
        fuehre "${GCLOUD}" compute resource-policies delete "${GCP_ZEITPLAN}" \
            --project "${GCP_PROJEKT}" --region "${GCP_REGION}" --quiet
    fi

    # Der Eimer mit allem darin. Ohne Versionierung und ohne weiches
    # Loeschen angelegt - danach liegt nichts mehr, das zahlt.
    if gibt_es "${GCLOUD}" storage buckets describe "gs://${name}" --project "${GCP_PROJEKT}" \
            || (( TROCKEN )); then
        fuehre "${GCLOUD}" storage rm --recursive "gs://${name}" --project "${GCP_PROJEKT}"
    fi

    # HMAC: erst deaktivieren, dann loeschen - ein aktiver Schluessel laesst
    # sich nicht loeschen.
    if (( TROCKEN )); then
        fuehre "${GCLOUD}" storage hmac update "<zugangskennung>" --deactivate --project "${GCP_PROJEKT}"
        fuehre "${GCLOUD}" storage hmac delete "<zugangskennung>" --project "${GCP_PROJEKT}"
    else
        for kennung in $(frage "${GCLOUD}" storage hmac list --project "${GCP_PROJEKT}" \
                --service-account "${email}" --format='value(accessId)' || true); do
            fuehre "${GCLOUD}" storage hmac update "${kennung}" --deactivate --project "${GCP_PROJEKT}" || true
            fuehre "${GCLOUD}" storage hmac delete "${kennung}" --project "${GCP_PROJEKT}"
        done
    fi
    if gibt_es "${GCLOUD}" iam service-accounts describe "${email}" --project "${GCP_PROJEKT}" \
            || (( TROCKEN )); then
        fuehre "${GCLOUD}" iam service-accounts delete "${email}" --project "${GCP_PROJEKT}" --quiet
    fi

    # Das Tunnelkonto fuer Kibana: zuerst seine Rolle im Projekt, dann das
    # Konto samt seinen Schluesseln. Die Rolle **unabhaengig davon, ob es das
    # Konto noch gibt**: Ist es schon weg, steht die Bindung als
    # "deleted:serviceAccount:<email>?uid=<n>" in der Richtlinie, und auch
    # die gehoert entfernt. Fehlt eine Bindung, ist das kein Fehler. Die
    # Bindung auf der VM ist mit der VM weg.
    tunnel="$(tunnel_email)"
    fuehre "${GCLOUD}" projects remove-iam-policy-binding "${GCP_PROJEKT}" \
        --member="serviceAccount:${tunnel}" --role=roles/iap.tunnelResourceAccessor \
        --all --quiet \
        || warne "Rolle des Tunnelkontos: nicht entfernt (vielleicht schon weg)"
    for mitglied in $(frage "${GCLOUD}" projects get-iam-policy "${GCP_PROJEKT}" \
            --flatten='bindings[].members' \
            --filter='bindings.role=roles/iap.tunnelResourceAccessor' \
            --format='value(bindings.members)' \
            | grep -F "deleted:serviceAccount:${tunnel}?uid=" || true); do
        fuehre "${GCLOUD}" projects remove-iam-policy-binding "${GCP_PROJEKT}" \
            --member="${mitglied}" --role=roles/iap.tunnelResourceAccessor \
            --all --quiet \
            || warne "Rolle von ${mitglied}: nicht entfernt"
    done
    if gibt_es "${GCLOUD}" iam service-accounts describe "${tunnel}" --project "${GCP_PROJEKT}" \
            || (( TROCKEN )); then
        fuehre "${GCLOUD}" iam service-accounts delete "${tunnel}" --project "${GCP_PROJEKT}" --quiet
    fi

    # Netz zuletzt: Es laesst sich erst loeschen, wenn keine VM und keine
    # Regel mehr darin haengt.
    if gibt_es "${GCLOUD}" compute firewall-rules describe "${GCP_FIREWALL}" --project "${GCP_PROJEKT}" \
            || (( TROCKEN )); then
        fuehre "${GCLOUD}" compute firewall-rules delete "${GCP_FIREWALL}" --project "${GCP_PROJEKT}" --quiet
    fi
    if gibt_es "${GCLOUD}" compute firewall-rules describe "${GCP_FIREWALL_KIBANA}" --project "${GCP_PROJEKT}" \
            || (( TROCKEN )); then
        fuehre "${GCLOUD}" compute firewall-rules delete "${GCP_FIREWALL_KIBANA}" --project "${GCP_PROJEKT}" --quiet
    fi
    if gibt_es "${GCLOUD}" compute networks subnets describe "${GCP_SUBNETZ}" \
            --project "${GCP_PROJEKT}" --region "${GCP_REGION}" || (( TROCKEN )); then
        fuehre "${GCLOUD}" compute networks subnets delete "${GCP_SUBNETZ}" \
            --project "${GCP_PROJEKT}" --region "${GCP_REGION}" --quiet
    fi
    if gibt_es "${GCLOUD}" compute networks describe "${GCP_NETZ}" --project "${GCP_PROJEKT}" \
            || (( TROCKEN )); then
        fuehre "${GCLOUD}" compute networks delete "${GCP_NETZ}" --project "${GCP_PROJEKT}" --quiet
    fi

    # Das Budget zuletzt: Es wacht, bis alles andere weg ist.
    if (( TROCKEN )); then
        fuehre "${GCLOUD}" billing budgets delete "<budget>" --quiet
    else
        konto="$("${GCLOUD}" billing projects describe "${GCP_PROJEKT}" \
            --format='value(billingAccountName)' 2>/dev/null || true)"
        konto="${konto#billingAccounts/}"
        if [[ -n "${konto}" ]]; then
            for budget in $(frage "${GCLOUD}" billing budgets list --billing-account="${konto}" \
                    --filter="displayName=${GCP_BUDGET_NAME}" --format='value(name)' || true); do
                fuehre "${GCLOUD}" billing budgets delete "${budget}" --quiet
            done
        fi
    fi

    # Die Rolle fuer den Abendstopp. Fehlt sie schon, ist das kein Fehler.
    local nummer
    nummer="$(projektnummer)"
    fuehre "${GCLOUD}" projects remove-iam-policy-binding "${GCP_PROJEKT}" \
        --member="serviceAccount:service-${nummer}@compute-system.iam.gserviceaccount.com" \
        --role=roles/compute.instanceAdmin.v1 --condition=None --quiet \
        || warne "Rolle des Compute-Dienstagenten: nicht entfernt (vielleicht schon weg)"

    # Die Schluessel auf diesem Rechner (Entscheid vom 15.11.2026). Nur ein
    # Verzeichnis, das nicht HOME selbst ist - GCP_ZUSTAND ist ueberschreibbar.
    if [[ -d "${GCP_ZUSTAND}" && "${GCP_ZUSTAND}" != "${HOME}" && "${GCP_ZUSTAND}" != "/" ]]; then
        fuehre rm -rf "${GCP_ZUSTAND}"
    fi
    (( TROCKEN )) && melde "[trocken] nichts abgebaut." && return 0
    melde "Abgebaut: ${GCP_VM}, gs://${name}, ${email}, ${tunnel}, ${GCP_ZEITPLAN}, ${GCP_FIREWALL_KIBANA}, ${GCP_NETZ}, ${GCP_BUDGET_NAME}."
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
