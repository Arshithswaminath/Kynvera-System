"""Depth-pass CRUD coverage for the /tickets/api/settings/* catalog resources:
vendors, service-groups, categories, fault-codes, priorities, hold-reasons,
and cancel-reasons.

`tests/test_ticket_settings_resources.py` already covers project-scoped
vendor attach/detach and read-only classification/options paths as part of a
ticket-creation flow. This file targets the actual create/update/delete
handlers for each catalog resource group that aren't reached there.

All rows created here use a unique name/code prefix (PFX) so assertions can
be scoped to rows this file created, since the in-memory DB is shared across
the whole `pytest tests/` run.
"""

PFX = 'ZZTKTCRUD'


def _find_group(tree, gid):
    return next((g for g in tree if g['id'] == gid), None)


def _find_category(tree, gid, cid):
    g = _find_group(tree, gid)
    if not g:
        return None
    return next((c for c in g['categories'] if c['id'] == cid), None)


def _find_fault(tree, gid, cid, fid):
    c = _find_category(tree, gid, cid)
    if not c:
        return None
    return next((f for f in c['fault_codes'] if f['id'] == fid), None)


def _get_classification_tree(client, headers):
    res = client.get('/tickets/api/settings/classification', headers=headers)
    assert res.status_code == 200, res.get_json()
    return res.get_json()['service_groups']


class TestVendorSettingsCrud:
    def test_requires_auth(self, client):
        res = client.get('/tickets/api/settings/vendors')
        assert res.status_code in (401, 422)

    def test_non_admin_forbidden(self, client, auth_headers):
        res = client.get('/tickets/api/settings/vendors', headers=auth_headers)
        assert res.status_code == 403
        assert res.get_json()['success'] is False

    def test_create_missing_name(self, client, admin_auth_headers):
        res = client.post('/tickets/api/settings/vendors', json={}, headers=admin_auth_headers)
        assert res.status_code == 400
        assert res.get_json()['success'] is False

    def test_create_appears_in_active_list(self, client, admin_auth_headers):
        name = f'{PFX} Vendor Create'
        created = client.post(
            '/tickets/api/settings/vendors',
            json={'name': name, 'contact_name': 'Sam Supplier'},
            headers=admin_auth_headers,
        )
        assert created.status_code == 201, created.get_json()
        row = created.get_json()['vendor']
        assert row['name'] == name
        assert row['contact_name'] == 'Sam Supplier'
        assert row['is_active'] is True

        listed = client.get('/tickets/api/settings/vendors', headers=admin_auth_headers)
        assert listed.status_code == 200
        names = [v['name'] for v in listed.get_json()['vendors']]
        assert name in names

    def test_update_vendor_field(self, client, admin_auth_headers):
        name = f'{PFX} Vendor Update'
        created = client.post(
            '/tickets/api/settings/vendors', json={'name': name}, headers=admin_auth_headers,
        ).get_json()['vendor']

        upd = client.put(
            f"/tickets/api/settings/vendors/{created['id']}",
            json={'contact_email': 'vendor-crud@example.com'},
            headers=admin_auth_headers,
        )
        assert upd.status_code == 200, upd.get_json()
        assert upd.get_json()['vendor']['contact_email'] == 'vendor-crud@example.com'
        # Untouched fields survive a partial update.
        assert upd.get_json()['vendor']['name'] == name

    def test_update_unknown_vendor_404(self, client, admin_auth_headers):
        res = client.put(
            '/tickets/api/settings/vendors/999999', json={'name': 'x'}, headers=admin_auth_headers,
        )
        assert res.status_code == 404

    def test_deactivate_removes_from_active_list(self, client, admin_auth_headers):
        # Vendors have no DELETE route; "delete" is a PUT is_active=False soft-deactivate.
        name = f'{PFX} Vendor Deactivate'
        created = client.post(
            '/tickets/api/settings/vendors', json={'name': name}, headers=admin_auth_headers,
        ).get_json()['vendor']

        deact = client.put(
            f"/tickets/api/settings/vendors/{created['id']}",
            json={'is_active': False},
            headers=admin_auth_headers,
        )
        assert deact.status_code == 200
        assert deact.get_json()['vendor']['is_active'] is False

        listed = client.get('/tickets/api/settings/vendors', headers=admin_auth_headers).get_json()['vendors']
        assert all(v['id'] != created['id'] for v in listed)


