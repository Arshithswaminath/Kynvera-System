import os
import tempfile
from app.services.pdf_service import generate_visit_pdf

def test_generate_visit_pdf_creates_file():
    tmpdir = tempfile.mkdtemp()
    visit_info = {
        "building_name": "Test Building",
        "email": "tech@example.com",
        "building_address": "123 Test St"
    }
    items = [
        {"title": "Item 1", "description": "Desc 1", "image_urls": []},
        {"title": "Item 2", "description": "Desc 2", "image_urls": []}
    ]
    pdf_path, pdf_filename = generate_visit_pdf(visit_info, items, tmpdir, report_id="unittest")
    assert os.path.exists(pdf_path)
    assert pdf_filename.endswith(".pdf")
    assert os.path.getsize(pdf_path) > 0