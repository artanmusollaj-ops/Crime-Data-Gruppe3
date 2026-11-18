#!/usr/bin/env bash
# Ein Takt der Engineering-Konsole auf srv01: hoechstens ein Auftrag, dann Ende.
#
# Der Worker der Konsole fuehrt die Pipelines aus und braucht deren Platz
# (1'280 MiB). Dauernd laufend laege er rund 1,3 GiB ueber dem Budget von
# FR-13; deshalb startet ihn cron jede Minute als Stapellauf, wie die
# Pipeline. Ein Takt prueft die Zeitplaene der Konsole, nimmt den naechsten
# Auftrag aus ihrer Warteschlange und endet. Ein leerer Takt dauert auf
# srv01 rund 3 s (gemessen am 18.11.2026); vorher kam er alle fuenf Minuten,
# und ein Klick in der Oberflaeche wartete bis zu fuenf Minuten.
#
# **Nie neben dem Datenlauf.** Der Crontab nimmt dieselbe Sperrdatei wie
# srv01-datenlauf.sh, aber ohne zu warten: Ist sie belegt, faellt der Takt
# aus, und der naechste kommt in einer Minute. Zwei 1'280-MiB-Container
# gleichzeitig haelt das Budget nicht aus.
set -Eeuo pipefail

readonly PROJECT_DIR="/srv/docker/apps/urbancrime"

exec /usr/bin/docker compose \
    --project-directory "${PROJECT_DIR}" \
    -f "${PROJECT_DIR}/docker-compose.srv01.yml" \
    --env-file "${PROJECT_DIR}/.env" \
    run --rm worker
