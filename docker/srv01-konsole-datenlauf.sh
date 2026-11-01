#!/usr/bin/env bash
# Montags: den geplanten Quellenlauf in die Engineering-Konsole einreihen.
#
# Ersetzt srv01-datenlauf.sh, sobald der Bestand verwaltet ist
# ("platform_admin enable-managed"): Danach sperrt storage.verwaltet run_all
# und release fuer alles ausser dem Konsolen-Worker, und der alte Lauf
# scheiterte. Dieses Skript laedt und baut nichts selbst. Es reiht einen
# Batch ein; die Takte des Workers laden die Quellen, bauen den Kandidaten,
# lassen ihn vom Qualitaetstor freigeben, setzen ihn ein, fragen das
# Dashboard nach seinem Stand, messen die Drift, holen den Sicherungssatz und schreiben den Betriebsstand.
#
# **Der Rhythmus ist derselbe, aus derselben Funktion.** Erster Montag
# Delta, zweiter Voll, dritter und vierter Delta, fuenfter frei - der
# Volllauf nie am Monatsersten, wegen des Restic-Restores um 05:00. Die Regel
# steht einmal, in srv01-datenlauf.sh; hier wird sie gelesen, nicht
# abgeschrieben.
set -Eeuo pipefail

# Bringt PROJECT_DIR, COMPOSE_FILE, ENV_FILE, compose() und mode_for_day()
# mit. Der Lauf selbst startet beim Einlesen nicht: srv01-datenlauf.sh ruft
# main nur auf, wenn es selbst ausgefuehrt wird.
source "$(dirname "${BASH_SOURCE[0]}")/srv01-datenlauf.sh"

einreihen() {
    local mode="${1:-}"

    if [[ "${mode}" == "auto" ]]; then
        mode="$(mode_for_day "$(date +%d)")"
        if [[ "${mode}" == "skip" ]]; then
            echo "Urban Crime: fifth Monday, nothing queued"
            return 0
        fi
    fi
    case "${mode}" in
        full|delta) ;;
        *)
            echo "Usage: $0 {auto|full|delta}" >&2
            return 64
            ;;
    esac

    # Der Slot macht das Einreihen wiederholbar: Ein zweiter Aufruf am
    # selben Tag mit demselben Modus reiht nichts Neues ein.
    compose run --rm worker python -m platform_admin.batch \
        --project-root /app --data-root /app/data \
        --mode "${mode}" \
        --slot "scheduled-$(date -u +%F)-${mode}" \
        --operator scheduler
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    einreihen "$@"
fi
