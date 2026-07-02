"""Load unified QHSA inspection catalogs (HVAC, Civil, Cleaning)."""
import json
import os

BLUEPRINT_DIR = os.path.dirname(os.path.abspath(__file__))

_DEPARTMENT_LABELS = {
    'hvac': 'HVAC & MEP',
    'civil': 'Civil Works',
    'cleaning': 'Cleaning Services',
}

_STAFF_KIT_TYPES = [
    {'id': 'uniform_shirt', 'label': 'Uniform — Shirt / Top'},
    {'id': 'uniform_trouser', 'label': 'Uniform — Trousers'},
    {'id': 'uniform_coverall', 'label': 'Coverall / Overall'},
    {'id': 'safety_shoes', 'label': 'Safety Shoes / Boots'},
    {'id': 'helmet', 'label': 'Safety Helmet / Hard Hat'},
    {'id': 'hi_vis_vest', 'label': 'Hi-Vis Vest / Jacket'},
    {'id': 'gloves', 'label': 'Protective Gloves'},
    {'id': 'goggles', 'label': 'Safety Goggles'},
    {'id': 'ear_protection', 'label': 'Ear Protection'},
    {'id': 'id_badge', 'label': 'ID Badge / Access Card'},
    {'id': 'ppe_other', 'label': 'Other PPE / Company Issue'},
]


def staff_kit_types():
    return list(_STAFF_KIT_TYPES)


def department_labels():
    return dict(_DEPARTMENT_LABELS)


def _load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_hvac_catalog():
    """HVAC hierarchy: trade → system → equipment (from module_hvac_mep)."""
    hvac_path = os.path.join(
        os.path.dirname(BLUEPRINT_DIR),
        'module_hvac_mep',
        'dropdown_data.json',
    )
    return _load_json(hvac_path)


def load_local_inspection_catalog():
    return _load_json(os.path.join(BLUEPRINT_DIR, 'inspection_catalog.json'))


def build_unified_inspection_catalog():
    """
    Returns {
      departments: [{id, label}],
      catalogs: { hvac: {...}, civil: {...}, cleaning: {...} }
    }
    """
    local = load_local_inspection_catalog()
    return {
        'departments': [
            {'id': 'hvac', 'label': _DEPARTMENT_LABELS['hvac']},
            {'id': 'civil', 'label': _DEPARTMENT_LABELS['civil']},
            {'id': 'cleaning', 'label': _DEPARTMENT_LABELS['cleaning']},
        ],
        'catalogs': {
            'hvac': load_hvac_catalog(),
            'civil': local.get('civil', {}),
            'cleaning': local.get('cleaning', {}),
        },
    }
