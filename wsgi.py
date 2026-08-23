# Resilient WSGI entrypoint for Gunicorn / Render.
# Tries several common module/attribute combinations and:
#  - If an attribute 'app' is found, uses it.
#  - If a 'create_app' factory is found, calls it (no args).
# If nothing is found it raises a clear RuntimeError so logs show what to fix.

import importlib
import traceback
import logging
import sys

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger("wsgi")

# Priority list: try the most likely module that holds your app first.
# Note: 'Injaaz' is the primary app module in this repository.
candidates = [
    ("Injaaz", "create_app"),
    ("Injaaz", "app"),
    ("wsgi", "app"),
    ("app", "create_app"),
    ("app", "app"),
    ("application", "app"),
    ("main", "app"),
    ("src.app", "create_app"),
    ("src.app", "app"),
    ("run", "app"),
]

app = None
errors = []

for module_name, attr in candidates:
    try:
        logger.info("Attempting to import %s and look for %s()", module_name, attr)
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

        # If it's the factory named create_app, call it (no args)
        if attr == "create_app" and callable(obj):
            try:
                logger.info("Calling factory %s.%s()", module_name, attr)
                maybe_app = obj()
                if maybe_app:
                    app = maybe_app
                    logger.info("Obtained WSGI app from %s.create_app()", module_name)
                    break
            except Exception as e:
                err = f"{module_name}.create_app() raised: {e}\n{traceback.format_exc()}"
                errors.append(err)
                logger.exception(err)
                continue

        else:
            # If attribute is an 'app' instance or callable app
            app = obj
            logger.info("Using attribute %s.%s as WSGI app", module_name, attr)
            break

    except Exception as e:
        err = f"Error while inspecting {module_name}.{attr}: {e}\n{traceback.format_exc()}"
        errors.append(err)
        logger.exception(err)
        continue

if app is None:
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

# Export 'app' for WSGI servers (gunicorn)
# At this point 'app' should be a WSGI callable (Flask app)
logger.info("WSGI app successfully located and exposed as 'app'.")