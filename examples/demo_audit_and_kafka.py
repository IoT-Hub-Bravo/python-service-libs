"""
examples/demo_audit_and_kafka.py
=================================
Tutorial: Creating and publishing an AuditRecord via Kafka.

This script shows the complete audit publishing workflow that a downstream
microservice (e.g. a device management API) would follow when something
noteworthy happens — like a device being created or a rule being triggered.

We use FakeKafkaProducer instead of a real broker so the script runs
anywhere without infrastructure. In production code, replace it with a
real KafkaProducer pointing at your broker.

Run:
    python examples/demo_audit_and_kafka.py
"""

# ---------------------------------------------------------------------------
# Step 1 — Build the "who did this?" actor
# ---------------------------------------------------------------------------
# AuditActor describes the agent that caused the event.
# Use .user() for an authenticated end-user, .system() for a background
# service/worker, and .external() for a third-party integration.

from iot_hub_shared.audit_kit import AuditActor, AuditEntity, AuditRecord, AuditSeverity
from iot_hub_shared.audit_kit.publisher import publish_audit_event
from iot_hub_shared.kafka_kit.producer import ProduceResult
from iot_hub_shared.test_kit.kafka import FakeKafkaProducer

actor = AuditActor.user(user_id=42)
print(f"Actor  : type={actor.type.value!r}, id={actor.id!r}")

# ---------------------------------------------------------------------------
# Step 2 — Build the "what was affected?" entity
# ---------------------------------------------------------------------------
# AuditEntity is the domain object the event is about.
# `type` is a free-form string — use a consistent naming convention across
# your services (e.g. 'Device', 'Rule', 'Action').

entity = AuditEntity(type='Device', id='dev-99')
print(f"Entity : type={entity.type!r}, id={entity.id!r}")

# ---------------------------------------------------------------------------
# Step 3 — Build the AuditRecord (the full event)
# ---------------------------------------------------------------------------
# AuditRecord is a frozen dataclass — it is immutable once created.
# occurred_at and audit_event_id are auto-populated with sensible defaults
# (UTC now and a new UUID respectively), so you rarely need to set them.

record = AuditRecord(
    actor=actor,
    entity=entity,
    event_type='device.CREATED',
    severity=AuditSeverity.INFO,
    details={
        'name': 'sensor-north',
        'firmware': '2.1.0',
    },
)
print(f"\nAuditRecord")
print(f"  event_type  : {record.event_type}")
print(f"  severity    : {record.severity.value}")
print(f"  occurred_at : {record.occurred_at.isoformat()}")
print(f"  event_id    : {record.audit_event_id}")

# ---------------------------------------------------------------------------
# Step 4 — Serialise the record to a plain dict for the wire
# ---------------------------------------------------------------------------
# to_record() converts the dataclass to a JSON-serialisable dict.
# This is what actually goes onto the Kafka topic.

payload = record.to_record()
print(f"\nto_record() output:")
for k, v in payload.items():
    print(f"  {k:<18} : {v!r}")

# ---------------------------------------------------------------------------
# Step 5 — Publish to Kafka (via FakeKafkaProducer for this demo)
# ---------------------------------------------------------------------------
# In production you would create a real producer:
#
#   from iot_hub_shared.kafka_kit.producer import KafkaProducer
#   from iot_hub_shared.kafka_kit.config import ProducerConfig
#   producer = KafkaProducer(config=ProducerConfig(), topic='audit.records')
#
# FakeKafkaProducer has the same interface but stores messages in memory.

producer = FakeKafkaProducer(topic='audit.records')
result = publish_audit_event(event=record, producer=producer)

print(f"\nPublish result : {result.name}")  # ENQUEUED

# ---------------------------------------------------------------------------
# Step 6 — Inspect what was sent (FakeKafkaProducer specific)
# ---------------------------------------------------------------------------
# In tests you assert against producer.messages.
# In production you would configure delivery callbacks on the real producer.

assert result == ProduceResult.ENQUEUED
assert len(producer.messages) == 1

captured = producer.messages[0]
print(f"\nCaptured message on topic {captured['topic']!r}:")
print(f"  key     : {captured['key']!r}")
print(f"  payload : {captured['payload']}")

# ---------------------------------------------------------------------------
# Step 7 — Simulate infrastructure failure (FakeKafkaProducer specific)
# ---------------------------------------------------------------------------
# Use force_result() in tests to verify your service handles broker errors
# gracefully without needing a real broker to go down.

producer.force_result(ProduceResult.BUFFER_FULL)
error_result = publish_audit_event(event=record, producer=producer)
print(f"\nSimulated BUFFER_FULL result : {error_result.name}")
assert error_result == ProduceResult.BUFFER_FULL
assert len(producer.messages) == 1  # no new message was enqueued

print("\n\033[92mDemo completed successfully.\033[0m")
