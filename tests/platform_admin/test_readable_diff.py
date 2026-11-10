"""Der lesende Vergleich bindet an die ursprüngliche Revision, nicht den Head."""
from copy import deepcopy

from platform_admin.store import Store
from platform_admin.web import create_app
from .helpers import PROJECT


def test_diff_returns_exact_settings_and_keeps_existing_text(tmp_path):
    store = Store(PROJECT, tmp_path / 'data')
    store.initialize('bootstrap')
    original = store.current('settings')
    proposed = deepcopy(original['payload'])
    proposed['jobs'][0]['at_utc'] = '09:45'
    rid = store.propose('settings', proposed, original['id'], 'Engineer', 'Zeitplan prüfen')
    client = create_app(store, operator='Reviewer', token='local-test',
                        config={'ADMIN_AUTH': 'local'}).test_client()
    assert client.get('/api/diff?id=' + rid).status_code == 401
    response = client.get('/api/diff?id=' + rid,
                          headers={'Authorization': 'Bearer local-test'})
    assert response.status_code == 200
    result = response.get_json()
    assert result['resource'] == 'settings'
    assert result['before'] == original['payload']
    assert result['after'] == proposed
    assert '+      "at_utc": "09:45"' in result['diff']
    assert store.current('settings')['id'] == original['id']


def test_mapping_diff_preserves_leading_zero_and_parent(tmp_path):
    store = Store(PROJECT, tmp_path / 'data')
    store.initialize('bootstrap')
    original = store.current('mapping')
    rid = store.propose_mapping('chicago', '0110', '09B', original['id'],
                                'Engineer', 'Zuordnung prüfen')
    client = create_app(store, operator='Reviewer', token='local-test',
                        config={'ADMIN_AUTH': 'local'}).test_client()
    result = client.get('/api/diff?id=' + rid,
                        headers={'Authorization': 'Bearer local-test'}).get_json()
    assert result['resource'] == 'mapping'
    assert result['before'] == original['payload']
    assert 'chicago,0110,09B,' in result['after']['mapping_overrides.csv']
    assert result['after']['iucr_nibrs_mapping.csv'] == result['before']['iucr_nibrs_mapping.csv']
    assert store.current('mapping')['id'] == original['id']

