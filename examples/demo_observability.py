"""
examples/demo_observability.py
================================
Tutorial: Structured JSON logging and request context propagation.

This script shows how a downstream microservice configures its logging
pipeline using iot-hub-shared and then uses ContextVars to attach
request-scoped metadata (request_id, duration) to every log line
automatically — without passing those values through every function call.

No Django app or web server is required. The ContextVar mechanism is
pure Python stdlib (PEP 567) and works in any service: Django, FastAPI,
Celery workers, or standalone scripts.

Run:
    python examples/demo_observability.py
"""

import logging
import logging.config
import uuid

# ---------------------------------------------------------------------------
# Step 1 — Generate the logging configuration dict
# ---------------------------------------------------------------------------
# get_json_logging_config() returns a standard logging.config dictConfig-
# compatible dict. Wire it into your Django settings.py or call
# logging.config.dictConfig() directly at service startup.
#
# Flags:
#   include_django=True  — adds a 'django' logger entry (set False for FastAPI)
#   include_celery=True  — adds a 'celery' logger entry (set False if no Celery)

from iot_hub_shared.observability_kit.logging import get_json_logging_config

logging_config = get_json_logging_config(
    django_level='INFO',
    celery_level='WARNING',
    include_django=True,
    include_celery=True,
)

# Inspect the generated structure before applying it
print("Generated logging config keys:", list(logging_config.keys()))
print("Configured loggers          :", list(logging_config['loggers'].keys()))
print("Configured filters          :", list(logging_config['filters'].keys()))

# Apply the config — from this point on, all loggers use the JSON formatter
# and the RequestContextFilter / CeleryContextFilter are active.
logging.config.dictConfig(logging_config)

logger = logging.getLogger('myservice.devices')

# ---------------------------------------------------------------------------
# Step 2 — Understand ContextVars
# ---------------------------------------------------------------------------
# request_id and request_duration are module-level ContextVar instances.
# Any code that runs within the same Python context (the same request/task)
# can read them without explicit parameter threading.
#
# RequestLoggingMiddleware (Django) sets both automatically for every HTTP
# request. Here we set them manually to simulate what the middleware does.

from iot_hub_shared.observability_kit.context import request_duration, request_id

# Simulate "a new request came in"
rid = str(uuid.uuid4())
token_id = request_id.set(rid)
token_dur = request_duration.set(0.0)

print(f"\nSimulated request_id : {request_id.get()}")

# ---------------------------------------------------------------------------
# Step 3 — Log something mid-request
# ---------------------------------------------------------------------------
# RequestContextFilter is declared in the logging config and automatically
# attaches request_id and duration to every LogRecord before it is formatted.
# You do NOT need to pass them manually to logger.info().

logger.info(
    'Device lookup started',
    extra={
        'device_id': 'dev-42',
        'action': 'read',
    },
)

# ---------------------------------------------------------------------------
# Step 4 — Simulate request completion (duration is now known)
# ---------------------------------------------------------------------------

import time
time.sleep(0.01)   # pretend some work happened
elapsed = 0.012    # in a real middleware this comes from time.monotonic()

request_duration.set(elapsed)

logger.info(
    'Device lookup completed',
    extra={
        'device_id': 'dev-42',
        'action': 'read',
        'result': 'found',
    },
)

print(f"request_duration after response : {request_duration.get():.3f}s")

# ---------------------------------------------------------------------------
# Step 5 — Reset ContextVars (middleware does this automatically)
# ---------------------------------------------------------------------------
# In a real Django service, RequestLoggingMiddleware resets these after
# the response is sent so they do not bleed into the next request.
# In a Celery task, you would reset at task teardown.

request_id.reset(token_id)
request_duration.reset(token_dur)

# ---------------------------------------------------------------------------
# Step 6 — CeleryContextFilter no-op outside a task
# ---------------------------------------------------------------------------
# CeleryContextFilter safely sets task_id / task_name to None when there is
# no active Celery task. It never raises even if Celery is not installed.

from iot_hub_shared.observability_kit.filters import CeleryContextFilter

record = logging.LogRecord('test', logging.INFO, '', 0, 'msg', (), None)
CeleryContextFilter().filter(record)
print(f"\nOutside Celery task — task_id={record.task_id!r}, task_name={record.task_name!r}")

# ---------------------------------------------------------------------------
# Step 7 — Django-free services: disable framework loggers
# ---------------------------------------------------------------------------
# For a FastAPI or plain asyncio service, pass include_django=False so
# no 'django' logger entry is generated (avoids a spurious warning if
# Django is not installed).

fastapi_config = get_json_logging_config(
    include_django=False,
    include_celery=False,
)
print(f"\nFastAPI config loggers: {list(fastapi_config['loggers'].keys())}")
assert 'django' not in fastapi_config['loggers']
assert 'celery' not in fastapi_config['loggers']

print("\n\033[92mDemo completed successfully.\033[0m")
