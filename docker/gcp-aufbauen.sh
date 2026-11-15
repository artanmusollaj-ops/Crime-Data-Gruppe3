#!/usr/bin/env bash
#
# Baut die Google-Cloud-Probe auf (FR-44, FR-47): Eimer, HMAC-Schluessel,
# Netz mit SSH und Kibana nur ueber IAP, VM (danach gestoppt), das
# Tunnelkonto fuer Kibana, Abendstopp und Budget-Alarme. Jeder Schritt fragt zuerst, ob es das schon gibt - ein
# zweiter Aufruf legt nichts doppelt an.
#
#   docker/gcp-aufbauen.sh --trocken   # nur zeigen, was geschaehe
#   docker/gcp-aufbauen.sh             # aufbauen
#
# **Was es kostet** (Plan, Kosten; Preise geschaetzt): solange die VM steht,
# nur die Disk (30 GB pd-balanced, rund 3,60 $ im Monat) und der Eimer
# (wenige Rappen). Die VM zahlt nur, wenn sie laeuft - deshalb endet dieses
# Skript mit einer **gestoppten** VM, und der Zeitplan stoppt sie jeden Abend
# um 20:00 Zuericher Zeit.
#
# **Was es nicht tut:** keine statische IP, kein Load Balancer, kein NAT,
# keine offene Firewall-Regel ausser SSH und Kibana (tcp:5601) aus dem
# IAP-Bereich. Die VM hat
# kein Dienstkonto: Sie braucht keine Google-API, nur den Eimer, und den
# erreicht sie ueber die S3-Schnittstelle mit dem HMAC-Schluessel aus ihrer
# .env.
#
# **Die Geheimnisse.** Der HMAC-Schluessel ist nur beim Anlegen lesbar. Das
# Skript schreibt ihn in ${GCP_ZUSTAND}/hmac.env (Vorgabe
# ~/.config/urbancrime-probe/, Modus 600, nie ins Repository-Verzeichnis;
# Entscheid vom 15.11.2026) und gibt ihn **nie** aus - nur die
# Zugangskennung und den Pfad. Die Datei ist zugleich die .env fuer die
# Werkzeuge auf dem eigenen Rechner (tools/kopiere_laeufe.py,
# tools/vergleiche_releases.py) und Teil der .env der VM, die
# "gcp-starten.sh --env" hinueberbringt. gcp-abbauen.sh loescht das
# Verzeichnis mit.
#
set -Eeuo pipefail

SKRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=docker/gcp-gemeinsam.sh
source "${SKRIPT_DIR}/gcp-gemeinsam.sh"

