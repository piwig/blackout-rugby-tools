"""Energy scale consistency through real local imports; no Classic calls."""
import json

import pytest
from fastapi.testclient import TestClient

from server.main import create_app
from server.workbench import fatigue_summary


def test_imported_fractional_energy_is_unknown_as_level_without_false_fatigue_alert(tmp_path):
    app = create_app(tmp_path, 'Synthetic-review-password-1234', secure=False)
    with TestClient(app) as client:
        signed = client.post('/api/login', json={'username': 'piwig', 'password': 'Synthetic-review-password-1234'})
        assert signed.status_code == 200
        headers = {'X-CSRF-Token': signed.json()['csrf']}
        source = [{'id': '42', 'name': 'Synthetic energy', 'energy': 5.5}]
        imported = client.post('/api/import', headers=headers,
                               data={'team_id': '72450', 'youth': 'false'},
                               files={'file': ('synthetic.json', json.dumps(source), 'application/json')})
        assert imported.status_code == 200, imported.text
        saved = client.post('/api/workbench/preferences', headers=headers,
                            json={'expected_revision': 0,
                                  'preferences': {'energy_scale': 'level', 'energy_floor': 6}})
        assert saved.status_code == 200, saved.text
        daily = client.get('/api/workbench/daily').json()
        club = next(item for item in daily['clubs'] if item['team_id'] == '72450')
        assert club['fatigue'] == {'scale': 'level', 'floor': 6, 'low_count': 0,
                                  'known_count': 0, 'unknown_count': 1, 'total': 1}
        assert not any(action['kind'] == 'fatigue' and action['team_id'] == '72450'
                       for action in daily['actions'])
        optimized = client.get('/api/optimization?team_id=72450&energy_scale=level&energy_floor=60').json()
        assert optimized['reports'][0]['summary']['unknown_energy'] == 1
        # The same decimal remains a real measurement when the manager selects percent.
        saved = client.post('/api/workbench/preferences', headers=headers,
                            json={'expected_revision': 1,
                                  'preferences': {'energy_scale': 'percent', 'energy_floor': 6}})
        assert saved.status_code == 200, saved.text
        daily = client.get('/api/workbench/daily').json()
        club = next(item for item in daily['clubs'] if item['team_id'] == '72450')
        assert club['fatigue'] == {'scale': 'percent', 'floor': 6, 'low_count': 1,
                                  'known_count': 1, 'unknown_count': 0, 'total': 1}


@pytest.mark.parametrize('scale,floor,values,known,low', [
    ('level', 6, [1, 6, 11, 1.0, 11.0], 5, 2),
    ('level', 6, [1.5, 5.5, 10.5, 0, 12, True, False, None, float('nan'), float('inf')], 0, 0),
    ('percent', 6, [0, 5.5, 6, 110, -1, 111, True, False, None, float('nan'), float('inf')], 4, 2),
    ('unknown', 6, [0, 1, 5.5, 6, 11, 110], 0, None),
])
def test_fatigue_known_measurements_and_boundaries_follow_selected_energy_scale(scale, floor, values, known, low):
    result = fatigue_summary([{'energy': value} for value in values],
                             {'energy_scale': scale, 'energy_floor': floor})
    assert result == {'scale': scale, 'floor': floor, 'low_count': low,
                      'known_count': known, 'unknown_count': len(values) - known, 'total': len(values)}
