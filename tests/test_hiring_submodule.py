"""Hiring trackers are an HR submodule gated by access_hiring."""

from tests.factories import make_user


def _login(client, username, password):
    response = client.post('/api/auth/login', json={'username': username, 'password': password})
    data = response.get_json() or {}
    token = data.get('access_token')
    assert token, data
    return {'Authorization': f'Bearer {token}'}


TRACKER_PAGES = (
    '/hr/hiring',
    '/hr/hiring/offer-letters',
    '/hr/leave-tracker',
    '/hr/manpower-tracker',
)


def test_hr_without_hiring_cannot_open_trackers(client, app):
    with app.app_context():
        user, pwd = make_user(access_hr=True, access_hiring=False)
        username = user.username
    headers = _login(client, username, pwd)
    for path in TRACKER_PAGES:
        response = client.get(path, headers=headers)
        assert response.status_code == 403, (path, response.status_code, response.get_json())


def test_hr_with_hiring_can_open_trackers(client, app):
    with app.app_context():
        user, pwd = make_user(access_hr=True, access_hiring=True)
        username = user.username
    headers = _login(client, username, pwd)
    for path in TRACKER_PAGES:
        response = client.get(path, headers=headers)
        assert response.status_code == 200, (path, response.status_code, response.get_data(as_text=True)[:400])


def test_hr_dashboard_omits_hiring_cards_without_flag(client, app):
    with app.app_context():
        user, pwd = make_user(access_hr=True, access_hiring=False)
        username = user.username
    headers = _login(client, username, pwd)
    response = client.get('/hr/', headers=headers)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Hiring Documents' not in html
    assert 'Letters of Intent' not in html
    assert 'Manpower Tracker' not in html
    assert 'Leave Application' in html


def test_hr_dashboard_shows_hiring_cards_with_flag(client, app):
    with app.app_context():
        user, pwd = make_user(access_hr=True, access_hiring=True)
        username = user.username
    headers = _login(client, username, pwd)
    response = client.get('/hr/', headers=headers)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Hiring Documents' in html
    assert 'Letters of Intent' in html
    assert 'Leave Tracker' in html
    assert 'Manpower Tracker' in html
    assert 'Leave Application' in html
