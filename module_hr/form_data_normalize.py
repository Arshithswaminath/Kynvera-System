"""Flatten nested HR form_data and map legacy field aliases for view/print/export."""

_EMPTY = (None, '', [], {})

_LEAVE_TYPE_ALIASES = {
    'annual': 'annual',
    'annual leave': 'annual',
    'sick': 'sick',
    'sick leave': 'sick',
    'ot_compensatory': 'ot_compensatory',
    'ot compensatory off': 'ot_compensatory',
    'unpaid': 'unpaid',
    'unpaid leave': 'unpaid',
    'compassionate': 'compassionate',
    'compassionate leave': 'compassionate',
    'study': 'study',
    'study leave': 'study',
    'examination': 'examination',
    'hajj': 'hajj',
    'hajj leave': 'hajj',
    'other': 'other',
}


def _is_empty(val) -> bool:
    return val in _EMPTY


def flatten_nested_form_data(form_data):
    """Merge legacy ``form_data.data`` into a flat dict. Top-level non-empty keys win."""
    if not isinstance(form_data, dict):
        return {}
    fd = dict(form_data)
    nested = fd.pop('data', None)
    if not isinstance(nested, dict):
        if nested is not None:
            fd['data'] = nested
        return fd
    out = dict(nested)
    for key, val in fd.items():
        if not _is_empty(val) or key not in out:
            out[key] = val
    return out


def apply_hr_view_aliases(form_data, module_type=None):
    """Map smoke-test / legacy leave keys onto the current form field names."""
    out = dict(form_data or {})
    form_type = str(module_type or out.get('form_type') or '').replace('hr_', '').strip().lower()
    leave_like = form_type in ('', 'leave', 'leave_application') or any(
        k in out for k in ('from_date', 'to_date', 'number_of_days')
    )
    if leave_like:
        if not _is_empty(out.get('from_date')) and _is_empty(out.get('first_day_of_leave')):
            out['first_day_of_leave'] = out['from_date']
        if not _is_empty(out.get('to_date')) and _is_empty(out.get('last_day_of_leave')):
            out['last_day_of_leave'] = out['to_date']
        if not _is_empty(out.get('number_of_days')) and _is_empty(out.get('total_days_requested')):
            out['total_days_requested'] = out['number_of_days']
        leave_type = out.get('leave_type')
        if isinstance(leave_type, str) and leave_type.strip():
            key = leave_type.strip().lower().replace('_', ' ').replace('-', ' ')
            mapped = _LEAVE_TYPE_ALIASES.get(key) or _LEAVE_TYPE_ALIASES.get(key.replace(' ', '_'))
            if mapped:
                out['leave_type'] = mapped
    return out


def normalize_hr_form_data_for_view(form_data, module_type=None):
    """Flatten nested ``data`` and apply view aliases for print, PDF, Word, and ?edit=."""
    return apply_hr_view_aliases(flatten_nested_form_data(form_data), module_type)
