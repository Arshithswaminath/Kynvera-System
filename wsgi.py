# Resilient WSGI entrypoint for Gunicorn / Render.
# Tries several common module/attribute combinations and:
#  - If an attribute 'app' is found, uses it.
#  - If a 'create_app' factory is found, calls it (no args).
# If nothing is found it raises a clear RuntimeError so logs show what to fix.
#
# create_app() is deferred until the first request so gunicorn can bind
# 0.0.0.0:$PORT even when Render injects --preload. Otherwise a hung
# Postgres connect never opens a port and Render reports a port-scan timeout.

import importlib
import logging
import os
import sys
import traceback

logging.basicConfig(level=logging.INFO, stream=sys.stdout, force=True)
logger = logging.getLogger("wsgi")
print(
    "wsgi.py import (PORT=%s, FLASK_ENV=%s)"
    % (os.environ.get("PORT", "<unset>"), os.environ.get("FLASK_ENV", "<unset>")),
    flush=True,
)

# Priority list: try the most likely module that holds your app first.
# Note: 'Injaaz' is the primary app module in this repository.
candidates = [
    ("Injaaz", "create_app"),
    ("Injaaz", "app"),
    ("app", "create_app"),
    ("app", "app"),
    ("application", "app"),
    ("main", "app"),
    ("src.app", "create_app"),
    ("src.app", "app"),
    ("run", "app"),
]


def _load_flask_app():
    errors = []
    for module_name, attr in candidates:
        try:
            logger.info("Attempting to import %s and look for %s()", module_name, attr)
            sys.stdout.flush()
            mod = importlib.import_module(module_name)
        except Exception as e:
            err = f"import {module_name} failed: {e}\n{traceback.format_exc()}"
            errors.append(err)
            logger.debug(err)
            continue

        try:
            if not hasattr(mod, attr):
                logger.info("Module %s does not have attribute %s", module_name, attr)
                continue

            obj = getattr(mod, attr)

            if attr == "create_app" and callable(obj):
                try:
                    logger.info("Calling factory %s.%s()", module_name, attr)
                    sys.stdout.flush()
                    maybe_app = obj()
                    if maybe_app:
                        logger.info("Obtained WSGI app from %s.create_app()", module_name)
                        sys.stdout.flush()
                        return maybe_app
                except Exception as e:
                    err = f"{module_name}.create_app() raised: {e}\n{traceback.format_exc()}"
                    errors.append(err)
                    logger.exception(err)
                    continue
            else:
                logger.info("Using attribute %s.%s as WSGI app", module_name, attr)
                return obj

        except Exception as e:
            err = f"Error while inspecting {module_name}.{attr}: {e}\n{traceback.format_exc()}"
            errors.append(err)
            logger.exception(err)
            continue

    msg_lines = [
        "Could not locate a Flask WSGI 'app' instance or a 'create_app' factory in any of the checked modules.",
        "Checked candidates (module, attribute):",
        *[f"  - {m}.{a}" for m, a in candidates],
        "",
        "Import errors and tracebacks (if any):",
        *errors,
        "",
        "Please ensure your Flask app exposes one of the following examples:",
        "  - Injaaz.py: def create_app(): return Flask(...)  (preferred for this repo)",
        "  - Injaaz.py: app = Flask(__name__)",
        "",
        "Common fixes:",
        "  - Ensure package/folder names are valid Python identifiers (no hyphens).",
        "  - Ensure each module directory contains an __init__.py if it is intended as a package.",
        "  - If using Gunicorn, point it at this module (gunicorn wsgi:app).",
    ]
    full_msg = "\n".join(msg_lines)
    logger.error(full_msg)
    raise RuntimeError(full_msg)


class _DeferredApp:
    """WSGI callable that constructs Flask only when a request arrives."""

    def __init__(self):
        self._app = None

    def _ensure(self):
        if self._app is None:
            self._app = _load_flask_app()
        return self._app

    def __call__(self, environ, start_response):
        return self._ensure()(environ, start_response)

    def __getattr__(self, name):
        return getattr(self._ensure(), name)


app = _DeferredApp()
logger.info("WSGI deferred wrapper ready (Flask loads on first request).")
sys.stdout.flush()
