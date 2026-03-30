"""Unit tests for serializer_kit — no framework dependencies."""

import pytest

from iot_hub_shared.serializer_kit.base_serializer import BaseSerializer
from iot_hub_shared.serializer_kit.base_validator import BaseValidator
from iot_hub_shared.serializer_kit.json_serializer import JSONSerializer


# ---------------------------------------------------------------------------
# BaseSerializer
# ---------------------------------------------------------------------------

class ConcreteSerializer(BaseSerializer):
    """Minimal concrete implementation for testing the base class."""
    def _validate(self, data):
        if not isinstance(data, dict):
            self._errors['non_field_errors'] = 'Must be a dict.'
            return None
        return data


class TestBaseSerializer:
    def test_validated_data_raises_before_is_valid(self):
        s = ConcreteSerializer({'key': 'value'})
        with pytest.raises(ValueError, match='Call is_valid()'):
            _ = s.validated_data

    def test_is_valid_true_for_valid_data(self):
        s = ConcreteSerializer({'key': 'value'})
        assert s.is_valid() is True
        assert s.validated_data == {'key': 'value'}

    def test_is_valid_false_populates_errors(self):
        s = ConcreteSerializer('not-a-dict')
        assert s.is_valid() is False
        assert 'non_field_errors' in s.errors

    def test_errors_empty_before_is_valid(self):
        s = ConcreteSerializer({})
        assert s.errors == {}

    def test_is_valid_resets_errors_on_second_call(self):
        s = ConcreteSerializer('bad')
        s.is_valid()
        assert s.errors

        s.initial_data = {'ok': True}
        s.is_valid()
        assert s.errors == {}


# ---------------------------------------------------------------------------
# JSONSerializer
# ---------------------------------------------------------------------------

class StrictSerializer(JSONSerializer):
    REQUIRED_FIELDS = {'name': str, 'age': int}
    OPTIONAL_FIELDS = {'nickname': str}
    STRICT_SCHEMA = True


class LooseSerializer(JSONSerializer):
    REQUIRED_FIELDS = {'name': str}
    STRICT_SCHEMA = False


class CustomSerializer(JSONSerializer):
    REQUIRED_FIELDS = {'value': (int, float)}

    def _validate_fields(self, data):
        if data['value'] < 0:
            self._errors['value'] = 'Must be non-negative.'
            return None
        return {'value': data['value'] * 2}


class TestJSONSerializer:
    def test_valid_payload_is_accepted(self):
        s = StrictSerializer({'name': 'Alice', 'age': 30})
        assert s.is_valid() is True
        assert s.validated_data == {'name': 'Alice', 'age': 30}

    def test_non_dict_payload_rejected(self):
        s = StrictSerializer(['not', 'a', 'dict'])
        assert s.is_valid() is False
        assert 'non_field_errors' in s.errors

    def test_missing_required_field_rejected(self):
        s = StrictSerializer({'name': 'Alice'})
        assert s.is_valid() is False
        assert 'age' in s.errors

    def test_wrong_type_for_required_field_rejected(self):
        s = StrictSerializer({'name': 'Alice', 'age': 'thirty'})
        assert s.is_valid() is False
        assert 'age' in s.errors

    def test_optional_field_present_and_valid(self):
        s = StrictSerializer({'name': 'Alice', 'age': 30, 'nickname': 'Al'})
        assert s.is_valid() is True
        assert s.validated_data['nickname'] == 'Al'

    def test_optional_field_absent_is_accepted(self):
        s = StrictSerializer({'name': 'Alice', 'age': 30})
        assert s.is_valid() is True
        assert 'nickname' not in s.validated_data

    def test_optional_field_none_is_accepted(self):
        s = StrictSerializer({'name': 'Alice', 'age': 30, 'nickname': None})
        assert s.is_valid() is True

    def test_strict_schema_rejects_unknown_fields(self):
        s = StrictSerializer({'name': 'Alice', 'age': 30, 'extra': 'field'})
        assert s.is_valid() is False
        assert 'non_field_errors' in s.errors

    def test_loose_schema_allows_unknown_fields(self):
        s = LooseSerializer({'name': 'Alice', 'unknown': 'ok'})
        assert s.is_valid() is True

    def test_union_type_accepts_either(self):
        s = CustomSerializer({'value': 1})
        assert s.is_valid() is True
        s2 = CustomSerializer({'value': 1.5})
        assert s2.is_valid() is True

    def test_validate_fields_override_applied(self):
        s = CustomSerializer({'value': 4})
        assert s.is_valid() is True
        assert s.validated_data == {'value': 8}  # doubled

    def test_validate_fields_can_add_errors(self):
        s = CustomSerializer({'value': -1})
        assert s.is_valid() is False
        assert 'value' in s.errors


# ---------------------------------------------------------------------------
# BaseValidator
# ---------------------------------------------------------------------------

class ConcreteValidator(BaseValidator):
    def __init__(self, value):
        super().__init__()
        self._value = value

    def _validate_payload(self):
        if not isinstance(self._value, int):
            self._errors.append({'value': 'Must be an integer.'})


class TestBaseValidator:
    def test_returns_true_for_valid_payload(self):
        v = ConcreteValidator(42)
        result = v.validate()
        assert result is True

    def test_returns_false_for_invalid_payload(self):
        v = ConcreteValidator('bad')
        result = v.validate()
        assert result is False

    def test_errors_populated_on_failure(self):
        v = ConcreteValidator('bad')
        v.validate()
        assert len(v.errors) == 1
        assert 'value' in v.errors[0]

    def test_return_type_is_bool(self):
        v = ConcreteValidator(1)
        result = v.validate()
        assert isinstance(result, bool)
