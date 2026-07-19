#!/usr/bin/env python3
"""
Back-compat entry point for the full email trigger suite.

Prefer:
  python scripts/test_suite_all_emails.py
  python scripts/run_document_test_suites.py --email

Recipients default to arshith@injaaz.ae (CC: arshithinjaaz@gmail.com).
Override with EMAIL_TEST_TO / EMAIL_TEST_CC.
"""
from __future__ import annotations

import os
import sys

_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from test_suite_all_emails import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
