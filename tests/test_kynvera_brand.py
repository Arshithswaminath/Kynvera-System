"""Kynvera brand catalog and brand-kit PDF."""
from io import BytesIO

from pypdf import PdfReader

from common.kynvera_brand import (
    BRAND,
    BRAND_DIR,
    BRAND_KIT_FILENAME,
    BRAND_KIT_PATH,
    COLOR_SWATCHES,
    CORAL,
    LOGOS,
    existing_logos,
)
from common.kynvera_brand_kit import build_brand_kit_pdf
from common.kynvera_excel_brand import HEADER_FILL_HEX
from common.kynvera_pdf_brand import PRIMARY, WORDMARK_PATH


def _pdf_text(data: bytes) -> str:
    reader = PdfReader(BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


class TestBrandCatalog:
    def test_all_logo_files_exist(self):
        missing = [logo.key for logo in LOGOS if not logo.exists]
        assert missing == [], missing

    def test_brand_hex_matches_excel_and_pdf(self):
        from reportlab.lib.colors import HexColor

        assert BRAND.lower() == "#ff8e68"
        assert HEADER_FILL_HEX == "FF8E68"
        assert PRIMARY == HexColor("#ff8e68")

    def test_wordmark_path_is_png(self):
        assert WORDMARK_PATH.endswith("kynvera-wordmark.png")

    def test_brand_folder_holds_logos_and_pdf(self):
        import os

        assert os.path.isdir(BRAND_DIR)
        assert os.path.isfile(BRAND_KIT_PATH)
        names = {logo.filename for logo in LOGOS}
        names.add(BRAND_KIT_FILENAME)
        on_disk = set(os.listdir(BRAND_DIR))
        assert names <= on_disk, names - on_disk

    def test_color_swatches_include_core_tokens(self):
        hexes = {row[1].lower() for row in COLOR_SWATCHES}
        assert "#ff8e68" in hexes
        assert "#191b23" in hexes
        assert CORAL["950"] == "#5c1f05"


class TestBrandKitPdf:
    def test_pdf_lists_logos_and_colour_codes(self):
        data = build_brand_kit_pdf()
        assert data[:5] == b"%PDF-"
        text = _pdf_text(data).lower()
        assert "kynvera" in text
        assert "brand kit" in text
        assert "app mark" in text
        assert "wordmark" in text
        assert "reversed" in text
        assert "#ff8e68" in text
        assert "#191b23" in text
        assert "--color-brand" in text or "color-brand" in text
        reader = PdfReader(BytesIO(data))
        assert len(reader.pages) == 4
        assert existing_logos()


class TestBrandKitNotInFilesApp:
    def test_files_tree_omits_brand_kit_pdf(self, client, admin_auth_headers, monkeypatch):
        monkeypatch.setattr("module_files.drive_service.drive_enabled", lambda: False)
        monkeypatch.setattr("module_files.drive_service.drive_configured", lambda: False)
        monkeypatch.setattr("module_files.drive_service.get_connection", lambda: None)
        response = client.get("/files/api/tree", headers=admin_auth_headers)
        assert response.status_code == 200
        data = response.get_json()
        folders = data["folders"]
        items = data["items"]
        branding = next(f for f in folders if f["path_key"] == "branding")
        assert not any(i["filename"] == BRAND_KIT_FILENAME for i in items)
        logos = [i for i in items if i["folder_id"] == branding["id"] and i["filename"].endswith(".png")]
        assert len(logos) >= 6

    def test_previously_seeded_pdf_is_removed(self, app, client, admin_auth_headers, monkeypatch):
        monkeypatch.setattr("module_files.drive_service.drive_enabled", lambda: False)
        monkeypatch.setattr("module_files.drive_service.drive_configured", lambda: False)
        monkeypatch.setattr("module_files.drive_service.get_connection", lambda: None)
        from app.models import FilesFolder, FilesItem, db
        from module_files.service import BRAND_KIT_SOURCE_KIND, ensure_default_folders

        with app.app_context():
            folders = ensure_default_folders()
            branding = folders["branding"]
            db.session.add(FilesItem(
                folder_id=branding.id,
                name="Kynvera brand kit",
                filename=BRAND_KIT_FILENAME,
                mime_type="application/pdf",
                size_bytes=8,
                stored_path="missing-brand-kit.pdf",
                source_module="branding",
                source_kind=BRAND_KIT_SOURCE_KIND,
            ))
            db.session.commit()
            assert FilesItem.query.filter_by(source_kind=BRAND_KIT_SOURCE_KIND).count() == 1
            ensure_default_folders()
            assert FilesItem.query.filter_by(source_kind=BRAND_KIT_SOURCE_KIND).count() == 0

        response = client.get("/files/api/tree", headers=admin_auth_headers)
        assert response.status_code == 200
        assert not any(i["filename"] == BRAND_KIT_FILENAME for i in response.get_json()["items"])
