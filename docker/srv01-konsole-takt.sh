#!/usr/bin/env bash
# Ein Takt der Engineering-Konsole auf srv01: hoechstens ein Auftrag, dann Ende.
#
# Der Worker der Konsole fuehrt die Pipelines aus und braucht deren Platz
# (1'280 MiB). Dauernd laufend laege er rund 1,3 GiB ueber dem Budget von
# FR-13; deshalb startet ihn cron alle fuenf Minuten als Stapellauf, wie die
# Pipeline. Ein Takt prueft die Zeitplaene der Konsole, nimmt den naechsten
# Auftrag aus ihrer Warteschlange und endet.
#
# **Nie neben dem Datenlauf.** Der Crontab nimmt dieselbe Sperrdatei wie
# srv01-datenlauf.sh, aber ohne zu warten: Ist sie belegt, faellt der Takt
# aus, und der naechste kommt in fuenf Minuten. Zwei 1'280-MiB-Container
# gleichzeitig haelt das Budget nicht aus.
set -Eeuo pipefail

readonly PROJECT_DIR="/srv/docker/apps/urbancrime"

exec /usr/bin/docker compose \
    --project-directory "${PROJECT_DIR}" \
    -f "${PROJECT_DIR}/docker-compose.srv01.yml" \
    --env-file "${PROJECT_DIR}/.env" \
    run --rm worker
