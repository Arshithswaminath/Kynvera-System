# app/form_schemas.py
# Fire Systems inspection form schema (legacy form registry / forms dashboard).

FORM_SCHEMAS = {
    "hvac_mep": {
        "title": "Fire Systems Inspection",
        "description": "Fire systems inspection form (alarms, sprinklers, pumps, extinguishers, and related checks).",
        "fields": [
            {"name": "building_name", "label": "Building name", "type": "text", "required": True},
            {"name": "email", "label": "Contact email", "type": "email", "required": True},
            {"name": "unit_number", "label": "Unit / Room", "type": "text", "required": False},
            {"name": "system_type", "label": "System type", "type": "text", "required": False},
            {"name": "notes", "label": "Notes", "type": "textarea", "required": False}
        ],
        "allow_photos": True
    },
}
