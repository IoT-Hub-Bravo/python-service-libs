"""Unit tests for utils_kit — no Django, no external dependencies."""

import datetime

import pytest

from iot_hub_shared.utils_kit.dicts import diff_dicts, normalize_schema
from iot_hub_shared.utils_kit.json import is_json_serializable, json_equal
from iot_hub_shared.utils_kit.normalization import (
    normalize_str,
    parse_iso8601_utc,
    to_iso8601_utc,
)


# ---------------------------------------------------------------------------
# normalize_str
# ---------------------------------------------------------------------------

class TestNormalizeStr:
    def test_strips_whitespace(self):
        assert normalize_str('  hello  ') == 'hello'

    def test_blank_returns_none_by_default(self):
        assert normalize_str('   ') is None

    def test_empty_returns_none_by_default(self):
        assert normalize_str('') is None

    def test_allow_blank_preserves_empty_string(self):
        assert normalize_str('', allow_blank=True) == ''

    def test_allow_blank_preserves_whitespace_stripped(self):
        assert normalize_str('  ', allow_blank=True) == ''

    def test_normal_string_unchanged(self):
        assert normalize_str('hello') == 'hello'


# ---------------------------------------------------------------------------
# parse_iso8601_utc
# ---------------------------------------------------------------------------

class TestParseIso8601Utc:
    def test_parses_z_suffix(self):
        result = parse_iso8601_utc('2024-01-15T10:30:00Z')
        assert result is not None
        assert result.tzinfo == datetime.timezone.utc
        assert result.year == 2024
        assert result.microsecond == 0

    def test_parses_plus_offset(self):
        result = parse_iso8601_utc('2024-01-15T12:30:00+02:00')
        assert result is not None
        assert result.tzinfo == datetime.timezone.utc
        assert result.hour == 10  # converted to UTC

    def test_parses_naive_datetime_as_utc(self):
        result = parse_iso8601_utc('2024-01-15T10:30:00')
        assert result is not None
        assert result.tzinfo == datetime.timezone.utc

    def test_empty_string_returns_none(self):
        assert parse_iso8601_utc('') is None

    def test_whitespace_only_returns_none(self):
        assert parse_iso8601_utc('   ') is None

    def test_garbage_string_returns_none(self):
        assert parse_iso8601_utc('not-a-date') is None

    def test_strips_microseconds(self):
        result = parse_iso8601_utc('2024-01-15T10:30:00.123456Z')
        assert result is not None
        assert result.microsecond == 0


# ---------------------------------------------------------------------------
# to_iso8601_utc
# ---------------------------------------------------------------------------

class TestToIso8601Utc:
    def test_none_returns_none(self):
        assert to_iso8601_utc(None) is None

    def test_aware_datetime_formatted(self):
        dt = datetime.datetime(2024, 1, 15, 10, 30, tzinfo=datetime.timezone.utc)
        assert to_iso8601_utc(dt) == '2024-01-15T10:30:00+00:00'

    def test_naive_datetime_treated_as_utc(self):
        dt = datetime.datetime(2024, 1, 15, 10, 30)
        result = to_iso8601_utc(dt)
        assert '+00:00' in result

    def test_date_formatted(self):
        d = datetime.date(2024, 1, 15)
        assert to_iso8601_utc(d) == '2024-01-15'

    def test_time_formatted(self):
        t = datetime.time(10, 30, 0)
        assert to_iso8601_utc(t) == '10:30:00'

    def test_valid_string_round_trips(self):
        result = to_iso8601_utc('2024-01-15T10:30:00Z')
        assert result is not None
        assert '2024-01-15' in result

    def test_invalid_string_returns_none(self):
        # F-03 fix: must not raise AttributeError
        assert to_iso8601_utc('not-a-date') is None

    def test_unsupported_type_returns_none(self):
        assert to_iso8601_utc(42) is None


# ---------------------------------------------------------------------------
# is_json_serializable
# ---------------------------------------------------------------------------

class TestIsJsonSerializable:
    def test_dict_is_serializable(self):
        assert is_json_serializable({'key': 'value'}) is True

    def test_list_is_serializable(self):
        assert is_json_serializable([1, 2, 3]) is True

    def test_string_is_serializable(self):
        assert is_json_serializable('hello') is True

    def test_none_is_serializable(self):
        assert is_json_serializable(None) is True

    def test_set_is_not_serializable(self):
        assert is_json_serializable({1, 2, 3}) is False

    def test_custom_object_is_not_serializable(self):
        class Obj:
            pass
        assert is_json_serializable(Obj()) is False


