"""
examples/demo_utils.py
========================
Tutorial: Generic utility functions from utils_kit.

utils_kit contains four categories of pure-Python helpers that have no
framework coupling and can be used anywhere — Django views, FastAPI
handlers, Celery tasks, or standalone scripts.

  - normalization.normalize_str   : strip + blank-guard strings
  - normalization.to_iso8601_utc  : convert any date/time value to an ISO 8601 string
  - normalization.parse_iso8601_utc: parse any ISO 8601 string → UTC datetime
  - dicts.normalize_schema        : extract + type-coerce fields from an incoming dict
  - dicts.diff_dicts              : find which keys changed between two snapshots

Run:
    python examples/demo_utils.py
"""

import datetime

# ---------------------------------------------------------------------------
# normalize_str
# ---------------------------------------------------------------------------
# The most common utility: strip surrounding whitespace and treat blank
# strings as absent (returns None) unless you explicitly opt in.

from iot_hub_shared.utils_kit.normalization import normalize_str

print("=== normalize_str ===\n")

# Typical use: clean an incoming form/API field before storing it
print(repr(normalize_str('  sensor-north  ')))  # 'sensor-north'
print(repr(normalize_str('')))                   # None  — blank treated as absent
print(repr(normalize_str('   ')))                # None  — whitespace-only also absent

# allow_blank=True: keep empty string when an explicit empty value is meaningful
print(repr(normalize_str('', allow_blank=True)))  # ''
print(repr(normalize_str('   ', allow_blank=True)))  # ''  (still stripped)

assert normalize_str('  hello  ') == 'hello'
assert normalize_str('') is None
assert normalize_str('', allow_blank=True) == ''

# ---------------------------------------------------------------------------
# to_iso8601_utc
# ---------------------------------------------------------------------------
# Converts any recognised date/time value to an ISO 8601 string.
# Returns None for None and for unrecognised types — never raises.

from iot_hub_shared.utils_kit.normalization import to_iso8601_utc

print("\n=== to_iso8601_utc ===\n")

