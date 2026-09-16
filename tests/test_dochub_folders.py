"""DocHub folder tree: merge of gunicorn-raced duplicates and unique sibling names."""
import pytest

from app.docs.folder_service import (
    create_folder,
    merge_duplicate_folders,
)
from app.models import DocHubDocument, DocHubFolder, db


def _folder(name, parent_id=None):
    row = DocHubFolder(name=name, parent_id=parent_id)
    db.session.add(row)
    db.session.flush()
    return row


def _doc(title, folder_id, category='Internal'):
    row = DocHubDocument(
        title=title,
        category=category,
        status='published',
        doc_type='content',
        content='<p>body</p>',
        folder_id=folder_id,
    )
    db.session.add(row)
    db.session.flush()
    return row


def _cleanup_named(name):
    rows = DocHubFolder.query.filter_by(name=name).all()
    for folder in rows:
        DocHubDocument.query.filter_by(folder_id=folder.id).delete()
        db.session.delete(folder)
    db.session.commit()


class TestMergeDuplicateFolders:
    def test_keeps_the_folder_that_has_documents(self, app):
        name = 'zz-dup-contracts'
        with app.app_context():
            _cleanup_named(name)
            empty = _folder(name)
            filled = _folder(name)
            doc = _doc('Service Agreement', filled.id, category=name)
            db.session.commit()
            empty_id, filled_id, doc_id = empty.id, filled.id, doc.id

            merged = merge_duplicate_folders()
            assert merged == 1

            remaining = DocHubFolder.query.filter_by(name=name).all()
            assert len(remaining) == 1
            assert remaining[0].id == filled_id
            assert db.session.get(DocHubFolder, empty_id) is None
            assert db.session.get(DocHubDocument, doc_id).folder_id == filled_id

            _cleanup_named(name)

    def test_collapses_empty_same_named_roots(self, app):
        name = 'zz-dup-uncategorized'
        with app.app_context():
            _cleanup_named(name)
            first = _folder(name)
            _folder(name)
            db.session.commit()
            first_id = first.id

            merged = merge_duplicate_folders()
            assert merged == 1
            remaining = DocHubFolder.query.filter_by(name=name).all()
            assert len(remaining) == 1
            assert remaining[0].id == first_id

            _cleanup_named(name)

    def test_is_idempotent_when_names_are_unique(self, app):
        with app.app_context():
            _cleanup_named('zz-dup-hr')
            _cleanup_named('zz-dup-manuals')
            a = _folder('zz-dup-hr')
            b = _folder('zz-dup-manuals')
            db.session.commit()
            assert merge_duplicate_folders() == 0
            assert merge_duplicate_folders() == 0
            db.session.delete(a)
            db.session.delete(b)
            db.session.commit()

    def test_rejects_creating_a_duplicate_sibling_name(self, app, admin_user):
        name = 'zz-dup-policies'
        with app.app_context():
            _cleanup_named(name)
            create_folder(name, None, admin_user.id)
            with pytest.raises(ValueError, match='already exists'):
                create_folder(name.upper(), None, admin_user.id)
            _cleanup_named(name)


class TestDocHubFoldersApi:
    def test_list_folders_after_merge_is_unique(self, app, client, admin_auth_headers):
        name = 'zz-dup-onboarding'
        with app.app_context():
            _cleanup_named(name)
            filled = _folder(name)
            _folder(name)
            _doc('Welcome pack', filled.id, category=name)
            db.session.commit()
            merge_duplicate_folders()

        resp = client.get('/api/docs/folders', headers=admin_auth_headers)
        assert resp.status_code == 200
        names = [f['name'] for f in resp.get_json()['folders'] if f['name'] == name]
        assert names == [name]

        with app.app_context():
            _cleanup_named(name)

    def test_dochub_page_ships_collection_skeletons(self, client):
        html = client.get('/dochub').get_data(as_text=True)
        assert 'dh-folder-card--skeleton' in html
        assert 'dh-editor-area--home' in html
        assert 'Browse your collections' in html
