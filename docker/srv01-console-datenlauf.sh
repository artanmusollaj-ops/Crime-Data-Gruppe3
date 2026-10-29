#!/usr/bin/env bash
set -Eeuo pipefail
project_dir="${URBANCRIME_PROJECT_DIR:-/srv/docker/apps/urbancrime}"
mode="${1:-auto}"
if [[ "$mode" == auto ]]; then
    day=$((10#$(date -u +%d)))
    if (( day > 28 )); then exit 0; fi
    mode=delta
    if (( day >= 8 && day <= 14 )); then mode=full; fi
fi
if [[ "$mode" != full && "$mode" != delta ]]; then
    echo 'Aufruf: srv01-console-datenlauf.sh [auto|full|delta]' >&2
    exit 64
fi
# Only enqueue. One persistent worker executes all pipeline/serving writes.
/usr/bin/docker compose --project-directory "$project_dir" \
    --env-file "$project_dir/.env" \
    -f "$project_dir/docker-compose.srv01.yml" \
    -f "$project_dir/docker-compose.console.yml" \
    run --rm --no-deps worker python -m platform_admin.batch \
    --project-root /app --data-root /app/data --mode "$mode" \
    --slot "scheduled-$(date -u +%F)-$mode" --operator scheduler
