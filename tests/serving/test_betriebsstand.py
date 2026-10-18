"""Der Betriebsblick - und was ein fehlender Lauf heissen muss.

Am 17.10.2026 war zu sehen, was fehlt: Der woechentliche Lauf auf ``srv01``
ist am 12. und am 15.10. gescheitert, und gewusst hat es niemand. Danach
meldete ``pruefe_stand`` wochenlang eine fehlende Tabelle, ohne dass jemand
hinsah. Der Betrieb hatte keine Stimme.

Der schaerfste Test dieser Datei ist der mit dem **fehlenden** Protokoll:
Eine Metrikdatei, die dann schweigt, sieht aus wie eine, die Erfolg meldet.
"""

from __future__ import annotations

import json

import pytest

from serving import betriebsstand as bs


def protokoll(**rest) -> dict:
    grund = {
        "status": "complete",
        "started_at_utc": "2026-10-17T08:38:27.370283+00:00",
        "finished_at_utc": "2026-10-17T08:38:50.911042+00:00",
        "stages": [{"gruppe": "silver", "name": "tract_2021",
                    "sekunden": 1.5, "exit": 0}],
        "source_freshness": {"city=chicago": "2026-10-17T08:00:00Z"},
        "output_rows": {"gold/fact_offense": 1864086},
        "release": {"release_id": "2026-10-17T08-38-50Z", "files": 27,
                    "bytes": 190000000, "published": True},
    }
    grund.update(rest)
    return grund


# Der Zeitpunkt, gegen den gerechnet wird - 3600 s nach dem Laufende.
JETZT = 1792226330.911 + 3600


def werte(text: str) -> dict[str, float]:
    """Messzeilen ohne Marken als {Name: Wert}."""
    gefunden = {}
    for zeile in text.splitlines():
        if zeile.startswith("#") or "{" in zeile or not zeile.strip():
            continue
        name, _, wert = zeile.rpartition(" ")
        gefunden[name] = float(wert)
    return gefunden


# --------------------------------------------------------------------------
# Der Fall, der zaehlt
# --------------------------------------------------------------------------


def test_ohne_protokoll_sagt_die_datei_dass_sie_nichts_weiss():
    """Schweigen saehe aus wie Erfolg.

    Das ist die teuerste Art, falsch zu sein: Eine Metrikdatei ohne
    ``lauf_erfolgreich`` liest sich auf der anderen Seite als "keine Daten",
    und "keine Daten" wird in jedem Dashboard als Luecke gezeichnet, nicht
    als Alarm. Mit ``lauf_bekannt 0`` ist es eine Aussage.
    """
    text = bs.metriken(None)
    w = werte(text)
    assert w["urbancrime_lauf_bekannt"] == 0
    assert "lauf_erfolgreich" not in text, (
        "ohne Protokoll darf kein Erfolgswert dastehen - weder 0 noch 1: "
        "Die eine Zahl waere erfunden, die andere eine Luege")


def test_ein_gescheiterter_lauf_ist_nicht_gruen():
    w = werte(bs.metriken(protokoll(status="failed"), jetzt=JETZT))
    assert w["urbancrime_lauf_bekannt"] == 1
    assert w["urbancrime_lauf_erfolgreich"] == 0


def test_ein_gruener_lauf_ist_gruen():
    w = werte(bs.metriken(protokoll(), jetzt=JETZT))
    assert w["urbancrime_lauf_erfolgreich"] == 1


def test_ein_unlesbares_protokoll_gilt_als_keines(tmp_path, monkeypatch):
    """Eine halbe Datei darf nicht als halber Erfolg durchgehen."""
    from storage import Config, Storage, set_storage

    ablage = Storage(Config(backend="local", local_root=tmp_path))
    set_storage(ablage)
    (tmp_path / bs.PROTOKOLL).write_text("{kein json", encoding="utf-8")
    assert bs.protokoll_lesen(ablage) is None


# --------------------------------------------------------------------------
# Was der Blick zeigen muss
# --------------------------------------------------------------------------


def test_das_alter_des_standes_steht_da():
    """FR-30 nennt es ausdruecklich: *wie alt der Stand ist*."""
    w = werte(bs.metriken(protokoll(), jetzt=JETZT))
    assert w["urbancrime_lauf_alter_sekunden"] == pytest.approx(3600, abs=1)


def test_jede_stufe_traegt_ihren_exitcode():
    text = bs.metriken(protokoll(stages=[
        {"gruppe": "silver", "name": "crime_offense", "sekunden": 117.3, "exit": 0},
        {"gruppe": "gold", "name": "gold", "sekunden": 0.0, "exit": 1},
    ]), jetzt=JETZT)
    assert 'urbancrime_stufe_exit{gruppe="silver",name="crime_offense"} 0' in text
    assert 'urbancrime_stufe_exit{gruppe="gold",name="gold"} 1' in text


