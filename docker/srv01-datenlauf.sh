#!/usr/bin/env bash
set -Eeuo pipefail

readonly PROJECT_DIR="/srv/docker/apps/urbancrime"
readonly COMPOSE_FILE="${PROJECT_DIR}/docker-compose.srv01.yml"
readonly ENV_FILE="${PROJECT_DIR}/.env"
readonly START_YEAR=2021
readonly END_YEAR="$(date +%Y)"
readonly YEAR_RANGE="${START_YEAR}-${END_YEAR}"
readonly LAST_CENSUS_VINTAGE=2024

compose() {
    /usr/bin/docker compose \
        --project-directory "${PROJECT_DIR}" \
        -f "${COMPOSE_FILE}" \
        --env-file "${ENV_FILE}" \
        "$@"
}

pipeline() {
    compose run --rm pipeline "$@"
}

mode_for_day() {
    local day_of_month
    day_of_month=$((10#$1))

    if (( day_of_month < 1 || day_of_month > 31 )); then
        echo "Urban Crime: invalid day of month: $1" >&2
        return 64
    elif (( day_of_month <= 7 )); then
        echo "delta"
    elif (( day_of_month <= 14 )); then
        echo "full"
    elif (( day_of_month <= 28 )); then
        echo "delta"
    else
        echo "skip"
    fi
}

main() {
    local mode="${1:-}"

    if [[ "${mode}" == "auto" ]]; then
        mode="$(mode_for_day "$(date +%d)")"
        if [[ "${mode}" == "skip" ]]; then
            echo "Urban Crime: fifth Monday, no scheduled run"
            return 0
        fi
    fi

    # Erst fragen, ob der Lauf durchlaufen kann, dann laden. Am 12.10.2026
    # feuerte der Anstoss zum ersten Mal und brach nach einer halben Stunde
    # an einem fehlenden CENSUS_API_KEY ab - Chicago und Detroit waren da
    # vollstaendig geladen, publiziert und die lokalen Kopien entfernt. Der
    # Volllauf ruft die Pipelines einzeln, die Schluesselpruefung sitzt aber
    # dort, wo der Schluessel gebraucht wird: in census_pipeline. Diese Zeile
    # holt sie nach vorn und prueft zugleich die Ablage.
    pipeline python -m orchestration.vorpruefung

case "${mode}" in
    full)
        echo "Urban Crime: full monthly ingestion for ${YEAR_RANGE}"

        for year in $(seq "${START_YEAR}" "${END_YEAR}"); do
            pipeline python -m chicago_pipeline.download_chicago \
                --year "${year}" --full
        done

        mapfile -t years < <(seq "${START_YEAR}" "${END_YEAR}")
        pipeline python -m detroit_pipeline.extract_detroit \
            --mode full --years "${years[@]}"

        census_end="${END_YEAR}"
        if (( census_end > LAST_CENSUS_VINTAGE )); then
            census_end="${LAST_CENSUS_VINTAGE}"
        fi
        for vintage in $(seq "${START_YEAR}" "${census_end}"); do
            pipeline python -m census_pipeline.download_tiger \
                --auslieferung tract --vintage "${vintage}"
            pipeline python -m census_pipeline.download_tiger \
                --auslieferung place --vintage "${vintage}"
            pipeline python -m census_pipeline.download_acs \
                --vintage "${vintage}"
        done
        pipeline python -m weather_pipeline.download_noaa

        # All sources were refreshed explicitly; derive every downstream
        # layer without creating a redundant city delta immediately after
        # the full snapshots.
        pipeline python -m orchestration.run_all \
            --ohne-ingestion --jahre "${YEAR_RANGE}"
        ;;
    delta)
        echo "Urban Crime: weekly delta ingestion for ${YEAR_RANGE}"
        pipeline python -m orchestration.run_all --jahre "${YEAR_RANGE}"
        ;;
    *)
        echo "Usage: $0 {auto|full|delta}" >&2
        return 64
        ;;
esac

# Serving is part of a successful publication. Ensure the long-running
# services exist and are healthy even after a host reboot or manual stop.
# The landing page service (start) is deliberately not in this list: its
# health check fetches the page itself, and the page is written further down.
compose up -d --wait elasticsearch kibana

# In s3 mode SeaweedFS is authoritative. Restore and verify the just-published
# release before switching the serving layers to it.
pipeline python -m orchestration.release holen aktuell --einsetzen
pipeline python -m serving.load_elasticsearch
pipeline python -m serving.build_kibana

