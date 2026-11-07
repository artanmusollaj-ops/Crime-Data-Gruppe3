"""Die Betriebseinstellungen der Konsole, wie sie in Git liegen.

Seit dem 7.11.2026 traegt das Repository ``config/platform_admin_settings.json``
(#209): Die Konsole haelt vor einem Impact die aktiven Einstellungen gegen
``main``. Die Konsolentests unter ``tests/platform_admin/`` starten mit Absicht
von ``DEFAULT_SETTINGS`` (ihre ``conftest.py``); dieser Test steht deshalb
ausserhalb und prueft die echte Datei.
"""

from __future__ import annotations

import json
from pathlib import Path

from platform_admin.store import Store, repository_settings, validate_settings

PROJEKT = Path(__file__).resolve().parents[1]
DATEI = PROJEKT / "config" / "platform_admin_settings.json"


def test_die_datei_liegt_im_repository_und_ist_gueltig():
    einstellungen = json.loads(DATEI.read_text(encoding="utf-8"))
    validate_settings(einstellungen)


def test_der_store_uebernimmt_die_datei_als_basis(tmp_path):
    store = Store(PROJEKT, tmp_path / "data")
    store.initialize("Test")
    assert repository_settings(PROJEKT) == json.loads(DATEI.read_text(encoding="utf-8"))
    assert store.current("settings")["payload"] == repository_settings(PROJEKT)


def test_der_zeitraum_ist_der_studienzeitraum():
    """2021-2026, wie in AGENTS.md und im Konzept - nicht die Vorgabe 2024."""
    einstellungen = repository_settings(PROJEKT)
    assert (einstellungen["scope_start"], einstellungen["scope_end_exclusive"]) == (
        "2021-01-01", "2027-01-01")
