#!/usr/bin/env python3
"""
Run the three document test suites:

  1. All PDFs with test data
  2. All Excel sheets with test data
  3. All email triggers → Arshith (arshith@injaaz.ae)

Usage (from project root):
  python scripts/run_document_test_suites.py              # PDF + Excel (offline)
  python scripts/run_document_test_suites.py --all        # PDF + Excel + Email
  python scripts/run_document_test_suites.py --pdf
  python scripts/run_document_test_suites.py --excel
  python scripts/run_document_test_suites.py --email

Email recipients (optional):
  EMAIL_TEST_TO=arshith@injaaz.ae EMAIL_TEST_CC=arshithinjaaz@gmail.com \\
    python scripts/run_document_test_suites.py --email
"""
from __future__ import annotations

import argparse
import os
import sys

_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

ROOT = os.path.dirname(_SCRIPTS)
os.chdir(ROOT)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main() -> int:
    p = argparse.ArgumentParser(description="Run Amaan document test suites")
    p.add_argument("--pdf", action="store_true", help="Run PDF suite only")
    p.add_argument("--excel", action="store_true", help="Run Excel suite only")
    p.add_argument("--email", action="store_true", help="Run email suite only")
    p.add_argument(
        "--all",
        action="store_true",
        help="Run PDF + Excel + Email (email needs mail credentials)",
    )
    args = p.parse_args()

    any_flag = args.pdf or args.excel or args.email or args.all
    if not any_flag:
        # Default: offline suites only (email needs live mail credentials)
        run_pdf, run_excel, run_email = True, True, False
    elif args.all:
        run_pdf, run_excel, run_email = True, True, True
    else:
        run_pdf, run_excel, run_email = args.pdf, args.excel, args.email

    codes = []
    print("\n" + "=" * 70)
    print("  Amaan document test suites")
    print("=" * 70)

    if run_pdf:
        import test_suite_all_pdfs as pdf_suite
        codes.append(("PDF", pdf_suite.main()))

    if run_excel:
        import test_suite_all_excels as excel_suite
        codes.append(("Excel", excel_suite.main()))

    if run_email:
        import test_suite_all_emails as email_suite
        codes.append(("Email", email_suite.main()))

    print("\n" + "=" * 70)
    print("  Overall")
    print("=" * 70)
    for name, code in codes:
        status = "PASS" if code == 0 else "FAIL"
        print(f"  {name:8s}  {status}")
    print()
    return 0 if all(c == 0 for _, c in codes) else 1


if __name__ == "__main__":
    sys.exit(main())
