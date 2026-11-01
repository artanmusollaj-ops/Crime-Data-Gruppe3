"""Waechter ueber die Aussagen zum Betriebsstand von ``srv01``.

Am 9.10.2026 wurden Cloudflare Access und die Tunnel-Routen fuer
``urbancrime-*`` eingerichtet. Von aussen messbar ist davon genau eine Sache:
dass die beiden Hostnamen mit **302** auf das Anmeldetor umleiten und beide
Umleitungen dieselbe Anwendungskennung tragen. Nicht messbar ist, ob dahinter
etwas antwortet - Access faengt die Anfrage **vor** dem Ursprung ab.

Daraus folgen drei Pflichten, und dieser Waechter haelt sie:

* **Was gedreht wurde, bleibt gedreht.** Die ueberholten absoluten Aussagen
  ("keine Access-Anwendung") duerfen in keinem Abgabedokument wieder
  auftauchen.
* **Was noch wahr ist, bleibt stehen.** "kein Zeitplan" und der offene
  Restic-Datentraeger sind nicht mitgedreht worden und sollen es auch nicht
  werden, nur weil ein Satz daneben freundlicher klingt.
* **Wer die Messung beschreibt, nennt ihre Grenze.** Ein Absatz, der die 302
  und die gemeinsame Anwendungskennung vorzeigt und nicht dazusagt, was sie
  nicht zeigen, liest sich als Betriebszusage. Das ist der Fehler, vor dem die
  Kernthese von ``architektur-ist-und-ziel.md`` warnt.

``docs/intern/AENDERUNGEN.md`` ist von den ersten beiden Pflichten
ausgenommen: Es ist ein **datiertes Protokoll** und zitiert die alten
Formulierungen absichtlich, um zu sagen, was sich geaendert hat. Von der
dritten ist es nicht ausgenommen - dort steht die Messung im Wortlaut, also
gehoert ihre Grenze dorthin erst recht.

Einen Test gegen die Wirklichkeit kann es hier nicht geben: Eine Abfrage von
``urbancrime-kibana.datenwerft.ch`` braeuchte Netz, eine Abfrage von ``srv01``
oder der privaten Registry zusaetzlich ein Token. In CI gibt es beides nicht,
und ein Waechter, der sich selbst ueberspringt, ist keiner. Belegtraeger ist
deshalb der datierte Eintrag in ``AENDERUNGEN.md``; dieser Waechter haelt die
**Dokumente** gegeneinander, nicht die Dokumente gegen den Server.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: Das datierte Protokoll - zitiert alte Formulierungen mit Absicht.
PROTOKOLL = "docs/intern/AENDERUNGEN.md"

#: Was aus der Suche faellt: ``docs/referenz/`` ist aus dem Code erzeugt und
#: sagt nichts ueber den Betriebsstand.
AUSGENOMMEN = ("docs/referenz/",)

#: Die bewachten Dokumente - die, die eine Aussage ueber den Betriebsstand
#: tragen. Diese Liste ist von Hand gefuehrt; **entdeckt** wird dagegen ueber
#: ``alle_dokumente()``, sonst bemerkte die Vollstaendigkeitsprobe nur, was
#: hier schon dasteht.
DOKUMENTE = (
    "README.md",
    "docs/architektur-ist-und-ziel.md",
    "docs/storage-architektur.md",
    "docs/ln2_konzept.md",
    "docs/ausblick.md",
    PROTOKOLL,
)

#: Was am 9.10.2026 gedreht wurde und nicht zurueckkommen darf. Je **Muster**
#: der Grund, warum es falsch geworden ist.
#:
#: Muster und nicht Zeichenkette, weil dieselbe absolute Aussage in drei
#: Wortstellungen dastand: "Angewandt ist sie nirgends" (README),
#: "Angewandt ist sie zum Zeitpunkt dieses Abschnitts nirgends"
#: (storage-architektur) und "sie ist nirgends angewandt"
#: (architektur-ist-und-ziel, zweimal). Eine Regel, die nur eine davon sperrt,
#: ist eine Scheinregel - die anderen zwei stehen dann unbewacht daneben, und
#: genau so war es im ersten Entwurf.
UEBERHOLT = {
    "keine Access-Anwendung": "die Anwendung ueber urbancrime-* ist angelegt",
    r"[Aa]ngewandt ist (?:sie|es)[^.]{0,60}nirgends|nirgends angewandt":
        "die Beschreibung ist seit dem 8.10.2026 angewandt - drei Dienste "
        "laufen auf srv01",
    "kein Tunnel, keine Anmeldung": "beide am 9.10.2026 gemessen",
    # Dazugekommen am 11.10.2026, als ``docker compose ps`` auf srv01 drei
    # laufende Dienste und ``crontab -l`` einen Zeitplan zeigte.
    "Gestartet ist sie nirgends":
        "der Stapel laeuft seit dem 8.10.2026 auf srv01",
    r"kein(?:en)? Zeitplan":
        "es gibt einen: montags 04:30 per cron, mit flock",
    r"l[äa]uft nichts davon":
        "Elasticsearch, Kibana und Jupyter laufen dort",
    r"[Ss]tapel\s+nicht gestartet":
        "am 11.10.2026 waren alle drei Dienste healthy",
    "Nichts startet den Lauf von selbst":
        "zwei Anstoesse: datenlauf.yml seit 13.9., srv01-cron seit Oktober",
    "nichts davon ist gebaut":
        "fuenf Bausteine stehen; Teil B und der Einseiter datieren jetzt "
        "je Baustein",
}

#: Was **nicht** mitgedreht wurde, weil es unbelegt blieb. Datei -> Phrase.
NOCH_WAHR = {
    # Der Zeitplan steht, aber er hat am 11.10.2026 noch nie gefeuert -
    # ``logs/scheduled-pipeline.log`` gibt es nicht, und der Crontab schreibt
    # mit ``>>`` hinein. Dieselbe Elle, die 5.3 an den Datenlauf in GitHub
    # Actions legt: bis zum ersten gruenen Lauf eine Einrichtung.
    "docs/architektur-ist-und-ziel.md": "Einrichtung, kein Nachweis",
    "README.md": "Einrichtung, kein Nachweis",
    "docs/ln2_konzept.md": "Einrichtung, kein Nachweis",
    # Hier stand bis zum 1.11.2026 der vierte Posten unter "Was daneben
    # einzurichten ist": der Elasticsearch-Datentraeger fuer Restic, am
    # 11.10.2026 nicht geprueft. Er ist nicht eingerichtet, sondern
    # **entfallen** - der Sicherungsabschnitt nahm ihn am 18.10.2026 aus der
    # Policy, und seit C-9 gibt es den Dienst auf srv01 nicht mehr. Gedreht
    # ist die Aussage also nicht ohne Beleg, sondern mit ihrem Gegenstand.
}

#: Woran ein Absatz zu erkennen ist, der die Messung **vorzeigt**. Bewusst das
#: Vokabular des Befunds und nicht "von aussen" - das ist eine Alltagswendung
#: und traf im ersten Entwurf einen unverwandten Protokolleintrag von weit
#: oberhalb.
BESCHREIBT_MESSUNG = ("Anmeldetor", "Anwendungskennung", "cloudflareaccess.com")

#: Was neben so einem Absatz stehen muss: die Grenze selbst, im Wortlaut.
#:
#: Ein **Verweis** genuegt hier nicht, auch kein Verweis auf eine Stelle, die
#: selbst gefuehrt ist. Der erste Entwurf liess fuer
#: ``architektur-ist-und-ziel.md`` zusaetzlich ``"B.3"`` zu - und machte den
#: Waechter damit beweisbar wirkungslos: Die Abschnittsueberschrift "## B.3 …"
#: liegt rund 505 Zeichen vor dem Marker "Anmeldetor" und gilt in der
#: Reichweite ``NAHE`` selbst als Beleg. Der Absatz belegte also sich selbst.
#: Nachgemessen in einer Kopie des Baumes: Grenzsatz aus dem B.3-Absatz
#: entfernt, alle elf Tests blieben gruen. Ohne ``"B.3"`` faellt dieselbe
#: Mutation.
BELEG_JE_DOKUMENT = {
    "docs/architektur-ist-und-ziel.md": ("vor dem Ursprung",),
    "docs/storage-architektur.md": ("vor dem Ursprung",),
    PROTOKOLL: ("vor dem Ursprung",),
}

#: Wie weit der Beleg von der Behauptung entfernt stehen darf. Ohne Schranke
#: genuegte ein Vorkommen irgendwo im Dokument, und weil fast jedes Dokument
#: irgendwo auf ``AENDERUNGEN.md`` verlinkt, war der erste Entwurf dieses
#: Waechters gruen, obwohl die Grenze aus dem Absatz entfernt war - aufgefallen
#: erst bei der Mutationsprobe. Gemessen am 9.10.2026 liegt der weiteste
#: ehrliche Abstand bei 842 Zeichen (Protokoll, ueber den Code-Block hinweg);
#: der naechste unehrliche lag bei 1'833.
NAHE = 1200

#: Das README zeigt die Messung nicht vor, es beruft sich auf sie. Dann muss
#: der Verweis daneben stehen, nicht irgendwo.
BERUFT_SICH = "von aussen gemessen"
README_VERWEIS = "Abschnitt 16"
README_NAHE = 300


def flach(text: str) -> str:
    """Auszeichnung und Umbrueche weg, damit eine Suche nicht luegt.

    Drei Fallen sind hier zugeschnappt, jede einmal:

    * ``**vor** dem Ursprung`` findet keine Suche nach ``vor dem Ursprung``.
    * Ein Satz, den der Zeilenumbruch in der Mitte teilt, ebenso nicht.
    * Und im README steht die Stelle in einem **Zitatblock**: Aus
      ``von aussen\n> gemessen`` wurde mit der ersten Fassung dieser Funktion
      ``von aussen > gemessen``, und die Suche fand nichts - am 11.10.2026
      genau so passiert, als der Satz dort umgeschrieben wurde.

    Ein Waechter, der daran scheitert, meldet eine Luecke, die es nicht gibt -
    oder, schlimmer, keine, die es gibt.
    """
    ohne_zitat = re.sub(r"^\s*>\s?", "", text, flags=re.M)
    return re.sub(r"\s+", " ", ohne_zitat.replace("*", ""))


def text_von(rel: str) -> str:
    return flach((PROJECT_ROOT / rel).read_text(encoding="utf-8"))


def alle_dokumente() -> list[str]:
    """Jedes Dokument, das eine Aussage ueber den Betriebsstand tragen kann.

    Ein Glob und keine Handliste - Idiom wie in ``test_dokumentzahlen.py``:
    ``docs/**/*.md`` plus ``README.md`` plus den Einseiter. Der Einseiter ist
    die Kurzfassung desselben Textes und lag genau deshalb im blinden Fleck,
    solange die Suchmenge aus ``DOKUMENTE`` gebildet wurde.
    """
    docs = PROJECT_ROOT / "docs"
    pfade = sorted(docs.rglob("*.md")) + [PROJECT_ROOT / "README.md",
                                          docs / "architektur-einseiter.html"]
    rel = [p.relative_to(PROJECT_ROOT).as_posix()
           for p in pfade if p.is_file()]
    return [r for r in rel if not any(a in r for a in AUSGENOMMEN)]


def stellen(text: str, marker: tuple[str, ...]) -> list[int]:
    return sorted(m.start() for s in marker
                  for m in re.finditer(re.escape(s), text))


def ohne_beleg(text: str, orte: list[int], erlaubt: tuple[str, ...],
               nahe: int) -> list[int]:
    return [s for s in orte
            if not any(e in text[max(0, s - nahe):s + nahe] for e in erlaubt)]


@pytest.mark.parametrize("phrase", sorted(UEBERHOLT))
def test_die_gedrehten_aussagen_kommen_nicht_zurueck(phrase: str) -> None:
    """Eine ueberholte Aussage darf in keinem Abgabedokument stehen."""
    schuldig = [d for d in DOKUMENTE
                if d != PROTOKOLL and re.search(phrase, text_von(d))]
    assert not schuldig, (
        f"{schuldig} sagt wieder {phrase!r} - {UEBERHOLT[phrase]}"
    )


@pytest.mark.parametrize("rel,phrase", sorted(NOCH_WAHR.items()))
def test_die_unbelegten_aussagen_stehen_weiter_da(rel: str, phrase: str) -> None:
    """Was nicht belegt ist, bleibt stehen - auch wenn es unfertig klingt.

    Faellt dieser Test, ist eine Aussage mitgedreht worden, fuer die es keinen
    Beleg gibt. Dann gehoert entweder der Beleg her (``docker compose ps`` auf
    der Maschine) oder die Aussage zurueck.
    """
    assert phrase in text_von(rel), (
        f"{rel} sagt {phrase!r} nicht mehr - ist der Beleg dafuer da, oder "
        "ist die Aussage ohne Beleg gedreht worden?"
    )


@pytest.mark.parametrize("rel", sorted(BELEG_JE_DOKUMENT))
def test_wer_die_messung_beschreibt_nennt_ihre_grenze(rel: str) -> None:
    """Die Messung ohne ihre Grenze ist eine Behauptung ueber den Betrieb.

    Eine 302 belegt Cloudflare, DNS und die Access-Anwendung. Sie belegt
    nicht, dass Traefik, Kibana oder Jupyter antworten, denn Access greift vor
    dem Ursprung. Ein Absatz, der das Erste vorzeigt und das Zweite
    verschweigt, liest sich als Betriebszusage - und ``AGENTS.md`` verlangt,
    dass derselbe Satz in zwei Dokumenten in beiden bewacht ist.
    """
    text = text_von(rel)
    erlaubt = BELEG_JE_DOKUMENT[rel]
    orte = stellen(text, BESCHREIBT_MESSUNG)
    assert orte, (
        f"{rel} beschreibt die Messung nicht mehr - dann gehoert es aus "
        "BELEG_JE_DOKUMENT heraus, statt hier stillschweigend durchzulaufen"
    )
    nackt = ohne_beleg(text, orte, erlaubt, NAHE)
    assert not nackt, (
        f"{rel}: {len(nackt)} von {len(orte)} Stellen zeigen die Messung "
        f"vor, ohne dass {erlaubt} in {NAHE} Zeichen Reichweite steht"
    )


def test_das_readme_beruft_sich_nur_mit_verweis() -> None:
    """Das README zeigt die Messung nicht vor - dann muss der Verweis daneben.

    Es sagt "von aussen gemessen" und nennt den Abschnitt, der die Grenze
    ausfuehrt. Rutscht der Verweis weg, bleibt im README eine Behauptung ohne
    Anschluss stehen.
    """
    text = text_von("README.md")
    orte = stellen(text, (BERUFT_SICH,))
    assert orte, f"README.md sagt {BERUFT_SICH!r} nicht mehr"
    nackt = ohne_beleg(text, orte, (README_VERWEIS,), README_NAHE)
    assert not nackt, (
        f"README.md beruft sich auf die Messung, ohne {README_VERWEIS!r} in "
        f"{README_NAHE} Zeichen Reichweite zu nennen"
    )


def test_die_liste_der_beschreibenden_dokumente_ist_vollstaendig() -> None:
    """Wer die Messung neu beschreibt, faellt auf - und wer sie verliert auch.

    Ohne diesen Test waere ``BELEG_JE_DOKUMENT`` eine Liste, die veraltet: Ein
    neues Dokument koennte die 302 vorzeigen, ohne ihre Grenze zu nennen, und
    kein Waechter sprach darueber. Genau diese Flanke hat ``AUSNAHMEN`` in
    ``test_architektur_dokument.py`` drei Tage offen gehalten.

    Gesucht wird deshalb ueber ``alle_dokumente()`` und nicht in ``DOKUMENTE``:
    Aus der Handliste gebildet, bemerkte die Probe nur Dokumente, die schon
    darin stehen - sie haette genau das nicht gekonnt, was ihr Name verspricht.
    """
    beschreibend = {d for d in alle_dokumente()
                    if stellen(text_von(d), BESCHREIBT_MESSUNG)}
    gefuehrt = set(BELEG_JE_DOKUMENT)
    assert beschreibend == gefuehrt, (
        f"dazugekommen: {sorted(beschreibend - gefuehrt)}, "
        f"weggefallen: {sorted(gefuehrt - beschreibend)} - "
        "BELEG_JE_DOKUMENT mitfuehren, sonst prueft niemand die neue Stelle"
    )
