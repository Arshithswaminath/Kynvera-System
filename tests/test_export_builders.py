"""Magic-byte checks for module PDF/Excel builders (no live server, no Cloudinary).

These catch export regressions in CI for inspection, QHSI, and MMR without
hitting job workers or network I/O.
"""
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MMR_FIXTURE = ROOT / 'tests' / 'fixtures' / 'mmr' / 'cafm_sample.xlsx'
PDF_MAGIC = b'%PDF'
XLSX_MAGIC = b'PK'


def test_inspection_builders_magic_bytes(tmp_path):
    from module_inspection.inspection_generators import create_excel_report, create_pdf_report

    sample = {
        'site_name': 'Builder Magic Site',
        'visit_date': date.today().isoformat(),
        'items': [{'asset': 'AHU-01', 'system': 'HVAC', 'description': 'Filter check'}],
    }
    pdf_path = create_pdf_report(sample, str(tmp_path))
    xls_path = create_excel_report(sample, str(tmp_path))
    assert Path(pdf_path).read_bytes()[:4] == PDF_MAGIC
    assert Path(xls_path).read_bytes()[:2] == XLSX_MAGIC


def test_qhsi_builders_magic_bytes(tmp_path):
    from module_qhsi.qhsi_generators import create_excel_report, create_pdf_report

    record = {
        'project_name': 'QHSI Builder Site',
        'visit_date': date.today().isoformat(),
        'department': 'hvac',
        'inspector_name': 'Test Inspector',
        'location': 'Marina',
        'summary': 'Magic-byte fixture.',
        'items': [
            {
                'area': 'AHU room',
                'equipment': 'AHU-01',
                'severity': 'Low',
                'description': 'OK',
                'photos': [],
            }
        ],
    }
    pdf_path = tmp_path / 'qhsi.pdf'
    xls_path = tmp_path / 'qhsi.xlsx'
    create_pdf_report(record, str(pdf_path))
    create_excel_report(record, str(xls_path))
    assert pdf_path.read_bytes()[:4] == PDF_MAGIC
    assert xls_path.read_bytes()[:2] == XLSX_MAGIC


def test_inspection_pdf_header_does_not_repeat_kynvera(tmp_path):
    """Wordmark already says Kynvera — running header must not print the name again."""
    from pypdf import PdfReader
    from module_inspection.inspection_generators import create_pdf_report

    sample = {
        'site_name': 'Injaaz',
        'visit_date': date.today().isoformat(),
        'items': [{
            'asset': 'Electronics',
            'system': 'PA System',
            'description': 'Speakers',
            'quantity': 1,
            'brand': 'TVS',
            'specification': 'Good one.',
            'comments': 'Testing.',
        }],
        'materials_required': [
            {'name': 'LED Tube 18W', 'brand': 'Philips', 'uom': 'PCS', 'quantity': 1, 'unit_price': 22},
        ],
        'user': {'full_name': 'System Administrator', 'designation': 'admin'},
    }
    pdf_path = create_pdf_report(sample, str(tmp_path))
    reader = PdfReader(pdf_path)
    text = '\n'.join((page.extract_text() or '') for page in reader.pages)
    assert 'INSPECTION REPORT' in text
    assert 'Injaaz' in text
    # Company name should not appear as extracted text next to the wordmark image.
    assert 'Kynvera' not in text
    assert len(reader.pages[0].images) >= 1

    assert MMR_FIXTURE.is_file(), f'MMR fixture missing: {MMR_FIXTURE}'
    assert MMR_FIXTURE.read_bytes()[:2] == XLSX_MAGIC

    from module_mmr.mmr_service import generate_report_excel, parse_excel

    df = parse_excel(str(MMR_FIXTURE))
    raw = generate_report_excel(df)
    assert raw[:2] == XLSX_MAGIC
    assert len(raw) > 100
