"""
One-time data-prep: turn the raw "Device List - Injaaz & Amaan.xlsx" (no header
row, fixed column order) into a properly-headered .xlsx that can be uploaded
through the Device Management "Import Excel" button.

Makes no database or network calls - it only reads the source spreadsheet and
writes a new file next to it.

Run: python prepare_device_import.py
"""
import pandas as pd

SOURCE = 'Device List - Injaaz & Amaan.xlsx'
OUTPUT = 'Device List - Injaaz & Amaan (import-ready).xlsx'

COMPANY_MAP = {
    'amaan system': 'Amaan Systems',
    'amaan systems': 'Amaan Systems',
    'injaaz': 'Injaaz',
    'inaaz dxb': 'Injaaz',
}

TYPE_MAP = {
    'ipad': 'Tablet',
}


def clean(value):
    if pd.isna(value):
        return ''
    return str(value).replace('\xa0', ' ').strip()


def normalize_company(value):
    cleaned = clean(value)
    return COMPANY_MAP.get(cleaned.lower(), cleaned)


def normalize_type(value):
    cleaned = clean(value)
    return TYPE_MAP.get(cleaned.lower(), cleaned)


def main():
    raw = pd.read_excel(SOURCE, sheet_name='Sheet1', header=None)

    out_rows = []
    for _, row in raw.iterrows():
        owner = clean(row[0])
        device_type = normalize_type(row[2])
        if not owner and not device_type:
            continue  # blank/junk row

        out_rows.append({
            'Owner': owner,
            'Company': normalize_company(row[1]),
            'Device Type': device_type or 'Laptop',
            'Serial / Asset Tag': clean(row[3]),
            'OS': clean(row[4]),
            'Comment': clean(row[5]),
            'Status': 'online',
            'Health': 100,
            'Assignment Date': '',
        })

    df = pd.DataFrame(out_rows)
    df.to_excel(OUTPUT, index=False)

    print(f"Wrote {len(df)} rows to '{OUTPUT}'")
    print("\nBy device type:")
    print(df['Device Type'].value_counts().to_string())
    print("\nBy company:")
    print(df['Company'].value_counts().to_string())


if __name__ == '__main__':
    main()