def test_ein_lauf_ohne_release_sagt_es():
    """Auch das ist eine Aussage - am 17.10.2026 dreimal der Fall.

    Zweimal scheiterte das Release am Kontingent des Buckets, einmal an einem
    Serverfehler beim Upload. Die Strecke war jedes Mal gruen; wer nur auf
    ``lauf_erfolgreich`` sieht, merkt nichts.
    """
    w = werte(bs.metriken(protokoll(release={}), jetzt=JETZT))
    assert w["urbancrime_lauf_erfolgreich"] == 1
    assert w["urbancrime_release_dateien"] == 0


def test_die_quellenfrische_steht_je_quelle_da():
    text = bs.metriken(protokoll(source_freshness={
        "city=chicago": "2026-10-17T08:00:00Z",
        "dataset=noaa_ghcnd": "2026-10-12T14:41:31Z",
    }), jetzt=JETZT)
    assert 'urbancrime_quelle_alter_sekunden{quelle="city=chicago"}' in text
    assert 'urbancrime_quelle_alter_sekunden{quelle="dataset=noaa_ghcnd"}' in text


# --------------------------------------------------------------------------
# Form
# --------------------------------------------------------------------------


def test_jeder_messwert_traegt_hilfe_und_typ():
    """Eine Metrikdatei ist eine Schnittstelle.

    Ohne ``# HELP`` steht in Grafana ein Name ohne Bedeutung, und wer ihn in
    einem Jahr liest, raet. Geprueft wird fuer **jeden** Wert, nicht fuer
    einen - sonst waechst die Datei, und die Haelfte bleibt unerklaert.
    """
    text = bs.metriken(protokoll(), jetzt=JETZT)
    namen = {z.split("{")[0].split(" ")[0]
             for z in text.splitlines()
             if z and not z.startswith("#")}
    ohne = [n for n in sorted(namen)
            if f"# HELP {n} " not in text or f"# TYPE {n} " not in text]
    assert not ohne, f"ohne HELP oder TYPE: {ohne}"


def test_ein_anfuehrungszeichen_wird_maskiert():
    """Markenwerte kommen aus den Daten - ein Tabellenname, ein Quellpfad.

    Geprueft wird die **Zusage des Formats**, nicht die Zahl der
    Anfuehrungszeichen: Ein maskiertes macht drei, und drei ist richtig. Die
    erste Fassung dieses Tests zaehlte auf Paarigkeit und meldete damit die
    korrekte Maskierung als Fehler.
    """
    text = bs.metriken(protokoll(output_rows={'gold/mit"zitat': 1}), jetzt=JETZT)
    zeile = next(z for z in text.splitlines()
                 if "mit" in z and not z.startswith("#"))
    assert zeile == r'urbancrime_tabelle_zeilen{tabelle="gold/mit\"zitat"} 1', zeile


def test_die_reihenfolge_ist_bei_zwei_laeufen_dieselbe():
    """Eine Schnittstelle, deren Felder sich je Lauf anders ordnen, ist keine."""
    p = protokoll()
    assert bs.metriken(p, jetzt=JETZT) == bs.metriken(p, jetzt=JETZT)


def test_geschrieben_wird_wohin_gesagt(tmp_path, monkeypatch, capsys):
    from storage import Config, Storage, set_storage

    set_storage(Storage(Config(backend="local", local_root=tmp_path)))
    (tmp_path / bs.PROTOKOLL).write_text(json.dumps(protokoll()), encoding="utf-8")
    ziel = tmp_path / "unterordner" / "metrics"

    assert bs.main(["--ziel", str(ziel)]) == 0

    assert "urbancrime_lauf_erfolgreich 1" in ziel.read_text(encoding="utf-8")
    assert "Messwerte" in capsys.readouterr().out


def test_ohne_protokoll_sagt_der_aufruf_es_auch(tmp_path, capsys):
    from storage import Config, Storage, set_storage

    set_storage(Storage(Config(backend="local", local_root=tmp_path)))
    ziel = tmp_path / "metrics"

    assert bs.main(["--ziel", str(ziel)]) == 0

    assert "lauf_bekannt 0" in ziel.read_text(encoding="utf-8")
    assert "kein Laufprotokoll" in capsys.readouterr().out, (
        "ein stiller Erfolg bei fehlendem Protokoll ist genau der Fehler, "
        "den dieses Modul behebt")
