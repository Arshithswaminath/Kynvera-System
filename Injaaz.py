"""Compatibility shim — application entrypoint is kynver.py.

Prefer:  flask --app kynver:create_app
         from kynver import create_app
"""
from kynver import create_app

__all__ = ['create_app']