class TestServiceGroupSettingsCrud:
    def test_requires_auth(self, client):
        res = client.post('/tickets/api/settings/service-groups', json={'name': 'x'})
        assert res.status_code in (401, 422)

    def test_create_missing_name(self, client, admin_auth_headers):
        res = client.post('/tickets/api/settings/service-groups', json={}, headers=admin_auth_headers)
        assert res.status_code == 400
        assert res.get_json()['success'] is False

    def test_create_update_delete_cycle(self, client, admin_auth_headers):
        name = f'{PFX} Service Group'
        created = client.post(
            '/tickets/api/settings/service-groups',
            json={'name': name, 'sort_order': 5},
            headers=admin_auth_headers,
        )
        assert created.status_code == 201, created.get_json()
        gid = created.get_json()['service_group']['id']
        assert created.get_json()['service_group']['sort_order'] == 5

        tree = _get_classification_tree(client, admin_auth_headers)
        match = _find_group(tree, gid)
        assert match is not None
        assert match['name'] == name
        assert match['is_active'] is True

        upd = client.put(
            f'/tickets/api/settings/service-groups/{gid}',
            json={'name': f'{name} Renamed', 'sort_order': 9},
            headers=admin_auth_headers,
        )
        assert upd.status_code == 200, upd.get_json()
        assert upd.get_json()['service_group']['name'] == f'{name} Renamed'
        assert upd.get_json()['service_group']['sort_order'] == 9

        deleted = client.delete(f'/tickets/api/settings/service-groups/{gid}', headers=admin_auth_headers)
        assert deleted.status_code == 200
        assert deleted.get_json()['success'] is True

        # Soft-delete: row stays in the (include_inactive) tree with is_active False.
        tree2 = _get_classification_tree(client, admin_auth_headers)
        match2 = _find_group(tree2, gid)
        assert match2 is not None
        assert match2['is_active'] is False

    def test_update_missing_name_rejected(self, client, admin_auth_headers):
        gid = client.post(
            '/tickets/api/settings/service-groups',
            json={'name': f'{PFX} SG For Blank Rename'},
            headers=admin_auth_headers,
        ).get_json()['service_group']['id']
        res = client.put(
            f'/tickets/api/settings/service-groups/{gid}', json={'name': '  '}, headers=admin_auth_headers,
        )
        assert res.status_code == 400

    def test_update_unknown_404(self, client, admin_auth_headers):
        res = client.put(
            '/tickets/api/settings/service-groups/999999', json={'name': 'x'}, headers=admin_auth_headers,
        )
        assert res.status_code == 404

    def test_delete_unknown_404(self, client, admin_auth_headers):
        res = client.delete('/tickets/api/settings/service-groups/999999', headers=admin_auth_headers)
        assert res.status_code == 404


class TestCategorySettingsCrud:
    def _make_group(self, client, headers, name=None):
        res = client.post(
            '/tickets/api/settings/service-groups',
            json={'name': name or f'{PFX} Cat Parent Group'},
            headers=headers,
        )
        assert res.status_code == 201, res.get_json()
        return res.get_json()['service_group']['id']

    def test_requires_auth(self, client):
        res = client.post('/tickets/api/settings/categories', json={'service_group_id': 1, 'name': 'x'})
        assert res.status_code in (401, 422)

    def test_create_missing_service_group_id(self, client, admin_auth_headers):
        res = client.post('/tickets/api/settings/categories', json={'name': 'x'}, headers=admin_auth_headers)
        assert res.status_code == 400
        assert res.get_json()['success'] is False

    def test_create_unknown_service_group_404(self, client, admin_auth_headers):
        res = client.post(
            '/tickets/api/settings/categories',
            json={'service_group_id': 999999, 'name': 'x'},
            headers=admin_auth_headers,
        )
        assert res.status_code == 404

    def test_create_update_delete_cycle(self, client, admin_auth_headers):
        gid = self._make_group(client, admin_auth_headers, name=f'{PFX} Cat Cycle Group')
        name = f'{PFX} Category'
        created = client.post(
            '/tickets/api/settings/categories',
            json={'service_group_id': gid, 'name': name},
            headers=admin_auth_headers,
        )
        assert created.status_code == 201, created.get_json()
        cid = created.get_json()['category']['id']
        assert created.get_json()['category']['service_group_id'] == gid

        tree = _get_classification_tree(client, admin_auth_headers)
        cat = _find_category(tree, gid, cid)
        assert cat is not None
        assert cat['name'] == name
        assert cat['is_active'] is True

        upd = client.put(
            f'/tickets/api/settings/categories/{cid}', json={'name': f'{name} v2'}, headers=admin_auth_headers,
        )
        assert upd.status_code == 200, upd.get_json()
        assert upd.get_json()['category']['name'] == f'{name} v2'

        deleted = client.delete(f'/tickets/api/settings/categories/{cid}', headers=admin_auth_headers)
        assert deleted.status_code == 200

        tree2 = _get_classification_tree(client, admin_auth_headers)
        cat2 = _find_category(tree2, gid, cid)
        assert cat2 is not None
        assert cat2['is_active'] is False

    def test_update_unknown_404(self, client, admin_auth_headers):
        res = client.put(
            '/tickets/api/settings/categories/999999', json={'name': 'x'}, headers=admin_auth_headers,
        )
        assert res.status_code == 404

    def test_delete_unknown_404(self, client, admin_auth_headers):
        res = client.delete('/tickets/api/settings/categories/999999', headers=admin_auth_headers)
        assert res.status_code == 404


