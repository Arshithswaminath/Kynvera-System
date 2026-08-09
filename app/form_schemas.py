# app/form_schemas.py
# Unified inspection form schema (legacy keys kept as aliases).

_INSPECTION_SCHEMA = {
    "title": "Inspection",
    "description": "Site inspection form.",
    "fields": [
        {"name": "site_name", "label": "Site name", "type": "text", "required": True},
        {"name": "visit_date", "label": "Visit date", "type": "date", "required": True},
        {"name": "category", "label": "Category", "type": "text", "required": False},
        {"name": "notes", "label": "Notes", "type": "textarea", "required": False},
    ],
    "allow_photos": True,
}

FORM_SCHEMAS = {
    "inspection": _INSPECTION_SCHEMA,
    "hvac_mep": _INSPECTION_SCHEMA,
    "civil": _INSPECTION_SCHEMA,
    "cleaning": _INSPECTION_SCHEMA,
    "cleanings": _INSPECTION_SCHEMA,
}
