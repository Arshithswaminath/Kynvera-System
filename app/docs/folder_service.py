"""
DocHub folder tree service — create/rename/delete folders, move/copy documents.

Mirrors the module_files folder-service pattern (module_files/service.py) but as
its own table (dochub_folders), since DocHub is a separate document library with
different semantics than the Drive-synced Files module.
"""
import os
import uuid

from app.models import DocHubDocument, DocHubFolder, db
from common.datetime_utils import utc_now_naive


UNCATEGORIZED_NAME = 'Uncategorized'


def sync_category_from_folder(doc):
    """Keep the legacy `category` string in sync with the document's current folder name.

    Several other modules (assistant search/RAG citations, the Files export, tests)
    still read `category` directly — this keeps them working without changes by
    treating `category` as derived from `folder_id` rather than independently set.
    """
    if doc.folder_id:
        folder = db.session.get(DocHubFolder, doc.folder_id)
        doc.category = folder.name if folder else UNCATEGORIZED_NAME
    else:
        doc.category = UNCATEGORIZED_NAME


def _sibling_name_key(name):
    return (name or '').strip().lower()


def find_sibling_folder(name, parent_id):
    """Return an existing folder with the same name under the same parent (case-insensitive)."""
    want = _sibling_name_key(name)
    if not want:
        return None
    for folder in DocHubFolder.query.filter_by(parent_id=parent_id).all():
        if _sibling_name_key(folder.name) == want:
            return folder
    return None


def get_or_create_default_folder(name='Internal'):
    """Lazily resolve (or create) a top-level folder, used as the fallback destination
    when a create/upload request doesn't specify a folder_id."""
    folder = find_sibling_folder(name, None)
    if not folder:
        folder = DocHubFolder(name=name)
        db.session.add(folder)
        db.session.flush()
    return folder


def create_folder(name, parent_id, created_by):
    name = (name or '').strip()
    if not name:
        raise ValueError('Folder name is required')
    if parent_id is not None:
        parent = db.session.get(DocHubFolder, parent_id)
        if not parent:
            raise ValueError('Parent folder not found')
    if find_sibling_folder(name, parent_id):
        raise ValueError('A folder with this name already exists here')
    folder = DocHubFolder(name=name, parent_id=parent_id, created_by=created_by)
    db.session.add(folder)
    db.session.commit()
    return folder


def merge_duplicate_folders():
    """Collapse same-named siblings left by the multi-worker category backfill.

    Gunicorn workers each ran the one-time backfill against an empty
    `dochub_folders` table, so live ended up with two root folders per
    category — one holding the documents, one empty. Reassign documents and
    children onto the keeper, then delete the extras. Idempotent.
    """
    merged = 0
    for _ in range(8):
        folders = DocHubFolder.query.order_by(DocHubFolder.id.asc()).all()
        groups = {}
        for folder in folders:
            key = (folder.parent_id, _sibling_name_key(folder.name))
            groups.setdefault(key, []).append(folder)

        pass_merged = 0
        for group in groups.values():
            if len(group) < 2:
                continue
            scored = sorted(
                group,
                key=lambda f: (
                    -DocHubDocument.query.filter_by(folder_id=f.id).count(),
                    f.id,
                ),
            )
            keeper = scored[0]
            for dup in scored[1:]:
                DocHubDocument.query.filter_by(folder_id=dup.id).update(
                    {'folder_id': keeper.id, 'category': keeper.name},
                    synchronize_session=False,
                )
                DocHubFolder.query.filter_by(parent_id=dup.id).update(
                    {'parent_id': keeper.id},
                    synchronize_session=False,
                )
                db.session.delete(dup)
                pass_merged += 1

        if not pass_merged:
            break
        db.session.commit()
        merged += pass_merged

    return merged


def _collect_folder_ids(folder_id):
    """Return folder_id and all descendant folder ids (depth-first)."""
    ids = [folder_id]
    kids = DocHubFolder.query.filter_by(parent_id=folder_id).all()
    for kid in kids:
        ids.extend(_collect_folder_ids(kid.id))
    return ids


def rename_folder(folder_id, name=None, parent_id=None):
    """Rename and/or re-parent a folder. Bulk-syncs `category` on contained documents
    when the name changes, so search/exports keep reflecting the current folder label."""
    folder = db.session.get(DocHubFolder, folder_id)
    if not folder:
        raise ValueError('Folder not found')

    if parent_id is not None:
        if parent_id == folder_id:
            raise ValueError('A folder cannot be its own parent')
        descendant_ids = set(_collect_folder_ids(folder_id))
        if parent_id in descendant_ids:
            raise ValueError('Cannot move a folder into its own subfolder')
        new_parent = db.session.get(DocHubFolder, parent_id)
        if not new_parent:
            raise ValueError('Parent folder not found')
        folder.parent_id = parent_id

    if name is not None:
        name = name.strip()
        if not name:
            raise ValueError('Folder name is required')
        folder.name = name
        DocHubDocument.query.filter_by(folder_id=folder_id).update(
            {'category': name}, synchronize_session=False
        )

    clash = find_sibling_folder(folder.name, folder.parent_id)
    if clash and clash.id != folder.id:
        db.session.rollback()
        raise ValueError('A folder with this name already exists here')

    folder.updated_at = utc_now_naive()
    db.session.commit()
    return folder


