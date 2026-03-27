"""
Prometheus registry reset fixture.

Provides:
    reset_prometheus_registry — function-scoped fixture that unregisters any
                                Prometheus collectors created during a test,
                                preventing "Duplicated timeseries" errors when
                                the same metric is created across multiple tests.

Usage:
    def test_metrics_increment(reset_prometheus_registry):
        counter = Counter('my_counter', 'test counter', ['label'])
        counter.labels(label='x').inc()
        assert counter.labels(label='x')._value.get() == 1.0
        # counter is unregistered automatically after the test

Or autouse it for an entire test module:
    pytestmark = pytest.mark.usefixtures('reset_prometheus_registry')
"""

from __future__ import annotations

import pytest
from prometheus_client import REGISTRY


@pytest.fixture
def reset_prometheus_registry():
    """
    Snapshot the set of registered collectors before the test and unregister
    any that were added during the test after it completes.

    This is safe to combine with multiprocess mode: it only touches the default
    in-process REGISTRY, not files in PROMETHEUS_MULTIPROC_DIR.
    """
    collectors_before: frozenset = frozenset(REGISTRY._collectors)

    yield

    new_collectors = REGISTRY._collectors - collectors_before
    seen_ids: set[int] = set()
    for collector in list(new_collectors):
        if id(collector) in seen_ids:
            continue
        seen_ids.add(id(collector))
        try:
            REGISTRY.unregister(collector)
        except Exception:
            pass