hilfe() {
    # Der Kopf bis vor "set -Eeuo pipefail", ohne Rautenzeichen.
    awk 'NR > 2 && /^set -Eeuo/ { exit } NR > 2' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

# Bricht ab, wenn das Projekt fehlt oder die Abrechnung aus ist - bevor
# irgendetwas angelegt wird (Plan, I/O-Matrix "Aufbau").
pruefe_projekt() {
    if (( TROCKEN )); then
        melde "[trocken] Projekt ${GCP_PROJEKT} und Abrechnung werden im echten Lauf zuerst geprueft"
        return 0
    fi
    if ! command -v "${GCLOUD}" >/dev/null 2>&1; then
        warne "gcloud fehlt (${GCLOUD}) - https://cloud.google.com/sdk/docs/install"
        return 1
    fi
    if ! frage "${GCLOUD}" projects describe "${GCP_PROJEKT}" --format='value(projectNumber)' >/dev/null; then
        warne "Projekt ${GCP_PROJEKT} nicht gefunden oder nicht lesbar - nichts angelegt."
        return 1
    fi
    local aktiv
    aktiv="$(frage "${GCLOUD}" billing projects describe "${GCP_PROJEKT}" \
        --format='value(billingEnabled)' || true)"
    if [[ "${aktiv}" != "True" ]]; then
        warne "Abrechnung fuer ${GCP_PROJEKT} ist aus (billingEnabled=${aktiv:-?}) - nichts angelegt."
        return 1
    fi
}

rechnungskonto() {
    if (( TROCKEN )); then
        printf '%s\n' "<rechnungskonto>"
        return 0
    fi
    local name
    name="$("${GCLOUD}" billing projects describe "${GCP_PROJEKT}" \
        --format='value(billingAccountName)')"
    printf '%s\n' "${name#billingAccounts/}"
}

dienste_aktivieren() {
    # Alle kostenlos; was zahlt, sind die Ressourcen darin.
    fuehre "${GCLOUD}" services enable \
        compute.googleapis.com storage.googleapis.com iam.googleapis.com \
        iap.googleapis.com billingbudgets.googleapis.com \
        --project "${GCP_PROJEKT}"
}

netz_anlegen() {
    # Ein eigenes Netz statt "default": Das Standardnetz bringt
    # default-allow-ssh und default-allow-rdp aus 0.0.0.0/0 mit, und die
    # Probe soll keine offene Regel haben ausser SSH ueber IAP.
    if frage "${GCLOUD}" compute networks describe "${GCP_NETZ}" --project "${GCP_PROJEKT}" >/dev/null; then
        melde "Netz ${GCP_NETZ}: besteht"
    else
        fuehre "${GCLOUD}" compute networks create "${GCP_NETZ}" \
            --project "${GCP_PROJEKT}" --subnet-mode=custom
    fi
    if frage "${GCLOUD}" compute networks subnets describe "${GCP_SUBNETZ}" \
            --project "${GCP_PROJEKT}" --region "${GCP_REGION}" >/dev/null; then
        melde "Teilnetz ${GCP_SUBNETZ}: besteht"
    else
        fuehre "${GCLOUD}" compute networks subnets create "${GCP_SUBNETZ}" \
            --project "${GCP_PROJEKT}" --region "${GCP_REGION}" \
            --network "${GCP_NETZ}" --range=10.60.0.0/24
    fi
    if frage "${GCLOUD}" compute firewall-rules describe "${GCP_FIREWALL}" --project "${GCP_PROJEKT}" >/dev/null; then
        melde "Firewall ${GCP_FIREWALL}: besteht"
    else
        fuehre "${GCLOUD}" compute firewall-rules create "${GCP_FIREWALL}" \
            --project "${GCP_PROJEKT}" --network "${GCP_NETZ}" \
            --direction=INGRESS --action=allow --rules=tcp:22 \
            --source-ranges="${GCP_IAP_BEREICH}"
    fi
    # Kibana, ebenfalls nur aus dem IAP-Bereich: Durch diese Regel kommt der
    # Tunnel des Tunnelkontos (tunnel_anlegen). Das Dashboard (8050) bleibt
    # an 127.0.0.1 der VM und bekommt keine Regel.
    if frage "${GCLOUD}" compute firewall-rules describe "${GCP_FIREWALL_KIBANA}" --project "${GCP_PROJEKT}" >/dev/null; then
        melde "Firewall ${GCP_FIREWALL_KIBANA}: besteht"
    else
        fuehre "${GCLOUD}" compute firewall-rules create "${GCP_FIREWALL_KIBANA}" \
            --project "${GCP_PROJEKT}" --network "${GCP_NETZ}" \
            --direction=INGRESS --action=allow --rules="tcp:${GCP_KIBANA_PORT}" \
            --source-ranges="${GCP_IAP_BEREICH}"
    fi
}

eimer_anlegen() {
    local name="$1"
    if frage "${GCLOUD}" storage buckets describe "gs://${name}" --project "${GCP_PROJEKT}" >/dev/null; then
        melde "Eimer gs://${name}: besteht"
        return 0
    fi
    # **Ohne Versionierung und ohne weiches Loeschen.** Der Eimer auf srv01
    # war versioniert, und 3'863 alte Fassungen lagen drei Wochen unsichtbar
    # (AGENTS.md, Known pitfalls). GCS haelt geloeschte Objekte vorgabemaessig
    # sieben Tage weich und berechnet sie; --soft-delete-duration=0 schaltet
    # das ab. Versionierung ist in GCS vorgabemaessig aus.
    fuehre "${GCLOUD}" storage buckets create "gs://${name}" \
        --project "${GCP_PROJEKT}" --location "${GCP_REGION}" \
        --default-storage-class=STANDARD --uniform-bucket-level-access \
        --public-access-prevention --soft-delete-duration=0 \
        --labels="${GCP_LABELS}"
}

konto_anlegen() {
    local name="$1" email
    email="$(konto_email)"
    if frage "${GCLOUD}" iam service-accounts describe "${email}" --project "${GCP_PROJEKT}" >/dev/null; then
        melde "Dienstkonto ${email}: besteht"
    else
        fuehre "${GCLOUD}" iam service-accounts create "${GCP_KONTO_NAME}" \
            --project "${GCP_PROJEKT}" \
            --display-name="Urban Crime Probe - Eimerzugang ueber HMAC"
    fi
    # Nur auf diesem Eimer, nicht im Projekt: Der Schluessel kann sonst nichts.
    wiederhole fuehre "${GCLOUD}" storage buckets add-iam-policy-binding "gs://${name}" \
        --member="serviceAccount:${email}" --role=roles/storage.objectAdmin
}

# Der Aufruf, der den Schluessel anlegt; seine Ausgabe traegt das Geheimnis
# und geht nur in die Variable ZEILE, nie auf den Bildschirm.
hmac_aufruf() {
    ZEILE="$("${GCLOUD}" storage hmac create "$1" --project "${GCP_PROJEKT}" \
        --format='value(metadata.accessId,secret)')"
}

hmac_anlegen() {
    local name="$1" email ziel vorhanden zeile kennung geheim
    email="$(konto_email)"
    ziel="${GCP_ZUSTAND}/hmac.env"
    if (( TROCKEN )); then
        melde "[trocken] ${GCLOUD} storage hmac create ${email} --project ${GCP_PROJEKT} -> ${ziel} (Modus 600, Schluessel nie auf dem Bildschirm)"
        return 0
    fi
    # Genau der Zustand ACTIVE - ein "grep ACTIVE" zaehlte INACTIVE mit.
    vorhanden="$(frage "${GCLOUD}" storage hmac list --project "${GCP_PROJEKT}" \
        --service-account "${email}" --format='value(accessId,state)' \
        | awk -F '\t' '$2 == "ACTIVE"' | wc -l | tr -d ' ' || true)"
    if (( ${vorhanden:-0} > 0 )) && [[ -f "${ziel}" ]]; then
        melde "HMAC: ${vorhanden} aktive(r) Schluessel, Datei ${ziel} liegt"
        return 0
    fi
    # Kein aktiver Schluessel, oder die Datei fehlt: Das Geheimnis ist nur
    # beim Anlegen lesbar, also ein neuer. Ein alter bleibt bis zum Abbau
    # liegen (gcp-abbauen.sh loescht alle des Kontos).
    if (( ${vorhanden:-0} > 0 )); then
        warne "HMAC: ${ziel} fehlt - lege einen neuen Schluessel an."
    fi
    melde "+ ${GCLOUD} storage hmac create ${email} (Ausgabe geht in ${ziel})"
    ZEILE=""
    wiederhole hmac_aufruf "${email}"
    zeile="${ZEILE}"
    kennung="$(printf '%s' "${zeile}" | cut -f1)"
    geheim="$(printf '%s' "${zeile}" | cut -f2)"
    if [[ -z "${kennung}" || -z "${geheim}" ]]; then
        warne "HMAC: keine Zugangskennung oder kein Geheimnis in der Antwort - abgebrochen."
        return 1
    fi
    mkdir -p "${GCP_ZUSTAND}"
    chmod 700 "${GCP_ZUSTAND}"
    ( umask 077
      {
          printf '# Angelegt von docker/gcp-aufbauen.sh am %s\n' "$(date +%Y-%m-%dT%H:%M:%S%z)"
          printf 'STORAGE_BACKEND=s3\n'
          printf 'S3_ENDPOINT=storage.googleapis.com\n'
          printf 'S3_BUCKET=%s\n' "${name}"
          printf 'S3_ACCESS_KEY=%s\n' "${kennung}"
          printf 'S3_SECRET_KEY=%s\n' "${geheim}"
          # Siehe .env.gcp.example: Cloud Storage und die Pruefsummen von botocore.
          printf 'AWS_REQUEST_CHECKSUM_CALCULATION=when_required\n'
          printf 'AWS_RESPONSE_CHECKSUM_VALIDATION=when_required\n'
      } > "${ziel}" )
    melde "HMAC: Zugangskennung ${kennung}, Schluessel in ${ziel} (600)"
}

zeitplan_anlegen() {
    if frage "${GCLOUD}" compute resource-policies describe "${GCP_ZEITPLAN}" \
            --project "${GCP_PROJEKT}" --region "${GCP_REGION}" >/dev/null; then
        melde "Zeitplan ${GCP_ZEITPLAN}: besteht"
    else
        # Nur ein Stopp, kein Start: Die VM laeuft, wenn jemand sie braucht
        # (gcp-starten.sh), und endet jeden Abend, auch wenn es vergessen ist.
        fuehre "${GCLOUD}" compute resource-policies create instance-schedule "${GCP_ZEITPLAN}" \
            --project "${GCP_PROJEKT}" --region "${GCP_REGION}" \
            --vm-stop-schedule="${GCP_ABENDSTOPP}" --timezone="${GCP_ZEITZONE}" \
            --description="Abendstopp der Urban-Crime-Probe"
    fi
    # Ein Zeitplan stoppt die VM im Namen des Compute-Dienstagenten, und der
    # darf das vorgabemaessig nicht: Ohne diese Rolle bleibt der Abendstopp
    # still wirkungslos (Google-Dokumentation "Scheduling a VM instance to
    # start and stop", Abschnitt "Required permissions").
    local nummer
    nummer="$(projektnummer)"
    fuehre "${GCLOUD}" projects add-iam-policy-binding "${GCP_PROJEKT}" \
        --member="serviceAccount:service-${nummer}@compute-system.iam.gserviceaccount.com" \
        --role=roles/compute.instanceAdmin.v1 --condition=None --quiet
}

# Liest die serielle Konsole, bis das Startskript seine Schlusszeile
# geschrieben hat (docker/gcp-startup.sh, MARKE_FERTIG), hoechstens
# GCP_WARTE_S Sekunden.
warte_auf_startskript() {
    if (( TROCKEN )); then
        melde "[trocken] warten, bis die serielle Konsole 'urbancrime-startup: fertig' zeigt"
        return 0
    fi
    local bis=$(( SECONDS + ${GCP_WARTE_S:-900} )) konsole
    while (( SECONDS < bis )); do
        # Erst ganz lesen, dann suchen: Mit pipefail meldete ein "grep -q",
        # das nach dem ersten Treffer schliesst, den SIGPIPE von gcloud als
        # Fehlschlag - und die Schleife liefe trotz Treffer weiter.
        konsole="$(frage "${GCLOUD}" compute instances get-serial-port-output "${GCP_VM}" \
                --project "${GCP_PROJEKT}" --zone "${GCP_ZONE}" || true)"
        if [[ "${konsole}" == *'urbancrime-startup: fertig'* ]]; then
            melde "Startskript: fertig"
            return 0
        fi
        sleep 15
    done
    warne "Startskript nach ${GCP_WARTE_S:-900} s nicht fertig - die VM wird trotzdem gestoppt;"
    warne "der naechste Start holt nach, was fehlt."
}

vm_anlegen() {
    local status
    status="$(vm_status)"
    if [[ -n "${status}" ]]; then
        melde "VM ${GCP_VM}: besteht (${status})"
        return 0
    fi
    # Ephemere externe Adresse statt --no-address: ohne sie kaeme die VM nur
    # ueber Cloud NAT ins Netz (Abbilder, apt, Quellen), und NAT zahlt
    # stuendlich. Eine ephemere Adresse zahlt nur, solange die VM laeuft;
    # erreichbar ist trotzdem nur Port 22 aus dem IAP-Bereich.
    fuehre "${GCLOUD}" compute instances create "${GCP_VM}" \
        --project "${GCP_PROJEKT}" --zone "${GCP_ZONE}" \
        --machine-type="${GCP_MASCHINE}" \
        --image-family="${GCP_ABBILD_FAMILIE}" --image-project="${GCP_ABBILD_PROJEKT}" \
        --boot-disk-size="${GCP_DISK_GB}GB" --boot-disk-type="${GCP_DISK_TYP}" \
        --network "${GCP_NETZ}" --subnet "${GCP_SUBNETZ}" \
        --no-service-account --no-scopes \
        --shielded-secure-boot --shielded-vtpm --shielded-integrity-monitoring \
        --resource-policies="${GCP_ZEITPLAN}" \
        --labels="${GCP_LABELS}" \
        --metadata-from-file=startup-script="${SKRIPT_DIR}/gcp-startup.sh" \
        --metadata=repo-url="${GCP_REPO_URL}",repo-zweig="${GCP_REPO_ZWEIG}"
    # Die Boot-Disk erbt die Labels der VM nicht.
    fuehre "${GCLOUD}" compute disks add-labels "${GCP_VM}" \
        --project "${GCP_PROJEKT}" --zone "${GCP_ZONE}" --labels="${GCP_LABELS}"
    # Gestoppt zurueckgeben (I/O-Matrix "Aufbau") - aber erst, wenn das
    # Startskript beim ersten Start fertig ist. Ein Stopp mitten in apt
    # hinterliesse ein halb eingerichtetes Docker; das Startskript holt das
    # zwar beim naechsten Start nach (dpkg --configure -a), aber gewartet
    # ist billiger als repariert.
    warte_auf_startskript
    fuehre "${GCLOUD}" compute instances stop "${GCP_VM}" \
        --project "${GCP_PROJEKT}" --zone "${GCP_ZONE}"
}

# Das Konto des Tunneldienstes, der Kibana nach aussen bringt (Entscheid vom
# 15.11.2026: IAP-Tunnel, nicht SSH mit fester IP). Zwei Rollen, sonst nichts:
#
#   * roles/iap.tunnelResourceAccessor mit der Bedingung
#     destination.port == 5601 - ein Tunnel auf Port 22 (SSH) wird von IAP
#     abgelehnt. Im Projekt gebunden, weil gcloud die Rolle nicht auf einer
#     einzelnen Tunnel-Instanz setzen kann; die Probe hat genau eine VM.
#     Die Bedingungsattribute destination.ip und destination.port nennt die
#     Google-Dokumentation "Using IAP for TCP forwarding", Abschnitt
#     "Grant the permissions to use IAP TCP forwarding".
#   * roles/compute.viewer auf der einen Instanz: start-iap-tunnel liest die
#     VM (compute.instances.get), um die Verbindung aufzubauen.
#
# Kein Eimer, kein SSH, keine Rolle zum Starten oder Stoppen. Der Schluessel
# geht in eine Datei mit Modus 600 und nie auf den Bildschirm; gcloud nennt
# beim Anlegen nur die Schluesselkennung.
tunnel_anlegen() {
    local email ziel
    email="$(tunnel_email)"
    ziel="$(tunnel_schluessel)"
    if frage "${GCLOUD}" iam service-accounts describe "${email}" --project "${GCP_PROJEKT}" >/dev/null; then
        melde "Tunnelkonto ${email}: besteht"
    else
        fuehre "${GCLOUD}" iam service-accounts create "${GCP_TUNNEL_NAME}" \
            --project "${GCP_PROJEKT}" \
            --display-name="Urban Crime Probe - IAP-Tunnel auf Kibana (Port ${GCP_KIBANA_PORT})"
    fi
    wiederhole fuehre "${GCLOUD}" projects add-iam-policy-binding "${GCP_PROJEKT}" \
        --member="serviceAccount:${email}" --role=roles/iap.tunnelResourceAccessor \
        --condition="expression=destination.port == ${GCP_KIBANA_PORT},title=nur-kibana-${GCP_KIBANA_PORT}" \
        --quiet
    wiederhole fuehre "${GCLOUD}" compute instances add-iam-policy-binding "${GCP_VM}" \
        --project "${GCP_PROJEKT}" --zone "${GCP_ZONE}" \
        --member="serviceAccount:${email}" --role=roles/compute.viewer
    if [[ -f "${ziel}" ]]; then
        melde "Tunnelschluessel: ${ziel} liegt"
        return 0
    fi
    if (( TROCKEN )); then
        melde "[trocken] ${GCLOUD} iam service-accounts keys create ${ziel} --iam-account ${email} (Modus 600, Schluessel nie auf dem Bildschirm)"
        return 0
    fi
    mkdir -p "${GCP_ZUSTAND}"
    chmod 700 "${GCP_ZUSTAND}"
    ( umask 077
      wiederhole fuehre "${GCLOUD}" iam service-accounts keys create "${ziel}" \
          --iam-account "${email}" --project "${GCP_PROJEKT}" >/dev/null )
    chmod 600 "${ziel}"
    melde "Tunnelschluessel in ${ziel} (600)"
}

budget_anlegen() {
    local konto vorhanden schwelle
    konto="$(rechnungskonto)"
    vorhanden="$(frage "${GCLOUD}" billing budgets list --billing-account="${konto}" \
        --filter="displayName=${GCP_BUDGET_NAME}" --format='value(name)' || true)"
    if [[ -n "${vorhanden}" ]]; then
        melde "Budget ${GCP_BUDGET_NAME}: besteht"
        return 0
    fi
    local -a regeln=()
    for schwelle in ${GCP_BUDGET_SCHWELLEN}; do
        regeln+=("--threshold-rule=percent=${schwelle}")
    done
    # **exclude-all-credits**: Das Studienguthaben ist eine Gutschrift. Mit
    # der Vorgabe (alle Gutschriften abgezogen) stuende der Verbrauch bis zum
    # letzten Dollar auf null, und kein Alarm kaeme je. Gezaehlt wird, was
    # verbraucht wird, nicht was zu zahlen bleibt. Die Alarme gehen an die
    # Abrechnungsadministratoren des Kontos - das ist das eigene Konto.
    fuehre "${GCLOUD}" billing budgets create \
        --billing-account="${konto}" --display-name="${GCP_BUDGET_NAME}" \
        --budget-amount="${GCP_BUDGET_BETRAG}${GCP_BUDGET_WAEHRUNG}" \
        --filter-projects="projects/${GCP_PROJEKT}" \
        --credit-types-treatment=exclude-all-credits \
        "${regeln[@]}"
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

    pruefe_projekt
    local name
    name="$(eimer)"

    dienste_aktivieren
    netz_anlegen
    eimer_anlegen "${name}"
    konto_anlegen "${name}"
    hmac_anlegen "${name}"
    zeitplan_anlegen
    vm_anlegen
    tunnel_anlegen
    budget_anlegen

    melde ""
    melde "Probe in ${GCP_PROJEKT} (${GCP_REGION}), Label ${GCP_LABELS}:"
    melde "  Netz       ${GCP_NETZ} / ${GCP_SUBNETZ}, Firewall ${GCP_FIREWALL} (tcp:22 aus ${GCP_IAP_BEREICH})"
    melde "             und ${GCP_FIREWALL_KIBANA} (tcp:${GCP_KIBANA_PORT} aus ${GCP_IAP_BEREICH})"
    melde "  Eimer      gs://${name} (ohne Versionierung, ohne weiches Loeschen)"
    melde "  Konto      $(konto_email), HMAC in ${GCP_ZUSTAND}/hmac.env"
    melde "  Tunnel     $(tunnel_email): IAP nur Port ${GCP_KIBANA_PORT}, Schluessel in $(tunnel_schluessel)"
    melde "  VM         ${GCP_VM} (${GCP_MASCHINE}, ${GCP_DISK_GB} GB ${GCP_DISK_TYP}, ${GCP_ZONE}), gestoppt"
    melde "  Zeitplan   ${GCP_ZEITPLAN}: Stopp '${GCP_ABENDSTOPP}' ${GCP_ZEITZONE}"
    melde "  Budget     ${GCP_BUDGET_NAME}: ${GCP_BUDGET_BETRAG} ${GCP_BUDGET_WAEHRUNG}, Schwellen ${GCP_BUDGET_SCHWELLEN}"
    melde ""
    melde "Weiter (alles unter ${GCP_ZUSTAND}, Modus 600):"
    melde "  quelle.env die S3-Angaben des Eimers, gegen den verglichen wird (nur gelesen) - von Hand"
    melde "  python tools/kopiere_laeufe.py --release <id> --von ${GCP_ZUSTAND}/quelle.env --nach ${GCP_ZUSTAND}/hmac.env"
    melde "  vm.env     aus .env.gcp.example und hmac.env, dann docker/gcp-starten.sh --env ${GCP_ZUSTAND}/vm.env"
    melde "  Tunneldienst: base64 des Tunnelschluessels als GCP_TUNNEL_SCHLUESSEL in dessen .env"
    melde "             (Wert nie anzeigen: base64 < $(tunnel_schluessel) | tr -d '\\n' > Datei, dann einsetzen)"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
