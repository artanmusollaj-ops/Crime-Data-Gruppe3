#!/usr/bin/env bash
#
# Der Tunneldienst `kibana` auf srv01: ein IAP-Tunnel auf Kibana in der
# Google-Cloud-Probe, sonst nichts (Entscheid vom 15.11.2026). Traefik
# routet urbancrime-kibana.datenwerft.ch auf Port 5601 dieses Containers,
# Cloudflare Access steht davor; gcloud reicht jede Verbindung durch IAP an
# Port 5601 der VM weiter. Elasticsearch und Kibana selbst laufen nicht auf
# srv01 (C-9) - nur in der Probe, gestartet mit
# "docker/gcp-starten.sh --nur-kibana".
#
# Eingehaengt in docker-compose.srv01.yml, gestartet im gcloud-Abbild:
#
#   GCP_TUNNEL_SCHLUESSEL  der JSON-Schluessel des Tunnelkontos, base64,
#                          aus der .env des Stapels (Pflicht)
#   GCP_PROJEKT, GCP_ZONE, GCP_VM
#                          wohin der Tunnel geht (Compose setzt sie)
#   TUNNEL_GEHEIM          wohin der Schluessel kommt; ein tmpfs, Vorgabe
#                          /run/geheim (ueberschreibbar fuer die Tests)
#
# **Der Schluessel beruehrt keine Platte.** Er wird nur in das tmpfs
# geschrieben (Modus 600), und dorthin legt gcloud auch seine Konfiguration
# (CLOUDSDK_CONFIG) - sonst kopierte "auth activate-service-account" ihn in
# ~/.config/gcloud auf die Schreibschicht des Containers. Er erscheint nie
# in der Ausgabe; fehlt er, endet der Container mit dem Namen der Variable.
#
# **Ist die VM gestoppt**, laeuft der Tunnel weiter: Mit
# --iap-tunnel-disable-connection-check prueft gcloud die Verbindung nicht
# beim Start, sondern je Anfrage. Eine Anfrage scheitert dann, und Traefik
# antwortet mit 502 (Plan, I/O-Matrix "VM gestoppt").
#
set -Eeuo pipefail

: "${GCP_TUNNEL_SCHLUESSEL:?GCP_TUNNEL_SCHLUESSEL fehlt - der base64-kodierte Schluessel des Tunnelkontos, siehe .env.example}"
: "${GCP_PROJEKT:?GCP_PROJEKT fehlt}"
: "${GCP_ZONE:?GCP_ZONE fehlt}"
: "${GCP_VM:?GCP_VM fehlt}"
: "${TUNNEL_GEHEIM:=/run/geheim}"
: "${GCLOUD:=gcloud}"
readonly PORT="5601"

schluessel="${TUNNEL_GEHEIM}/tunnel-schluessel.json"
export CLOUDSDK_CONFIG="${TUNNEL_GEHEIM}/gcloud"
# Keine Protokolldateien: gcloud schriebe sie nach ${CLOUDSDK_CONFIG}/logs,
# also in das kleine tmpfs, und der Healthcheck oeffnet alle 30 s eine
# Verbindung. Was gcloud meldet, steht ohnehin in "docker logs".
export CLOUDSDK_CORE_DISABLE_FILE_LOGGING=true

umask 077
mkdir -p "${CLOUDSDK_CONFIG}"
if ! printf '%s' "${GCP_TUNNEL_SCHLUESSEL}" | base64 -d > "${schluessel}" 2>/dev/null \
        || ! grep -q '"private_key"' "${schluessel}"; then
    rm -f "${schluessel}"
    printf '%s\n' "GCP_TUNNEL_SCHLUESSEL ist kein base64-kodierter JSON-Schluessel eines Dienstkontos" >&2
    exit 1
fi
chmod 600 "${schluessel}"
unset GCP_TUNNEL_SCHLUESSEL

"${GCLOUD}" auth activate-service-account --key-file="${schluessel}" --quiet
exec "${GCLOUD}" compute start-iap-tunnel "${GCP_VM}" "${PORT}" \
    --project "${GCP_PROJEKT}" --zone "${GCP_ZONE}" \
    --local-host-port="0.0.0.0:${PORT}" \
    --iap-tunnel-disable-connection-check