# datetime with timezone → normalised to UTC ISO string
aware_dt = datetime.datetime(2024, 6, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
print(to_iso8601_utc(aware_dt))           # '2024-06-01T12:00:00+00:00'

# naive datetime → treated as UTC (no conversion, just attaches tzinfo)
naive_dt = datetime.datetime(2024, 6, 1, 12, 0, 0)
result = to_iso8601_utc(naive_dt)
print(result)                              # '2024-06-01T12:00:00+00:00'
assert '+00:00' in result

# date → ISO date string (no time component)
d = datetime.date(2024, 6, 1)
print(to_iso8601_utc(d))                  # '2024-06-01'

# time → ISO time string
t = datetime.time(14, 30, 0)
print(to_iso8601_utc(t))                  # '14:30:00'

# valid ISO string → round-trips through parse + format
print(to_iso8601_utc('2024-06-01T12:00:00Z'))   # '2024-06-01T12:00:00+00:00'

# None → None (safe no-op, useful when a field is optional)
print(to_iso8601_utc(None))               # None

# Unrecognised type → None (never raises — F-03 bug fix)
print(to_iso8601_utc('not-a-date'))       # None
print(to_iso8601_utc(42))                 # None

assert to_iso8601_utc(None) is None
assert to_iso8601_utc('garbage') is None
assert to_iso8601_utc(42) is None

# ---------------------------------------------------------------------------
# parse_iso8601_utc
# ---------------------------------------------------------------------------
# Parses an ISO 8601 string into a timezone-aware UTC datetime.
# Handles the 'Z' suffix, explicit offsets, and naive strings.
# Returns None for blank or unparseable input — never raises.

from iot_hub_shared.utils_kit.normalization import parse_iso8601_utc

print("\n=== parse_iso8601_utc ===\n")

# 'Z' suffix (common in JavaScript / REST APIs)
r1 = parse_iso8601_utc('2024-06-01T12:00:00Z')
print(f"'...Z'       → {r1}  tzinfo={r1.tzinfo}")
assert r1.tzinfo == datetime.timezone.utc

# Explicit UTC offset: +02:00 → converted to UTC (hour becomes 10)
r2 = parse_iso8601_utc('2024-06-01T14:00:00+02:00')
print(f"'+02:00'     → {r2}  hour={r2.hour} (converted to UTC)")
assert r2.hour == 12

# Naive string → assumed UTC, tzinfo attached
r3 = parse_iso8601_utc('2024-06-01T12:00:00')
print(f"naive        → {r3}  tzinfo={r3.tzinfo}")
assert r3.tzinfo == datetime.timezone.utc

# Microseconds are stripped for a clean timestamp
r4 = parse_iso8601_utc('2024-06-01T12:00:00.123456Z')
print(f"microseconds → {r4}  microsecond={r4.microsecond}")
assert r4.microsecond == 0

# Unparseable input → None (safe for untrusted API data)
print(f"'garbage'    → {parse_iso8601_utc('garbage')}")
print(f"''           → {parse_iso8601_utc('')}")
assert parse_iso8601_utc('garbage') is None
assert parse_iso8601_utc('') is None

# ---------------------------------------------------------------------------
# normalize_schema
# ---------------------------------------------------------------------------
# Extracts a known set of fields from a raw incoming dict, strips strings,
# drops optional None/blank values, and collects errors for missing fields.
# Useful as a lightweight, framework-agnostic alternative to a serializer
# when you only need field extraction without type validation.

from iot_hub_shared.utils_kit.dicts import normalize_schema

print("\n=== normalize_schema ===\n")

raw_payload = {
    'name': '  sensor-north  ',   # will be stripped
    'type': 'temperature',
    'description': '',            # blank optional → will be dropped
    'location': 'roof',
    'injected_extra': 'ignored',  # not in required or optional → dropped
}

normalized, errors = normalize_schema(
    raw_payload,
    required=['name', 'type'],
    optional=['description', 'location'],
)
print(f"normalized : {normalized}")
print(f"errors     : {errors}")
assert normalized['name'] == 'sensor-north'       # stripped
assert normalized['type'] == 'temperature'
assert 'description' not in normalized             # blank optional dropped
assert normalized['location'] == 'roof'
assert 'injected_extra' not in normalized          # unknown field dropped
assert errors == {}

# Missing required field → error entry, field absent from result
_, errors2 = normalize_schema({'name': 'sensor'}, required=['name', 'type'])
print(f"\nMissing 'type' errors : {errors2}")
assert 'type' in errors2

# drop_optional_none=False: keep None values in the output
normalized3, _ = normalize_schema(
    {'name': 'x', 'tag': None},
    required=['name'],
    optional=['tag'],
    drop_optional_none=False,
)
print(f"\ndrop_optional_none=False → tag={normalized3.get('tag')!r}")
assert normalized3['tag'] is None

# ---------------------------------------------------------------------------
# diff_dicts
# ---------------------------------------------------------------------------
# Compares two snapshots of the same object dict and returns:
#   changed — list of keys whose values differ
#   before  — dict of old values for changed keys
#   after   — dict of new values for changed keys
# Useful for audit log "before/after" entries.

from iot_hub_shared.utils_kit.dicts import diff_dicts

print("\n=== diff_dicts ===\n")

old_device = {'name': 'sensor-north', 'firmware': '1.0.0', 'active': True}
new_device = {'name': 'sensor-north', 'firmware': '2.1.0', 'active': True}

changed, before, after = diff_dicts(old_device, new_device)
print(f"changed : {changed}")
print(f"before  : {before}")
print(f"after   : {after}")
assert changed == ['firmware']
assert before['firmware'] == '1.0.0'
assert after['firmware'] == '2.1.0'

# No changes
changed2, before2, after2 = diff_dicts(old_device, old_device)
print(f"\nNo change → changed={changed2}, before={before2}, after={after2}")
assert changed2 == []
assert before2 == {}
assert after2 == {}

# Nested dict change is detected at the top-level key
old_cfg = {'settings': {'threshold': 80, 'unit': 'celsius'}}
new_cfg = {'settings': {'threshold': 90, 'unit': 'celsius'}}
changed3, before3, after3 = diff_dicts(old_cfg, new_cfg)
print(f"\nNested change → changed={changed3}")
assert 'settings' in changed3

print("\n\033[92mDemo completed successfully.\033[0m")