# ---------------------------------------------------------------------------
# json_equal
# ---------------------------------------------------------------------------

class TestJsonEqual:
    def test_equal_dicts(self):
        assert json_equal({'a': 1, 'b': 2}, {'a': 1, 'b': 2}) is True

    def test_dicts_with_different_key_order_are_equal(self):
        assert json_equal({'b': 2, 'a': 1}, {'a': 1, 'b': 2}) is True

    def test_unequal_dicts(self):
        assert json_equal({'a': 1}, {'a': 2}) is False

    def test_equal_lists(self):
        assert json_equal([1, 2, 3], [1, 2, 3]) is True

    def test_unequal_lists(self):
        assert json_equal([1, 2], [1, 3]) is False

    def test_nested_equal_dicts(self):
        assert json_equal({'x': {'y': 1}}, {'x': {'y': 1}}) is True

    def test_nested_unequal_dicts(self):
        assert json_equal({'x': {'y': 1}}, {'x': {'y': 2}}) is False


# ---------------------------------------------------------------------------
# normalize_schema
# ---------------------------------------------------------------------------

class TestNormalizeSchema:
    def test_required_fields_are_copied(self):
        normalized, errors = normalize_schema({'a': 'x', 'b': 'y'}, required=['a', 'b'])
        assert normalized == {'a': 'x', 'b': 'y'}
        assert errors == {}

    def test_missing_required_field_adds_error(self):
        _, errors = normalize_schema({'a': 'x'}, required=['a', 'b'])
        assert 'b' in errors

    def test_optional_field_included_when_present(self):
        normalized, _ = normalize_schema({'a': 'x', 'b': 'y'}, required=['a'], optional=['b'])
        assert normalized['b'] == 'y'

    def test_optional_field_absent_is_not_included(self):
        normalized, _ = normalize_schema({'a': 'x'}, required=['a'], optional=['b'])
        assert 'b' not in normalized

    def test_strips_strings_by_default(self):
        normalized, _ = normalize_schema({'a': '  hello  '}, required=['a'])
        assert normalized['a'] == 'hello'

    def test_strip_strings_false_preserves_whitespace(self):
        normalized, _ = normalize_schema({'a': '  hello  '}, required=['a'], strip_strings=False)
        assert normalized['a'] == '  hello  '

    def test_optional_none_dropped_by_default(self):
        normalized, _ = normalize_schema({'a': 'x', 'b': None}, required=['a'], optional=['b'])
        assert 'b' not in normalized

    def test_optional_none_kept_when_drop_disabled(self):
        normalized, _ = normalize_schema(
            {'a': 'x', 'b': None}, required=['a'], optional=['b'], drop_optional_none=False
        )
        assert normalized['b'] is None

    def test_optional_blank_string_dropped_by_default(self):
        normalized, _ = normalize_schema({'a': 'x', 'b': ''}, required=['a'], optional=['b'])
        assert 'b' not in normalized


# ---------------------------------------------------------------------------
# diff_dicts
# ---------------------------------------------------------------------------

class TestDiffDicts:
    def test_no_changes(self):
        changed, before, after = diff_dicts({'a': 1, 'b': 2}, {'a': 1, 'b': 2})
        assert changed == []
        assert before == {}
        assert after == {}

    def test_scalar_change_detected(self):
        changed, before, after = diff_dicts({'a': 1}, {'a': 2})
        assert 'a' in changed
        assert before['a'] == 1
        assert after['a'] == 2

    def test_nested_dict_change_detected(self):
        changed, before, after = diff_dicts({'x': {'y': 1}}, {'x': {'y': 2}})
        assert 'x' in changed

    def test_nested_dict_no_change(self):
        changed, _, _ = diff_dicts({'x': {'y': 1}}, {'x': {'y': 1}})
        assert changed == []

    def test_list_change_detected(self):
        changed, _, _ = diff_dicts({'items': [1, 2]}, {'items': [1, 3]})
        assert 'items' in changed

    def test_list_no_change(self):
        changed, _, _ = diff_dicts({'items': [1, 2]}, {'items': [1, 2]})
        assert changed == []
