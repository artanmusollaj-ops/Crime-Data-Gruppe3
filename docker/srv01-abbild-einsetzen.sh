#!/usr/bin/env bash
#
# Setzt die zuletzt gebauten Abbilder auf srv01 ein - ein Befehl statt fuenf.
#
# Vorher waren es: den Workflow anstossen, zwei Digests aus der
# Job-Zusammenfassung abschreiben, die .env von Hand aendern, ziehen, den
# richtigen Dienst neu starten. Fuenf Handgriffe fuer eine Codeaenderung, und
# der dritte ist der, bei dem ein Zeichen verlorengeht.
#
# **Was dieses Skript nicht tut: bauen.** Der Bau bleibt der Workflow
# "Abbilder" auf GitHub, von Hand angestossen. Ihn von hier aus auszuloesen
# braeuchte ein GitHub-Token mit workflow-Recht auf einer Maschine, die von
# aussen erreichbar ist - ein zweites Geheimnis, das mehr kann als Pakete
# lesen. Das read:packages-Token, das srv01 ohnehin fuer ghcr.io hat, genuegt
# fuer alles hier.
#
# **Gepinnt bleibt der Digest.** Die Marke :aktuell dient nur dem
# Nachschlagen; in die .env schreibt dieses Skript den konkreten Digest, den
# es gerade gelesen hat. Eine Marke laesst sich umhaengen, ein Digest nicht.
#
#   docker/srv01-abbild-einsetzen.sh              # einsetzen
#   docker/srv01-abbild-einsetzen.sh --trocken    # nur zeigen, was geschaehe
#
set -Eeuo pipefail

# Die Pfade lassen sich ueberschreiben, damit ein Test die Funktionen
# gegen eine eigene .env stellen kann. Ohne das bliebe ``setze_in_env``
# ungeprueft - und das ist die Stelle, die eine Datei mit Geheimnissen
# anfasst, die sich aus dem Repository nicht wiederherstellen laesst.
: "${PROJECT_DIR:=/srv/docker/apps/urbancrime}"
: "${COMPOSE_FILE:=${PROJECT_DIR}/docker-compose.srv01.yml}"
: "${ENV_FILE:=${PROJECT_DIR}/.env}"
: "${MARKE:=aktuell}"

# Welche Variable welches Abbild pinnt. Die Namen stehen auch in
# .env.example und in docker-compose.srv01.yml; ein Test haelt sie dagegen.
# Paare aus Variablenname und Abbild, als einfache Liste.
#
# **Kein assoziatives Feld.** Die gibt es erst ab Bash 4; macOS liefert 3.2,
# und auf dieser Maschine laufen die Tests. Ein Skript, das sich nur auf dem
# Server pruefen laesst, ist genau die Sorte, die dort zum ersten Mal
# scheitert - diese Woche zweimal passiert.
ABBILDER=(
    "PIPELINE_IMAGE ghcr.io/datenwerft/urban-crime"
    "JUPYTER_IMAGE ghcr.io/datenwerft/urban-crime-jupyter"
)

# Dienste, die nach einem Abbildwechsel neu starten muessen. `pipeline` und
# `worker` stehen **nicht** dabei: Sie laufen als `run --rm` und nehmen das
# neue Abbild beim naechsten Lauf von selbst. `start` hat ein eigenes,
# fremdes Abbild und ist unberuehrt.
#
# `admin` und `dashboard` laufen dauernd auf dem Strecken-Abbild. Bis zum
# 1.11.2026 fehlte `admin` hier, und die Konsole lief nach einem Einsetzen
# auf dem alten Abbild weiter, bis jemand `up -d admin` tippte.
NEUSTART_DIENSTE=("jupyter" "admin" "dashboard")
NEUSTART_PROFIL="analyse"

compose() {
    /usr/bin/docker compose \
        --project-directory "${PROJECT_DIR}" \
        -f "${COMPOSE_FILE}" \
        --env-file "${ENV_FILE}" \
        "$@"
}

melde() { printf '%s\n' "$*"; }
warne() { printf '%s\n' "$*" >&2; }

# Der Digest, unter dem die Marke gerade liegt.
#
# Ueber `docker pull` und `docker image inspect` und nicht ueber
# `docker manifest inspect`: Der zweite Weg liefert bei einem
# Mehrplattform-Abbild den Digest der Liste, nicht den des Abbilds, das hier
# wirklich laeuft. Gezogen werden muss es ohnehin.
digest_der_marke() {
    local abbild="$1" ref
    ref="${abbild}:${MARKE}"
    docker pull --quiet "${ref}" >/dev/null
    docker image inspect --format='{{index .RepoDigests 0}}' "${ref}" \
        | sed 's/^.*@/@/'
}

