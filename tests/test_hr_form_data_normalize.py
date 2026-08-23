from module_hr.form_data_normalize import (
    flatten_nested_form_data,
    normalize_hr_form_data_for_view,
)


def test_flatten_nested_form_data_merges_legacy_data_block():
    fd = flatten_nested_form_data({
        'form_type': 'leave_application',
        'data': {'employee_name': 'Smoke Test User', 'from_date': '2026-08-10'},
    })
    assert fd['form_type'] == 'leave_application'
    assert fd['employee_name'] == 'Smoke Test User'
    assert 'data' not in fd


def test_flatten_keeps_top_level_when_nested_missing():
    fd = flatten_nested_form_data({'employee_name': 'Ahmed Hassan'})
    assert fd == {'employee_name': 'Ahmed Hassan'}


def test_normalize_maps_smoke_leave_aliases():
    fd = normalize_hr_form_data_for_view(
        {
            'form_type': 'leave_application',
            'data': {
                'employee_name': 'Smoke Test User',
                'leave_type': 'Annual',
                'from_date': '2026-08-10',
                'to_date': '2026-08-12',
                'number_of_days': 3,
            },
        },
        'hr_leave_application',
    )
    assert fd['employee_name'] == 'Smoke Test User'
    assert fd['leave_type'] == 'annual'
    assert fd['first_day_of_leave'] == '2026-08-10'
    assert fd['last_day_of_leave'] == '2026-08-12'
    assert fd['total_days_requested'] == 3
