"""Der Zeitraum eines Bretts: Perioden, Abdeckung, Vergleich und Nenner.

Seit Stufe 3 (24.11.2026) rechnen die Bretter auf einem Tagesbereich statt
auf Monaten eines Jahres. Was dabei fuer alle Bretter gleich gelten muss,
steht hier, damit es nicht siebenmal leicht verschieden entsteht. Die
Entscheide vom 23.11.2026:

**Achse nach Spanne.** Bis 92 Tage je Tag, bis zwei Jahre je Woche, sonst je
Monat. Ganze Monate eines Jahres bleiben je Monat, wie bisher: Ein Link auf
»Maerz bis Mai 2024« zeigt drei Punkte, nicht 92. Die erste und die letzte
Periode sind am Zeitraum abgeschnitten; eine Woche beginnt am Montag.

**Rate je Jahr.** Faelle je 1'000 Einwohner und Jahr. Der Nenner sind
Personenjahre: Jeder Tag im Zeitraum, fuer den die Stadt Daten hat, zaehlt
mit den Einwohnern seines Vintage, geteilt durch die Tage seines Jahres.
Ueber ein ganzes Jahr mit einem Vintage ist das genau die Einwohnerzahl -
die Rate der Abgabedokumente bleibt also 94,5. Ueber einen Monat ist sie
die Rate, die sich ergaebe, ginge es das ganze Jahr so weiter; ein einzelner
Tag zaehlt 365-fach und ist entsprechend unruhig. Bis Stufe 2 teilte ein
Teiljahr durch die Einwohner, ohne hochzurechnen: Maerz bis Mai ergab rund
ein Viertel der Jahresrate, und das laufende Jahr sah ruhiger aus, als es war.

**Vergleich bis ein Jahr Spanne**, mit demselben Zeitraum ein Jahr frueher,
ueber die Tage, die in beiden Jahren fuer jede gewaehlte Stadt Daten haben.
Bis Stufe 2 waren es die Monate, die in beiden Jahren ganz vorlagen; ein
Teilmonat am Datenende fiel ganz heraus. Ueber laengere Spannen gibt es
keinen Vergleich: Das Jahr davor ueberlappte den Zeitraum selbst.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from typing import Any

#: Bis zu so vielen Tagen zeigt die Achse jeden Tag.
TAGESACHSE = 92
#: Bis zu so vielen Tagen - zwei Jahre, eines davon ein Schaltjahr - je Woche.
WOCHENACHSE = 731
#: Bis zu dieser Spanne gibt es einen Vergleich mit dem Vorjahr.
VERGLEICHSSPANNE = 366


def vor_einem_jahr(tag: date) -> date:
    """Derselbe Tag ein Jahr frueher; der 29. Februar wird der 28."""
    try:
        return tag.replace(year=tag.year - 1)
    except ValueError:
        return tag.replace(year=tag.year - 1, day=28)


def nach_einem_jahr(tag: date) -> date:
    """Derselbe Tag ein Jahr spaeter; der 29. Februar wird der 28."""
    try:
        return tag.replace(year=tag.year + 1)
    except ValueError:
        return tag.replace(year=tag.year + 1, day=28)


def benutzt(sql: str, param: dict[str, Any]) -> dict[str, Any]:
    """Nur die Parameter, die ``sql`` nennt: DuckDB lehnt ueberzaehlige ab.

    Die Periode einer Tagesachse braucht ``$von`` nicht, die einer Wochen-
    oder Monatsachse schon (``Zeitraum.periode_sql``).
    """
    return {k: v for k, v in param.items() if re.search(rf"\${k}\b", sql)}


def koernung(a: Any) -> str:
    """``tag``, ``woche`` oder ``monat`` - die Achse fuer die Auswahl ``a``."""
    if a.ganze_monate or a.tage > WOCHENACHSE:
        return "monat"
    return "tag" if a.tage <= TAGESACHSE else "woche"


def perioden(von: date, bis: date, art: str) -> list[tuple[date, date]]:
    """Die Perioden der Achse, beide Enden eingeschlossen, am Zeitraum abgeschnitten."""
    ergebnis = []
    start = von
    while start <= bis:
        if art == "tag":
            ende = start
        elif art == "woche":
            ende = start + timedelta(days=6 - start.weekday())
        else:
            ende = date(start.year, start.month, calendar.monthrange(start.year, start.month)[1])
        ende = min(ende, bis)
        ergebnis.append((start, ende))
        start = ende + timedelta(days=1)
    return ergebnis


def _schnitt(a: tuple[date, date] | None, b: tuple[date, date] | None) -> tuple[date, date] | None:
    if a is None or b is None:
        return None
    von, bis = max(a[0], b[0]), min(a[1], b[1])
    return (von, bis) if von <= bis else None


class Zeitraum:
    """Der Zeitraum einer Auswahl fuer bestimmte Staedte, mit dem Fenster je Stadt."""

    def __init__(self, cur: Any, a: Any, staedte: list[str]):
        self.a = a
        self.von, self.bis = a.tag_von, a.tag_bis
        self.staedte = list(staedte)
        self.koernung = koernung(a)
        self.perioden = perioden(self.von, self.bis, self.koernung)
        self.starts = [p[0] for p in self.perioden]
        self.fenster: dict[str, tuple[date, date]] = {s: (v, b) for s, v, b in cur.execute(
            "SELECT stadt, von, bis FROM fenster WHERE stadt IN $staedte",
            {"staedte": self.staedte}).fetchall()}

    # -- SQL -------------------------------------------------------------

    @property
    def param(self) -> dict[str, Any]:
        return {"von": self.von, "bis": self.bis}

    def periode_sql(self, spalte: str = "f.tag") -> str:
        """Der Beginn der Periode eines Tages, als SQL; braucht ``$von``."""
        if self.koernung == "tag":
            return spalte
        einheit = "week" if self.koernung == "woche" else "month"
        return f"greatest(date_trunc('{einheit}', {spalte})::DATE, $von)"

    def index(self, start: date) -> int:
        return self.starts.index(start)

    # -- Abdeckung ---------------------------------------------------------

    def mit_daten(self, stadt: str, von: date | None = None,
                  bis: date | None = None) -> tuple[date, date] | None:
        """Die Tage zwischen ``von`` und ``bis``, fuer die ``stadt`` Daten hat."""
        return _schnitt((von or self.von, bis or self.bis), self.fenster.get(stadt))

    def tage_mit_daten(self, stadt: str) -> int:
        t = self.mit_daten(stadt)
        return (t[1] - t[0]).days + 1 if t else 0

    def ganz(self, von: date, bis: date) -> bool:
        """Ob die Periode ganz ist - eine ganze Woche ab Montag, ein ganzer Monat.

        Am Rand schneidet der Zeitraum sie ab: Ab einem Sonntag ist die erste
        Woche ein Tag lang. Ihr Wert ist dann kein Wochenwert, und die Seite
        zeichnet sie hohl wie eine Periode, der Daten fehlen.
        """
        if self.koernung == "tag":
            return True
        if self.koernung == "woche":
            return von.weekday() == 0 and (bis - von).days == 6
        return von.day == 1 and bis.day == calendar.monthrange(bis.year, bis.month)[1]

    def _status(self, stadt: str, von: date, bis: date, ganz: bool) -> str:
        t = self.mit_daten(stadt, von, bis)
        return "fehlt" if t is None else "voll" if ganz and t == (von, bis) else "teil"

    def status(self, stadt: str, rand: bool = True) -> list[str]:
        """Je Periode: ``voll``, ``teil`` oder ``fehlt`` - am Fenster dieser Stadt.

        Mit ``rand`` auch ``teil``, wo der Zeitraum die Periode anschneidet
        (``ganz``) - fuer die Diagramme. Ohne ``rand`` zaehlen nur die Daten:
        Eine angeschnittene Woche ist keine Datenluecke, und die Abdeckung
        sagt das nicht.
        """
        return [self._status(stadt, von, bis, not rand or self.ganz(von, bis))
                for von, bis in self.perioden]

    def status_vorjahr(self, stadt: str) -> list[str]:
        """Wie ``status``, fuer dieselben Perioden ein Jahr frueher."""
        return [self._status(stadt, vor_einem_jahr(von), vor_einem_jahr(bis), self.ganz(von, bis))
                for von, bis in self.perioden]

    # -- Vergleich ---------------------------------------------------------

    @property
    def vergleich_moeglich(self) -> bool:
        return self.a.tage <= VERGLEICHSSPANNE

    def vergleich(self, staedte: list[str] | None = None) -> tuple[date, date] | None:
        """Die Tage dieses Zeitraums, die mit ihrem Vorjahrestag vergleichbar sind.

        Vergleichbar ist ein Tag, wenn jede der ``staedte`` an ihm und ein Jahr
        frueher Daten hat. Weil jedes Fenster zusammenhaengt, ist das wieder
        ein Bereich. ``None`` ueber mehr als ein Jahr Spanne oder ohne Tag.
        """
        if not self.vergleich_moeglich:
            return None
        bereich: tuple[date, date] | None = (self.von, self.bis)
        for s in staedte if staedte is not None else self.staedte:
            f = self.fenster.get(s)
            if f is None:
                return None
            bereich = _schnitt(bereich, f)
            bereich = _schnitt(bereich, (nach_einem_jahr(f[0]), nach_einem_jahr(f[1])))
        return bereich

    # -- Nenner ------------------------------------------------------------

    def gewichte(self, stadt: str,
                 vintage_je_jahr: dict[int, int | None]) -> dict[int, float] | None:
        """Je Vintage die Jahre, die es im Zeitraum traegt - ueber die Tage mit Daten.

        Ein Tag zaehlt ``1 / Tage seines Jahres``. ``vintage_je_jahr`` je
        Kalenderjahr, ``None`` wo ein Jahr gemischte Vintages traegt: Dann gibt
        es keine Rate, wie in ``gold_pipeline.raten_je_stadt``.
        """
        t = self.mit_daten(stadt)
        if t is None:
            return None
        gewichte: dict[int, float] = {}
        for jahr in range(t[0].year, t[1].year + 1):
            von, bis = max(t[0], date(jahr, 1, 1)), min(t[1], date(jahr, 12, 31))
            vintage = vintage_je_jahr.get(jahr)
            if vintage is None:
                return None
            tage_im_jahr = 366 if calendar.isleap(jahr) else 365
            gewichte[vintage] = gewichte.get(vintage, 0.0) + ((bis - von).days + 1) / tage_im_jahr
        return gewichte

    def personenjahre(self, stadt: str, einwohner: dict[int, float],
                      vintage_je_jahr: dict[int, int | None]) -> float | None:
        """Einwohner mal Jahre ueber die Tage mit Daten (siehe Moduldoku)."""
        gewichte = self.gewichte(stadt, vintage_je_jahr)
        if not gewichte or any(einwohner.get(v) is None for v in gewichte):
            return None
        return sum(w * einwohner[v] for v, w in gewichte.items()) or None

    def json(self) -> dict[str, Any]:
        """Was die Seite ueber die Achse wissen muss."""
        return {"koernung": self.koernung,
                "perioden": [p[0].isoformat() for p in self.perioden],
                "enden": [p[1].isoformat() for p in self.perioden]}