# Was heute in der .env steht - leer, wenn die Variable fehlt.
steht_in_env() {
    local name="$1"
    sed -n "s/^${name}=//p" "${ENV_FILE}" | tail -1
}

# Eine Zeile in der .env ersetzen oder anhaengen, der Rest bleibt unberuehrt.
#
# Ueber eine temporaere Datei und `mv`: Ein `sed -i` auf einer Datei mit
# Geheimnissen laesst bei einem Abbruch eine halbe zurueck, und die .env ist
# das Einzige, was dieser Stapel nicht aus dem Repository wiederherstellen
# kann.
setze_in_env() {
    local name="$1" wert="$2" tmp
    tmp="$(mktemp "${ENV_FILE}.XXXXXX")"
    chmod --reference="${ENV_FILE}" "${tmp}" 2>/dev/null || chmod 600 "${tmp}"
    if grep -q "^${name}=" "${ENV_FILE}"; then
        awk -v n="${name}" -v w="${wert}" \
            'BEGIN{FS=OFS="="} $1==n {print n "=" w; next} {print}' \
            "${ENV_FILE}" > "${tmp}"
    else
        cat "${ENV_FILE}" > "${tmp}"
        printf '%s=%s\n' "${name}" "${wert}" >> "${tmp}"
    fi
    mv "${tmp}" "${ENV_FILE}"
}

# Traegt das Abbild den Commit, den es tragen soll?
#
# Das Abbild setzt GIT_COMMIT selbst (Dockerfile). Es ist das Einzige, was
# ein laufender Container ueber seinen Quellstand sagt - und die einzige
# Gegenprobe dafuer, dass hier wirklich der neue Code einzieht und nicht
# derselbe unter neuem Namen.
commit_im_abbild() {
    docker run --rm --entrypoint sh "$1" -c 'printf %s "$GIT_COMMIT"'
}

main() {
    local trocken=0
    [[ "${1:-}" == "--trocken" ]] && trocken=1

    [[ -f "${ENV_FILE}" ]] || { warne "Keine ${ENV_FILE} - nichts einzusetzen."; return 1; }

    local geaendert=()
    local eintrag name abbild neu alt ref

    for eintrag in "${ABBILDER[@]}"; do
        name="${eintrag%% *}"
        abbild="${eintrag#* }"
        melde "Nachschlagen: ${abbild}:${MARKE}"
        neu="${abbild}$(digest_der_marke "${abbild}")"
        alt="$(steht_in_env "${name}")"

        if [[ "${neu}" == "${alt}" ]]; then
            melde "  unveraendert"
            continue
        fi
        melde "  alt: ${alt:-(nicht gesetzt)}"
        melde "  neu: ${neu}"
        geaendert+=("${name}")
        (( trocken )) || setze_in_env "${name}" "${neu}"
    done

    if (( ${#geaendert[@]} == 0 )); then
        melde ""
        melde "Beide Abbilder sind schon eingesetzt - nichts zu tun."
        return 0
    fi

    if (( trocken )); then
        melde ""
        melde "Trockenlauf: ${geaendert[*]} wuerden gesetzt, nichts geaendert."
        return 0
    fi

    melde ""
    melde "Herkunft der neuen Abbilder:"
    for name in "${geaendert[@]}"; do
        ref="$(steht_in_env "${name}")"
        melde "  ${name}: $(commit_im_abbild "${ref}")"
    done

    melde ""
    melde "Ziehen..."
    compose --profile stapel --profile "${NEUSTART_PROFIL}" pull pipeline jupyter

    # Nur neu starten, was laeuft. Ein `up -d` auf einen Dienst, den niemand
    # gestartet hat, startete ihn - und Jupyter soll nicht dauerhaft laufen,
    # nur wenn jemand ihn braucht.
    for name in "${NEUSTART_DIENSTE[@]}"; do
        if compose --profile "${NEUSTART_PROFIL}" ps --services --filter status=running \
                | grep -qx "${name}"; then
            melde "Neu starten: ${name}"
            compose --profile "${NEUSTART_PROFIL}" up -d "${name}"
        else
            melde "Nicht gestartet, bleibt es auch: ${name}"
        fi
    done

    melde ""
    melde "Eingesetzt. Der naechste Datenlauf nimmt das neue Abbild von selbst:"
    melde "  flock --wait 60 logs/pipeline.lock docker/srv01-datenlauf.sh delta"
}

# Nur ausfuehren, wenn aufgerufen - nicht, wenn eine Testdatei die Funktionen
# hereinholt.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
