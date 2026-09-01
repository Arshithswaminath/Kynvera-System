"""Unit tests for non-negative / finite ticket cost amount parsing."""
import math

from module_ticketing.routes import _parse_non_negative_float


def test_parse_non_negative_float_accepts_zero_and_positive():
    assert _parse_non_negative_float(0, 'hours') == (0.0, None)
    assert _parse_non_negative_float('2.5', 'hours') == (2.5, None)
    assert _parse_non_negative_float(10, 'unit_price') == (10.0, None)


def test_parse_non_negative_float_rejects_negative():
    value, err = _parse_non_negative_float(-1, 'hours')
    assert value is None
    assert 'cannot be negative' in err

    value, err = _parse_non_negative_float('-0.01', 'unit_price')
    assert value is None
    assert 'cannot be negative' in err


def test_parse_non_negative_float_rejects_non_finite():
    value, err = _parse_non_negative_float(float('nan'), 'hours')
    assert value is None
    assert 'finite' in err

    value, err = _parse_non_negative_float(math.inf, 'rate_per_hour')
    assert value is None
    assert 'finite' in err


def test_parse_non_negative_float_rejects_invalid_and_required_missing():
    value, err = _parse_non_negative_float('abc', 'quantity')
    assert value is None
    assert 'Invalid quantity' in err

    value, err = _parse_non_negative_float(None, 'hours')
    assert value is None
    assert 'required' in err


def test_parse_non_negative_float_optional_default():
    assert _parse_non_negative_float(
        None, 'rate_per_hour', required=False, default=None,
    ) == (None, None)
    assert _parse_non_negative_float(
        '', 'rate_per_hour', required=False, default=None,
    ) == (None, None)
    value, err = _parse_non_negative_float(
        -5, 'rate_per_hour', required=False, default=None,
    )
    assert value is None
    assert 'cannot be negative' in err
