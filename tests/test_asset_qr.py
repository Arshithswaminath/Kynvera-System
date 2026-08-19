"""Asset QR labels, public tag page, and scan-code parsing."""
from datetime import date

from module_assets.qr_labels import (
    asset_text_payload,
    ensure_asset_qr_code,
    parse_scanned_asset_code,
    public_asset_url,
    qr_png_bytes,
)


def test_parse_scanned_asset_code_url():
    assert parse_scanned_asset_code(
        'https://injaaz.example/assets/tag/AST-0001'
    ) == 'AST-0001'
    assert parse_scanned_asset_code(
        'http://localhost:5002/assets/tag/AST-0042?x=1'
    ) == 'AST-0042'
    assert parse_scanned_asset_code('/assets/tag/AST-0007') == 'AST-0007'


def test_parse_scanned_asset_code_plain():
    assert parse_scanned_asset_code('AST-0001') == 'AST-0001'
    assert parse_scanned_asset_code('ast-0012') == 'AST-0012'
    assert parse_scanned_asset_code('QR-AST-0001') == 'AST-0001'
    assert parse_scanned_asset_code('  ') == ''
    assert parse_scanned_asset_code(None) == ''
    assert parse_scanned_asset_code('FOO-99') == 'FOO-99'


def test_ensure_asset_qr_code_assigns_label():
    class Fake:
        asset_id = 'AST-0003'
        qr_code = None

    assert ensure_asset_qr_code(Fake()) == 'QR-AST-0003'
    fake = Fake()
    fake.qr_code = 'CUSTOM-99'
    assert ensure_asset_qr_code(fake) == 'CUSTOM-99'


def test_qr_png_bytes_is_png():
    data = qr_png_bytes('https://example.com/assets/tag/AST-0001')
    assert data[:8] == b'\x89PNG\r\n\x1a\n'


def _add_asset(app, **kwargs):
    from app.models import db, Asset
    defaults = dict(
        asset_id='AST-0901',
        name='Plant Room Chiller',
        asset_type='chiller',
        building='Tower A',
        floor='B1',
        room='PR-1',
        manufacturer='Carrier',
        model='30XA',
        serial_number='SN-QR-TEST',
        installation_date=date(2022, 3, 1),
        warranty_expiry=date(2027, 3, 1),
        purchase_cost=12345.67,
        maintenance_cost_total=888.25,
        status='active',
        health_score=74,
        notes='Keep condenser coils clean.',
        qr_code=None,
    )
    defaults.update(kwargs)
    with app.app_context():
        asset = Asset(**defaults)
        db.session.add(asset)
        db.session.commit()
        return asset.asset_id


def _delete_asset(app, asset_id):
    from app.models import db, Asset
    with app.app_context():
        row = Asset.query.filter_by(asset_id=asset_id).first()
        if row:
            db.session.delete(row)
            db.session.commit()


def test_public_tag_page_no_login(client, app):
    aid = _add_asset(app)
    try:
        response = client.get(f'/assets/tag/{aid}')
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert 'Plant Room Chiller' in body
        assert aid in body
        assert 'Carrier' in body
        assert 'SN-QR-TEST' in body
        assert 'Tower A' in body
        assert 'Keep condenser coils clean.' in body
        assert 'Staff login' in body
        assert 'kynvera-wordmark.png' in body
        assert 'Specifications' in body
        assert 'Location' in body
        assert '12345' not in body
        assert '888.25' not in body
        assert 'Purchase cost' not in body
        assert 'Maint. cost' not in body
        assert 'AI estimate' not in body
        assert 'qrcode.min.js' in body
        assert f'/assets/tag/{aid}' in body
    finally:
        _delete_asset(app, aid)


def test_public_qr_png_no_login(client, app):
    aid = _add_asset(app, asset_id='AST-0907')
    try:
        response = client.get(f'/assets/tag/{aid}/qr.png')
        assert response.status_code == 200
        assert response.mimetype == 'image/png'
        assert response.data[:8] == b'\x89PNG\r\n\x1a\n'
    finally:
        _delete_asset(app, aid)


def test_public_tag_unknown_is_404(client):
    response = client.get('/assets/tag/AST-9999')
    assert response.status_code == 404


def test_public_tag_shows_decommissioned(client, app):
    aid = _add_asset(app, asset_id='AST-0902', status='decommissioned', name='Retired AHU')
    try:
        response = client.get(f'/assets/tag/{aid}')
        assert response.status_code == 200
        assert b'Retired AHU' in response.data
        assert b'decommissioned' in response.data
    finally:
        _delete_asset(app, aid)


def test_qr_png_requires_auth(client, app):
    aid = _add_asset(app, asset_id='AST-0903')
    try:
        response = client.get(f'/assets/api/assets/{aid}/qr.png')
        assert response.status_code in (401, 422)
    finally:
        _delete_asset(app, aid)