# FR-31: the landing page is generated from the release that was just put in
# place, not from the checkout, and with the server addresses
# (urbancrime-<service>.datenwerft.ch) instead of localhost. It goes into the
# named volume that the start service serves read-only.
#
# The volume is emptied first. Docker seeds an empty named volume from the
# image on first start, so nginx's own index.html and 50x.html end up in it;
# the read-only mount on the serving side does not prevent that. Without this
# step the volume would keep serving files that are not ours.
pipeline find /app/startseite -mindepth 1 -delete
pipeline python -m serving.build_einstieg --adressen server --ziel /app/startseite/index.html
compose up -d --wait start

pipeline python -m serving.pruefe_stand

# Die Drift, nach dem Release und gegen den frisch gebauten Stand: Wie weit
# sind die dokumentierten Zahlen weg?
#
# **Warum hier und nicht nur in GitHub Actions.** Dort lief sie schon, und
# dort schreibt sie in die Zusammenfassung eines Laufs - also dorthin, wo sie
# nach einer Woche niemand mehr ansieht. FR-30 verlangt sie im Betriebsblick,
# und der entsteht hier.
#
# `--nur-melden`, damit sie den Lauf nicht faellt: Eine Drift ueber der
# Toleranz ist eine Aufgabe fuer die Dokumente und kein Vorfall im Betrieb.
# Die Quellen bewegen sich woechentlich; ein Lauf, der daran scheitert, waere
# jede Woche rot - und ein Alarm, der immer klingelt, ist keiner (so steht es
# im Docstring von orchestration.drift).
pipeline python -m orchestration.drift --nur-melden --json /app/data/drift.json \
    || echo "WARNUNG: Driftbericht nicht geschrieben - siehe Ausgabe oben"

# Der Sicherungssatz, nach dem Release und nicht davor: Er soll das Release
# tragen, das jetzt gilt.
#
# **Warum das hier steht und nicht im Backup-Skript.** Die Serversicherung
# liest Verzeichnisse, sie weiss nichts von gepinnten Laeufen und Zeigern.
# Welcher Lauf unersetzlich ist, weiss nur dieses Vorhaben - und es steht in
# `config/referenzstand.csv`, demselben Register, das vor dem Aufraeumen
# schuetzt.
#
# `|| true` mit Bedacht: Ein unvollstaendiger Satz ist ein Problem fuer die
# naechste Sicherung, aber kein Grund, einen gruenen Datenlauf nachtraeglich
# rot zu machen. Dass etwas fehlt, meldet der Satz selbst - mit Exitcode 1
# und im Protokoll, und `sicherungssatz.json` schreibt es neben die Daten.
pipeline python -m orchestration.sicherungssatz --holen || \
    echo "WARNUNG: Sicherungssatz unvollstaendig - siehe Ausgabe oben"

echo "Urban Crime: ${mode} run completed for ${YEAR_RANGE}"
}

# Der Betriebsblick (FR-30). Geschrieben wird er in **jedem** Fall, und das
# ist der ganze Punkt: Am 12. und 15.10.2026 ist der Lauf hier gescheitert,
# und gewusst hat es niemand. Ein Zustand, der nur nach einem gruenen Lauf
# entsteht, beschreibt genau den Fall nicht, fuer den man ihn braucht.
#
# `pipeline_run.json` traegt schon alles - Status, Dauer, jede Stufe mit ihrem
# Exitcode, Quellenfrische, Zeilenzahlen, Release. `serving.betriebsstand`
# rendert es; gemessen wird nichts Neues.
#
# Mit `|| true`, weil ein Fehler *hier* den Lauf nicht nachtraeglich faellen
# darf: Der Bericht ueber einen Lauf ist nicht der Lauf.
betriebsstand() {
    pipeline python -m serving.betriebsstand \
        --ziel /app/startseite/metrics || true
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    # Auch wenn `set -e` zuschlaegt oder jemand abbricht. `trap` statt einer
    # Zeile am Ende: Die Zeile am Ende laeuft bei einem Abbruch gerade nicht.
    #
    # **Innerhalb dieses Zweigs**, nicht darueber: Auf der obersten Ebene
    # feuerte der trap auch, wenn ein Test das Skript nur einliest, um seine
    # Funktionen zu pruefen - und starte dann einen Container.
    trap betriebsstand EXIT
    main "$@"
fi