def count_documents_in_folders(folder_ids):
    return DocHubDocument.query.filter(
        DocHubDocument.folder_id.in_(folder_ids),
        db.or_(DocHubDocument.inline_asset.is_(False), DocHubDocument.inline_asset.is_(None)),
    ).count()


def delete_folder(folder_id, reassign=False):
    folder = db.session.get(DocHubFolder, folder_id)
    if not folder:
        raise ValueError('Folder not found')

    folder_ids = _collect_folder_ids(folder_id)
    doc_count = count_documents_in_folders(folder_ids)

    if doc_count > 0:
        if not reassign:
            return {'needs_confirmation': True, 'doc_count': doc_count}
        target_folder = folder.parent_id
        if target_folder is None:
            target_folder = get_or_create_default_folder(UNCATEGORIZED_NAME).id
        docs = DocHubDocument.query.filter(DocHubDocument.folder_id.in_(folder_ids)).all()
        for doc in docs:
            doc.folder_id = target_folder
            sync_category_from_folder(doc)

    for fid in reversed(folder_ids):
        f = db.session.get(DocHubFolder, fid)
        if f:
            db.session.delete(f)
    db.session.commit()
    return {'needs_confirmation': False, 'deleted_folder_ids': folder_ids, 'reassigned_count': doc_count}


def move_document(doc, folder_id):
    if folder_id is not None:
        target = db.session.get(DocHubFolder, folder_id)
        if not target:
            raise ValueError('Target folder not found')
    doc.folder_id = folder_id
    sync_category_from_folder(doc)
    doc.updated_at = utc_now_naive()
    db.session.commit()
    return doc


def _duplicate_stored_file(doc, generated_root):
    """Physically duplicate the file backing an uploaded document so the copy is a
    fully independent row — deleting either the original or the copy later must not
    break the other (delete_document hard-removes the local file with no reference
    counting, and pushes a fresh Cloudinary asset rather than reusing the same URL)."""
    from app.docs.routes import _is_remote_stored_path, _download_url_to_temp

    if not doc.stored_path:
        return doc.stored_path

    if _is_remote_stored_path(doc.stored_path):
        from app.services.cloudinary_service import upload_dochub_file

        ext = os.path.splitext(doc.filename or '')[1] or ''
        tmp_path = _download_url_to_temp(doc.stored_path, ext)
        try:
            url = upload_dochub_file(tmp_path, f'doc_copy_{uuid.uuid4().hex[:10]}')
            if not url:
                raise RuntimeError('Cloudinary re-upload failed for copied document')
            return url
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    if not os.path.isfile(doc.stored_path):
        raise FileNotFoundError(f'Source file missing on disk: {doc.stored_path}')
    dochub_dir = os.path.join(generated_root, 'dochub')
    os.makedirs(dochub_dir, exist_ok=True)
    new_name = f"{uuid.uuid4().hex[:12]}_{doc.filename or 'file'}"
    new_path = os.path.join(dochub_dir, new_name)
    import shutil
    shutil.copyfile(doc.stored_path, new_path)
    return new_path


def copy_document(doc, folder_id, user, generated_root):
    if doc.inline_asset:
        raise ValueError('Cannot copy an internal reference file')

    target_folder_id = folder_id if folder_id is not None else doc.folder_id

    new_doc = DocHubDocument(
        title=(f'{doc.title} (copy)')[:255],
        filename=doc.filename,
        stored_path=doc.stored_path,
        file_type=doc.file_type,
        doc_type=doc.doc_type,
        content=doc.content,
        reference_attachments=doc.reference_attachments,
        status=doc.status,
        size_bytes=doc.size_bytes,
        is_starred=False,
        author_id=user.id if user else None,
        folder_id=target_folder_id,
    )

    if doc.doc_type == 'upload' and doc.stored_path:
        new_doc.stored_path = _duplicate_stored_file(doc, generated_root)
        if not new_doc.stored_path.startswith(('http://', 'https://')) and os.path.isfile(new_doc.stored_path):
            new_doc.size_bytes = os.path.getsize(new_doc.stored_path)

    sync_category_from_folder(new_doc)
    db.session.add(new_doc)
    db.session.commit()
    return new_doc
