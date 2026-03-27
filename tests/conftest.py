"""
Internal test suite configuration for iot-hub-shared.

pytest_configure sets up a minimal Django environment before test collection
begins. This is required by test_observability_kit.py, which imports
django.http and django.test at module level to test RequestLoggingMiddleware
and metrics_view.

No database, no INSTALLED_APPS — RequestFactory and HttpResponse work with
only SECRET_KEY configured.

test_kit fixtures (fake_kafka_producer, audit_record_factory,
reset_prometheus_registry) are registered automatically via the pytest11
entry point declared in pyproject.toml. No explicit pytest_plugins needed.
"""

import django
from django.conf import settings


def pytest_configure(config):
    if not settings.configured:
        settings.configure(
            SECRET_KEY='test-only-key',
            USE_TZ=True,
            INSTALLED_APPS=[],
        )
        django.setup()