class TestFaultCodeSettingsCrud:
    def _make_category(self, client, headers, suffix=''):
        g = client.post(
            '/tickets/api/settings/service-groups',
            json={'name': f'{PFX} Fault Parent Group{suffix}'},
            headers=headers,
        )
        assert g.status_code == 201, g.get_json()
        gid = g.get_json()['service_group']['id']
        c = client.post(
            '/tickets/api/settings/categories',
            json={'service_group_id': gid, 'name': f'{PFX} Fault Parent Cat{suffix}'},
            headers=headers,
        )
        assert c.status_code == 201, c.get_json()
        return gid, c.get_json()['category']['id']

    def test_requires_auth(self, client):
        res = client.post(
            '/tickets/api/settings/fault-codes', json={'category_id': 1, 'code': 'x', 'name': 'y'},
        )
        assert res.status_code in (401, 422)

    def test_create_missing_category_id(self, client, admin_auth_headers):
        res = client.post(
            '/tickets/api/settings/fault-codes', json={'code': 'x', 'name': 'y'}, headers=admin_auth_headers,
        )
        assert res.status_code == 400
        assert res.get_json()['success'] is False

    def test_create_unknown_category_404(self, client, admin_auth_headers):
        res = client.post(
            '/tickets/api/settings/fault-codes',
            json={'category_id': 999999, 'code': 'x', 'name': 'y'},
            headers=admin_auth_headers,
        )
        assert res.status_code == 404

    def test_create_missing_code_and_name(self, client, admin_auth_headers):
        gid, cid = self._make_category(client, admin_auth_headers, suffix=' Missing')
        res = client.post(
            '/tickets/api/settings/fault-codes', json={'category_id': cid}, headers=admin_auth_headers,
        )
        assert res.status_code == 400
        assert res.get_json()['success'] is False

    def test_create_update_delete_cycle(self, client, admin_auth_headers):
        gid, cid = self._make_category(client, admin_auth_headers, suffix=' Cycle')
        code = f'{PFX}9001'
        name = f'{PFX} Fault'
        created = client.post(
            '/tickets/api/settings/fault-codes',
            json={'category_id': cid, 'code': code, 'name': name, 'duration_mins': 30},
            headers=admin_auth_headers,
        )
        assert created.status_code == 201, created.get_json()
        row = created.get_json()['fault_code']
        fid = row['id']
        assert row['fault_code'] == code
        assert row['fault_code_name'] == name
        assert row['duration_mins'] == 30
        assert row['is_active'] is True

        tree = _get_classification_tree(client, admin_auth_headers)
        found = _find_fault(tree, gid, cid, fid)
        assert found is not None
        assert found['fault_code_name'] == name

        upd = client.put(
            f'/tickets/api/settings/fault-codes/{fid}',
            json={'duration_mins': 45, 'name': f'{name} v2'},
            headers=admin_auth_headers,
        )
        assert upd.status_code == 200, upd.get_json()
        assert upd.get_json()['fault_code']['duration_mins'] == 45
        assert upd.get_json()['fault_code']['fault_code_name'] == f'{name} v2'

        deleted = client.delete(f'/tickets/api/settings/fault-codes/{fid}', headers=admin_auth_headers)
        assert deleted.status_code == 200
        assert deleted.get_json()['success'] is True

        tree2 = _get_classification_tree(client, admin_auth_headers)
        found2 = _find_fault(tree2, gid, cid, fid)
        assert found2 is not None
        assert found2['is_active'] is False

    def test_update_unknown_404(self, client, admin_auth_headers):
        res = client.put(
            '/tickets/api/settings/fault-codes/999999', json={'code': 'x'}, headers=admin_auth_headers,
        )
        assert res.status_code == 404

    def test_delete_unknown_404(self, client, admin_auth_headers):
        res = client.delete('/tickets/api/settings/fault-codes/999999', headers=admin_auth_headers)
        assert res.status_code == 404


