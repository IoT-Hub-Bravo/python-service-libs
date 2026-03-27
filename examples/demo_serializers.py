"""
examples/demo_serializers.py
==============================
Tutorial: Building a validated input serializer with JSONSerializer.

This script shows how a downstream microservice defines its own request
payload serializers using the library's base classes. The pattern is
intentionally similar to Django REST Framework's Serializer, but with
zero framework coupling — the same classes work in FastAPI, plain Django
views, Celery tasks, or CLI scripts.

Three classes are demonstrated:
  1. StrictDeviceSerializer  — required + optional fields, rejects unknowns
  2. FlexibleReadingSerializer — required only, allows extra fields through
  3. RangeValidator          — BaseValidator subclass for domain-level rules

Run:
    python examples/demo_serializers.py
"""

from iot_hub_shared.serializer_kit.base_validator import BaseValidator
from iot_hub_shared.serializer_kit.json_serializer import JSONSerializer

# ---------------------------------------------------------------------------
# Step 1 — Define a strict serializer (e.g. for a POST /devices endpoint)
# ---------------------------------------------------------------------------
# REQUIRED_FIELDS : {field_name: expected_type_or_tuple_of_types}
#   — missing field      → validation error
#   — wrong type         → validation error
#   — None value         → validation error (None is not an instance of str/int)
#
# OPTIONAL_FIELDS : {field_name: expected_type}
#   — absent field       → silently omitted from validated_data
#   — None value         → silently omitted from validated_data (pass-through)
#   — present + correct  → included in validated_data
#
# STRICT_SCHEMA = True
#   — any key not in REQUIRED_FIELDS or OPTIONAL_FIELDS → validation error
#   — protects against accidental field name typos from callers

class StrictDeviceSerializer(JSONSerializer):
    REQUIRED_FIELDS = {
        'name': str,
        'type': str,
        'firmware_version': str,
    }
    OPTIONAL_FIELDS = {
        'description': str,
        'location': str,
    }
    STRICT_SCHEMA = True


print("=== StrictDeviceSerializer ===\n")

# --- Valid payload ---
valid_payload = {
    'name': 'sensor-north',
    'type': 'temperature',
    'firmware_version': '2.1.0',
    'description': 'Outdoor sensor, north wall',
}
s = StrictDeviceSerializer(valid_payload)
print("Valid payload:")
print(f"  is_valid()      = {s.is_valid()}")
print(f"  validated_data  = {s.validated_data}")

# --- Missing required field ---
s2 = StrictDeviceSerializer({'name': 'sensor-south', 'type': 'humidity'})
print("\nMissing 'firmware_version':")
print(f"  is_valid()  = {s2.is_valid()}")
print(f"  errors      = {s2.errors}")

# --- Wrong type ---
s3 = StrictDeviceSerializer({'name': 'sensor-east', 'type': 'pressure', 'firmware_version': 3})
print("\nWrong type for 'firmware_version' (int instead of str):")
print(f"  is_valid()  = {s3.is_valid()}")
print(f"  errors      = {s3.errors}")

# --- Unknown field (strict schema) ---
s4 = StrictDeviceSerializer({
    'name': 'sensor-west',
    'type': 'humidity',
    'firmware_version': '1.0.0',
    'secret_field': 'i-should-not-be-here',
})
print("\nUnknown field with STRICT_SCHEMA=True:")
print(f"  is_valid()  = {s4.is_valid()}")
print(f"  errors      = {s4.errors}")

# --- Optional field absent (should be silently ignored) ---
s5 = StrictDeviceSerializer({
    'name': 'sensor-roof',
    'type': 'co2',
    'firmware_version': '3.0.0',
})
print("\nOptional 'description' absent:")
print(f"  is_valid()       = {s5.is_valid()}")
print(f"  validated_data   = {s5.validated_data}")
assert 'description' not in s5.validated_data

# ---------------------------------------------------------------------------
# Step 2 — Define a flexible serializer (e.g. for reading telemetry payloads)
# ---------------------------------------------------------------------------
# STRICT_SCHEMA = False allows extra keys through validated_data untouched.
# Useful when you control only a subset of a third-party payload's fields.

