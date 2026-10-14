"""Prueft vor dem Lauf, was er braucht - bevor die erste Zeile geladen wird.

Am 12.10.2026 feuerte der woechentliche Anstoss auf ``srv01`` zum ersten Mal
und scheiterte nach rund einer halben Stunde an einem fehlenden
``CENSUS_API_KEY``. Chicago und Detroit waren zu dem Zeitpunkt vollstaendig
geladen, nach SeaweedFS publiziert und die lokalen Arbeitskopien entfernt -
alles umsonst, und beim naechsten Anlauf noch einmal.

``docker-compose.srv01.yml`` verspricht im Kopf das Gegenteil: *"Eine
Variable, die dort fehlt, wird nicht in den Container gegeben - und
CENSUS_API_KEY faellt dann vor dem Lauf auf, nicht bei Stufe 5 von 14."* Das
stimmte nicht. Der Volllauf ruft die Pipelines **einzeln** auf, und die
Pruefung sitzt dort, wo der Schluessel gebraucht wird: in
``census_pipeline.download_acs``. Eine Vorpruefung ueber alle Stufen gab es
nirgends.

Dieses Modul ist sie. Es laedt nichts herunter und schreibt nichts - es
beantwortet eine Frage: *Kann dieser Lauf durchlaufen?*

**Die Namen stehen nicht hier.** Welcher Schluessel noetig ist, weiss das
Modul, das ihn braucht; diese Datei liest den Namen von dort
(``download_acs.KEY_VARIABLE``) und die Ablage-Regeln aus ``storage.config``.
Eine zweite Liste waere die, die veraltet, sobald eine Quelle dazukommt.
"""

from __future__ import annotations

import argparse
import os
import sys

#: Was fehlen darf. ``SOCRATA_APP_TOKEN`` ist ausdruecklich keine Pflicht -
#: Chicago antwortet auch ohne ihn, nur mit engeren Grenzen
#: (``chicago_pipeline.download_chicago``: ``os.getenv(...) or None``). Ein
#: Lauf daran scheitern zu lassen waere falsch; ihn zu verschweigen auch,
#: denn eine Drosselung sieht spaeter aus wie ein Netzproblem.
OPTIONAL = ("SOCRATA_APP_TOKEN",)


def pflichtschluessel() -> tuple[str, ...]:
    """Die Umgebungsvariablen, ohne die ein Lauf nicht durchlaeuft.

    Gelesen, nicht getippt: Der Name kommt aus dem Modul, das ihn braucht.
    Kaeme eine zweite Quelle mit eigenem Schluessel dazu, gehoerte sie hier
    dazu - und faende sich sofort, weil der Lauf sonst wieder mittendrin
    abbricht.
    """
    from census_pipeline.download_acs import KEY_VARIABLE

    return (KEY_VARIABLE,)


def fehlende(umgebung: dict[str, str] | None = None) -> list[str]:
    """Welche Pflichtschluessel fehlen oder leer sind.

    **Dieselbe Sicht wie die Pipeline.** ``download_acs`` ruft
    ``load_dotenv(find_dotenv(usecwd=True))`` und liest danach
    ``os.getenv`` - die Vorpruefung tut es ebenso. Faende sie den Schluessel
    nur in der Umgebung, meldete sie auf einem Entwicklungsrechner eine
    Luecke, die der Lauf gar nicht hat, und das waere schlimmer als keine
    Vorpruefung: Man lernt, sie zu uebergehen.

    Im Container gibt es keine ``.env``; dort kommt alles aus der Umgebung,
    die Compose aus der ignorierten ``.env`` des Stapels fuellt. Beide Wege
    enden also an derselben Stelle.
    """
    if umgebung is None:
        from dotenv import find_dotenv, load_dotenv

        pfad = find_dotenv(usecwd=True)
        if pfad:
            load_dotenv(pfad)
        umgebung = dict(os.environ)
    return [name for name in pflichtschluessel()
            if not (umgebung.get(name) or "").strip()]


def ablage_pruefen() -> str:
    """Die Ablage so bauen, wie der Lauf sie bauen wird - und nichts tun.

    ``storage.config.load`` prueft selbst, dass ``S3_ACCESS_KEY`` und
    ``S3_SECRET_KEY`` da sind, sobald der Modus sie braucht, und dass der
    Bucket nicht leer ist. Diese Regel hier zu wiederholen hiesse, sie zu
    verdoppeln; sie hier **auszuloesen** kostet nichts und faengt denselben
    Fehler eine halbe Stunde frueher.
    """
    from storage import load

    config = load()
    return config.backend


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m orchestration.vorpruefung",
        description=__doc__.splitlines()[0],
    )
    p.add_argument("--still", action="store_true",
                   help="nur im Fehlerfall etwas sagen")
    args = p.parse_args(argv)

    try:
        backend = ablage_pruefen()
    except Exception as fehler:          # StorageConfigError und Verwandte
        print(f"Vorpruefung: Ablage nicht benutzbar - {fehler}", file=sys.stderr)
        return 1

    offen = fehlende()
    if offen:
        print(
            "Vorpruefung: " + ", ".join(offen) + " fehlt in der Umgebung.\n"
            "Der Lauf braeuchte den Schluessel erst in der Mitte - er wuerde "
            "Chicago und Detroit laden und publizieren und dann abbrechen.\n"
            "Auf srv01 gehoert er in die .env des Stapels; "
            "docker-compose.srv01.yml nennt nur den Namen.",
            file=sys.stderr)
        return 1

    if not args.still:
        lauwarm = [n for n in OPTIONAL if not (os.environ.get(n) or "").strip()]
        print(f"Vorpruefung: Ablage {backend}, "
              f"{len(pflichtschluessel())} Pflichtschluessel gesetzt.")
        for name in lauwarm:
            print(f"  Hinweis: {name} fehlt - der Lauf geht, die Quelle "
                  f"drosselt frueher.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
