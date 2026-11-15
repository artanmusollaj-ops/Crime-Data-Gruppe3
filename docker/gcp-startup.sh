#!/usr/bin/env bash
#
# Startskript der Probe-VM in Google Cloud (FR-47). Laeuft bei **jedem**
# Start als root, gesetzt von docker/gcp-aufbauen.sh als Metadatum
# startup-script. Deshalb ist jeder Schritt wiederholbar: Was schon da ist,
# bleibt.
#
# 1. Elasticsearch braucht vm.max_map_count >= 262144 auf dem Host - ohne
#    das bricht es im Container beim Start ab ("max virtual memory areas
#    vm.max_map_count [65530] is too low").
# 2. Docker mit Compose-Plugin und git aus den Ubuntu-Paketen (docker.io,
#    docker-compose-v2), nicht aus einem "curl | sh".
# 3. Das Repository nach /opt/urbancrime, auf dem Zweig aus den Metadaten
#    repo-url und repo-zweig - **bei jedem Start** geholt und vorgespult
#    (nur fast-forward). Den Zweig setzt "gcp-starten.sh --zweig" vor dem
#    Start als Metadatum; ein Zweigwechsel braucht also keine neue VM.
#
# Es startet **keinen** Dienst. Die Dienste mit restart: unless-stopped
# kommen nach dem ersten "docker compose up -d" von selbst wieder, und vor
# dem ersten gibt es noch keine .env.
#
# Die Schlusszeile "urbancrime-startup: fertig" liest gcp-aufbauen.sh von
# der seriellen Konsole, bevor es die VM nach dem ersten Start stoppt.
set -Eeuo pipefail

readonly ZIEL="/opt/urbancrime"
readonly MARKE="urbancrime-startup"

metadatum() {
    curl -fs -H 'Metadata-Flavor: Google' \
        "http://metadata.google.internal/computeMetadata/v1/instance/attributes/$1" || true
}

melde() { printf '%s: %s\n' "${MARKE}" "$*"; }

REPO_URL="$(metadatum repo-url)"
REPO_ZWEIG="$(metadatum repo-zweig)"
: "${REPO_URL:=https://github.com/artanmusollaj-ops/Crime-Data-Gruppe3.git}"
: "${REPO_ZWEIG:=main}"

# 1. Elasticsearch
sysctl -w vm.max_map_count=262144 >/dev/null
printf 'vm.max_map_count=262144\n' > /etc/sysctl.d/99-elasticsearch.conf

# 2. Docker, Compose, git
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1 \
        || ! command -v git >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    # Ein Stopp mitten in einem frueheren Lauf hinterlaesst dpkg halb fertig.
    dpkg --configure -a || true
    apt-get update -q
    apt-get install -y -q docker.io docker-compose-v2 git
    systemctl enable --now docker
fi
melde "$(docker --version), $(docker compose version --short)"

# 3. Das Repository. Ueber init/fetch statt clone: Liegt die .env schon da
# (gcp-starten.sh --env kann vor diesem Schritt ankommen), weigert sich
# clone, in ein nicht leeres Verzeichnis zu schreiben. Die .env ist in
# .gitignore und bleibt beim checkout unberuehrt. Ohne --depth: Ein
# flacher Stand kennt die gemeinsame Geschichte nicht, und das Vorspulen
# beim naechsten Start schluege fehl.
if [[ ! -d "${ZIEL}/.git" ]]; then
    mkdir -p "${ZIEL}"
    git -C "${ZIEL}" init -q
    git -C "${ZIEL}" remote add origin "${REPO_URL}"
fi
git -C "${ZIEL}" remote set-url origin "${REPO_URL}"
# Ein Fehler hier (Netz, Zweig weg, Zweig umgeschrieben) laesst den Stand
# stehen, wie er ist, und sagt es - die VM bootet trotzdem fertig.
if git -C "${ZIEL}" fetch -q origin \
        "+refs/heads/${REPO_ZWEIG}:refs/remotes/origin/${REPO_ZWEIG}"; then
    if git -C "${ZIEL}" rev-parse -q --verify "refs/heads/${REPO_ZWEIG}" >/dev/null; then
        git -C "${ZIEL}" checkout -q "${REPO_ZWEIG}" \
            && git -C "${ZIEL}" merge -q --ff-only "origin/${REPO_ZWEIG}" \
            || melde "WARNUNG: ${REPO_ZWEIG} laesst sich nicht vorspulen - Stand bleibt"
    else
        git -C "${ZIEL}" checkout -q -b "${REPO_ZWEIG}" "origin/${REPO_ZWEIG}" \
            || melde "WARNUNG: ${REPO_ZWEIG} laesst sich nicht auschecken - Stand bleibt"
    fi
else
    melde "WARNUNG: ${REPO_ZWEIG} von ${REPO_URL} nicht geholt - Stand bleibt"
fi
melde "Repository ${ZIEL} auf $(git -C "${ZIEL}" rev-parse --short HEAD 2>/dev/null || echo "keinem Stand") (${REPO_ZWEIG})"
if [[ -f "${ZIEL}/.env" ]]; then
    melde ".env liegt"
else
    melde ".env fehlt - docker/gcp-starten.sh --env <datei> legt sie an"
fi
melde "fertig"
