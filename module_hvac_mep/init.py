# module_hvac_mep package initializer
# Blueprint is defined in routes.py - no need to define it here
# Import routes when package is imported so blueprint gets registered
from . import routes  # noqa: F401

# Export the blueprint from routes for convenience
from .routes import hvac_mep_bp  # noqa: F401