class FlexibleReadingSerializer(JSONSerializer):
    REQUIRED_FIELDS = {
        'device_id': str,
        'value': (int, float),   # accepts either numeric type
        'unit': str,
    }
    STRICT_SCHEMA = False        # extra keys are allowed through


print("\n\n=== FlexibleReadingSerializer ===\n")

reading_payload = {
    'device_id': 'dev-42',
    'value': 23.7,
    'unit': 'celsius',
    'raw_bytes': 'AA FF 23',    # extra field — allowed through
    'timestamp': 1717228800,    # extra field — allowed through
}
sr = FlexibleReadingSerializer(reading_payload)
print("Payload with extra fields (STRICT_SCHEMA=False):")
print(f"  is_valid()      = {sr.is_valid()}")
print(f"  validated_data  = {sr.validated_data}")

# Union type: int and float both accepted
sr2 = FlexibleReadingSerializer({'device_id': 'dev-99', 'value': 100, 'unit': 'percent'})
sr3 = FlexibleReadingSerializer({'device_id': 'dev-99', 'value': 99.5, 'unit': 'percent'})
print(f"\nint value   is_valid() = {sr2.is_valid()}")
print(f"float value is_valid() = {sr3.is_valid()}")

# ---------------------------------------------------------------------------
# Step 3 — Override _validate_fields for domain-level rules
# ---------------------------------------------------------------------------
# After type-checking, JSONSerializer calls self._validate_fields(data).
# Override it to add business rules (e.g. value ranges, cross-field checks).

class BoundedReadingSerializer(FlexibleReadingSerializer):
    def _validate_fields(self, data):
        if not (-50 <= data['value'] <= 150):
            self._errors['value'] = 'Sensor value out of physical range (-50 to 150).'
            return None
        return data


print("\n\n=== BoundedReadingSerializer (custom _validate_fields) ===\n")

sr4 = BoundedReadingSerializer({'device_id': 'dev-1', 'value': 23.7, 'unit': 'celsius'})
print(f"In-range value   is_valid() = {sr4.is_valid()}")

sr5 = BoundedReadingSerializer({'device_id': 'dev-1', 'value': 999, 'unit': 'celsius'})
print(f"Out-of-range 999 is_valid() = {sr5.is_valid()}")
print(f"                 errors     = {sr5.errors}")

# ---------------------------------------------------------------------------
# Step 4 — BaseValidator for standalone validation (no serialization)
# ---------------------------------------------------------------------------
# Use BaseValidator when you want a validate() -> bool pattern without
# the serialiser machinery (e.g. validating a dict that already came from
# your own trusted internal code, but you still want structured error list).

class DeviceNameValidator(BaseValidator):
    MAX_LENGTH = 64
    ALLOWED_CHARS = set('abcdefghijklmnopqrstuvwxyz0123456789-_')

    def __init__(self, name: str):
        super().__init__()
        self._name = name

    def _validate_payload(self):
        if not self._name:
            self._errors.append({'name': 'Device name must not be empty.'})
            return
        if len(self._name) > self.MAX_LENGTH:
            self._errors.append({'name': f'Name too long (max {self.MAX_LENGTH} chars).'})
        invalid = set(self._name.lower()) - self.ALLOWED_CHARS
        if invalid:
            self._errors.append({'name': f'Invalid characters: {sorted(invalid)}'})


print("\n\n=== DeviceNameValidator ===\n")

v1 = DeviceNameValidator('sensor-north-01')
print(f"'sensor-north-01'  valid={v1.validate()}, errors={v1.errors}")

v2 = DeviceNameValidator('Sensor With Spaces!')
print(f"'Sensor With Spaces!'  valid={v2.validate()}, errors={v2.errors}")

v3 = DeviceNameValidator('')
print(f"''  valid={v3.validate()}, errors={v3.errors}")

# validate() always returns a plain bool (not a truthy object)
assert isinstance(v1.validate(), bool)
assert isinstance(v2.validate(), bool)

print("\n\033[92mDemo completed successfully.\033[0m")
