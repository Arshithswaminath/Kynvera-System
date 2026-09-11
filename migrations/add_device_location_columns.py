"""
Add building, latitude, and longitude to devices.

Run: python migrations/add_device_location_columns.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from module_devices.service import ensure_device_columns
from Injaaz import create_app


def migrate_up():
    app = create_app()
    ensure_device_columns(app)
    print('[OK] devices location/owner/comment columns ready')


if __name__ == '__main__':
    migrate_up()
