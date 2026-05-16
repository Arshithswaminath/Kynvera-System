# app/form_schemas.py
# Define the three form schemas (fields and basic validation metadata).
# Keys are the form_name used in URLs: 'hvac_mep', 'civil', 'cleanings'

FORM_SCHEMAS = {
    "hvac_mep": {
        "title": "HVAC & MEP Inspection",
        "description": "HVAC & MEP inspection form.",
        "fields": [
            {"name": "building_name", "label": "Building name", "type": "text", "required": True},
            {"name": "email", "label": "Contact email", "type": "email", "required": True},
            {"name": "unit_number", "label": "Unit / Room", "type": "text", "required": False},
            {"name": "system_type", "label": "System type", "type": "text", "required": False},
            {"name": "notes", "label": "Notes", "type": "textarea", "required": False}
        ],
        "allow_photos": True
    },
    "civil": {
        "title": "Civil Inspection",
        "description": "Civil site inspection and observations.",
        "fields": [
            {"name": "building_name", "label": "Building name", "type": "text", "required": True},
            {"name": "email", "label": "Contact email", "type": "email", "required": True},
            {"name": "location", "label": "Location on site", "type": "text", "required": False},
            {"name": "severity", "label": "Severity (Low/Med/High)", "type": "text", "required": False},
            {"name": "notes", "label": "Notes", "type": "textarea", "required": False}
        ],
        "allow_photos": True
    },
    "cleanings": {
        "title": "Cleaning / Housekeeping Check",
        "description": "Cleaning checklists and photos.",
        "fields": [
            {"name": "building_name", "label": "Building name", "type": "text", "required": True},
            {"name": "email", "label": "Contact email", "type": "email", "required": True},
            {"name": "area", "label": "Area / Zone", "type": "text", "required": False},
            {"name": "checklist", "label": "Checklist notes", "type": "textarea", "required": False}
        ],
        "allow_photos": True
    }
}