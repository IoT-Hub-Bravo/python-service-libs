"""
examples/test_demo_fixtures.py
================================
Tutorial: Using test_kit fixtures in a downstream service test suite.

IMPORTANT: This file must be executed with pytest, not with Python directly.

    pytest -v examples/test_demo_fixtures.py

How the fixtures get here — the pytest11 entry point
------------------------------------------------------
When `iot-hub-shared` is installed (pip install ...), it registers a pytest
plugin via the `pytest11` entry point declared in its pyproject.toml:

    [project.entry-points."pytest11"]
    iot_hub_shared = "iot_hub_shared.test_kit.conftest"

pytest discovers this entry point automatically at startup, which makes the
following fixtures available in every test file of the consuming project
WITHOUT any import statement or conftest.py declaration:

    fake_kafka_producer       — fresh FakeKafkaProducer for each test
    audit_record_factory      — factory for AuditRecord instances
    reset_prometheus_registry — cleans up Prometheus collectors after the test

Notice: none of these fixtures are imported anywhere in this file.
pytest injects them purely by name matching.
"""

from iot_hub_shared.audit_kit.publisher import publish_audit_event
from iot_hub_shared.kafka_kit.producer import ProduceResult


# ---------------------------------------------------------------------------
# fake_kafka_producer
# ---------------------------------------------------------------------------
# FakeKafkaProducer has the same public interface as the real KafkaProducer
# (produce, flush, topic) but stores messages in memory. Use it wherever
# your code accepts a producer so you can assert on what was sent.

def test_fake_kafka_producer_starts_empty(fake_kafka_producer):
    # Each test gets a fresh producer — no bleed-over from other tests
    assert fake_kafka_producer.messages == []
    assert fake_kafka_producer.topic == 'fake-topic'


def test_fake_kafka_producer_captures_message(fake_kafka_producer):
    result = fake_kafka_producer.produce({'event': 'device.CREATED'}, key='device')

    assert result == ProduceResult.ENQUEUED
    assert len(fake_kafka_producer.messages) == 1
    assert fake_kafka_producer.messages[0]['key'] == 'device'
    assert fake_kafka_producer.messages[0]['payload'] == {'event': 'device.CREATED'}


def test_fake_kafka_producer_rejects_unserializable_payload(fake_kafka_producer):
    # Sets cannot be JSON-serialised — producer returns SERIALIZATION_FAILED
    result = fake_kafka_producer.produce({1, 2, 3})
    assert result == ProduceResult.SERIALIZATION_FAILED
    assert fake_kafka_producer.messages == []


def test_fake_kafka_producer_force_result_simulates_broker_errors(fake_kafka_producer):
    # Use force_result() to test how your service handles infrastructure failures
    # without needing a real broker to be unavailable.
    fake_kafka_producer.force_result(ProduceResult.BUFFER_FULL)
    result = fake_kafka_producer.produce({'event': 'rule.TRIGGERED'})

    assert result == ProduceResult.BUFFER_FULL
    assert fake_kafka_producer.messages == []   # nothing enqueued on failure


def test_fake_kafka_producer_reset_clears_state(fake_kafka_producer):
    fake_kafka_producer.produce({'x': 1})
    fake_kafka_producer.force_result(ProduceResult.PRODUCER_ERROR)

    fake_kafka_producer.reset()

    assert fake_kafka_producer.messages == []
    assert fake_kafka_producer.produce({'x': 1}) == ProduceResult.ENQUEUED


# ---------------------------------------------------------------------------
# audit_record_factory
# ---------------------------------------------------------------------------
# Returns a callable factory that builds AuditRecord instances with sensible
# defaults. Override any field via keyword argument.

def test_audit_record_factory_default_fields(audit_record_factory):
    record = audit_record_factory()

    assert record.event_type == 'test.EVENT_CREATED'
    assert record.actor is not None
    assert record.entity is not None
    assert record.details == {}


def test_audit_record_factory_accepts_overrides(audit_record_factory):
    record = audit_record_factory(
        event_type='device.DELETED',
        details={'device_id': 99, 'reason': 'decommissioned'},
    )

    assert record.event_type == 'device.DELETED'
    assert record.details['reason'] == 'decommissioned'


# ---------------------------------------------------------------------------
# fake_kafka_producer + audit_record_factory together
# ---------------------------------------------------------------------------
# This is the core integration pattern: build a record with the factory,
# publish it with your service code, and assert on the captured message.
# No real Kafka broker, no Django app, no database.

def test_publish_audit_event_end_to_end(fake_kafka_producer, audit_record_factory):
    record = audit_record_factory(
        event_type='rule.TRIGGERED',
        details={'rule_id': 7, 'threshold_exceeded': True},
    )

    result = publish_audit_event(event=record, producer=fake_kafka_producer)

    assert result == ProduceResult.ENQUEUED
    assert len(fake_kafka_producer.messages) == 1

    msg = fake_kafka_producer.messages[0]
    # The Kafka message key is set to event_type by publish_audit_event
    assert msg['key'] == 'rule.TRIGGERED'
    assert msg['payload']['event_type'] == 'rule.TRIGGERED'
    assert msg['payload']['details'] == {'rule_id': 7, 'threshold_exceeded': True}
    assert msg['payload']['actor_type'] == 'system'   # factory default
    assert isinstance(msg['payload']['audit_event_id'], str)


# ---------------------------------------------------------------------------
# reset_prometheus_registry
# ---------------------------------------------------------------------------
# Unregisters any Prometheus collectors created during the test after it
# completes. Without this, creating the same Counter name in two tests
# raises a DuplicateTimeseries error.

def test_prometheus_counter_can_be_created(reset_prometheus_registry):
    from prometheus_client import Counter

    c = Counter('demo_requests_total', 'Demo counter', ['status'])
    c.labels(status='ok').inc()
    assert c.labels(status='ok')._value.get() == 1.0
    # reset_prometheus_registry unregisters 'demo_requests_total' after this test


def test_prometheus_same_name_can_be_reused(reset_prometheus_registry):
    # Registering the same metric name in a second test would raise
    # DuplicateTimeseries if reset_prometheus_registry had not cleaned up.
    from prometheus_client import Counter

    c = Counter('demo_requests_total', 'Demo counter', ['status'])
    c.labels(status='error').inc()
    c.labels(status='error').inc()
    assert c.labels(status='error')._value.get() == 2.0
