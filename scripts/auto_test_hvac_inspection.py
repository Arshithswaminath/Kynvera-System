#!/usr/bin/env python3
"""
Auto Test: Generate HVAC inspection form Excel and PDF with sample data.
Run from project root: python scripts/auto_test_hvac_inspection.py
Output: test_output/inspection_forms_test/
"""
import os
import sys
from datetime import datetime

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

# Minimal 1x1 transparent PNG as base64 (for signatures)
SIG_PLACEHOLDER = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="


def _sample_photo(color=(70, 130, 180), size=(64, 64)):
    """Create a small placeholder image as data URI. color=(R,G,B), default steel blue."""
    try:
        from PIL import Image
        import io
        import base64
        img = Image.new("RGB", size, color=color)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        return f"data:image/png;base64,{b64}"
    except ImportError:
        return SIG_PLACEHOLDER


def _sample_photos():
    """Return list of sample photo dicts for items (url format expected by generators)."""
    # Steel blue, light gray, dark gray - visible placeholders
    uris = [
        _sample_photo((70, 130, 180)),   # steel blue
        _sample_photo((180, 180, 180)),  # light gray
    ]
    return [{"url": u} for u in uris]


def _date(days_offset=0):
    d = datetime.now()
    if days_offset:
        from datetime import timedelta
        d = d + timedelta(days=days_offset)
    return d.strftime("%Y-%m-%d")


def sample_hvac_data():
    """Sample HVAC form data matching hvac_generators expectations."""
    sample_photos = _sample_photos()
    return {
        "site_name": "Test Site - Ajman Tower",
        "site_address": "Sheikh Rashid Bin Saeed Street, Ajman",
        "visit_date": _date(),
        "tech_signature": SIG_PLACEHOLDER,
        "opman_signature": SIG_PLACEHOLDER,
        "items": [
            {
                "asset": "Chiller Unit 1",
                "system": "HVAC",
                "description": "Central chiller - 500 TR capacity",
                "quantity": "1",
                "brand": "Carrier",
                "specification": "Model 30XA-500",
                "comments": "Routine inspection. All readings normal.",
                "photos": sample_photos[:2],
            },
            {
                "asset": "AHU-12",
                "system": "HVAC",
                "description": "Air Handling Unit - Floor 12",
                "quantity": "1",
                "brand": "Trane",
                "specification": "15,000 CFM",
                "comments": "Filter replaced. Belt tension checked.",
                "photos": sample_photos,
            },
            {
                "asset": "Electrical Panel MDB-1",
                "system": "MEP",
                "description": "Main Distribution Board",
                "quantity": "1",
                "brand": "ABB",
                "specification": "800A",
                "comments": "Thermal scan completed. No hotspots detected.",
                "photos": sample_photos[:1],
            },
        ],
    }


def main():
    out_dir = os.path.join(PROJECT_ROOT, "test_output", "inspection_forms_test")
    os.makedirs(out_dir, exist_ok=True)
    print(f"Output directory: {out_dir}")

    data = sample_hvac_data()
    print("Sample data:")
    print(f"  Site: {data['site_name']}")
    print(f"  Visit date: {data['visit_date']}")
    print(f"  Items: {len(data['items'])}")

    # Import generators (must be done after chdir)
    from module_hvac_mep.hvac_generators import create_excel_report, create_pdf_report

    print("\nGenerating Excel...")
    excel_path = create_excel_report(data, out_dir)
    print(f"  Created: {os.path.basename(excel_path)}")

    print("\nGenerating PDF...")
    pdf_path = create_pdf_report(data, out_dir)
    print(f"  Created: {os.path.basename(pdf_path)}")

    print("\nHVAC inspection form test completed successfully.")
    print(f"Files saved to: {out_dir}")


if __name__ == "__main__":
    main()