class TestPrioritySettingsCrud:
    def test_requires_auth(self, client):
        res = client.get('/tickets/api/settings/priorities')
        assert res.status_code in (401, 422)

    def test_create_missing_label(self, client, admin_auth_headers):
        res = client.post('/tickets/api/settings/priorities', json={}, headers=admin_auth_headers)
        assert res.status_code == 400
        assert res.get_json()['success'] is False

    def test_create_update_delete_cycle(self, client, admin_auth_headers):
        label = f'{PFX} Priority'
        created = client.post(
            '/tickets/api/settings/priorities',
            json={'label': label, 'sla_hint': '5h', 'hint': 'Test priority hint'},
            headers=admin_auth_headers,
        )
        assert created.status_code == 201, created.get_json()
        row = created.get_json()['priority']
        rid = row['id']
        assert row['label'] == label
        assert row['sla_hint'] == '5h'
        assert row['is_active'] is True

        listed = client.get('/tickets/api/settings/priorities', headers=admin_auth_headers)
        assert listed.status_code == 200
        assert any(p['id'] == rid for p in listed.get_json()['priorities'])

        upd = client.put(
            f'/tickets/api/settings/priorities/{rid}', json={'label': f'{label} v2'}, headers=admin_auth_headers,
        )
        assert upd.status_code == 200, upd.get_json()
        assert upd.get_json()['priority']['label'] == f'{label} v2'

        deleted = client.delete(f'/tickets/api/settings/priorities/{rid}', headers=admin_auth_headers)
        assert deleted.status_code == 200
        assert deleted.get_json()['success'] is True

        listed2 = client.get('/tickets/api/settings/priorities', headers=admin_auth_headers).get_json()['priorities']
        row2 = next(p for p in listed2 if p['id'] == rid)
        assert row2['is_active'] is False

    def test_duplicate_value_rejected(self, client, admin_auth_headers):
        label = f'{PFX} Dup Priority'
        first = client.post('/tickets/api/settings/priorities', json={'label': label}, headers=admin_auth_headers)
        assert first.status_code == 201, first.get_json()
        dupe = client.post('/tickets/api/settings/priorities', json={'label': label}, headers=admin_auth_headers)
        assert dupe.status_code == 400
        assert dupe.get_json()['success'] is False

    def test_update_unknown_404(self, client, admin_auth_headers):
        res = client.put(
            '/tickets/api/settings/priorities/999999', json={'label': 'x'}, headers=admin_auth_headers,
        )
        assert res.status_code == 404

    def test_delete_unknown_404(self, client, admin_auth_headers):
        res = client.delete('/tickets/api/settings/priorities/999999', headers=admin_auth_headers)
        assert res.status_code == 404


