"""Public-site hardening: legal pages, robots, PWA icons, CSP, hub config."""


def test_robots_txt_disallows_app_shells(client):
    response = client.get('/robots.txt')
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'Disallow: /admin' in body
    assert 'Disallow: /api/' in body
    assert 'Allow: /privacy' in body
    assert response.mimetype == 'text/plain'


def test_privacy_and_terms_pages(client):
    privacy = client.get('/privacy')
    terms = client.get('/terms')
    assert privacy.status_code == 200
    assert terms.status_code == 200
    assert b'Privacy' in privacy.data
    assert b'Terms of use' in terms.data


def test_apple_touch_icon_at_root(client):
    response = client.get('/apple-touch-icon.png')
    assert response.status_code == 200
    assert response.mimetype == 'image/png'
    pre = client.get('/apple-touch-icon-precomposed.png')
    assert pre.status_code == 200


def test_csp_header_is_enforced(client):
    response = client.get('/')
    csp = response.headers.get('Content-Security-Policy')
    assert csp
    assert "default-src 'self'" in csp
    assert not response.headers.get('Content-Security-Policy-Report-Only')


def test_hub_config_points_home_at_marketing_apex(app, client):
    previous = {
        'KYNVERA_HUB_MODE': app.config.get('KYNVERA_HUB_MODE'),
        'KYNVERA_HOME_URL': app.config.get('KYNVERA_HOME_URL'),
        'APP_BASE_URL': app.config.get('APP_BASE_URL'),
        'KYNVERA_APP_NAME': app.config.get('KYNVERA_APP_NAME'),
    }
    app.config['KYNVERA_HUB_MODE'] = False
    app.config['KYNVERA_HOME_URL'] = 'https://kynvera.net'
    app.config['APP_BASE_URL'] = 'https://operations.kynvera.net'
    app.config['KYNVERA_APP_NAME'] = 'Kynvera'
    try:
        response = client.get('/api/hub/config')
        assert response.status_code == 200
        data = response.get_json()
        assert data['home_url'] == 'https://kynvera.net'
        assert data['app_name'] == 'Kynvera'
    finally:
        app.config.update(previous)


def test_operations_host_root_serves_landing(client, app):
    previous = app.config.get('KYNVERA_MARKETING_HOSTS')
    app.config['KYNVERA_MARKETING_HOSTS'] = 'kynvera.net,www.kynvera.net'
    try:
        response = client.get('/', headers={'Host': 'operations.kynvera.net'})
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'All your operations' in html
        assert 'og:image' in html
        assert '/static/images/kynvera/og-share.jpg' in html
        assert 'summary_large_image' in html
    finally:
        app.config['KYNVERA_MARKETING_HOSTS'] = previous


def test_og_share_image_is_public(client):
    response = client.get('/static/images/kynvera/og-share.jpg')
    assert response.status_code == 200
    assert response.mimetype == 'image/jpeg'


def test_marketing_host_serves_landing(client, app):
    previous = {
        'KYNVERA_MARKETING_HOSTS': app.config.get('KYNVERA_MARKETING_HOSTS'),
        'APP_BASE_URL': app.config.get('APP_BASE_URL'),
    }
    app.config['KYNVERA_MARKETING_HOSTS'] = 'kynvera.net,www.kynvera.net'
    app.config['APP_BASE_URL'] = 'https://operations.kynvera.net'
    try:
        response = client.get('/', headers={'Host': 'kynvera.net'})
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'All your operations' in html
        assert 'https://operations.kynvera.net/login' in html
        assert 'https://operations.kynvera.net/register' in html
    finally:
        app.config.update(previous)


def test_marketing_only_sends_staff_paths_to_operations(client, app):
    previous = {
        'KYNVERA_MARKETING_ONLY': app.config.get('KYNVERA_MARKETING_ONLY'),
        'APP_BASE_URL': app.config.get('APP_BASE_URL'),
    }
    app.config['KYNVERA_MARKETING_ONLY'] = True
    app.config['APP_BASE_URL'] = 'https://operations.kynvera.net'
    try:
        landing = client.get('/')
        assert landing.status_code == 200
        html = landing.get_data(as_text=True)
        assert 'https://operations.kynvera.net/login' in html
        login = client.get('/login')
        assert login.status_code == 302
        assert login.headers.get('Location') == 'https://operations.kynvera.net/login'
        dashboard = client.get('/dashboard')
        assert dashboard.status_code == 302
        assert dashboard.headers.get('Location') == 'https://operations.kynvera.net/login'
        health = client.get('/health')
        assert health.status_code == 200
        assert health.get_json().get('site') == 'marketing'
    finally:
        app.config.update(previous)


def test_pwa_manifest_starts_at_dashboard(client):
    response = client.get('/manifest.json')
    assert response.status_code == 200
    data = response.get_json()
    assert data.get('start_url') == '/dashboard'


def test_marketing_manifest_starts_at_root(client, app):
    previous = app.config.get('KYNVERA_MARKETING_HOSTS')
    app.config['KYNVERA_MARKETING_HOSTS'] = 'kynvera.net,www.kynvera.net'
    try:
        response = client.get('/manifest.json', headers={'Host': 'kynvera.net'})
        assert response.status_code == 200
        assert response.get_json().get('start_url') == '/'
    finally:
        app.config['KYNVERA_MARKETING_HOSTS'] = previous


def test_landing_has_public_signup(client, app):
    app.config['ALLOW_PUBLIC_REGISTRATION'] = True
    response = client.get('/')
    html = response.get_data(as_text=True)
    assert '/register' in html
    assert 'Create account' in html
    assert '/privacy' in html
    assert '/terms' in html
    assert '/forgot-password' in html
    assert 'Talk to us' in html
    assert 'mailto:support@kynvera.store' in html