def test_qr_png_and_label_pdf_admin(client, admin_auth_headers, app):
    aid = _add_asset(app, asset_id='AST-0904', qr_code=None)
    try:
        png = client.get(
            f'/assets/api/assets/{aid}/qr.png?download=1',
            headers=admin_auth_headers,
        )
        assert png.status_code == 200
        assert png.mimetype == 'image/png'
        assert png.data[:8] == b'\x89PNG\r\n\x1a\n'
        assert 'AST-0904-qr.png' in (png.headers.get('Content-Disposition') or '')

        label = client.get(
            f'/assets/api/assets/{aid}/qr-label.pdf',
            headers=admin_auth_headers,
        )
        assert label.status_code == 200
        assert label.mimetype == 'application/pdf'
        assert label.data[:4] == b'%PDF'
        assert 'AST-0904-qr-label.pdf' in (label.headers.get('Content-Disposition') or '')

        with app.app_context():
            from app.models import Asset
            row = Asset.query.filter_by(asset_id=aid).first()
            assert row.qr_code == 'QR-AST-0904'
    finally:
        _delete_asset(app, aid)


def test_bulk_qr_labels_pdf(client, admin_auth_headers, app):
    aid = _add_asset(app, asset_id='AST-0905', name='Bulk QR Pump')
    try:
        response = client.get('/assets/api/qr-labels.pdf', headers=admin_auth_headers)
        assert response.status_code == 200
        assert response.mimetype == 'application/pdf'
        assert response.data[:4] == b'%PDF'
        assert 'asset-qr-labels.pdf' in (response.headers.get('Content-Disposition') or '')
    finally:
        _delete_asset(app, aid)


def test_create_asset_auto_assigns_qr(client, admin_auth_headers, app):
    response = client.post(
        '/assets/api/assets',
        headers=admin_auth_headers,
        json={'name': 'Auto QR Fan', 'asset_type': 'fan'},
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data.get('success') is True
    asset = data['asset']
    assert asset['asset_id']
    assert asset['qr_code'] == f"QR-{asset['asset_id']}"
    _delete_asset(app, asset['asset_id'])


def test_public_asset_url_uses_tag_path(app):
    with app.app_context():
        url = public_asset_url('AST-0001', base_url='https://kynvera.example')
        assert url == 'https://kynvera.example/assets/tag/AST-0001'


def test_asset_text_payload_and_parse():
    class Fake:
        asset_id = 'AST-0002'
        name = 'AHU 2.105'
        asset_type = 'AHU'
        building = 'Tower A'
        floor = 'L3'
        room = '2.105'
        manufacturer = 'Carrier'
        model = '39M'
        serial_number = 'SN-22'
        status = 'active'
        health_score = 81
        warranty_expiry = date(2027, 3, 1)
        purchase_cost = 99999.0
        maintenance_cost_total = 50.0

    text = asset_text_payload(Fake())
    assert 'AST-0002' in text
    assert 'AHU 2.105' in text
    assert 'Tower A / L3 / 2.105' in text
    assert 'SN SN-22' in text or 'SN-22' in text
    assert '99999' not in text
    assert parse_scanned_asset_code(text) == 'AST-0002'


def test_qr_text_png_admin(client, admin_auth_headers, app):
    aid = _add_asset(app, asset_id='AST-0906', qr_code=None)
    try:
        png = client.get(
            f'/assets/api/assets/{aid}/qr-text.png?download=1',
            headers=admin_auth_headers,
        )
        assert png.status_code == 200
        assert png.mimetype == 'image/png'
        assert png.data[:8] == b'\x89PNG\r\n\x1a\n'
        assert 'AST-0906-qr-text.png' in (png.headers.get('Content-Disposition') or '')

        via_type = client.get(
            f'/assets/api/assets/{aid}/qr.png?type=text&download=1',
            headers=admin_auth_headers,
        )
        assert via_type.status_code == 200
        assert via_type.mimetype == 'image/png'
        assert via_type.data[:8] == b'\x89PNG\r\n\x1a\n'
    finally:
        _delete_asset(app, aid)


def test_label_pdf_lists_full_asset_fields(app):
    from io import BytesIO
    from pypdf import PdfReader
    from module_assets.qr_labels import build_single_label_pdf

    class Fake:
        asset_id = 'AST-0014'
        qr_code = 'QR-AST-0014'
        name = 'AHU-04 West Plant Handler'
        asset_type = 'AHU'
        building = 'A&F Building'
        floor = 'Ground floor'
        room = 'Plant Room 2'
        manufacturer = 'Carrier'
        model = '39M-AHU'
        serial_number = 'CAR-39M-88421'
        installation_date = date(2024, 3, 12)
        warranty_expiry = date(2027, 3, 11)
        status = 'active'
        health_score = 86
        purchase_cost = 126500.0

    with app.app_context():
        pdf = build_single_label_pdf(Fake())
    assert pdf[:4] == b'%PDF'
    text = ''.join((page.extract_text() or '') for page in PdfReader(BytesIO(pdf)).pages)
    for needle in ('AST-0014', 'AHU-04', 'Carrier', 'CAR-39M-88421', 'A&F Building', 'active'):
        assert needle in text, needle
    assert '126500' not in text