class TestHoldReasonSettingsCrud:
    def test_requires_auth(self, client):
        res = client.get('/tickets/api/settings/hold-reasons')
        assert res.status_code in (401, 422)

    def test_create_missing_label(self, client, admin_auth_headers):
        res = client.post('/tickets/api/settings/hold-reasons', json={}, headers=admin_auth_headers)
        assert res.status_code == 400
        assert res.get_json()['success'] is False

    def test_create_update_delete_cycle(self, client, admin_auth_headers):
        label = f'{PFX} Hold Reason'
        created = client.post(
            '/tickets/api/settings/hold-reasons', json={'label': label}, headers=admin_auth_headers,
        )
        assert created.status_code == 201, created.get_json()
        row = created.get_json()['reason']
        rid = row['id']
        assert row['label'] == label
        assert row['is_active'] is True

        listed = client.get('/tickets/api/settings/hold-reasons', headers=admin_auth_headers)
        assert listed.status_code == 200
        assert any(r['id'] == rid for r in listed.get_json()['reasons'])

        upd = client.put(
            f'/tickets/api/settings/hold-reasons/{rid}',
            json={'label': f'{label} v2'},
            headers=admin_auth_headers,
        )
        assert upd.status_code == 200, upd.get_json()
        assert upd.get_json()['reason']['label'] == f'{label} v2'

        deleted = client.delete(f'/tickets/api/settings/hold-reasons/{rid}', headers=admin_auth_headers)
        assert deleted.status_code == 200
        assert deleted.get_json()['success'] is True

        listed2 = client.get('/tickets/api/settings/hold-reasons', headers=admin_auth_headers).get_json()['reasons']
        row2 = next(r for r in listed2 if r['id'] == rid)
        assert row2['is_active'] is False

    def test_duplicate_key_rejected(self, client, admin_auth_headers):
        label = f'{PFX} Dup Hold Reason'
        first = client.post('/tickets/api/settings/hold-reasons', json={'label': label}, headers=admin_auth_headers)
        assert first.status_code == 201, first.get_json()
        dupe = client.post('/tickets/api/settings/hold-reasons', json={'label': label}, headers=admin_auth_headers)
        assert dupe.status_code == 400
        assert dupe.get_json()['success'] is False

    def test_update_unknown_404(self, client, admin_auth_headers):
        res = client.put(
            '/tickets/api/settings/hold-reasons/999999', json={'label': 'x'}, headers=admin_auth_headers,
        )
        assert res.status_code == 404

    def test_delete_unknown_404(self, client, admin_auth_headers):
        res = client.delete('/tickets/api/settings/hold-reasons/999999', headers=admin_auth_headers)
        assert res.status_code == 404


class TestCancelReasonSettingsCrud:
    def test_requires_auth(self, client):
        res = client.get('/tickets/api/settings/cancel-reasons')
        assert res.status_code in (401, 422)

    def test_create_missing_label(self, client, admin_auth_headers):
        res = client.post('/tickets/api/settings/cancel-reasons', json={}, headers=admin_auth_headers)
        assert res.status_code == 400
        assert res.get_json()['success'] is False

    def test_create_update_delete_cycle(self, client, admin_auth_headers):
        label = f'{PFX} Cancel Reason'
        created = client.post(
            '/tickets/api/settings/cancel-reasons', json={'label': label}, headers=admin_auth_headers,
        )
        assert created.status_code == 201, created.get_json()
        row = created.get_json()['reason']
        rid = row['id']
        assert row['label'] == label
        assert row['is_active'] is True

        listed = client.get('/tickets/api/settings/cancel-reasons', headers=admin_auth_headers)
        assert listed.status_code == 200
        assert any(r['id'] == rid for r in listed.get_json()['reasons'])

        upd = client.put(
            f'/tickets/api/settings/cancel-reasons/{rid}',
            json={'label': f'{label} v2'},
            headers=admin_auth_headers,
        )
        assert upd.status_code == 200, upd.get_json()
        assert upd.get_json()['reason']['label'] == f'{label} v2'

        deleted = client.delete(f'/tickets/api/settings/cancel-reasons/{rid}', headers=admin_auth_headers)
        assert deleted.status_code == 200
        assert deleted.get_json()['success'] is True

        listed2 = client.get(
            '/tickets/api/settings/cancel-reasons', headers=admin_auth_headers,
        ).get_json()['reasons']
        row2 = next(r for r in listed2 if r['id'] == rid)
        assert row2['is_active'] is False

    def test_duplicate_key_rejected(self, client, admin_auth_headers):
        label = f'{PFX} Dup Cancel Reason'
        first = client.post(
            '/tickets/api/settings/cancel-reasons', json={'label': label}, headers=admin_auth_headers,
        )
        assert first.status_code == 201, first.get_json()
        dupe = client.post(
            '/tickets/api/settings/cancel-reasons', json={'label': label}, headers=admin_auth_headers,
        )
        assert dupe.status_code == 400
        assert dupe.get_json()['success'] is False

    def test_update_unknown_404(self, client, admin_auth_headers):
        res = client.put(
            '/tickets/api/settings/cancel-reasons/999999', json={'label': 'x'}, headers=admin_auth_headers,
        )
        assert res.status_code == 404

    def test_delete_unknown_404(self, client, admin_auth_headers):
        res = client.delete('/tickets/api/settings/cancel-reasons/999999', headers=admin_auth_headers)
        assert res.status_code == 404
